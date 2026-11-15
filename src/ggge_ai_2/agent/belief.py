from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol, Self

from ggge_ai_2.interpreter.contract import Phase
from ggge_ai_2.mapparser.contract import MapReading
from ggge_ai_2.stream.contract import StillWindow
from ggge_ai_2.uisim.contract import Observed, Outcome, UiSim, UiState


class DomainState(Protocol):
    def absorb(self, intent: object, outcome: Outcome | None) -> Self: ...


class ScreenLock(StrEnum):
    ICON = "icon"
    DIM = "dim"


class Passing(StrEnum):
    WAIT = "wait"
    TAP_TO_CONTINUE = "tap_to_continue"


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
    reading: MapReading | None
    screen_lock: ScreenLock | None = None
    passing: Passing | None = None
    phase: Phase | None = None
    turn: int | None = None


@dataclass(frozen=True)
class Belief:
    ui: UiState
    ui_basis: UiBasis
    domain: DomainState
    as_of: StillWindow | None
    screen_lock: ScreenLock | None = None
    passing: Passing | None = None

    def update(self, sensed: Sensed, uisim: UiSim) -> Belief:
        if sensed.screen_lock is not None:
            return replace(self, screen_lock=sensed.screen_lock, passing=None, as_of=sensed.still)
        if sensed.passing is not None:
            return replace(self, passing=sensed.passing, as_of=sensed.still)

        ui, ui_basis = self.ui, self.ui_basis
        if sensed.observed is not None:
            ui = uisim.sync(self.ui, sensed.observed)
            ui_basis = UiBasis(UiSource.SEEN, sensed.still.frame_seq)
        elif self.ui_basis.source is not UiSource.LOST:
            ui_basis = UiBasis(UiSource.LOST, sensed.still.frame_seq)

        return replace(
            self,
            ui=ui,
            ui_basis=ui_basis,
            as_of=sensed.still,
            screen_lock=None,
            passing=None,
        )
