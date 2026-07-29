"""戰術定價：advise.Advisor 的沙盤實作。

符號狀態＋情報庫組裝 BattleState，戰鬥候選丟 expectiminimax 算分再折成
邊權；盤面上有任何一台缺情報就整盤不背書，規劃層於是自己把 Inspect 排
進計畫——偵察不需要特殊機制。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from ..stage.actions import Action, Attack, Brace, Inspect, Move, Standby, Withdraw
from ..stage.intel import Intelligence
from ..stage.state import Phase, StageState
from .advise import Appraisal, Guarantee, Pricing, Verdict
from .model import (
    DEFAULT_RULES,
    NO_DEFENSE_MULTIPLIER,
    BattleState,
    Decision,
    Faction,
    MoveKind,
    Rules,
    Stance,
    Unit,
    Weapon,
    chebyshev,
    find_support_defender,
    in_band,
    legal_attacks,
    reach_of,
    standby,
    step,
    strike_damage,
    strike_hit_probability,
)
from .search import (
    EnemyModel,
    EvalContext,
    NearestTargetPolicy,
    Objective,
    SearchConfig,
    default_evaluator,
    eval_bounds,
    solve,
    solve_reaction,
    wiped_out,
)

_STANCES = {stance.value: stance for stance in Stance}


@dataclass(frozen=True)
class TacticianConfig:
    """inspect_cost／withdraw_cost 是固定小額：兩者的收益不在沙盤的量綱裡，
    硬折成分數只會憑空多一組旋鈕。"""

    inspect_cost: float = 0.5
    withdraw_cost: float = 1.0
    kill_hit_threshold: float = 1.0
    withdraw_below: float | None = None
    search: SearchConfig = field(default_factory=SearchConfig)


class TacticalAdvisor:
    def __init__(
        self,
        intel: Intelligence,
        *,
        rules: Rules = DEFAULT_RULES,
        config: TacticianConfig = TacticianConfig(),
        enemy_model: EnemyModel | None = None,
    ) -> None:
        self.intel = intel
        self.rules = rules
        self.config = config
        self.enemy_model = enemy_model or NearestTargetPolicy()
        self.search_config = replace(config.search, rules=rules)

    def appraise(self, state: StageState) -> Appraisal:
        board = self.board(state)
        if board is None:
            return Appraisal(Verdict.PURSUE, "情報不全，先偵察")
        threshold = self.config.withdraw_below
        if threshold is None:
            return Appraisal(Verdict.PURSUE, "未設離場門檻")
        score = default_evaluator(board, self._eval_context(board))
        if score < threshold:
            return Appraisal(Verdict.WITHDRAW, f"葉評估 {score:.3f} 低於門檻 {threshold:.3f}")
        return Appraisal(Verdict.PURSUE, f"葉評估 {score:.3f}")

    def price(
        self, state: StageState, candidates: Sequence[Action]
    ) -> Sequence[Pricing | None]:
        board = self.board(state)
        return tuple(self._price(state, board, action) for action in candidates)

    def board(self, state: StageState) -> BattleState | None:
        """符號狀態＋情報庫的組裝口。缺一台就整盤回 None——沙盤推演不了
        看不見的單位，湊數的預設值會讓保守下界失去意義。"""
        units: list[Unit] = []
        for unit_id in sorted(state.allies):
            unit = self._unit(state, unit_id, Faction.ALLY, unit_id not in state.actionable)
            if unit is None:
                return None
            units.append(unit)
        for unit_id in sorted(state.enemies):
            unit = self._unit(state, unit_id, Faction.ENEMY, False)
            if unit is None:
                return None
            units.append(unit)
        if not units:
            return None
        phase = Faction.ALLY if state.phase is Phase.PLAYER else Faction.ENEMY
        return BattleState(units=units, phase=phase)

    def objective(self, board: BattleState) -> Objective:
        """把評估錨在計價當下的盤面：solve 預設會拿它自己收到的盤面重算
        基準，那樣「這一擊殺掉的那台」不算進 kill 項，候選之間也不同尺。"""
        ctx = self._eval_context(board)

        def evaluator(state: BattleState, _ctx: EvalContext) -> float:
            return default_evaluator(state, ctx)

        def terminal(state: BattleState, _ctx: EvalContext) -> float | None:
            return evaluator(state, _ctx) if wiped_out(state) else None

        return Objective(
            terminal=terminal,
            evaluator=evaluator,
            bounds=eval_bounds(ctx.base_allies, ctx.base_enemies, ctx.weights),
        )

    def _unit(
        self, state: StageState, unit_id: str, faction: Faction, acted: bool
    ) -> Unit | None:
        if unit_id not in state.known:
            return None
        pos = state.position_of(unit_id)
        if pos is None:
            return None
        return self.intel.unit(unit_id, faction, pos=pos, acted=acted)

    def _eval_context(self, board: BattleState) -> EvalContext:
        return EvalContext(
            weights=self.search_config.weights,
            base_allies=len(board.allies()),
            base_enemies=len(board.enemies()),
        )

    def _price(
        self, state: StageState, board: BattleState | None, action: Action
    ) -> Pricing | None:
        if isinstance(action, Inspect):
            return Pricing(self.config.inspect_cost, note="偵察")
        if isinstance(action, Withdraw):
            return Pricing(self.config.withdraw_cost, note="離場")
        if board is None:
            return None
        if isinstance(action, Attack):
            return self._price_attack(board, action)
        if isinstance(action, Move):
            return self._price_move(board, action)
        if isinstance(action, Standby):
            return self._price_standby(board, action)
        if isinstance(action, Brace):
            return self._price_brace(state, board, action)
        return None

    def _price_attack(self, board: BattleState, action: Attack) -> Pricing | None:
        actor = board.unit(action.unit)
        if actor is None or board.unit(action.target) is None:
            return None
        options = [d for d in legal_attacks(board, actor) if d.target_id == action.target]
        if not options:
            return None
        scored = [(self._value_after(board, decision), decision) for decision in options]
        value, best = max(scored, key=lambda pair: pair[0])
        weapon = actor.weapon(best.weapon)
        return Pricing(
            self._cost(board, value),
            self._guarantee(board, actor, action.target, weapon),
            note=best.weapon or "",
        )

    def _price_move(self, board: BattleState, action: Move) -> Pricing | None:
        actor = board.unit(action.unit)
        if actor is None:
            return None
        if action.destination not in reach_of(board, actor, self.search_config.reach_fn):
            return None
        decision = Decision(
            unit_id=action.unit, kind=MoveKind.REPOSITION, move_to=action.destination
        )
        return Pricing(self._cost(board, self._value_after(board, decision)))

    def _price_standby(self, board: BattleState, action: Standby) -> Pricing | None:
        if board.unit(action.unit) is None:
            return None
        return Pricing(self._cost(board, self._value_after(board, standby(action.unit))))

    def _price_brace(
        self, state: StageState, board: BattleState, action: Brace
    ) -> Pricing | None:
        reaction = state.reaction
        if reaction is None or reaction.defender != action.unit:
            return None
        if reaction.attacker != action.attacker:
            return None
        stance = _STANCES.get(action.stance)
        if stance is None:
            return None
        attacker = board.unit(action.attacker)
        defender = board.unit(action.unit)
        if attacker is None or defender is None:
            return None
        incoming = self._incoming(attacker, defender)
        if incoming is None:
            return None
        result = solve_reaction(
            board,
            incoming,
            self.enemy_model,
            replace(self.search_config, objective=self.objective(board)),
            allowed_stances=(stance,),
        )
        if result.decision is None:
            return None
        return Pricing(self._cost(board, result.value), note=stance.value)

    def _incoming(self, attacker: Unit, defender: Unit) -> Decision | None:
        """彈窗沒告訴我們敵方選了哪把武裝，取傷害最高的當保守假設。"""
        distance = chebyshev(attacker.pos, defender.pos)
        usable = [
            weapon
            for weapon in attacker.weapons
            if not weapon.map_weapon
            and attacker.en >= weapon.en_cost
            and in_band(distance, weapon)
        ]
        if not usable:
            return None
        weapon = max(
            usable, key=lambda w: strike_damage(attacker, defender, w, rules=self.rules)
        )
        return Decision(
            unit_id=attacker.unit_id,
            kind=MoveKind.ATTACK,
            target_id=defender.unit_id,
            weapon=weapon.name,
        )

    def _value_after(self, board: BattleState, decision: Decision) -> float:
        after = step(
            board, decision, rules=self.rules, reach_fn=self.search_config.reach_fn
        )
        config = replace(self.search_config, objective=self.objective(board))
        return solve(after, self.enemy_model, config).value

    def _cost(self, board: BattleState, value: float) -> float:
        _, vmax = eval_bounds(
            len(board.allies()), len(board.enemies()), self.search_config.weights
        )
        return max(0.0, vmax - value)

    def _guarantee(
        self, board: BattleState, actor: Unit, target_id: str, weapon: Weapon | None
    ) -> Guarantee:
        target = board.unit(target_id)
        if weapon is None or target is None:
            return Guarantee.NONE
        # 離線判準是替身：批 2d 接上實機攻擊預測後，命中率與傷害下界改以
        # 預測畫面為權威，這裡只保留公式版當畫面給不出數字時的後備。
        if find_support_defender(board, target) is not None:
            return Guarantee.NONE
        hit = strike_hit_probability(actor, target, weapon, dodging=True, rules=self.rules)
        if hit < self.config.kill_hit_threshold:
            return Guarantee.NONE
        floor = min(
            NO_DEFENSE_MULTIPLIER, self.rules.defend_multiplier, self.rules.shield_multiplier
        )
        damage = strike_damage(
            actor, target, weapon, defense_multiplier=floor, rules=self.rules
        )
        return Guarantee.KILL if damage >= target.hp else Guarantee.NONE
