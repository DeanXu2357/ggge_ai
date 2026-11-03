from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

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
from ggge_ai_2.uisim.stages import ButtonDef, ScreenDef, Stages

LONG_PRESS_SECONDS = 1.0
SWIPE_SECONDS = 0.4
WAIT_SECONDS = 60.0
AUTO_SUFFIX = "__auto"
PASS_THROUGH_KINDS = frozenset({"animation", "loading"})
_SCREEN_VALUES = frozenset(screen.value for screen in UiScreen)
Target = tuple[UiScreen, str | None]
NEXT_AUTO_MODE = {
    UiAutoMode.FULL: UiAutoMode.SEMI,
    UiAutoMode.SEMI: UiAutoMode.MANUAL,
    UiAutoMode.MANUAL: UiAutoMode.FULL,
}


@dataclass(frozen=True)
class StageUiSim:
    stages: Stages

    def successors(self, state: UiState) -> Sequence[Operation]:
        screen = self.stages.screens.get(state.screen.value)
        if screen is None:
            return ()
        operations: list[Operation] = []
        for button in screen.buttons:
            operation = self._button_operation(state, button)
            if operation is not None:
                operations.append(operation)
        for button in screen.buttons:
            if _is_auto(button) and button.rect is not None and state.auto is not None:
                operations.append(self._auto_toggle(state, state.auto, button, button.rect))
        wait = self._wait_operation(state, screen)
        if wait is not None:
            operations.append(wait)
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
            stack = self._restack(state, observed.screen, None)
        return UiState(observed.screen, stack, observed.auto)

    def danger_band(self, state: UiState) -> DangerBand:
        screen = self.stages.screens.get(state.screen.value)
        if screen is None:
            return DangerBand()
        return DangerBand(
            tuple(
                button.rect
                for button in screen.buttons
                if button.forbidden and button.rect is not None
            )
        )

    def _button_operation(self, state: UiState, button: ButtonDef) -> Operation | None:
        if button.forbidden or button.rect is None or not button.to:
            return None
        targets = self._resolve_all(button.to)
        if not targets:
            return None
        caller = state.stack[-1].caller if state.stack else None
        if caller is not None and any(screen == caller for screen, _ in targets):
            targets = ((caller, None),)
        return Operation(
            name=button.name,
            precondition=state,
            gesture=_gesture(button.gesture, button.rect),
            outcomes=tuple(self._outcome(state, screen, group) for screen, group in targets),
            deadline=button.deadline,
            cost=1.0,
        )

    def _auto_toggle(
        self, state: UiState, mode: UiAutoMode, button: ButtonDef, rect: RatioRect
    ) -> Operation:
        then = NEXT_AUTO_MODE[mode]
        outcome = Outcome(f"auto_{then.value}", UiState(state.screen, state.stack, then))
        return Operation(button.name, state, UiTap(_centre(rect)), (outcome,), button.deadline, 1.0)

    def _wait_operation(self, state: UiState, screen: ScreenDef) -> Operation | None:
        targets = self._resolve_all(screen.game_to)
        if not targets:
            return None
        if all(target != state.screen for target, _ in targets):
            targets = (*targets, (state.screen, None))
        outcomes = tuple(self._outcome(state, target, group) for target, group in targets)
        return Operation(f"{state.screen.value}__wait", state, None, outcomes, WAIT_SECONDS, 1.0)

    def _outcome(self, state: UiState, target: UiScreen, group: str | None) -> Outcome:
        then = UiState(
            target, self._restack(state, target, group), self._carried_auto(state, target)
        )
        return Outcome(target.value, then)

    def _restack(
        self, state: UiState, target: UiScreen, group: str | None
    ) -> tuple[OpenGroup, ...]:
        stack = state.stack
        if target == state.screen or (stack and self._contains(stack[-1].group, target)):
            return stack
        opened = {open_group.group for open_group in stack}
        if group is not None:
            candidates = [group] if group not in opened else []
        else:
            candidates = [
                name
                for name, caller_group in self.stages.groups.items()
                if target.value in caller_group.entry and name not in opened
            ]
        if len(candidates) == 1:
            (name,) = candidates
            # A screen inside the group cannot be the screen that opened the group.
            caller = None if self._contains(name, state.screen) else state.screen
            return (*stack, OpenGroup(name, caller))
        while stack and not self._contains(stack[-1].group, target):
            stack = stack[:-1]
        return stack

    def _contains(self, group: str, screen: UiScreen) -> bool:
        caller_group = self.stages.groups[group]
        return screen.value in caller_group.entry or screen.value in caller_group.inside

    def _carried_auto(self, state: UiState, target: UiScreen) -> UiAutoMode | None:
        screen = self.stages.screens.get(target.value)
        if screen is None or not any(_is_auto(button) for button in screen.buttons):
            return None
        return state.auto

    def _resolve_all(self, names: Sequence[str]) -> tuple[Target, ...]:
        resolved: list[Target] = []
        visited: set[str] = set()
        for name in names:
            self._resolve(name, None, visited, resolved)
        return tuple(resolved)

    def _resolve(
        self, name: str, group: str | None, visited: set[str], resolved: list[Target]
    ) -> None:
        if name in visited:
            return
        visited.add(name)
        if "@" in name:
            group_name = name.split("@", 1)[0]
            caller_group = self.stages.groups.get(group_name)
            if caller_group is None:
                self._resolve(group_name, None, visited, resolved)
                return
            for entry in caller_group.entry:
                self._resolve(entry, group_name, visited, resolved)
            return
        screen = self.stages.screens.get(name)
        if screen is not None and screen.kind in PASS_THROUGH_KINDS:
            for button in screen.buttons:
                for target in button.to:
                    self._resolve(target, None, visited, resolved)
            for target in screen.game_to:
                self._resolve(target, None, visited, resolved)
            return
        if name in _SCREEN_VALUES and all(screen != name for screen, _ in resolved):
            resolved.append((UiScreen(name), group))


def _is_auto(button: ButtonDef) -> bool:
    return button.name.endswith(AUTO_SUFFIX)


def _centre(rect: RatioRect) -> RatioPoint:
    return ((rect.left + rect.right) / 2, (rect.top + rect.bottom) / 2)


def _gesture(kind: str | None, rect: RatioRect) -> UiGesture:
    centre = _centre(rect)
    if kind == "long_press":
        return UiSwipe(centre, centre, LONG_PRESS_SECONDS)
    if kind == "swipe_x":
        width = rect.right - rect.left
        start = (rect.left + 0.8 * width, centre[1])
        end = (rect.left + 0.2 * width, centre[1])
        return UiSwipe(start, end, SWIPE_SECONDS)
    if kind == "swipe_y":
        height = rect.bottom - rect.top
        start = (centre[0], rect.top + 0.8 * height)
        end = (centre[0], rect.top + 0.2 * height)
        return UiSwipe(start, end, SWIPE_SECONDS)
    if kind is None:
        return UiTap(centre)
    raise ValueError(f"unknown gesture: {kind}")
