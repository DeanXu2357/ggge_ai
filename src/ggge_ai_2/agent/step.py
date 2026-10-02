from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ggge_ai_2.agent.clock import Instant
from ggge_ai_2.mapgeom.contract import BoardFact
from ggge_ai_2.uisim.contract import Operation, UiState


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
