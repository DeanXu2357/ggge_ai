from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, Self

from ggge_ai_2.actuator.contract import Gesture
from ggge_ai_2.interpreter.contract import Fact, Situation


@dataclass(frozen=True)
class UiState:
    screen: str
    overlays: frozenset[str] = frozenset()
    map_mode: str | None = None


@dataclass(frozen=True)
class Outcome:
    name: str
    fact: Fact
    then: UiState


@dataclass(frozen=True)
class Operation:
    name: str
    # Always include the screen and the overlays that the gesture assumes. The guard
    # checks only the facts that a step declares, so a missing domain fact can then
    # at worst tap the wrong place on the right screen.
    precondition: tuple[Fact, ...]
    gesture: Gesture
    outcomes: tuple[Outcome, ...]
    deadline: float
    cost: float


class UiSim(Protocol):
    # An instance must not change after it is made. The agent keeps an instance in its
    # belief and the planner reads the belief as a pure input; a change in place would
    # change the belief behind the planner and break the replay of a run.

    @property
    def state(self) -> UiState: ...

    def fact(self) -> Fact: ...

    def successors(self) -> Sequence[Operation]: ...

    def predecessors(self) -> Sequence[tuple[UiState, Operation]]: ...

    def advance(self, outcome: Outcome) -> Self: ...

    def sync(self, observed: Situation) -> Self: ...
