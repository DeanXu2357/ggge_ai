from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from ggge_ai_2.uisim.contract import DangerBand, Observed, Outcome, UiState


@dataclass(frozen=True)
class FakeUiSim:
    bands: Mapping[str, DangerBand] = field(default_factory=dict)

    def successors(self, state: UiState):
        return ()

    def predecessors(self, state: UiState):
        return ()

    def advance(self, state: UiState, outcome: Outcome) -> UiState:
        return outcome.then

    def sync(self, state: UiState, observed: Observed) -> UiState:
        return UiState(observed.screen, observed.overlays, observed.map_mode)

    def danger_band(self, state: UiState) -> DangerBand:
        return self.bands[state.screen]
