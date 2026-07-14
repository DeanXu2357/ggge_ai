"""Expectiminimax solver over the battle simulator.

Anytime iterative deepening (depth unit = one phase) with a time budget, a
transposition table keyed on SimState.key() carrying exact/lower/upper bound
flags, and Star1 pruning generalised to every expectation node -- both the
hit/miss chance node and the enemy policy node get interval-narrowed child
windows, and a cutoff propagates the guaranteed bound (fail-soft). Star2
probing is still a TODO. Node type follows *who decides now*
(docs/agent-architecture.md), not the phase:

  - our unit acting in the ally phase -> max node;
  - an enemy unit in the enemy phase -> policy expectation or min, per the
    injected EnemyModel's mode;
  - the hit/miss of an attack -> chance node weighted by the hit probability
    (from formulas.py);
  - the defender's reaction to an incoming enemy attack -> a nested max over
    every stance, doubled with support interception when an eligible
    supporter stands by, because that reaction is our decision even though
    it happens in the enemy phase; and
  - the enemy defender's reaction to our attack -> the enemy model's
    reactions(), resolved as an expectation (policy) or a min (worst case),
    so the tree prices counters and support fire against our own strikes.

The leaf evaluator is injectable; the default is a weighted sum of our
remaining HP ratio minus the enemy's, plus a kill/loss count term. It returns
the best first decision, the principal variation, and node/depth stats. Third
-party units are inert in v0: their phase auto-completes.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from . import formulas
from .actions import ActionKind
from .enemy_model import MODE_MIN, EnemyModel, ReachProvider
from .sim import (
    DEFAULT_PARAMS,
    DEFENSE_STANCES,
    Decision,
    DefenseKind,
    DefenseResponse,
    MoveValidator,
    Phase,
    SimParams,
    SimState,
    SimUnit,
    find_support_defender,
    legal_attacks,
    legal_map_attacks,
    legal_skills,
    reposition_moves,
    standby,
    step,
)
from .state import Faction

Evaluator = Callable[[SimState, "SearchContext"], float]

_INF = float("inf")


@dataclass(frozen=True)
class EvalWeights:
    ally_hp: float = 1.0
    enemy_hp: float = 1.0
    kill: float = 5.0
    loss: float = 5.0


@dataclass
class SearchStats:
    nodes: int = 0
    depth: int = 0


@dataclass
class SolverResult:
    decision: Decision | None
    pv: list[Decision]
    value: float
    stats: SearchStats


@dataclass
class SolverConfig:
    time_budget_s: float = 2.0
    max_depth: int = 16
    weights: EvalWeights = field(default_factory=EvalWeights)
    params: SimParams = DEFAULT_PARAMS
    move_validator: MoveValidator | None = None
    reach_provider: ReachProvider | None = None
    use_tt: bool = True
    use_star1: bool = True


_FLAG_EXACT = 0
_FLAG_LOWER = 1
_FLAG_UPPER = 2


class _Timeout(Exception):
    pass


def _defense_candidates(state: SimState, target: SimUnit) -> list[DefenseResponse]:
    out = [DefenseResponse(kind=k) for k in DEFENSE_STANCES]
    if find_support_defender(state, target) is not None:
        out.extend(DefenseResponse(kind=k, support_defend=True) for k in DEFENSE_STANCES)
    return out


@dataclass
class SearchContext:
    enemy_model: EnemyModel
    config: SolverConfig
    evaluator: Evaluator
    deadline: float
    stats: SearchStats
    base_allies: int
    base_enemies: int
    vmin: float
    vmax: float
    tt: dict = field(default_factory=dict)


def default_evaluator(state: SimState, ctx: SearchContext) -> float:
    w = ctx.config.weights
    allies = state.allies()
    enemies = state.enemies()
    ally_hp = sum(u.hp / u.max_hp for u in allies)
    enemy_hp = sum(u.hp / u.max_hp for u in enemies)
    kills = ctx.base_enemies - len(enemies)
    losses = ctx.base_allies - len(allies)
    return w.ally_hp * ally_hp - w.enemy_hp * enemy_hp + w.kill * kills - w.loss * losses


def _eval_bounds(base_allies: int, base_enemies: int, w: EvalWeights) -> tuple[float, float]:
    vmax = w.ally_hp * base_allies + w.kill * base_enemies
    vmin = -(w.enemy_hp * base_enemies + w.loss * base_allies)
    return vmin, vmax


def _terminal(state: SimState) -> bool:
    return not state.allies() or not state.enemies()


def _next_actor(state: SimState) -> SimUnit | None:
    fac = _current_faction(state)
    for u in state.units:
        if u.faction is fac and u.alive and not u.acted:
            return u
    return None


def _current_faction(state: SimState) -> Faction:
    return {Phase.ALLY: Faction.ALLY, Phase.THIRD_PARTY: Faction.THIRD_PARTY, Phase.ENEMY: Faction.ENEMY}[
        state.phase
    ]


def _ally_decisions(state: SimState, unit: SimUnit, ctx: SearchContext) -> list[Decision]:
    """Attacks first (best alpha-raisers), then skills, positioning, standby.

    When a teammate holds an unused support-attack charge, every attack is
    doubled with a support=False variant: keeping the volley home matters
    (an interceptor swallows it as overkill, and a spent charge is one a
    re-activated follow-up or the defensive phase no longer has).
    """
    provider = ctx.config.reach_provider
    decisions = legal_attacks(
        state,
        unit,
        move_validator=ctx.config.move_validator,
        reach=provider(state, unit) if provider else None,
    )
    if _teammate_has_support_charge(state, unit):
        decisions.extend(replace(d, support=False) for d in list(decisions))
    decisions.extend(legal_map_attacks(state, unit))
    decisions.extend(legal_skills(unit))
    decisions.extend(
        reposition_moves(state, unit, move_validator=ctx.config.move_validator)
    )
    decisions.append(standby(unit.unit_id))
    return decisions


def _teammate_has_support_charge(state: SimState, unit: SimUnit) -> bool:
    return any(
        u is not unit
        and u.alive
        and u.faction is unit.faction
        and u.support_attack_charges > 0
        for u in state.units
    )


def _hit_probability(state: SimState, decision: Decision, ctx: SearchContext) -> float:
    actor = state.unit(decision.unit_id)
    target = state.unit(decision.target_id)
    if actor is None or target is None:
        return 1.0
    weapon = actor.weapon(decision.weapon)
    ability = weapon.accuracy if weapon is not None else 0.0
    if decision.defense is not None and decision.defense.kind == DefenseKind.DODGE:
        ability -= ctx.config.params.dodge_hit_penalty
    return formulas.hit_probability(
        actor.mobility,
        target.mobility,
        actor.pilot_attack,
        target.reaction,
        ability_correction=ability,
    )


def _depth_after(before: SimState, after: SimState, depth: int) -> int:
    return depth - (after.phase_index() - before.phase_index())


def _step(state: SimState, decision: Decision, ctx: SearchContext) -> SimState:
    return step(
        state,
        decision,
        move_validator=ctx.config.move_validator,
        params=ctx.config.params,
    )


def _search(
    state: SimState, depth: int, alpha: float, beta: float, ctx: SearchContext
) -> tuple[float, list[Decision]]:
    ctx.stats.nodes += 1
    if time.monotonic() > ctx.deadline:
        raise _Timeout
    if _terminal(state) or depth <= 0:
        return ctx.evaluator(state, ctx), []

    key = (state.key(), depth)
    if ctx.config.use_tt:
        cached = ctx.tt.get(key)
        if cached is not None:
            flag, value, pv = cached
            if flag == _FLAG_EXACT:
                return value, pv
            if flag == _FLAG_LOWER:
                if value >= beta:
                    return value, pv
                alpha = max(alpha, value)
            else:
                if value <= alpha:
                    return value, pv
                beta = min(beta, value)

    actor = _next_actor(state)
    if actor is None:
        return ctx.evaluator(state, ctx), []

    if actor.faction is Faction.ALLY:
        value, pv = _max_node(state, actor, depth, alpha, beta, ctx)
    elif actor.faction is Faction.ENEMY:
        value, pv = _enemy_node(state, actor, depth, alpha, beta, ctx)
    else:
        value, pv = ctx.evaluator(state, ctx), []

    if ctx.config.use_tt:
        if value <= alpha:
            flag = _FLAG_UPPER
        elif value >= beta:
            flag = _FLAG_LOWER
        else:
            flag = _FLAG_EXACT
        ctx.tt[key] = (flag, value, pv)
    return value, pv


def _max_node(
    state: SimState, actor: SimUnit, depth: int, alpha: float, beta: float, ctx: SearchContext
) -> tuple[float, list[Decision]]:
    best = -_INF
    best_pv: list[Decision] = []
    for decision in _ally_decisions(state, actor, ctx):
        value, pv = _decision_value(state, decision, depth, alpha, beta, ctx)
        if value > best:
            best, best_pv = value, pv
        alpha = max(alpha, best)
        if alpha >= beta:
            break
    return best, best_pv


def _enemy_node(
    state: SimState, actor: SimUnit, depth: int, alpha: float, beta: float, ctx: SearchContext
) -> tuple[float, list[Decision]]:
    candidates = ctx.enemy_model.decisions(state, actor)
    if ctx.enemy_model.mode == MODE_MIN:
        best = _INF
        best_pv: list[Decision] = []
        for decision, _prob in candidates:
            value, pv = _decision_value(state, decision, depth, alpha, beta, ctx)
            if value < best:
                best, best_pv = value, pv
            beta = min(beta, best)
            if alpha >= beta:
                break
        return best, best_pv

    if not candidates:
        return ctx.evaluator(state, ctx), []

    def make_resolver(decision: Decision):
        def resolve(ax: float, bx: float) -> tuple[float, list[Decision]]:
            return _decision_value(state, decision, depth, ax, bx, ctx)

        return resolve

    branches = [(prob, make_resolver(decision)) for decision, prob in candidates]
    return _expectation(branches, alpha, beta, ctx)


def _expectation(
    branches: list[tuple[float, Callable[[float, float], tuple[float, list[Decision]]]]],
    alpha: float,
    beta: float,
    ctx: SearchContext,
) -> tuple[float, list[Decision]]:
    """Exact probability-weighted expectation with Star1 child windows.

    Each branch resolver is called with its own (ax, bx) window derived from
    the exact mass accumulated so far and the [vmin, vmax] envelope of the
    remaining mass. A child value at or beyond its window proves the node
    fails the parent window, so the guaranteed bound is returned fail-soft:
    the remaining mass is priced at vmin on a fail-high and vmax on a
    fail-low. With use_star1 off, children get the full window and the sum
    is exact. The pv reported is the highest-probability branch's.
    """
    total = sum(prob for prob, _ in branches)
    if total <= 0.0:
        raise ValueError("expectation node needs positive probability mass")
    vmin, vmax = ctx.vmin, ctx.vmax
    acc = 0.0
    rest = total
    best_prob = -1.0
    best_pv: list[Decision] = []
    for prob, resolve in branches:
        rest -= prob
        if prob <= 0.0:
            continue
        if ctx.config.use_star1:
            ax = (alpha * total - acc - rest * vmax) / prob
            bx = (beta * total - acc - rest * vmin) / prob
        else:
            ax, bx = -_INF, _INF
        value, pv = resolve(ax, bx)
        if prob > best_prob:
            best_prob, best_pv = prob, pv
        if ctx.config.use_star1:
            if value >= bx:
                return (acc + prob * value + rest * vmin) / total, best_pv
            if value <= ax:
                return (acc + prob * value + rest * vmax) / total, best_pv
        acc += prob * value
    return acc / total, best_pv


def _decision_value(
    state: SimState, decision: Decision, depth: int, alpha: float, beta: float, ctx: SearchContext
) -> tuple[float, list[Decision]]:
    """Route a decision through the defender-reaction node and the chance node.

    This is the single place that prefixes the decision onto the pv, so the
    line records the defence response actually chosen.
    """
    actor = state.unit(decision.unit_id)
    target = state.unit(decision.target_id)
    if (
        decision.kind == ActionKind.ATTACK
        and actor is not None
        and target is not None
        and decision.defense is None
    ):
        if actor.faction is Faction.ENEMY and target.faction is Faction.ALLY:
            return _our_defense_node(state, decision, target, depth, alpha, beta, ctx)
        if actor.faction is Faction.ALLY and target.faction is Faction.ENEMY:
            return _enemy_reaction_node(state, decision, depth, alpha, beta, ctx)
    value, pv = _chance_value(state, decision, depth, alpha, beta, ctx)
    return value, [decision, *pv]


def _our_defense_node(
    state: SimState,
    decision: Decision,
    target: SimUnit,
    depth: int,
    alpha: float,
    beta: float,
    ctx: SearchContext,
) -> tuple[float, list[Decision]]:
    best = -_INF
    best_pv: list[Decision] = []
    for response in _defense_candidates(state, target):
        responded = replace(decision, defense=response)
        value, pv = _chance_value(state, responded, depth, alpha, beta, ctx)
        if value > best:
            best, best_pv = value, [responded, *pv]
        alpha = max(alpha, best)
        if alpha >= beta:
            break
    return best, best_pv


def _enemy_reaction_node(
    state: SimState,
    decision: Decision,
    depth: int,
    alpha: float,
    beta: float,
    ctx: SearchContext,
) -> tuple[float, list[Decision]]:
    candidates = ctx.enemy_model.reactions(state, decision)
    if not candidates:
        value, pv = _chance_value(state, decision, depth, alpha, beta, ctx)
        return value, [decision, *pv]
    if ctx.enemy_model.mode == MODE_MIN:
        best = _INF
        best_pv: list[Decision] = []
        for response, _prob in candidates:
            responded = replace(decision, defense=response)
            value, pv = _chance_value(state, responded, depth, alpha, beta, ctx)
            if value < best:
                best, best_pv = value, [responded, *pv]
            beta = min(beta, best)
            if alpha >= beta:
                break
        return best, best_pv

    def make_resolver(responded: Decision):
        def resolve(ax: float, bx: float) -> tuple[float, list[Decision]]:
            value, pv = _chance_value(state, responded, depth, ax, bx, ctx)
            return value, [responded, *pv]

        return resolve

    branches = [
        (prob, make_resolver(replace(decision, defense=response)))
        for response, prob in candidates
    ]
    return _expectation(branches, alpha, beta, ctx)


def _chance_value(
    state: SimState, decision: Decision, depth: int, alpha: float, beta: float, ctx: SearchContext
) -> tuple[float, list[Decision]]:
    if decision.kind != ActionKind.ATTACK:
        nxt = _step(state, decision, ctx)
        return _search(nxt, _depth_after(state, nxt, depth), alpha, beta, ctx)

    prob = _hit_probability(state, decision, ctx)
    if prob >= 1.0:
        nxt = _step(state, replace(decision, hit=True), ctx)
        return _search(nxt, _depth_after(state, nxt, depth), alpha, beta, ctx)
    if prob <= 0.0:
        nxt = _step(state, replace(decision, hit=False), ctx)
        return _search(nxt, _depth_after(state, nxt, depth), alpha, beta, ctx)

    def make_resolver(hit: bool):
        def resolve(ax: float, bx: float) -> tuple[float, list[Decision]]:
            nxt = _step(state, replace(decision, hit=hit), ctx)
            return _search(nxt, _depth_after(state, nxt, depth), ax, bx, ctx)

        return resolve

    branches = [(prob, make_resolver(True)), (1.0 - prob, make_resolver(False))]
    return _expectation(branches, alpha, beta, ctx)


def solve(
    state: SimState,
    enemy_model: EnemyModel,
    config: SolverConfig | None = None,
    *,
    evaluator: Evaluator | None = None,
) -> SolverResult:
    """Iterative deepening expectiminimax; returns the best first decision."""
    config = config or SolverConfig()
    evaluator = evaluator or default_evaluator
    base_allies = len(state.allies())
    base_enemies = len(state.enemies())
    vmin, vmax = _eval_bounds(base_allies, base_enemies, config.weights)
    stats = SearchStats()

    best = SolverResult(decision=None, pv=[], value=0.0, stats=stats)
    deadline = time.monotonic() + config.time_budget_s

    for depth in range(1, config.max_depth + 1):
        ctx = SearchContext(
            enemy_model=enemy_model,
            config=config,
            evaluator=evaluator,
            deadline=deadline,
            stats=stats,
            base_allies=base_allies,
            base_enemies=base_enemies,
            vmin=vmin,
            vmax=vmax,
        )
        try:
            value, pv = _search(state, depth, -_INF, _INF, ctx)
        except _Timeout:
            break
        stats.depth = depth
        best = SolverResult(
            decision=pv[0] if pv else None,
            pv=pv,
            value=value,
            stats=stats,
        )
        if _terminal(state):
            break
    return best


def solve_reaction(
    state: SimState,
    attack: Decision,
    enemy_model: EnemyModel,
    config: SolverConfig | None = None,
    *,
    evaluator: Evaluator | None = None,
) -> SolverResult:
    """Iterative-deepening max over OUR defense responses to `attack` --
    the enemy decision the reaction popup has already shown on screen.
    The root is the same _our_defense_node the in-tree search uses; the
    returned decision is the attack with the chosen defense attached."""
    config = config or SolverConfig()
    evaluator = evaluator or default_evaluator
    stats = SearchStats()
    best = SolverResult(decision=None, pv=[], value=0.0, stats=stats)
    target = state.unit(attack.target_id)
    if target is None:
        return best
    base_allies = len(state.allies())
    base_enemies = len(state.enemies())
    vmin, vmax = _eval_bounds(base_allies, base_enemies, config.weights)
    deadline = time.monotonic() + config.time_budget_s

    for depth in range(1, config.max_depth + 1):
        ctx = SearchContext(
            enemy_model=enemy_model,
            config=config,
            evaluator=evaluator,
            deadline=deadline,
            stats=stats,
            base_allies=base_allies,
            base_enemies=base_enemies,
            vmin=vmin,
            vmax=vmax,
        )
        try:
            value, pv = _our_defense_node(state, attack, target, depth, -_INF, _INF, ctx)
        except _Timeout:
            break
        stats.depth = depth
        best = SolverResult(
            decision=pv[0] if pv else None,
            pv=pv,
            value=value,
            stats=stats,
        )
    return best
