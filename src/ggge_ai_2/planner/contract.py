from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ggge_ai_2.mapgeom.contract import Alignment, BoardFact, KnownMap
from ggge_ai_2.uisim.contract import Operation, UiState

Instant = float


class ActionStatus(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    GUARD_FAILED = "guard_failed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ActionResult:
    intent: object
    operation: str
    status: ActionStatus
    outcome: str | None = None
    failed_premise: UiState | BoardFact | None = None


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
class Premise:
    ui: UiState
    domain: tuple[BoardFact, ...]


@dataclass(frozen=True)
class Step:
    intent: object
    operation: Operation
    domain_premise: tuple[BoardFact, ...]
    based_on: Instant

    @property
    def premise(self) -> Premise:
        return Premise(ui=self.operation.precondition, domain=self.domain_premise)


@dataclass(frozen=True)
class Wait:
    pass


class Finish(StrEnum):
    DONE = "done"
    HALTED = "halted"


class Planner[A](Protocol):
    def plan(self, state: State, agenda: A) -> tuple[Step | Wait | Finish, A]: ...
