from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


from ggge_ai_2.stream.contract import Frame

ScreenPoint = tuple[int, int]
# A cell is (column, row) of a map cell that the frame shows whole and the HUD does not
# cover. (0, 0) is the top-left corner of the box around these cells.
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


class Marker(StrEnum):
    MOVE_RANGE = "move_range"
    THREAT = "threat"
    WEAPON_RANGE = "weapon_range"


@dataclass(frozen=True)
class UnitReading:
    # The anchor is the cell of the footprint with the least column and the least row,
    # as 'pos' in the battle engine. A unit cut by the frame edge can have its anchor
    # outside the frame.
    pos: ViewCell
    size: tuple[int, int]
    # None when the frame does not show the place of the chevron above the unit.
    controllable: bool | None


@dataclass(frozen=True)
class MapReading:
    cells: Mapping[ViewCell, CellReading]
    borders: frozenset[Edge]
    units: tuple[UnitReading, ...]
    markers: Mapping[ViewCell, frozenset[Marker]]


class MapParser(Protocol):
    def parse(self, frame: Frame) -> MapReading | None:
        """Return None when the frame has no readable grid."""
        ...

    def locate(self, frame: Frame, cell: ViewCell) -> ScreenPoint | None:
        """Return None when the cell is not in the tappable part of this frame."""
        ...
