from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ggge_ai_2.stream.contract import Frame

ScreenPoint = tuple[int, int]
# A cell is (column, row). Column 0 is the leftmost column in the frame. Row 0 is the top row.
ViewCell = tuple[int, int]


class CellReading(StrEnum):
    OCCUPIED = "occupied"
    EMPTY = "empty"
    UNREADABLE = "unreadable"


class Edge(StrEnum):
    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True)
class MapReading:
    cells: Mapping[ViewCell, CellReading]
    borders: frozenset[Edge]


class MapParser(Protocol):
    def parse(self, frame: Frame) -> MapReading | None:
        """Return None when the frame has no readable grid."""
        ...

    def locate(self, frame: Frame, cell: ViewCell) -> ScreenPoint | None:
        """Return None when the cell is not in the tappable part of this frame."""
        ...
