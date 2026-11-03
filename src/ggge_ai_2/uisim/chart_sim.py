from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ggge_ai_2.uisim.chart import AutoButton, Chart, Gesture, ScreenChart, Target, Transition
from ggge_ai_2.uisim.contract import (
    DangerBand,
    Observed,
    OpenGroup,
    Operation,
    Outcome,
    RatioPoint,
    RatioRect,
    UiAutoMode,
    UiGesture,
    UiScreen,
    UiState,
    UiSwipe,
    UiTap,
)

LONG_PRESS_SECONDS = 1.0
SWIPE_SECONDS = 0.4
WAIT_SECONDS = 60.0
NEXT_AUTO_MODE = {
    UiAutoMode.FULL: UiAutoMode.SEMI,
    UiAutoMode.SEMI: UiAutoMode.MANUAL,
    UiAutoMode.MANUAL: UiAutoMode.FULL,
}
NO_SCREEN = ScreenChart()


@dataclass(frozen=True)
class ChartUiSim:
    chart: Chart

    def successors(self, state: UiState) -> Sequence[Operation]:
        screen = self._screen(state.screen)
        operations = [
            self._transition_operation(state, transition, transition.rect)
            for transition in screen.transitions
            if transition.rect is not None
        ]
        if screen.auto is not None and state.auto is not None:
            operations.append(self._auto_toggle(state, state.auto, screen.auto))
        if screen.waits:
            operations.append(self._wait_operation(state, screen.waits))
        return tuple(operations)

    def advance(self, state: UiState, outcome: Outcome) -> UiState:
        return outcome.then

    def sync(self, state: UiState, observed: Observed) -> UiState:
        if observed.screen == state.screen:
            return UiState(observed.screen, state.stack, observed.auto)
        stack = next(
            (
                outcome.then.stack
                for operation in self.successors(state)
                for outcome in operation.outcomes
                if outcome.then.screen == observed.screen
            ),
            None,
        )
        if stack is None:
            stack = self._inferred_stack(state, observed.screen)
        return UiState(observed.screen, stack, observed.auto)

    def danger_band(self, state: UiState) -> DangerBand:
        return DangerBand(self._screen(state.screen).danger)

    def _transition_operation(
        self, state: UiState, transition: Transition, rect: RatioRect
    ) -> Operation:
        targets = transition.targets
        caller = state.stack[-1].caller if state.stack else None
        if caller is not None and any(target.screen == caller for target in targets):
            targets = (Target(caller),)
        return Operation(
            name=transition.button,
            precondition=state,
            gesture=_gesture(transition.gesture, rect),
            outcomes=tuple(self._outcome(state, target) for target in targets),
            deadline=transition.deadline,
            cost=1.0,
        )

    def _auto_toggle(self, state: UiState, mode: UiAutoMode, button: AutoButton) -> Operation:
        then = NEXT_AUTO_MODE[mode]
        outcome = Outcome(f"auto_{then.value}", UiState(state.screen, state.stack, then))
        gesture = UiTap(_centre(button.rect))
        return Operation(button.button, state, gesture, (outcome,), button.deadline, 1.0)

    def _wait_operation(self, state: UiState, waits: tuple[Target, ...]) -> Operation:
        if all(target.screen != state.screen for target in waits):
            waits = (*waits, Target(state.screen))
        outcomes = tuple(self._outcome(state, target) for target in waits)
        return Operation(f"{state.screen.value}__wait", state, None, outcomes, WAIT_SECONDS, 1.0)

    def _outcome(self, state: UiState, target: Target) -> Outcome:
        then = UiState(
            target.screen, self._stack(state, target), self._carried_auto(state, target.screen)
        )
        return Outcome(target.screen.value, then)

    def _stack(self, state: UiState, target: Target) -> tuple[OpenGroup, ...]:
        if self._keeps(state, target.screen):
            return state.stack
        if target.group is not None and not _is_open(state.stack, target.group):
            return self._pushed(state, target.group)
        return self._popped(state.stack, target.screen)

    def _inferred_stack(self, state: UiState, screen: UiScreen) -> tuple[OpenGroup, ...]:
        if self._keeps(state, screen):
            return state.stack
        candidates = [
            group.name
            for group in self.chart.groups
            if screen in group.entry and not _is_open(state.stack, group.name)
        ]
        if len(candidates) == 1:
            return self._pushed(state, candidates[0])
        return self._popped(state.stack, screen)

    def _keeps(self, state: UiState, screen: UiScreen) -> bool:
        if screen == state.screen:
            return True
        return bool(state.stack) and self._contains(state.stack[-1].group, screen)

    def _pushed(self, state: UiState, group: str) -> tuple[OpenGroup, ...]:
        caller = None if self._contains(group, state.screen) else state.screen
        return (*state.stack, OpenGroup(group, caller))

    def _popped(self, stack: tuple[OpenGroup, ...], screen: UiScreen) -> tuple[OpenGroup, ...]:
        while stack and not self._contains(stack[-1].group, screen):
            stack = stack[:-1]
        return stack

    def _contains(self, group: str, screen: UiScreen) -> bool:
        return any(
            candidate.name == group and screen in candidate.members
            for candidate in self.chart.groups
        )

    def _carried_auto(self, state: UiState, screen: UiScreen) -> UiAutoMode | None:
        return state.auto if self._screen(screen).auto is not None else None

    def _screen(self, screen: UiScreen) -> ScreenChart:
        return self.chart.screens.get(screen, NO_SCREEN)


def _is_open(stack: tuple[OpenGroup, ...], group: str) -> bool:
    return any(open_group.group == group for open_group in stack)


def _centre(rect: RatioRect) -> RatioPoint:
    return ((rect.left + rect.right) / 2, (rect.top + rect.bottom) / 2)


def _gesture(kind: Gesture, rect: RatioRect) -> UiGesture:
    centre = _centre(rect)
    match kind:
        case Gesture.TAP:
            return UiTap(centre)
        case Gesture.LONG_PRESS:
            return UiSwipe(centre, centre, LONG_PRESS_SECONDS)
        case Gesture.SWIPE_X:
            width = rect.right - rect.left
            start = (rect.left + 0.8 * width, centre[1])
            end = (rect.left + 0.2 * width, centre[1])
            return UiSwipe(start, end, SWIPE_SECONDS)
        case Gesture.SWIPE_Y:
            height = rect.bottom - rect.top
            start = (centre[0], rect.top + 0.8 * height)
            end = (centre[0], rect.top + 0.2 * height)
            return UiSwipe(start, end, SWIPE_SECONDS)
