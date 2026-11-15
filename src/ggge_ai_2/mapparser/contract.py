from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import numpy as np

from ggge_ai_2.stream.contract import Frame

# A rectangle is (left, top, right, bottom) in frame pixels. Right and bottom are excluded.
Rect = tuple[int, int, int, int]
ScreenPoint = tuple[int, int]
# A cell is (column, row) of a map cell that the frame shows whole and that no occluded
# rectangle covers. (0, 0) is the top-left corner of the box around these cells.
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
    ENEMY_MOVE_RANGE = "enemy_move_range"


@dataclass(frozen=True)
class UnitReading:
    # The anchor is the cell of the footprint with the least column and the least row,
    # as 'pos' in the battle engine. A unit cut by the frame edge can have its anchor
    # outside the frame.
    pos: ViewCell
    size: tuple[int, int]
    # None when the scope does not ask for the chevrons, or the frame does not show the
    # place of the chevron above the unit.
    controllable: bool | None
    selected: bool
    enemy_selected: bool
    # True when a cell of the footprint is not a readable cell: an occluded rectangle or the
    # frame edge cuts the unit. Its readable cells are occupied, but the frame does not show the
    # whole unit.
    cropped: bool = False


class PanelIcon(StrEnum):
    RED = "red"
    BLUE = "blue"
    YELLOW = "yellow"
    GRAY = "gray"


class PilotState(StrEnum):
    NORMAL = "一般"
    STRONG = "強勢"
    SUPER_STRONG = "超強勢"
    SUPER_STRIKE = "超一擊"


# The white mask of a name, cut to the box around its white pixels. Two crops of one name
# differ in some pixels, so compare two templates by their similarity. Equality is identity.
@dataclass(frozen=True, eq=False)
class NameTemplate:
    mask: np.ndarray


@dataclass(frozen=True)
class MechPanel:
    icon: PanelIcon | None
    # The name as the panel shows it, cut with '…' when it is long.
    name: NameTemplate | None
    hp: int | None
    en: int | None
    hp_change: int | None
    en_change: int | None
    overlay: str | None


@dataclass(frozen=True)
class PilotPanel:
    icon: PanelIcon | None
    name: NameTemplate | None
    mp: int | None
    mp_max: int | None
    state: PilotState | None
    damage: int | None
    chance_step: int | None


@dataclass(frozen=True)
class UnitPanel:
    mech: MechPanel
    pilot: PilotPanel


class Terrain(StrEnum):
    AIR = "air"
    GROUND = "ground"
    SPACE = "space"
    SURFACE = "surface"
    UNDERWATER = "underwater"


# The mark that a tap on an empty cell leaves: a fill on the cell and a terrain box above it.
@dataclass(frozen=True)
class TapMarkReading:
    cell: ViewCell
    # The icons of the terrain box from left to right. None when the box is outside the frame.
    terrain: tuple[Terrain, ...] | None


@dataclass(frozen=True)
class CellPlace:
    center: ScreenPoint
    # Top left, top right, bottom right, bottom left. The camera tilts down, so a cell is a
    # trapezoid on the screen.
    corners: tuple[ScreenPoint, ScreenPoint, ScreenPoint, ScreenPoint]


@dataclass(frozen=True)
class MapReading:
    cells: Mapping[ViewCell, CellReading]
    borders: frozenset[Edge]
    units: tuple[UnitReading, ...]
    markers: Mapping[ViewCell, frozenset[Marker]]
    # The place on the screen of each readable cell in this frame.
    places: Mapping[ViewCell, CellPlace]
    # The panel of the selected unit at the top right.
    panel: UnitPanel | None
    # The panel of the selected enemy at the top left.
    enemy_panel: UnitPanel | None
    # None also when the marked cell is not a readable cell.
    tap_mark: TapMarkReading | None = None


@dataclass(frozen=True)
class MapScope:
    occluded: tuple[Rect, ...]
    chevrons: bool


class MapParser(Protocol):
    def parse(self, frame: Frame, scope: MapScope) -> MapReading | None:
        """Return None when the frame has no readable grid."""
        ...
