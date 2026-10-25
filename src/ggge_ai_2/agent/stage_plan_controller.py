from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from ggge_ai_2.agent.belief import Belief, UiSource
from ggge_ai_2.agent.contract import Plan, Step
from ggge_ai_2.agent.generic_plans import (
    AutoOffPlan,
    PassingWaitPlan,
    PowerSaveLockPlan,
    TapToContinuePlan,
)
from ggge_ai_2.agent.ui_steps import first_move, operation_step
from ggge_ai_2.uisim.contract import Operation, UiScreen, UiSim, UiState

GREEDY_BUTTONS: Mapping[UiScreen, str] = {
    UiScreen.BATTLE_INFO_PREVIEW: "battle_info_preview__tap_next",
    UiScreen.PLAYER_PHASE_OVERVIEW: "player_phase_overview__unit_card",
    UiScreen.SELECT_ACTION_IN_BATTLE: "select_action_in_battle__select_weapon",
    UiScreen.SELECT_WEAPON_IN_BATTLE: "select_weapon_in_battle__attack",
    UiScreen.BATTLE_PREP_ATTACK: "battle_prep_attack__start_battle",
    UiScreen.BATTLE_PREP_RESPONSE_ATTACK: "battle_prep_response_attack__start_battle",
    UiScreen.NON_PLAYER_PHASE_BATTLE_VIEW: "non_player_phase_battle_view__wait",
    UiScreen.CHALLENGE_BATTLE_CHECK: "challenge_battle_check__challenge",
    UiScreen.BATTLE_MAIN_SETTING: "battle_main_setting__close",
}
FALLBACK_WEAPON_BUTTON = "select_weapon_in_battle__wait"


@dataclass(frozen=True)
class StagePlan:
    goal: UiScreen
    uisim: UiSim
    screen: tuple[int, int]
    auto_off: AutoOffPlan
    tap_to_continue: TapToContinuePlan
    fallback: bool = False
    power_save: PowerSaveLockPlan = PowerSaveLockPlan()
    passing_wait: PassingWaitPlan = PassingWaitPlan()

    def still_valid(self, belief: Belief) -> bool:
        if self.auto_off.awaiting_confirmation(belief):
            return False
        return self._generic(belief) is not None or self._operation(belief) is not None

    def next(self, belief: Belief) -> Step:
        generic = self._generic(belief)
        if generic is not None:
            return generic.next(belief)
        operation = self._operation(belief)
        assert operation is not None, "the main loop takes a step only from a valid plan"
        return operation_step(operation, belief, self.uisim, self.screen)

    def _generic(self, belief: Belief) -> Plan | None:
        order: tuple[Plan, ...] = (
            self.power_save,
            self.passing_wait,
            self.tap_to_continue,
            self.auto_off,
        )
        return next((plan for plan in order if plan.still_valid(belief)), None)

    def _operation(self, belief: Belief) -> Operation | None:
        screen = belief.ui.screen
        if self.fallback and screen is not UiScreen.SELECT_WEAPON_IN_BATTLE:
            return None
        if screen in GREEDY_BUTTONS:
            operations = {
                operation.name: operation for operation in self.uisim.successors(belief.ui)
            }
            if self.fallback:
                return operations.get(FALLBACK_WEAPON_BUTTON)
            return operations.get(GREEDY_BUTTONS[screen])
        goal = UiState(self.goal)
        if belief.ui == goal:
            return None
        move = first_move(self.uisim, belief.ui, goal)
        return None if move is None else move[0]


@dataclass(frozen=True)
class StagePlanController:
    goal: UiScreen
    uisim: UiSim
    screen: tuple[int, int]

    def goal_reached(self, belief: Belief) -> bool:
        return (
            belief.ui_basis.source is UiSource.SEEN
            and belief.ui.screen is self.goal
            and belief.passing is None
        )

    def think(self, belief: Belief, history: Sequence[object]) -> StagePlan | None:
        previous = history[-1] if history and isinstance(history[-1], StagePlan) else None
        if previous is None:
            auto_off = AutoOffPlan(self.uisim, self.screen)
        else:
            auto_off = previous.auto_off.confirmed(belief)
        # The loop thinks again on a valid plan only after MISMATCH_LIMIT mismatches.
        # So a valid greedy plan on this screen means that '攻擊' did not change the
        # screen: no target is in range.
        fallback = (
            belief.ui.screen is UiScreen.SELECT_WEAPON_IN_BATTLE
            and previous is not None
            and not previous.fallback
            and previous.still_valid(belief)
        )
        # TODO: after CONFIRMED, think keeps the greedy plan. The strategy after AUTO is
        #     not decided.
        plan = StagePlan(
            self.goal,
            self.uisim,
            self.screen,
            auto_off,
            TapToContinuePlan(self.screen),
            fallback,
        )
        return plan if plan.still_valid(belief) else None

    def review(self, plan: StagePlan, belief: Belief) -> object:
        return replace(plan, auto_off=copy.copy(plan.auto_off))
