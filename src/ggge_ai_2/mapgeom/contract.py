from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

ScreenPoint = tuple[int, int]
WorldCell = tuple[int, int]
ViewCell = tuple[int, int]


class CellContent(StrEnum):
    OCCUPIED = "occupied"
    EMPTY = "empty"
    UNREADABLE = "unreadable"


class BoardEdge(StrEnum):
    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True)
class LocalBoard:
    cells: Mapping[ViewCell, CellContent]
    borders: frozenset[BoardEdge]


@dataclass(frozen=True)
class KnownMap:
    cells: Mapping[WorldCell, CellContent]


@dataclass(frozen=True)
class Alignment:
    shift: WorldCell

    def to_view(self, cell: WorldCell) -> ViewCell:
        return (cell[0] - self.shift[0], cell[1] - self.shift[1])


@dataclass(frozen=True)
class CellAt:
    point: ScreenPoint
    cell: WorldCell


@dataclass(frozen=True)
class CellHolds:
    cell: WorldCell
    content: CellContent

    def holds_on(self, board: LocalBoard, alignment: Alignment) -> bool:
        return board.cells.get(alignment.to_view(self.cell)) is self.content


BoardFact = CellAt | CellHolds


class MapGeometry(Protocol):
    def align(
        self, board: LocalBoard, known: KnownMap, prior: Alignment | None
    ) -> Alignment | None:
        """Return None when the board has no place on the known map."""
        ...

    def merge(self, known: KnownMap, board: LocalBoard, alignment: Alignment) -> KnownMap: ...
