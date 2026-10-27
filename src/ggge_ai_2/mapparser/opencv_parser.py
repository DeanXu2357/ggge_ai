from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from ggge_ai_2.mapparser.border import Border, read_border
from ggge_ai_2.mapparser.contract import MapReading, ScreenPoint, ViewCell
from ggge_ai_2.mapparser.hud import Rect, hud_rects
from ggge_ai_2.mapparser.lattice import Lattice, read_lattice
from ggge_ai_2.mapparser.markers import read_markers
from ggge_ai_2.mapparser.region import Region, read_region
from ggge_ai_2.mapparser.topview import TopView, top_view
from ggge_ai_2.mapparser.units import read_units
from ggge_ai_2.stream.contract import Frame


@dataclass(frozen=True)
class OpenCvMapParser:
    def parse(self, frame: Frame) -> MapReading | None:
        read = _read(frame.image)
        if read is None:
            return None
        lattice, rects, view, border, region = read
        units, cells = read_units(frame.image, lattice, rects, view)
        markers = read_markers(frame.image, view, sorted(region.lattice_cells))
        return MapReading(
            cells={region.to_view(cell): cells[cell] for cell in region.lattice_cells},
            borders=border.edges(),
            units=tuple(
                replace(unit, pos=region.to_view(unit.pos))
                for unit in units
                if all(region.holds(cell) for cell in _footprint(unit.pos, unit.size))
            ),
            markers={region.to_view(cell): value for cell, value in markers.items()},
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


def _footprint(pos: ViewCell, size: tuple[int, int]) -> list[ViewCell]:
    return [(pos[0] + dx, pos[1] + dy) for dx in range(size[0]) for dy in range(size[1])]
