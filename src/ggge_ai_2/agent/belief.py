from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol, Self

from ggge_ai_2.agent.evidence import Dispatched, GuardFailed, Sensed
from ggge_ai_2.mapgeom.contract import KnownMap, LocalBoard, MapGeometry, Projection
from ggge_ai_2.planner.contract import ActionResult, ActionStatus, Step
from ggge_ai_2.stream.contract import Displacement, StillWindow
from ggge_ai_2.uisim.contract import Outcome, UiSim, UiState


class DomainState(Protocol):
    def absorb(self, intent: object, outcome: Outcome | None) -> Self: ...

    def observe(self, board: LocalBoard) -> Self: ...

    def known_map(self) -> KnownMap: ...


class UiSource(StrEnum):
    ASSUMED = "assumed"
    SEEN = "seen"
    PREDICTED = "predicted"
    LOST = "lost"


@dataclass(frozen=True)
class UiBasis:
    source: UiSource
    frame_seq: int | None = None
    outcome: str | None = None


@dataclass(frozen=True)
class Belief:
    ui: UiState
    ui_basis: UiBasis
    camera: Projection | None
    drift: Displacement
    domain: DomainState
    as_of: StillWindow | None
    last_action: ActionResult | None = None

    def sensed(self, sensed: Sensed, uisim: UiSim, mapgeom: MapGeometry) -> Belief:
        ui, basis = self._read_ui(sensed, uisim)
        camera, domain = self.camera, self.domain
        if sensed.map is not None:
            board = mapgeom.fit(sensed.map, domain.known_map(), camera, self.drift)
            if board is not None:
                camera, domain = board.projection, domain.observe(board)
        return replace(
            self, ui=ui, ui_basis=basis, camera=camera, domain=domain, as_of=sensed.still
        )

    def dispatched(self, dispatched: Dispatched, uisim: UiSim) -> Belief:
        step, outcome = dispatched.step, dispatched.outcome
        domain = self.domain.absorb(step.intent, outcome)
        if outcome is None:
            result = ActionResult(step.intent, step.operation.name, ActionStatus.UNVERIFIED)
            return replace(self, domain=domain, last_action=result)
        result = ActionResult(
            step.intent, step.operation.name, ActionStatus.VERIFIED, outcome=outcome.name
        )
        return replace(
            self,
            ui=uisim.advance(self.ui, outcome),
            ui_basis=UiBasis(UiSource.PREDICTED, outcome=outcome.name),
            domain=domain,
            last_action=result,
        )

    def guard_failed(self, failed: GuardFailed) -> Belief:
        step = failed.step
        result = ActionResult(
            step.intent,
            step.operation.name,
            ActionStatus.GUARD_FAILED,
            failed_premise=failed.premise,
        )
        return replace(self, last_action=result)

    def band_blocked(self, step: Step) -> Belief:
        result = ActionResult(step.intent, step.operation.name, ActionStatus.BLOCKED)
        return replace(self, last_action=result)

    def _read_ui(self, sensed: Sensed, uisim: UiSim) -> tuple[UiState, UiBasis]:
        seen = UiBasis(UiSource.SEEN, frame_seq=sensed.frame_seq)
        if sensed.prediction_holds:
            return self.ui, seen
        if sensed.observed is not None:
            return uisim.sync(self.ui, sensed.observed), seen
        if self.ui_basis.source is UiSource.LOST:
            return self.ui, self.ui_basis
        return self.ui, UiBasis(UiSource.LOST, frame_seq=sensed.frame_seq)
