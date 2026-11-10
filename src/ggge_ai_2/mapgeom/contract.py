from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import numpy as np

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


class Faction(StrEnum):
    ALLY = "ally"
    ENEMY = "enemy"


class UnitRole(StrEnum):
    ATTACK = "attack"
    ENDURANCE = "endurance"
    SUPPORT = "support"
    # Only the NPC units of the system have this role.
    NO_ROLE = "no_role"


class PilotState(StrEnum):
    NORMAL = "一般"
    STRONG = "強勢"
    SUPER_STRONG = "超強勢"
    SUPER_STRIKE = "超一擊"


# Two crops of one name differ in some pixels, so compare two masks by their
# similarity. Equality is identity.
@dataclass(frozen=True, eq=False)
class NameMask:
    mask: np.ndarray


@dataclass(frozen=True)
class UnitBrief:
    mech_role: UnitRole | None
    mech_name: NameMask | None
    hp: int | None
    en: int | None
    pilot_role: UnitRole | None
    pilot_name: NameMask | None
    mp: int | None
    mp_max: int | None
    state: PilotState | None


@dataclass(frozen=True)
class ViewUnit:
    pos: ViewCell
    size: tuple[int, int]
    controllable: bool | None
    faction: Faction | None
    brief: UnitBrief | None


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


# Warning: a unit id is valid only in its own judgment. Do not compare ids between
# two judgments.
UnitId = int


@dataclass(frozen=True)
class MapUnit:
    controllable: bool | None
    faction: Faction | None
    brief: UnitBrief | None


@dataclass(frozen=True)
class MapJudgment:
    stage: str | None
    turn: int | None
    phase: ViewPhase | None
    columns: Axis
    rows: Axis
    cells: Mapping[MapCell, CellContent]
    uncertain: frozenset[MapCell]
    unit_cells: Mapping[MapCell, UnitId]
    units: Mapping[UnitId, MapUnit]
    current: frozenset[MapCell] | None


class MapGeometry(Protocol):
    def judge(self, views: Sequence[View]) -> MapJudgment | None:
        """Join the views into one map and return what is above the threshold.

        'views' is in time order; the last view is the current frame.
        Return None when the views give no consistent result above the threshold.
        'cells', 'unit_cells' and 'units' hold only content above the threshold. Every other cell
        inside the axes is in 'uncertain'. 'current' is the range of the last view,
        or None when the last view has no place above the threshold.
        """
        ...
