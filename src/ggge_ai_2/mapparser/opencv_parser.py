from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from ggge_ai_2.mapparser.border import Border, read_border
from ggge_ai_2.mapparser.contract import (
    CellPlace,
    CellReading,
    MapReading,
    MapScope,
    Marker,
    ViewCell,
)
from ggge_ai_2.mapparser.lattice import Lattice, read_lattice
from ggge_ai_2.mapparser.markers import enemy_move_range, read_markers
from ggge_ai_2.mapparser.region import Region, read_region
from ggge_ai_2.mapparser.tap_mark import read_tap_mark
from ggge_ai_2.mapparser.topview import TopView, top_view
from ggge_ai_2.mapparser.unit_panel import ENEMY, SELECTED, read_panel
from ggge_ai_2.mapparser.units import read_units
from ggge_ai_2.stream.contract import Frame


@dataclass(frozen=True)
class OpenCvMapParser:
    def parse(self, frame: Frame, scope: MapScope) -> MapReading | None:
        read = _read(frame.image, scope)
        if read is None:
            return None
        lattice, view, border, region = read
        units, cells = read_units(frame.image, lattice, scope.occluded, view, scope.chevrons)
        markers = read_markers(frame.image, view, sorted(region.lattice_cells))
        enemy = next((unit for unit in units if unit.enemy_selected), None)
        if enemy is not None:
            # The user ruled that the move range leaves out the cells that units occupy,
            # also the cell of the selected enemy.
            occupied = {cell for cell, value in cells.items() if value is CellReading.OCCUPIED}
            for cell in enemy_move_range(view, region.lattice_cells) - occupied:
                markers[cell] = markers[cell] | {Marker.ENEMY_MOVE_RANGE}
        return MapReading(
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
            places={region.to_view(cell): _place(lattice, cell) for cell in region.lattice_cells},
            panel=read_panel(frame.image, SELECTED),
            enemy_panel=read_panel(frame.image, ENEMY),
            tap_mark=read_tap_mark(
                frame.image,
                lattice,
                region,
                view,
                frozenset(cell for cell, value in cells.items() if value is CellReading.EMPTY),
            ),
        )


def _read(image: np.ndarray, scope: MapScope) -> tuple[Lattice, TopView, Border, Region] | None:
    lattice = read_lattice(image)
    if lattice is None:
        return None
    view = top_view(image, lattice, scope.occluded)
    border = read_border(view)
    return lattice, view, border, read_region(lattice, scope.occluded, border)


def _place(lattice: Lattice, cell: ViewCell) -> CellPlace:
    column, row = cell
    corners = [
        lattice.project(column + dx, row + dy) for dx, dy in ((0, 0), (1, 0), (1, 1), (0, 1))
    ]
    top_left, top_right, bottom_right, bottom_left = ((round(x), round(y)) for x, y in corners)
    return CellPlace(lattice.center(cell), (top_left, top_right, bottom_right, bottom_left))


def _footprint(pos: ViewCell, size: tuple[int, int]) -> list[ViewCell]:
    return [(pos[0] + dx, pos[1] + dy) for dx in range(size[0]) for dy in range(size[1])]
