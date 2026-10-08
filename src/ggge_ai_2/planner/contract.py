from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ggge_ai_2.actuator.contract import Gesture
from ggge_ai_2.mapgeom.contract import Alignment, KnownMap
from ggge_ai_2.stream.contract import Frame
from ggge_ai_2.uisim.contract import Operation, Outcome, UiState

Instant = float


class ActionStatus(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    GUARD_FAILED = "guard_failed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class Refused:
    reason: str


@dataclass(frozen=True)
class ActionResult:
    intent: object
    operation: str
    status: ActionStatus
    outcome: str | None = None
    refused: Refused | None = None


@dataclass(frozen=True)
class State:
    ui: UiState
    ui_lost: bool
    camera: Alignment | None
    known_map: KnownMap
    domain: object
    as_of: Instant | None
    last_action: ActionResult | None


@dataclass(frozen=True)
class Step:
    intent: object
    operation: Operation
    guard: Callable[[Frame], Gesture | Refused]
    verify: Callable[[Frame], Outcome | None]
    interrupt: Callable[[Frame], bool]
    frame_after: Instant | None = None


@dataclass(frozen=True)
class Wait:
    pass


class Finish(StrEnum):
    DONE = "done"
    HALTED = "halted"


class Planner[A](Protocol):
    def plan(self, state: State, agenda: A) -> tuple[Step | Wait | Finish, A]: ...
