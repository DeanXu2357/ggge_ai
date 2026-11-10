from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

# A view cell is (column, row) in the coordinates of one view: (0, 0) is the top-left
# corner of the box around the cells that the view reads.
ViewCell = tuple[int, int]
# A map cell is (column, row) in the coordinates of one judgment: (0, 0) is the
# top-left corner of the consistent result. The origin moves when the result grows
# up or left, so a map cell is valid only in its own judgment.
MapCell = tuple[int, int]


class ViewPhase(StrEnum):
    PLAYER = "player"
    NON_PLAYER = "non_player"


class CellSeen(StrEnum):
    OCCUPIED = "occupied"
    EMPTY = "empty"
    UNREADABLE = "unreadable"


class Side(StrEnum):
    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True)
class ViewUnit:
    pos: ViewCell
    size: tuple[int, int]
    controllable: bool | None
    selected: bool


@dataclass(frozen=True)
class View:
    stage: str | None
    turn: int | None
    phase: ViewPhase | None
    cells: Mapping[ViewCell, CellSeen]
    borders: frozenset[Side]
    units: tuple[ViewUnit, ...]


class CellContent(StrEnum):
    OCCUPIED = "occupied"
    EMPTY = "empty"


@dataclass(frozen=True)
class Axis:
    length: int
    start_closed: bool
    end_closed: bool

    def size(self) -> int | None:
        """Return the size of the whole map on this axis, or None while an end is open."""
        return self.length if self.start_closed and self.end_closed else None


@dataclass(frozen=True)
class MapUnit:
    # Warning: the id is valid only in its own judgment. Do not compare ids between
    # two judgments.
    id: int
    pos: MapCell
    size: tuple[int, int]


@dataclass(frozen=True)
class MapJudgment:
    stage: str | None
    turn: int | None
    phase: ViewPhase | None
    columns: Axis
    rows: Axis
    cells: Mapping[MapCell, CellContent]
    uncertain: frozenset[MapCell]
    units: tuple[MapUnit, ...]
    current: frozenset[MapCell] | None


class MapGeometry(Protocol):
    def judge(self, views: Sequence[View]) -> MapJudgment | None:
        """Join the views into one map and return what is above the threshold.

        'views' is in time order; the last view is the current frame.
        Return None when the views give no consistent result above the threshold.
        'cells' and 'units' hold only content above the threshold. Every other cell
        inside the axes is in 'uncertain'. 'current' is the range of the last view,
        or None when the last view has no place above the threshold.
        """
        ...
