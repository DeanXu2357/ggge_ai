from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from ggge_ai_2.interpreter.contract import Screen
from ggge_ai_2.interpreter.phase_cue import PHASE_SCREENS, phase
from ggge_ai_2.mapparser.border import Border, read_border
from ggge_ai_2.mapparser.contract import (
    CellReading,
    MapPhase,
    MapReading,
    Marker,
    ScreenPoint,
    ViewCell,
)
from ggge_ai_2.mapparser.hud import Rect, hud_rects
from ggge_ai_2.mapparser.lattice import Lattice, read_lattice
from ggge_ai_2.mapparser.markers import enemy_move_range, read_markers
from ggge_ai_2.mapparser.region import Region, read_region
from ggge_ai_2.mapparser.tap_mark import read_tap_mark
from ggge_ai_2.mapparser.topview import TopView, top_view
from ggge_ai_2.mapparser.unit_panel import ENEMY, SELECTED, read_panel
from ggge_ai_2.mapparser.units import read_units
from ggge_ai_2.stream.contract import Frame


# The map screens of the player phase. The battle prep screens show a damage preview,
# and the parser does not read the phases of the other factions.
MAP_SCREENS = frozenset(
    {
        Screen.PLAYER_PHASE_OVERVIEW,
        Screen.SELECT_ACTION_IN_BATTLE,
        Screen.SELECT_WEAPON_IN_BATTLE,
    }
)


@dataclass(frozen=True)
class OpenCvMapParser:
    def parse(self, frame: Frame, screen: Screen | None) -> MapReading | None:
        if screen not in MAP_SCREENS:
            return None
        read = _read(frame.image)
        if read is None:
            return None
        lattice, rects, view, border, region = read
        units, cells = read_units(frame.image, lattice, rects, view)
        markers = read_markers(frame.image, view, sorted(region.lattice_cells))
        enemy = next((unit for unit in units if unit.enemy_selected), None)
        if enemy is not None:
            # The user ruled that the move range leaves out the cells that units occupy,
            # also the cell of the selected enemy.
            occupied = {cell for cell, value in cells.items() if value is CellReading.OCCUPIED}
            for cell in enemy_move_range(view, region.lattice_cells) - occupied:
                markers[cell] = markers[cell] | {Marker.ENEMY_MOVE_RANGE}
        return MapReading(
            # Warning: the parser does not read the stage and the turn yet.
            stage=None,
            turn=None,
            phase=_phase(frame.image, screen),
            cells={region.to_view(cell): cells[cell] for cell in region.lattice_cells},
            borders=border.edges(),
            units=tuple(
                replace(
                    unit,
                    pos=region.to_view(unit.pos),
                    cropped=not all(region.holds(cell) for cell in _footprint(unit.pos, unit.size)),
                )
                for unit in units
            ),
            markers={region.to_view(cell): value for cell, value in markers.items()},
            panel=read_panel(frame.image, SELECTED),
            enemy_panel=read_panel(frame.image, ENEMY),
            tap_mark=read_tap_mark(frame.image, lattice, region),
        )

    def locate(self, frame: Frame, cell: ViewCell) -> ScreenPoint | None:
        read = _read(frame.image)
        if read is None:
            return None
        lattice, _, _, _, region = read
        target = region.to_lattice(cell)
        return lattice.center(target) if region.holds(target) else None


def _read(
    image: np.ndarray,
) -> tuple[Lattice, tuple[Rect, ...], TopView, Border, Region] | None:
    lattice = read_lattice(image)
    if lattice is None:
        return None
    rects = hud_rects(image)
    view = top_view(image, lattice, rects)
    border = read_border(view)
    return lattice, rects, view, border, read_region(lattice, rects, border)


def _phase(image: np.ndarray, screen: Screen | None) -> MapPhase | None:
    read = phase(image) if screen in PHASE_SCREENS else None
    return None if read is None else MapPhase(read.value)


def _footprint(pos: ViewCell, size: tuple[int, int]) -> list[ViewCell]:
    return [(pos[0] + dx, pos[1] + dy) for dx in range(size[0]) for dy in range(size[1])]
