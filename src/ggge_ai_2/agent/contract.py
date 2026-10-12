from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from ggge_ai_2.actuator.contract import Gesture, Rect
from ggge_ai_2.agent.belief import Belief


@dataclass(frozen=True)
class Step:
    name: str
    gesture: Gesture
    band: tuple[Rect, ...]
    deadline: float
    expected: Belief


class Plan(Protocol):
    def still_valid(self, belief: Belief) -> bool: ...

    def next(self, belief: Belief) -> Step: ...


class Reflex(Protocol):
    def still_valid(self, belief: Belief) -> bool: ...

    def react(self, belief: Belief) -> Step | None: ...


class PlanController(Protocol):
    def goal_reached(self, belief: Belief) -> bool: ...

    def think(self, belief: Belief, history: Sequence[object]) -> Plan | None: ...

    def review(self, plan: Plan, belief: Belief) -> object: ...
