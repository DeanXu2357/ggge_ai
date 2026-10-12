from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import ClassVar

from ggge_ai_2.actuator.contract import Swipe, Tap
from ggge_ai_2.agent.belief import Belief, ScreenLock
from ggge_ai_2.agent.contract import Plan, Reflex, Step


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
            return Step("power_save_poke", self.POKE_TOP_CENTRE, (), self.POKE_DEADLINE, shown)
        unlocked = replace(belief, screen_lock=None)
        return Step(
            "power_save_unlock",
            self.DRAG_UP_FROM_LOCK_ICON,
            (),
            self.DRAG_DEADLINE,
            unlocked,
        )


@dataclass(frozen=True)
class DefaultPlanController:
    reflexes: tuple[Reflex, ...]

    def goal_reached(self, belief: Belief) -> bool:
        # TODO: the stage goal of scenario 3.8 (groups B and C).
        return False

    def think(self, belief: Belief, history: Sequence[object]) -> Plan | None:
        # TODO: choose the domain planner for the belief (groups B and C):
        #     plan = planner.plan(belief)
        #     return None if plan is None else ReflexPlan(self.reflexes, plan)
        return None

    def review(self, plan: Plan, belief: Belief) -> object:
        # TODO: the shape of a review is deferred (roadmap section 6).
        return plan


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
