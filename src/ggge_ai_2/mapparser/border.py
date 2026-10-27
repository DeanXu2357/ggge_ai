from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ggge_ai_2.mapparser.contract import Edge, ViewCell
from ggge_ai_2.mapparser.topview import CELL, TopView

EDGE_SPAN = (0.15, 0.85)
# In top-view pixels: a grid line is within LINE_SLACK of its lattice place, and the
# map art at LINE_SIDE on each side of it is darker.
LINE_SLACK = 3
LINE_SIDE = (10, 16)
LINE_CONTRAST = 12.0
EDGE_VISIBLE = 0.5
EDGE_SHOWN = 0.5
# Past a border, at least this many edges must show, and few of them with a grid line.
OFF_MAP_EDGES = 3
OFF_MAP_SHOWN = 0.2


@dataclass(frozen=True)
class Border:
    # Each bound is the first or the last map column or row.
    # A bound is None when the frame does not show that edge of the map.
    left: int | None
    right: int | None
    top: int | None
    bottom: int | None

    def edges(self) -> frozenset[Edge]:
        bounds = (
            (Edge.LEFT, self.left),
            (Edge.RIGHT, self.right),
            (Edge.TOP, self.top),
            (Edge.BOTTOM, self.bottom),
        )
        return frozenset(edge for edge, bound in bounds if bound is not None)

    def contains(self, cell: ViewCell) -> bool:
        column, row = cell
        return (
            (self.left is None or column >= self.left)
            and (self.right is None or column <= self.right)
            and (self.top is None or row >= self.top)
            and (self.bottom is None or row <= self.bottom)
        )


def read_border(view: TopView) -> Border:
    """Return the map bounds that the frame shows.

    The game draws the grid only on the map, and the map is a rectangle of cells.
    So the bounds are the rectangle that holds the most edges with a grid line
    and the fewest visible edges without one.
    """
    verticals = _edge_values(view, vertical=True)
    horizontals = _edge_values(view, vertical=False)
    columns = horizontals.shape[1]
    rows = verticals.shape[1]
    left, right, top, bottom = _best_rectangle(verticals, horizontals)
    # Past one border, only the rows or the columns of the map count. A corner past
    # two borders shows no grid lines, also when the first border is wrong.
    rows_in = slice(top, bottom + 1)
    columns_in = slice(left, right + 1)
    beyond_left = (verticals[:left, rows_in], horizontals[top : bottom + 2, :left])
    beyond_right = (verticals[right + 2 :, rows_in], horizontals[top : bottom + 2, right + 1 :])
    beyond_top = (horizontals[:top, columns_in], verticals[left : right + 2, :top])
    beyond_bottom = (
        horizontals[bottom + 2 :, columns_in],
        verticals[left : right + 2, bottom + 1 :],
    )
    return Border(
        left=_bound(left, left == 0, beyond_left, view.first_column),
        right=_bound(right, right == columns - 1, beyond_right, view.first_column),
        top=_bound(top, top == 0, beyond_top, view.first_row),
        bottom=_bound(bottom, bottom == rows - 1, beyond_bottom, view.first_row),
    )


def _bound(index: int, at_limit: bool, beyond: tuple[np.ndarray, ...], first: int) -> int | None:
    values = np.concatenate([part.ravel() for part in beyond])
    shown = values[values != 0]
    if at_limit or len(shown) < OFF_MAP_EDGES or (shown > 0).mean() > OFF_MAP_SHOWN:
        return None
    return first + index


def _edge_values(view: TopView, vertical: bool) -> np.ndarray:
    """Return the grid-line value of each cell edge on the lines of one direction.

    For the vertical edges, value[line, row] is the edge on the column line
    'view.first_column + line'. For the horizontal edges, value[line, column] is
    the edge on the row line 'view.first_row + line'. A value is +1 when the edge
    shows a grid line, -1 when the edge is visible and shows none, and 0 when the
    frame or the HUD hides the edge.
    """
    white = view.white if vertical else view.white.T
    visible = view.visible if vertical else view.visible.T
    length, across = white.shape
    lines = across // CELL + 1
    cells = length // CELL
    low, high = (round(bound * CELL) for bound in EDGE_SPAN)
    near, far = LINE_SIDE
    padded = np.pad(white, ((0, 0), (far, far)), mode="edge")
    shown = np.pad(visible, ((0, 0), (far, far)), constant_values=False)
    values = np.zeros((lines, cells), np.int32)
    for line in range(lines):
        center = line * CELL + far
        on = padded[:, center - LINE_SLACK : center + LINE_SLACK + 1].max(axis=1)
        before = padded[:, center - far : center - near + 1].mean(axis=1)
        after = padded[:, center + near : center + far + 1].mean(axis=1)
        hit = np.minimum(on - before, on - after) >= LINE_CONTRAST
        seen = shown[:, center - far : center + far + 1].all(axis=1)
        for cell in range(cells):
            span = slice(cell * CELL + low, cell * CELL + high)
            count = int(seen[span].sum())
            if count < EDGE_VISIBLE * (high - low):
                continue
            share = float(hit[span][seen[span]].mean())
            values[line, cell] = 1 if share >= EDGE_SHOWN else -1
    return values


def _best_rectangle(verticals: np.ndarray, horizontals: np.ndarray) -> tuple[int, int, int, int]:
    """Return (left, right, top, bottom) cell indices of the rectangle with the best sum.

    The rectangle of columns left..right and rows top..bottom holds the vertical
    edges on the column lines left..right + 1 and the horizontal edges on the row
    lines top..bottom + 1. Among equal sums, the larger rectangle wins.
    """
    rows = verticals.shape[1]
    columns = horizontals.shape[1]
    # vertical[r][k] = sum of verticals[line k, rows < r]
    vertical = np.zeros((rows + 1, verticals.shape[0] + 1), np.int64)
    vertical[1:, 1:] = np.cumsum(np.cumsum(verticals.T, axis=0), axis=1)
    horizontal = np.zeros((horizontals.shape[0] + 1, columns + 1), np.int64)
    horizontal[1:, 1:] = np.cumsum(np.cumsum(horizontals, axis=0), axis=1)
    best: tuple[int, int] | None = None
    found = (0, columns - 1, 0, rows - 1)
    for top in range(rows):
        for bottom in range(top, rows):
            for left in range(columns):
                rights: np.ndarray = np.arange(left, columns, dtype=np.int64)
                total: np.ndarray = (
                    vertical[bottom + 1, rights + 2]
                    - vertical[top, rights + 2]
                    - vertical[bottom + 1, left]
                    + vertical[top, left]
                    + horizontal[bottom + 2, rights + 1]
                    - horizontal[top, rights + 1]
                    - horizontal[bottom + 2, left]
                    + horizontal[top, left]
                )
                # The rightmost of the best sums gives the larger rectangle.
                index = int(np.flatnonzero(total == total.max())[-1])
                key = (int(total[index]), (index + 1) * (bottom - top + 1))
                if best is None or key > best:
                    best = key
                    found = (left, left + index, top, bottom)
    return found
