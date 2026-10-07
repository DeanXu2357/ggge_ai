from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ggge_ai_2.agent.clock import Instant
from ggge_ai_2.mapparser.contract import CellReading, MapReading, ViewCell
from ggge_ai_2.stream.contract import StillWindow
from ggge_ai_2.uisim.contract import DangerBand, Observed, Operation, Outcome, UiState


@dataclass(frozen=True)
class Sensed:
    still: StillWindow
    observed: Observed | None
    map: MapReading | None


@dataclass(frozen=True)
class CellReads:
    cell: ViewCell
    reading: CellReading


@dataclass(frozen=True)
class Step:
    operation: Operation
    map_premise: tuple[CellReads, ...]
    band: DangerBand
    # Tap this cell, not the gesture point. The loop finds the point on the guard frame.
    target: ViewCell | None = None
    frame_after: Instant | None = None


@dataclass(frozen=True)
class Wait:
    pass


class Finish(StrEnum):
    DONE = "done"
    HALTED = "halted"


class ActionStatus(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    GUARD_FAILED = "guard_failed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ActionResult:
    step: Step
    status: ActionStatus
    outcome: Outcome | None = None
    failed_premise: UiState | CellReads | None = None


class AgentPlanner[S](Protocol):
    def plan(
        self, state: S, sensed: Sensed, acted: ActionResult | None
    ) -> tuple[Step | Wait | Finish, S]: ...
