from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from ggge_ai_2.actuator.contract import Gesture, Rect
from ggge_ai_2.agent.belief import Belief
from ggge_ai_2.mapparser.contract import MapReading, ViewCell
from ggge_ai_2.stream.contract import StillWindow


@dataclass(frozen=True)
class MapReadingRecord:
    still: StillWindow
    reading: MapReading


@dataclass(frozen=True)
class Evidence:
    map_readings: Sequence[MapReadingRecord]


# The loop converts the cell to a screen point on the frame of the cycle that sends it.
@dataclass(frozen=True)
class MapTap:
    cell: ViewCell


@dataclass(frozen=True)
class Step:
    name: str
    gesture: Gesture | MapTap | None
    band: tuple[Rect, ...]
    deadline: float
    expected: tuple[Belief, ...]


class Plan(Protocol):
    """`still_valid` is the precondition: the plan can give a step for this belief and
    this evidence. `still_valid` has no side effects.

    The loop calls `next` at most once per cycle. The loop calls `next` only after
    `still_valid` returned True. `next` can change the state of the plan.

    A step with `expected=()` makes no prediction.
    """

    def still_valid(self, belief: Belief, evidence: Evidence) -> bool: ...

    def next(self, belief: Belief, evidence: Evidence) -> Step: ...


class PlanController[P: Plan](Protocol):
    def goal_reached(self, belief: Belief) -> bool: ...

    def think(self, belief: Belief, evidence: Evidence, history: Sequence[object]) -> P | None: ...

    def review(self, plan: P, belief: Belief) -> object: ...
