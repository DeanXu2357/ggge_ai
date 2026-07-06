"""Expectiminimax solver skeleton over the battle simulator.

Anytime iterative deepening (depth unit = one phase) with a time budget, a
transposition table keyed on SimState.key(), and Star1 pruning at chance
nodes (Star2 is left as a TODO). Node type follows *who decides now*
(docs/agent-architecture.md), not the phase:

  - our unit acting in the ally phase -> max node;
  - an enemy unit in the enemy phase -> policy expectation or min, per the
    injected EnemyModel's mode;
  - the hit/miss of an attack -> chance node weighted by the hit probability
    (from formulas.py); and
  - the defender's reaction to an incoming enemy attack -> a nested max over
    {no defence, dodge, defend, shield, counter}, because that reaction is
    our decision even though it happens in the enemy phase.

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
from .enemy_model import MODE_MIN, EnemyModel
from .sim import (
    DEFAULT_PARAMS,
    Decision,
    DefenseKind,
    DefenseResponse,
    MoveValidator,
    Phase,
    SimParams,
    SimState,
    SimUnit,
    legal_attacks,
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


class _Timeout(Exception):
    pass


DEFENSE_RESPONSES: tuple[DefenseResponse, ...] = (
    DefenseResponse(DefenseKind.NONE),
    DefenseResponse(DefenseKind.DODGE),
    DefenseResponse(DefenseKind.DEFEND),
    DefenseResponse(DefenseKind.SHIELD),
    DefenseResponse(DefenseKind.COUNTER),
)


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
    decisions = legal_attacks(state, unit, move_validator=ctx.config.move_validator)
    decisions.append(standby(unit.unit_id))
    return decisions


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
    cached = ctx.tt.get(key)
    if cached is not None:
        return cached

    actor = _next_actor(state)
    if actor is None:
        return ctx.evaluator(state, ctx), []

    if actor.faction is Faction.ALLY:
        result = _max_node(state, actor, depth, alpha, beta, ctx)
    elif actor.faction is Faction.ENEMY:
        result = _enemy_node(state, actor, depth, alpha, beta, ctx)
    else:
        result = ctx.evaluator(state, ctx), []

    ctx.tt[key] = result
    return result


def _max_node(
    state: SimState, actor: SimUnit, depth: int, alpha: float, beta: float, ctx: SearchContext
) -> tuple[float, list[Decision]]:
    best = -_INF
    best_pv: list[Decision] = []
    for decision in _ally_decisions(state, actor, ctx):
        value, pv = _decision_value(state, decision, depth, alpha, beta, ctx)
        if value > best:
            best, best_pv = value, [decision, *pv]
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
                best, best_pv = value, [decision, *pv]
            beta = min(beta, best)
            if alpha >= beta:
                break
        return best, best_pv

    total = 0.0
    norm = 0.0
    best_prob = -1.0
    best_pv = []
    for decision, prob in candidates:
        value, pv = _decision_value(state, decision, depth, alpha, beta, ctx)
        total += prob * value
        norm += prob
        if prob > best_prob:
            best_prob, best_pv = prob, [decision, *pv]
    return (total / norm if norm else ctx.evaluator(state, ctx)), best_pv


def _decision_value(
    state: SimState, decision: Decision, depth: int, alpha: float, beta: float, ctx: SearchContext
) -> tuple[float, list[Decision]]:
    """Route a decision through the defender-reaction max and the chance node."""
    actor = state.unit(decision.unit_id)
    target = state.unit(decision.target_id)
    if (
        decision.kind == ActionKind.ATTACK
        and actor is not None
        and actor.faction is Faction.ENEMY
        and target is not None
        and target.faction is Faction.ALLY
        and decision.defense is None
    ):
        best = -_INF
        best_pv: list[Decision] = []
        for response in DEFENSE_RESPONSES:
            responded = replace(decision, defense=response)
            value, pv = _chance_value(state, responded, depth, alpha, beta, ctx)
            if value > best:
                best, best_pv = value, pv
        return best, best_pv
    return _chance_value(state, decision, depth, alpha, beta, ctx)


def _chance_value(
    state: SimState, decision: Decision, depth: int, alpha: float, beta: float, ctx: SearchContext
) -> tuple[float, list[Decision]]:
    if decision.kind != ActionKind.ATTACK:
        nxt = _step(state, decision, ctx)
        value, pv = _search(nxt, _depth_after(state, nxt, depth), alpha, beta, ctx)
        return value, [decision, *pv]

    prob = _hit_probability(state, decision, ctx)
    if prob >= 1.0:
        nxt = _step(state, replace(decision, hit=True), ctx)
        value, pv = _search(nxt, _depth_after(state, nxt, depth), alpha, beta, ctx)
        return value, [decision, *pv]
    if prob <= 0.0:
        nxt = _step(state, replace(decision, hit=False), ctx)
        value, pv = _search(nxt, _depth_after(state, nxt, depth), alpha, beta, ctx)
        return value, [decision, *pv]

    vmin, vmax = ctx.vmin, ctx.vmax
    ax = max(vmin, (alpha - (1.0 - prob) * vmax) / prob)
    bx = min(vmax, (beta - (1.0 - prob) * vmin) / prob)
    hit_state = _step(state, replace(decision, hit=True), ctx)
    v_hit, pv_hit = _search(hit_state, _depth_after(state, hit_state, depth), ax, bx, ctx)
    if v_hit >= bx:
        return prob * v_hit + (1.0 - prob) * vmax, [decision, *pv_hit]
    if v_hit <= ax:
        return prob * v_hit + (1.0 - prob) * vmin, [decision, *pv_hit]

    ay = max(vmin, (alpha - prob * v_hit) / (1.0 - prob))
    by = min(vmax, (beta - prob * v_hit) / (1.0 - prob))
    miss_state = _step(state, replace(decision, hit=False), ctx)
    v_miss, _ = _search(miss_state, _depth_after(state, miss_state, depth), ay, by, ctx)
    return prob * v_hit + (1.0 - prob) * v_miss, [decision, *pv_hit]


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
