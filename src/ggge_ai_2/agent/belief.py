from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol, Self

from ggge_ai_2.mapgeom.contract import Alignment, KnownMap, LocalBoard, MapGeometry
from ggge_ai_2.stream.contract import StillWindow
from ggge_ai_2.uisim.contract import Observed, Outcome, UiSim, UiState


class DomainState(Protocol):
    def absorb(self, intent: object, outcome: Outcome | None) -> Self: ...


class UiSource(StrEnum):
    ASSUMED = "assumed"
    SEEN = "seen"
    LOST = "lost"


@dataclass(frozen=True)
class UiBasis:
    source: UiSource
    frame_seq: int | None = None


@dataclass(frozen=True)
class Sensed:
    still: StillWindow
    observed: Observed | None
    board: LocalBoard | None


@dataclass(frozen=True)
class Belief:
    ui: UiState
    ui_basis: UiBasis
    camera: Alignment | None
    known_map: KnownMap
    domain: DomainState
    as_of: StillWindow | None

    def update(self, sensed: Sensed, uisim: UiSim, mapgeom: MapGeometry) -> Belief:
        ui, ui_basis = self.ui, self.ui_basis
        if sensed.observed is not None:
            ui = uisim.sync(self.ui, sensed.observed)
            ui_basis = UiBasis(UiSource.SEEN, sensed.still.frame_seq)
        elif self.ui_basis.source is not UiSource.LOST:
            ui_basis = UiBasis(UiSource.LOST, sensed.still.frame_seq)

        camera, known_map = self.camera, self.known_map
        if sensed.board is not None:
            alignment = mapgeom.align(sensed.board, self.known_map, self.camera)
            if alignment is not None:
                camera = alignment
                known_map = mapgeom.merge(self.known_map, sensed.board, alignment)

        return replace(
            self, ui=ui, ui_basis=ui_basis, camera=camera, known_map=known_map, as_of=sensed.still
        )
