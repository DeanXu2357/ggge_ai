from __future__ import annotations

from dataclasses import dataclass

from ggge_ai_2.mapparser.border import Border
from ggge_ai_2.mapparser.contract import ViewCell
from ggge_ai_2.mapparser.hud import Rect
from ggge_ai_2.mapparser.lattice import Lattice

# The HUD rectangles are a few pixels larger than the panels. An overlap thinner than
# this share of the cell is the margin of a rectangle, not a panel over the cell.
HUD_SLACK = 0.1


@dataclass(frozen=True)
class Region:
    lattice_cells: frozenset[ViewCell]
    origin: ViewCell

    def to_view(self, cell: ViewCell) -> ViewCell:
        return cell[0] - self.origin[0], cell[1] - self.origin[1]

    def to_lattice(self, cell: ViewCell) -> ViewCell:
        return cell[0] + self.origin[0], cell[1] + self.origin[1]

    def holds(self, lattice_cell: ViewCell) -> bool:
        return lattice_cell in self.lattice_cells


def read_region(lattice: Lattice, rects: tuple[Rect, ...], border: Border) -> Region:
    cells = frozenset(
        cell
        for cell in lattice.cells()
        if border.contains(cell)
        and _in_frame(lattice, cell)
        and not _under_hud(lattice, cell, rects)
    )
    if not cells:
        return Region(cells, (0, 0))
    return Region(cells, (min(column for column, _ in cells), min(row for _, row in cells)))


def _corners(lattice: Lattice, cell: ViewCell) -> list[tuple[float, float]]:
    column, row = cell
    return [lattice.project(column + dx, row + dy) for dx in (0, 1) for dy in (0, 1)]


def _in_frame(lattice: Lattice, cell: ViewCell) -> bool:
    return all(
        0 <= x <= lattice.width and 0 <= y <= lattice.height for x, y in _corners(lattice, cell)
    )


def _under_hud(lattice: Lattice, cell: ViewCell, rects: tuple[Rect, ...]) -> bool:
    corners = _corners(lattice, cell)
    left, right = min(x for x, _ in corners), max(x for x, _ in corners)
    top, bottom = min(y for _, y in corners), max(y for _, y in corners)
    inset_x, inset_y = (right - left) * HUD_SLACK, (bottom - top) * HUD_SLACK
    left, right, top, bottom = left + inset_x, right - inset_x, top + inset_y, bottom - inset_y
    return any(
        left < rect_right and rect_left < right and top < rect_bottom and rect_top < bottom
        for rect_left, rect_top, rect_right, rect_bottom in rects
    )
