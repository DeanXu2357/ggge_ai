from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ggge_ai_2.uisim.contract import (
    DangerBand,
    Observed,
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

    def predecessors(self, state: UiState) -> Sequence[tuple[UiState, Operation]]:
        found: list[tuple[UiState, Operation]] = []
        for screen in UiScreen:
            if screen.value not in self.stages.screens:
                continue
            source = UiState(screen)
            for operation in self.successors(source):
                if any(outcome.then.screen == state.screen for outcome in operation.outcomes):
                    found.append((source, operation))
        return found

    def advance(self, state: UiState, outcome: Outcome) -> UiState:
        return outcome.then

    def sync(self, state: UiState, observed: Observed) -> UiState:
        observed_groups = self._groups_of(observed.screen)
        if not observed_groups:
            caller = None
        elif observed_groups & self._groups_of(state.screen):
            caller = state.caller
        else:
            caller = state.screen
        return UiState(observed.screen, caller, observed.auto)

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
        caller = state.caller
        if caller is not None and caller in targets and self._groups_of(state.screen):
            outcomes = (self._outcome(state, caller, None),)
        else:
            outcomes = tuple(
                self._outcome(state, target, self._caller(state, target)) for target in targets
            )
        return Operation(
            name=button.name,
            precondition=state,
            gesture=_gesture(button.gesture, button.rect),
            outcomes=outcomes,
            deadline=button.deadline,
            cost=1.0,
        )

    def _auto_toggle(
        self, state: UiState, mode: UiAutoMode, button: ButtonDef, rect: RatioRect
    ) -> Operation:
        then = NEXT_AUTO_MODE[mode]
        outcome = Outcome(f"auto_{then.value}", UiState(state.screen, state.caller, then))
        return Operation(button.name, state, UiTap(_centre(rect)), (outcome,), button.deadline, 1.0)

    def _wait_operation(self, state: UiState, screen: ScreenDef) -> Operation | None:
        targets = self._resolve_all(screen.game_to)
        if not targets:
            return None
        stay = (state.screen,) if state.screen not in targets else ()
        outcomes = tuple(self._outcome(state, target, state.caller) for target in targets + stay)
        return Operation(f"{state.screen.value}__wait", state, None, outcomes, WAIT_SECONDS, 1.0)

    def _outcome(self, state: UiState, target: UiScreen, caller: UiScreen | None) -> Outcome:
        return Outcome(target.value, UiState(target, caller, self._carried_auto(state, target)))

    def _caller(self, state: UiState, target: UiScreen) -> UiScreen | None:
        source_groups = self._groups_of(state.screen)
        if source_groups & self._groups_of(target):
            return state.caller
        if any(
            target.value in group.entry
            for name, group in self.stages.groups.items()
            if name not in source_groups
        ):
            return state.screen
        return None

    def _groups_of(self, screen: UiScreen) -> frozenset[str]:
        return frozenset(
            name
            for name, group in self.stages.groups.items()
            if screen.value in group.entry or screen.value in group.inside
        )

    def _carried_auto(self, state: UiState, target: UiScreen) -> UiAutoMode | None:
        screen = self.stages.screens.get(target.value)
        if screen is None or not any(_is_auto(button) for button in screen.buttons):
            return None
        return state.auto

    def _resolve_all(self, names: Sequence[str]) -> tuple[UiScreen, ...]:
        resolved: list[UiScreen] = []
        visited: set[str] = set()
        for name in names:
            self._resolve(name, visited, resolved)
        return tuple(resolved)

    def _resolve(self, name: str, visited: set[str], resolved: list[UiScreen]) -> None:
        if name in visited:
            return
        visited.add(name)
        if "@" in name:
            group_name = name.split("@", 1)[0]
            group = self.stages.groups.get(group_name)
            for entry in group.entry if group is not None else (group_name,):
                self._resolve(entry, visited, resolved)
            return
        screen = self.stages.screens.get(name)
        if screen is not None and screen.kind in PASS_THROUGH_KINDS:
            for button in screen.buttons:
                for target in button.to:
                    self._resolve(target, visited, resolved)
            for target in screen.game_to:
                self._resolve(target, visited, resolved)
            return
        if name in _SCREEN_VALUES and UiScreen(name) not in resolved:
            resolved.append(UiScreen(name))


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
