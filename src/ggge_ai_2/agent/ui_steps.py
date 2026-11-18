from __future__ import annotations

from collections import deque
from dataclasses import replace

from ggge_ai_2.actuator.contract import Gesture, Key, Rect, ScreenPoint, Swipe, Tap
from ggge_ai_2.agent.belief import Belief
from ggge_ai_2.agent.contract import Step
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
    expected = tuple(replace(belief, ui=uisim.advance(belief.ui, o)) for o in operation.outcomes)
    band = danger_rects(uisim, belief, screen)
    return Step(operation.name, gesture, band, operation.deadline, expected)


def danger_rects(uisim: UiSim, belief: Belief, screen: tuple[int, int]) -> tuple[Rect, ...]:
    width, height = screen
    return tuple(
        Rect(
            round(region.left * width),
            round(region.top * height),
            round(region.right * width),
            round(region.bottom * height),
        )
        for region in uisim.danger_band(belief.ui).regions
    )


def first_move(uisim: UiSim, state: UiState, goal: UiScreen) -> tuple[Operation, Outcome] | None:
    firsts: dict[UiState, tuple[Operation, Outcome] | None] = {state: None}
    frontier = deque([state])
    while frontier:
        current = frontier.popleft()
        if current.screen is goal:
            return firsts[current]
        for operation in uisim.successors(current):
            for outcome in operation.outcomes:
                then = uisim.advance(current, outcome)
                if then not in firsts:
                    firsts[then] = firsts[current] or (operation, outcome)
                    frontier.append(then)
    return None
