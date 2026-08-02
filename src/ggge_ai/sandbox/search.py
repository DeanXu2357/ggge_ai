"""沙盤之上的 expectiminimax：anytime 迭代加深、轉置表、Star1 剪枝。

節點型別依「當下的決策者」而定，不依相位：我方單位行動＝max；敵方單位行動
＝敵方模型的期望（policy）或 min；一次攻擊的命中／未命中＝機率節點；我方
單位被攻擊時的應戰選項＝巢狀 max（雖然發生在敵方相位，決定權在我們）；敵方
被我方攻擊時的反應＝敵方模型的 reactions()，同樣以期望或 min 收斂。

葉評估器與終局判定由 Objective 注入；敵方模型可抽換。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Protocol

from .model import (
    DEFAULT_RULES,
    STANCES,
    BattleState,
    Decision,
    EventTable,
    Faction,
    MoveKind,
    ReachFn,
    Reaction,
    Rules,
    Stance,
    Unit,
    chebyshev,
    decision_hit_probability,
    find_support_defender,
    legal_attacks,
    legal_map_attacks,
    legal_skills,
    reach_of,
    reposition_moves,
    standby,
    step,
)

_INF = float("inf")


@dataclass(frozen=True)
class EvalWeights:
    ally_hp: float = 1.0
    enemy_hp: float = 1.0
    kill: float = 5.0
    loss: float = 5.0


@dataclass(frozen=True)
class EvalContext:
    weights: EvalWeights
    base_allies: int
    base_enemies: int


Evaluator = Callable[[BattleState, EvalContext], float]
# None ＝ 尚未終局；回傳 float 時該值必須落在 Objective.bounds 內，否則 Star1 不成立。
TerminalFn = Callable[[BattleState, EvalContext], "float | None"]


@dataclass(frozen=True)
class Objective:
    terminal: TerminalFn
    evaluator: Evaluator
    bounds: tuple[float, float] | None = None


def default_evaluator(state: BattleState, ctx: EvalContext) -> float:
    w = ctx.weights
    allies = state.allies()
    enemies = state.enemies()
    ally_hp = sum(u.hp / u.max_hp for u in allies)
    enemy_hp = sum(u.hp / u.max_hp for u in enemies)
    kills = ctx.base_enemies - len(enemies)
    losses = ctx.base_allies - len(allies)
    return w.ally_hp * ally_hp - w.enemy_hp * enemy_hp + w.kill * kills - w.loss * losses


def eval_bounds(base_allies: int, base_enemies: int, w: EvalWeights) -> tuple[float, float]:
    vmax = w.ally_hp * base_allies + w.kill * base_enemies
    vmin = -(w.enemy_hp * base_enemies + w.loss * base_allies)
    return vmin, vmax


def wiped_out(state: BattleState) -> bool:
    return not state.allies() or not state.enemies()


def annihilation_objective(evaluator: Evaluator | None = None) -> Objective:
    chosen = evaluator or default_evaluator

    def terminal(state: BattleState, ctx: EvalContext) -> float | None:
        return chosen(state, ctx) if wiped_out(state) else None

    return Objective(terminal=terminal, evaluator=chosen)


class EnemyMode(StrEnum):
    POLICY = "policy"
    MIN = "min"


class EnemyModel(Protocol):
    """敵方單位的行動候選與被我方攻擊時的反應候選。

    POLICY 模式下機率是搜尋取期望用的分布；MIN 模式下機率被忽略，搜尋改取
    最小值當保守界。
    """

    mode: EnemyMode

    def decisions(self, state: BattleState, unit: Unit) -> list[tuple[Decision, float]]: ...

    def reactions(
        self, state: BattleState, decision: Decision
    ) -> list[tuple[Reaction, float]]: ...


class NearestTargetPolicy:
    """最近目標基線：打得到就打最近的，打不到就待機；被攻擊一律應戰＋攔截。"""

    mode = EnemyMode.POLICY

    def __init__(self, reach_fn: ReachFn | None = None) -> None:
        self._reach_fn = reach_fn

    def decisions(self, state: BattleState, unit: Unit) -> list[tuple[Decision, float]]:
        attacks = legal_attacks(state, unit, reach=reach_of(state, unit, self._reach_fn))
        if not attacks:
            return [(standby(unit.unit_id), 1.0)]
        return [(min(attacks, key=lambda d: _target_distance(state, unit, d)), 1.0)]

    def reactions(
        self, state: BattleState, decision: Decision
    ) -> list[tuple[Reaction, float]]:
        return [(Reaction(stance=Stance.COUNTER, support_defend=True), 1.0)]


class MinimaxEnemy:
    """保守界：每個合法攻擊加待機都是候選，反應枚舉全部姿態×攔截與否。"""

    mode = EnemyMode.MIN

    def __init__(self, reach_fn: ReachFn | None = None) -> None:
        self._reach_fn = reach_fn

    def decisions(self, state: BattleState, unit: Unit) -> list[tuple[Decision, float]]:
        attacks = legal_attacks(state, unit, reach=reach_of(state, unit, self._reach_fn))
        candidates = [*attacks, standby(unit.unit_id)]
        weight = 1.0 / len(candidates)
        return [(d, weight) for d in candidates]

    def reactions(
        self, state: BattleState, decision: Decision
    ) -> list[tuple[Reaction, float]]:
        responses = _reaction_candidates(state, state.unit(decision.target_id))
        weight = 1.0 / len(responses)
        return [(r, weight) for r in responses]


def _target_distance(state: BattleState, unit: Unit, decision: Decision) -> int:
    target = state.unit(decision.target_id)
    if target is None:
        return 1_000_000
    origin = decision.move_to if decision.move_to is not None else unit.pos
    return chebyshev(origin, target.pos)


def _reaction_candidates(state: BattleState, target: Unit | None) -> list[Reaction]:
    out = [Reaction(stance=s) for s in STANCES]
    if target is not None and find_support_defender(state, target) is not None:
        out.extend(Reaction(stance=s, support_defend=True) for s in STANCES)
    return out


@dataclass
class SearchStats:
    nodes: int = 0
    depth: int = 0


@dataclass
class SearchResult:
    decision: Decision | None
    pv: list[Decision]
    value: float
    stats: SearchStats


@dataclass
class SearchConfig:
    time_budget_s: float = 2.0
    max_depth: int = 16
    weights: EvalWeights = field(default_factory=EvalWeights)
    rules: Rules = DEFAULT_RULES
    reach_fn: ReachFn | None = None
    use_tt: bool = True
    use_star1: bool = True
    objective: Objective | None = None
    events: EventTable | None = None


_FLAG_EXACT = 0
_FLAG_LOWER = 1
_FLAG_UPPER = 2


class _Timeout(Exception):
    pass


@dataclass
class _Context:
    enemy_model: EnemyModel
    config: SearchConfig
    evaluator: Evaluator
    terminal: TerminalFn
    eval_ctx: EvalContext
    deadline: float
    stats: SearchStats
    vmin: float
    vmax: float
    tt: dict = field(default_factory=dict)


def _next_actor(state: BattleState) -> Unit | None:
    for u in state.units:
        if u.faction is state.phase and u.alive and not u.acted:
            return u
    return None


def _teammate_has_support_charge(state: BattleState, unit: Unit) -> bool:
    return any(
        u is not unit and u.alive and u.faction is unit.faction and u.support_attack_charges > 0
        for u in state.units
    )


def _ally_decisions(state: BattleState, unit: Unit, ctx: _Context) -> list[Decision]:
    reach = reach_of(state, unit, ctx.config.reach_fn)
    decisions = legal_attacks(state, unit, reach=reach)
    # 隊友還有支援次數時，每個攻擊都補一個 support=False 版本：齊射灌進攔截者
    # 是浪費，燒掉的次數再動或防守相位就沒得用。
    if _teammate_has_support_charge(state, unit):
        decisions.extend(replace(d, support=False) for d in list(decisions))
    decisions.extend(legal_map_attacks(state, unit))
    decisions.extend(legal_skills(unit))
    decisions.extend(reposition_moves(state, unit, reach=reach))
    decisions.append(standby(unit.unit_id))
    return decisions


def _step(state: BattleState, decision: Decision, ctx: _Context) -> BattleState:
    return step(
        state,
        decision,
        rules=ctx.config.rules,
        events=ctx.config.events,
        reach_fn=ctx.config.reach_fn,
    )


def _depth_after(before: BattleState, after: BattleState, depth: int) -> int:
    return depth - (after.phase_index() - before.phase_index())


def _search(
    state: BattleState, depth: int, alpha: float, beta: float, ctx: _Context
) -> tuple[float, list[Decision]]:
    ctx.stats.nodes += 1
    if time.monotonic() > ctx.deadline:
        raise _Timeout
    terminal_value = ctx.terminal(state, ctx.eval_ctx)
    if terminal_value is not None:
        return terminal_value, []
    if depth <= 0:
        return ctx.evaluator(state, ctx.eval_ctx), []

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
        return ctx.evaluator(state, ctx.eval_ctx), []

    if actor.faction is Faction.ALLY:
        value, pv = _max_node(state, actor, depth, alpha, beta, ctx)
    elif actor.faction is Faction.ENEMY:
        value, pv = _enemy_node(state, actor, depth, alpha, beta, ctx)
    else:
        value, pv = ctx.evaluator(state, ctx.eval_ctx), []

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
    state: BattleState, actor: Unit, depth: int, alpha: float, beta: float, ctx: _Context
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
    state: BattleState, actor: Unit, depth: int, alpha: float, beta: float, ctx: _Context
) -> tuple[float, list[Decision]]:
    candidates = ctx.enemy_model.decisions(state, actor)
    if ctx.enemy_model.mode is EnemyMode.MIN:
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
        return ctx.evaluator(state, ctx.eval_ctx), []

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
    ctx: _Context,
) -> tuple[float, list[Decision]]:
    """機率加權期望，帶 Star1 子窗。

    每個分支依「已結算的精確質量＋剩餘質量落在 [vmin, vmax] 的合理範圍」推出
    自己的 (ax, bx)；子值觸窗即證明本節點過不了父窗，fail-soft 回傳保證界
    （fail-high 把剩餘質量計成 vmin、fail-low 計成 vmax）。關掉 Star1 時子窗
    全開、總和精確。
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
    state: BattleState, decision: Decision, depth: int, alpha: float, beta: float, ctx: _Context
) -> tuple[float, list[Decision]]:
    actor = state.unit(decision.unit_id)
    target = state.unit(decision.target_id)
    if (
        decision.kind is MoveKind.ATTACK
        and actor is not None
        and target is not None
        and decision.reaction is None
    ):
        if actor.faction is Faction.ENEMY and target.faction is Faction.ALLY:
            return _our_reaction_node(state, decision, target, depth, alpha, beta, ctx)
        if actor.faction is Faction.ALLY and target.faction is Faction.ENEMY:
            return _enemy_reaction_node(state, decision, depth, alpha, beta, ctx)
    value, pv = _chance_value(state, decision, depth, alpha, beta, ctx)
    return value, [decision, *pv]


def _our_reaction_node(
    state: BattleState,
    decision: Decision,
    target: Unit,
    depth: int,
    alpha: float,
    beta: float,
    ctx: _Context,
    candidates: list[Reaction] | None = None,
) -> tuple[float, list[Decision]]:
    best = -_INF
    best_pv: list[Decision] = []
    pool = candidates if candidates is not None else _reaction_candidates(state, target)
    for reaction in pool:
        responded = replace(decision, reaction=reaction)
        value, pv = _chance_value(state, responded, depth, alpha, beta, ctx)
        if value > best:
            best, best_pv = value, [responded, *pv]
        alpha = max(alpha, best)
        if alpha >= beta:
            break
    return best, best_pv


def _enemy_reaction_node(
    state: BattleState, decision: Decision, depth: int, alpha: float, beta: float, ctx: _Context
) -> tuple[float, list[Decision]]:
    candidates = ctx.enemy_model.reactions(state, decision)
    if not candidates:
        value, pv = _chance_value(state, decision, depth, alpha, beta, ctx)
        return value, [decision, *pv]
    if ctx.enemy_model.mode is EnemyMode.MIN:
        best = _INF
        best_pv: list[Decision] = []
        for reaction, _prob in candidates:
            responded = replace(decision, reaction=reaction)
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
        (prob, make_resolver(replace(decision, reaction=reaction)))
        for reaction, prob in candidates
    ]
    return _expectation(branches, alpha, beta, ctx)


def _chance_value(
    state: BattleState, decision: Decision, depth: int, alpha: float, beta: float, ctx: _Context
) -> tuple[float, list[Decision]]:
    if decision.kind is not MoveKind.ATTACK:
        nxt = _step(state, decision, ctx)
        return _search(nxt, _depth_after(state, nxt, depth), alpha, beta, ctx)

    prob = decision_hit_probability(state, decision, ctx.config.rules)
    if prob >= 1.0 or prob <= 0.0:
        nxt = _step(state, replace(decision, hit=prob >= 1.0), ctx)
        return _search(nxt, _depth_after(state, nxt, depth), alpha, beta, ctx)

    def make_resolver(hit: bool):
        def resolve(ax: float, bx: float) -> tuple[float, list[Decision]]:
            nxt = _step(state, replace(decision, hit=hit), ctx)
            return _search(nxt, _depth_after(state, nxt, depth), ax, bx, ctx)

        return resolve

    branches = [(prob, make_resolver(True)), (1.0 - prob, make_resolver(False))]
    return _expectation(branches, alpha, beta, ctx)


def _prepare(
    state: BattleState, config: SearchConfig
) -> tuple[Objective, EvalContext, tuple[float, float]]:
    objective = config.objective or annihilation_objective()
    base_allies = len(state.allies())
    base_enemies = len(state.enemies())
    bounds = objective.bounds or eval_bounds(base_allies, base_enemies, config.weights)
    eval_ctx = EvalContext(
        weights=config.weights, base_allies=base_allies, base_enemies=base_enemies
    )
    return objective, eval_ctx, bounds


def _context(
    enemy_model: EnemyModel,
    config: SearchConfig,
    objective: Objective,
    eval_ctx: EvalContext,
    bounds: tuple[float, float],
    deadline: float,
    stats: SearchStats,
) -> _Context:
    return _Context(
        enemy_model=enemy_model,
        config=config,
        evaluator=objective.evaluator,
        terminal=objective.terminal,
        eval_ctx=eval_ctx,
        deadline=deadline,
        stats=stats,
        vmin=bounds[0],
        vmax=bounds[1],
    )


def solve(
    state: BattleState, enemy_model: EnemyModel, config: SearchConfig | None = None
) -> SearchResult:
    config = config or SearchConfig()
    objective, eval_ctx, bounds = _prepare(state, config)
    stats = SearchStats()
    best = SearchResult(decision=None, pv=[], value=0.0, stats=stats)
    deadline = time.monotonic() + config.time_budget_s

    for depth in range(1, config.max_depth + 1):
        ctx = _context(enemy_model, config, objective, eval_ctx, bounds, deadline, stats)
        try:
            value, pv = _search(state, depth, -_INF, _INF, ctx)
        except _Timeout:
            break
        stats.depth = depth
        best = SearchResult(decision=pv[0] if pv else None, pv=pv, value=value, stats=stats)
        if objective.terminal(state, eval_ctx) is not None:
            break
    return best


def solve_reaction(
    state: BattleState,
    attack: Decision,
    enemy_model: EnemyModel,
    config: SearchConfig | None = None,
    *,
    allowed_stances: tuple[Stance, ...] | None = None,
    allow_support_defend: bool = True,
) -> SearchResult:
    """畫面上的應戰彈窗已經定死了敵方那一擊，這裡只在我方反應上迭代加深。

    allowed_stances／allow_support_defend 只縮限根節點的枚舉（彈窗提供什麼由
    畫面裁決），樹內的反應節點不受限；縮限後無候選時回傳 decision None。
    """
    config = config or SearchConfig()
    stats = SearchStats()
    best = SearchResult(decision=None, pv=[], value=0.0, stats=stats)
    target = state.unit(attack.target_id)
    if target is None:
        return best
    objective, eval_ctx, bounds = _prepare(state, config)

    candidates = _reaction_candidates(state, target)
    if allowed_stances is not None:
        candidates = [r for r in candidates if r.stance in allowed_stances]
    if not allow_support_defend:
        candidates = [r for r in candidates if not r.support_defend]
    if not candidates:
        return best

    deadline = time.monotonic() + config.time_budget_s
    for depth in range(1, config.max_depth + 1):
        ctx = _context(enemy_model, config, objective, eval_ctx, bounds, deadline, stats)
        try:
            value, pv = _our_reaction_node(
                state, attack, target, depth, -_INF, _INF, ctx, candidates=candidates
            )
        except _Timeout:
            break
        stats.depth = depth
        best = SearchResult(decision=pv[0] if pv else None, pv=pv, value=value, stats=stats)
    return best
