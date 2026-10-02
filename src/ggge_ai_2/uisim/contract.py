from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

RatioPoint = tuple[float, float]


@dataclass(frozen=True)
class RatioRect:
    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True)
class DangerBand:
    regions: tuple[RatioRect, ...] = ()


@dataclass(frozen=True)
class UiState:
    screen: str
    overlays: frozenset[str] = frozenset()
    map_mode: str | None = None


@dataclass(frozen=True)
class Observed:
    screen: str
    overlays: frozenset[str] = frozenset()
    map_mode: str | None = None


@dataclass(frozen=True)
class UiTap:
    point: RatioPoint


@dataclass(frozen=True)
class UiSwipe:
    start: RatioPoint
    end: RatioPoint
    duration: float


@dataclass(frozen=True)
class UiKey:
    code: str


UiGesture = UiTap | UiSwipe | UiKey


@dataclass(frozen=True)
class Outcome:
    name: str
    then: UiState


@dataclass(frozen=True)
class Operation:
    name: str
    precondition: UiState
    gesture: UiGesture
    outcomes: tuple[Outcome, ...]
    deadline: float
    cost: float


class UiSim(Protocol):
    def successors(self, state: UiState) -> Sequence[Operation]: ...

    def predecessors(self, state: UiState) -> Sequence[tuple[UiState, Operation]]: ...

    def advance(self, state: UiState, outcome: Outcome) -> UiState: ...

    def sync(self, state: UiState, observed: Observed) -> UiState: ...

    def danger_band(self, state: UiState) -> DangerBand: ...
