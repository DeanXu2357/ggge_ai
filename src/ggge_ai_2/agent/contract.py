from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from ggge_ai_2.actuator.contract import Gesture, Rect
from ggge_ai_2.agent.belief import Belief


@dataclass(frozen=True)
class Step:
    name: str
    gesture: Gesture | None
    band: tuple[Rect, ...]
    deadline: float
    expected: tuple[Belief, ...]


class Plan(Protocol):
    """`still_valid` is the precondition: the plan can give a step for this belief.
    `still_valid` has no side effects.

    The loop calls `next` at most once per cycle. The loop calls `next` only after
    `still_valid` returned True. `next` can change the state of the plan.

    A step with `expected=()` makes no prediction.
    """

    def still_valid(self, belief: Belief) -> bool: ...

    def next(self, belief: Belief) -> Step: ...


class PlanController[P: Plan](Protocol):
    def goal_reached(self, belief: Belief) -> bool: ...

    def think(self, belief: Belief, history: Sequence[object]) -> P | None: ...

    def review(self, plan: P, belief: Belief) -> object: ...
