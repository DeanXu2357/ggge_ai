from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ggge_ai_2.verdict import Verdict
from ggge_ai_2.mapparser.contract import MapReading
from ggge_ai_2.screen import ScreenPoint

WorldCell = tuple[int, int]
ViewCell = tuple[int, int]


class CellContent(StrEnum):
    OCCUPIED = "occupied"
    EMPTY = "empty"
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class KnownMap:
    cells: Mapping[WorldCell, CellContent]


class Projection(Protocol):
    @property
    def frame_seq(self) -> int: ...

    @property
    def shift(self) -> WorldCell: ...

    def to_view(self, point: ScreenPoint) -> ViewCell | None: ...

    def to_screen(self, cell: WorldCell) -> ScreenPoint | None:
        """Return None when the cell is not in the tappable part of this frame."""
        ...

    def to_world(self, cell: ViewCell) -> WorldCell: ...


@dataclass(frozen=True)
class LocalBoard:
    projection: Projection
    cells: Mapping[WorldCell, CellContent]


@dataclass(frozen=True)
class CellAt:
    point: ScreenPoint
    cell: WorldCell

    def holds_on(self, board: LocalBoard) -> Verdict:
        view = board.projection.to_view(self.point)
        if view is None:
            return Verdict.UNREADABLE
        same = board.projection.to_world(view) == self.cell
        return Verdict.HOLDS if same else Verdict.DOES_NOT_HOLD


@dataclass(frozen=True)
class CellHolds:
    cell: WorldCell
    content: CellContent

    def holds_on(self, board: LocalBoard) -> Verdict:
        seen = board.cells.get(self.cell, CellContent.UNREADABLE)
        if seen is CellContent.UNREADABLE:
            return Verdict.UNREADABLE
        return Verdict.HOLDS if seen is self.content else Verdict.DOES_NOT_HOLD


BoardFact = CellAt | CellHolds


class MapGeometry(Protocol):
    def fit(
        self,
        reading: MapReading,
        known: KnownMap,
        prior: Projection | None,
        displacement: tuple[float, float],
    ) -> LocalBoard | None:
        """Return None when the frame has no readable grid."""
        ...
