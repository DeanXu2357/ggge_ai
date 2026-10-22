from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import ClassVar

from ggge_ai_2.actuator.contract import Gesture, Key, Rect, ScreenPoint, Swipe, Tap
from ggge_ai_2.agent.belief import Belief, ScreenLock
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
        width, height = self.screen

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
            for region in self.uisim.danger_band(belief.ui).regions
        )
        expected = tuple(
            replace(belief, ui=self.uisim.advance(belief.ui, o)) for o in operation.outcomes
        )
        return Step(operation.name, gesture, band, operation.deadline, expected)

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
