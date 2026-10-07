from __future__ import annotations

from typing import Protocol

from ggge_ai_2.uisim.contract import Operation, UiState


class UiShiftPlan(Protocol):
    def next(self, state: UiState, goal: UiState) -> Operation | None:
        """Return None when no known path leads from the state to the goal."""
        ...

    def tap_map(self, state: UiState) -> Operation | None:
        """Return None when the state has no map to tap."""
        ...
