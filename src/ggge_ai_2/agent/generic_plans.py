from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import ClassVar, Protocol

from ggge_ai_2.actuator.contract import Swipe, Tap
from ggge_ai_2.agent.belief import Belief, Passing, ScreenLock
from ggge_ai_2.agent.contract import Step
from ggge_ai_2.agent.ui_steps import operation_step
from ggge_ai_2.uisim.contract import Operation, UiSim


@dataclass(frozen=True)
class PowerSaveLockPlan:
    # These points apply only to the test phone R5CRC37JBYJ (2340x1080).
    DRAG_UP_FROM_LOCK_ICON: ClassVar[Swipe] = Swipe((1164, 430), (1164, 60), 0.35)
    POKE_TOP_CENTRE: ClassVar[Tap] = Tap((1170, 90))
    # The deadlines are the settle times that the old 'keyguard.py' used on that phone.
    DRAG_DEADLINE: ClassVar[float] = 1.5
    POKE_DEADLINE: ClassVar[float] = 0.8

    def still_valid(self, belief: Belief) -> bool:
        return belief.screen_lock is not None

    def next(self, belief: Belief) -> Step:
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
class PassingWaitPlan:
    def still_valid(self, belief: Belief) -> bool:
        return belief.passing is Passing.WAIT

    def next(self, belief: Belief) -> Step:
        # The loop ignores the deadline and the expected belief: it does not predict
        # from a step on a pass-through frame.
        return Step("passing_wait", None, (), 0.0, (belief,))


@dataclass(frozen=True)
class TapToContinuePlan:
    screen: tuple[int, int]

    def still_valid(self, belief: Belief) -> bool:
        return belief.passing is Passing.TAP_TO_CONTINUE

    def next(self, belief: Belief) -> Step:
        width, height = self.screen
        # The loop ignores the deadline and the expected belief: it does not predict
        # from a step on a pass-through frame.
        return Step("tap_to_continue", Tap((width // 2, height // 2)), (), 0.0, (belief,))


class AutoOffPhase(StrEnum):
    UNTOUCHED = "untouched"
    PENDING = "pending"
    CONFIRMED = "confirmed"


class AutoOffStatus(Protocol):
    def phase(self) -> AutoOffPhase: ...

    def awaiting_confirmation(self, belief: Belief) -> bool: ...


@dataclass
class AutoOffPlan:
    # This value is a hypothesis. '_at' is the time of the frame that the plan decided
    # on, not the time of the tap. So the deadline includes the delay of the actuator.
    CONFIRM_DEADLINE: ClassVar[float] = 3.0

    uisim: UiSim
    screen: tuple[int, int]
    _phase: AutoOffPhase = field(default=AutoOffPhase.UNTOUCHED, init=False)
    _at: float | None = field(default=None, init=False)

    def still_valid(self, belief: Belief) -> bool:
        return belief.ui.auto is True and self._toggle(belief) is not None

    def next(self, belief: Belief) -> Step:
        assert belief.as_of is not None, "the main loop plans only on a sensed belief"
        if (
            self._phase is AutoOffPhase.PENDING
            and self._at is not None
            and belief.as_of.until < self._at + self.CONFIRM_DEADLINE
        ):
            # The frame can predate the reaction of the game. A second tap turns AUTO on again.
            return Step("auto_off_wait", None, (), 0.0, ())
        toggle = self._toggle(belief)
        assert toggle is not None, "the main loop takes a step only from a valid plan"
        self._phase, self._at = AutoOffPhase.PENDING, belief.as_of.until
        return replace(operation_step(toggle, belief, self.uisim, self.screen), expected=())

    def phase(self) -> AutoOffPhase:
        return self._phase

    def awaiting_confirmation(self, belief: Belief) -> bool:
        return self._phase is AutoOffPhase.PENDING and belief.ui.auto is False

    def confirmed(self, belief: Belief) -> AutoOffPlan:
        twin = copy.copy(self)
        if self.awaiting_confirmation(belief):
            twin._phase = AutoOffPhase.CONFIRMED
        return twin

    def _toggle(self, belief: Belief) -> Operation | None:
        name = f"{belief.ui.screen.value}__auto"
        return next(
            (operation for operation in self.uisim.successors(belief.ui) if operation.name == name),
            None,
        )
