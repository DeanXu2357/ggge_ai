from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import ClassVar

from ggge_ai_2.actuator.contract import Gesture, Key, Rect, ScreenPoint, Swipe, Tap
from ggge_ai_2.agent.belief import Belief, Passing, ScreenLock, UiSource
from ggge_ai_2.agent.contract import Plan, Reflex, Step
from ggge_ai_2.uisim.contract import (
    Operation,
    Outcome,
    RatioPoint,
    UiKey,
    UiScreen,
    UiSim,
    UiState,
    UiSwipe,
    UiTap,
)


@dataclass(frozen=True)
class PowerSaveUnlock:
    # These points apply only to the test phone R5CRC37JBYJ (2340x1080).
    DRAG_UP_FROM_LOCK_ICON: ClassVar[Swipe] = Swipe((1164, 430), (1164, 60), 0.35)
    POKE_TOP_CENTRE: ClassVar[Tap] = Tap((1170, 90))
    # The deadlines are the settle times that the old 'keyguard.py' used on that phone.
    DRAG_DEADLINE: ClassVar[float] = 1.5
    POKE_DEADLINE: ClassVar[float] = 0.8

    def still_valid(self, belief: Belief) -> bool:
        return belief.screen_lock is not None

    def react(self, belief: Belief) -> Step | None:
        if belief.screen_lock is None:
            return None
        if belief.screen_lock is ScreenLock.DIM:
            shown = replace(belief, screen_lock=ScreenLock.ICON)
            return Step("power_save_poke", self.POKE_TOP_CENTRE, (), self.POKE_DEADLINE, (shown,))
        unlocked = replace(belief, screen_lock=None)
        return Step(
            "power_save_unlock",
            self.DRAG_UP_FROM_LOCK_ICON,
            (),
            self.DRAG_DEADLINE,
            (unlocked,),
        )


@dataclass(frozen=True)
class PassingWait:
    def still_valid(self, belief: Belief) -> bool:
        return belief.passing is Passing.WAIT

    def react(self, belief: Belief) -> Step | None:
        if not self.still_valid(belief):
            return None
        # The loop ignores the deadline and the expected belief: it does not predict
        # from a step on a pass-through frame.
        return Step("passing_wait", None, (), 0.0, (belief,))


@dataclass(frozen=True)
class TapToContinue:
    screen: tuple[int, int]

    def still_valid(self, belief: Belief) -> bool:
        return belief.passing is Passing.TAP_TO_CONTINUE

    def react(self, belief: Belief) -> Step | None:
        if not self.still_valid(belief):
            return None
        width, height = self.screen
        # The loop ignores the deadline and the expected belief: it does not predict
        # from a step on a pass-through frame.
        return Step("tap_to_continue", Tap((width // 2, height // 2)), (), 0.0, (belief,))


@dataclass(frozen=True)
class DefaultPlanController:
    BATTLE_MAP: ClassVar[UiState] = UiState(UiScreen.PLAYER_PHASE_OVERVIEW)

    reflexes: tuple[Reflex, ...]
    uisim: UiSim
    screen: tuple[int, int]

    def goal_reached(self, belief: Belief) -> bool:
        # TODO(#105): the stage goal.
        return False

    def think(self, belief: Belief, history: Sequence[object]) -> Plan | None:
        # TODO(#105): before the map, check AUTO and '顯示方格'. On the map, give an
        #     unrecorded map to the map sync plan and a recorded map to the battle
        #     plan. After the map is explored, leave the stage.
        if belief.ui == self.BATTLE_MAP:
            return None
        to_map = UiShiftPlan(self.BATTLE_MAP, self.uisim, self.screen)
        return ReflexPlan(self.reflexes, to_map)

    def review(self, plan: Plan, belief: Belief) -> object:
        # TODO: the shape of a review is deferred.
        return plan


@dataclass(frozen=True)
class StagePlanController:
    goal: UiScreen
    reflexes: tuple[Reflex, ...]
    uisim: UiSim
    screen: tuple[int, int]

    def goal_reached(self, belief: Belief) -> bool:
        return (
            belief.ui_basis.source is UiSource.SEEN
            and belief.ui.screen is self.goal
            and belief.passing is None
        )

    def think(self, belief: Belief, history: Sequence[object]) -> Plan | None:
        plan = ReflexPlan(self.reflexes, self._inner(belief, history))
        return plan if plan.still_valid(belief) else None

    def review(self, plan: Plan, belief: Belief) -> object:
        return plan.inner if isinstance(plan, ReflexPlan) else plan

    def _inner(self, belief: Belief, history: Sequence[object]) -> Plan:
        screen = belief.ui.screen
        # The loop thinks again on a valid plan only after MISMATCH_LIMIT mismatches.
        # So a greedy plan in the last review on this screen means that '攻擊' did not
        # change the screen: no target is in range.
        if (
            screen is UiScreen.SELECT_WEAPON_IN_BATTLE
            and history
            and isinstance(history[-1], GreedyBattlePlan)
            and not history[-1].fallback
        ):
            return GreedyBattlePlan(self.uisim, self.screen, fallback=True)
        if screen in GREEDY_BUTTONS:
            return GreedyBattlePlan(self.uisim, self.screen)
        return UiShiftPlan(UiState(self.goal), self.uisim, self.screen)


@dataclass(frozen=True)
class UiShiftPlan:
    goal: UiState
    uisim: UiSim
    screen: tuple[int, int]

    def still_valid(self, belief: Belief) -> bool:
        return belief.ui != self.goal and self.first_move(belief.ui) is not None

    def next(self, belief: Belief) -> Step:
        move = self.first_move(belief.ui)
        assert move is not None, "the main loop takes a step only from a valid plan"
        operation, _ = move
        return operation_step(operation, belief, self.uisim, self.screen)

    def first_move(self, state: UiState) -> tuple[Operation, Outcome] | None:
        firsts: dict[UiState, tuple[Operation, Outcome] | None] = {state: None}
        frontier = deque([state])
        while frontier:
            current = frontier.popleft()
            if current == self.goal:
                return firsts[current]
            for operation in self.uisim.successors(current):
                for outcome in operation.outcomes:
                    then = self.uisim.advance(current, outcome)
                    if then not in firsts:
                        firsts[then] = firsts[current] or (operation, outcome)
                        frontier.append(then)
        return None


def operation_step(
    operation: Operation, belief: Belief, uisim: UiSim, screen: tuple[int, int]
) -> Step:
    width, height = screen

    def touch(point: RatioPoint) -> ScreenPoint:
        return (round(point[0] * width), round(point[1] * height))

    gesture: Gesture | None
    match operation.gesture:
        case UiTap(point):
            gesture = Tap(touch(point))
        case UiSwipe(start, end, duration):
            gesture = Swipe(touch(start), touch(end), duration)
        case UiKey(code):
            gesture = Key(code)
        case None:
            gesture = None
    band = tuple(
        Rect(*touch((region.left, region.top)), *touch((region.right, region.bottom)))
        for region in uisim.danger_band(belief.ui).regions
    )
    expected = tuple(replace(belief, ui=uisim.advance(belief.ui, o)) for o in operation.outcomes)
    return Step(operation.name, gesture, band, operation.deadline, expected)


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
class GreedyBattlePlan:
    uisim: UiSim
    screen: tuple[int, int]
    fallback: bool = False

    def still_valid(self, belief: Belief) -> bool:
        if self.fallback and belief.ui.screen is not UiScreen.SELECT_WEAPON_IN_BATTLE:
            return False
        return self._operation(belief) is not None

    def next(self, belief: Belief) -> Step:
        operation = self._operation(belief)
        assert operation is not None, "the main loop takes a step only from a valid plan"
        return operation_step(operation, belief, self.uisim, self.screen)

    def _operation(self, belief: Belief) -> Operation | None:
        screen = belief.ui.screen
        if screen not in GREEDY_BUTTONS:
            return None
        operations = {operation.name: operation for operation in self.uisim.successors(belief.ui)}
        auto = operations.get(f"{screen.value}__auto")
        if belief.ui.auto is True and auto is not None:
            return auto
        if self.fallback and screen is UiScreen.SELECT_WEAPON_IN_BATTLE:
            return operations.get(FALLBACK_WEAPON_BUTTON)
        return operations.get(GREEDY_BUTTONS[screen])


@dataclass(frozen=True)
class ReflexPlan:
    reflexes: tuple[Reflex, ...]
    inner: Plan

    def still_valid(self, belief: Belief) -> bool:
        return any(r.still_valid(belief) for r in self.reflexes) or self.inner.still_valid(belief)

    def next(self, belief: Belief) -> Step:
        return self._react(belief) or self.inner.next(belief)

    def _react(self, belief: Belief) -> Step | None:
        for reflex in self.reflexes:
            step = reflex.react(belief)
            if step is not None:
                return step
        return None
