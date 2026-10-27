from __future__ import annotations

import functools
import math
from dataclasses import dataclass

import cv2
import numpy as np

from ggge_ai_2.mapparser.contract import CellReading, UnitReading, ViewCell
from ggge_ai_2.mapparser.hud import PROMPT, TEMPLATES, Rect, covered, outside, template_match
from ggge_ai_2.mapparser.lattice import Lattice, ridge
from ggge_ai_2.mapparser.rings import (
    RING_DEPTH,
    Ring,
    find_rings,
    ring_image,
    sample,
)
from ggge_ai_2.mapparser.topview import CELL, TopView

HUD_MARGIN = 8

# In cells of the top view. The walk goes up from the middle of a hidden ring through
# the body in front of it, in steps, while the body keeps the color at the ring.
BODY_SPAN = (0.4, 0.6)
BODY_REFERENCE = (0.15, 0.25)
BODY_STEP = 0.1
BODY_GAP = 0.25
BODY_COLOR = 40
BODY_SHARE = 0.5
# A body that reaches into this share of a row covers the row: the top view draws a
# raised body higher than its cells.
BODY_REACH = 0.25

LINE_RIDGE = 20
LINE_NEAR = 5
TOP_SPAN = np.linspace(0.35, 0.65, 7)
SIDE_SPAN = np.linspace(0.35, 0.85, 9)
LINE_VISIBLE = 0.5
TOP_HIDDEN = 0.5
TOP_ARC = 0.5
SIDE_SHOWN = 0.4
SIDE_CLEAR = 0.7

CHEVRON_PITCH = 114.0
CHEVRON_SCALES = (0.8, 0.9, 1.0, 1.12, 1.25)
CHEVRON_WHITE = 150
CHEVRON_SCORE = 0.75
CHEVRON_SPACING = 0.5
# The chevron center is about half a cell above the top edge of the footprint, and at
# the middle of the footprint width. The bounds are in cells.
CHEVRON_ACROSS = 0.35
CHEVRON_RISE = (0.3, 0.8)

# The selection circle lies on the ground around the selected unit. In footprint widths,
# its center is this far above the bottom edge, and the radii cover its glow. The angles
# keep to the two sides, because the sprite hides the top and the ring lies at the bottom.
CIRCLE_RISE = 0.7
CIRCLE_RADII = (0.55, 0.62, 0.69)
CIRCLE_ANGLES = np.radians(np.linspace(-60.0, 40.0, 11))
GLOW_HUE = (95, 118)
GLOW_SATURATION = 25
GLOW_VALUE = 225
CIRCLE_SIDE = 0.4
CIRCLE_ON = 0.5


@dataclass(frozen=True)
class _Footprint:
    pos: ViewCell
    width: int
    height: int

    @staticmethod
    def square(pos: ViewCell, width: int) -> _Footprint:
        return _Footprint(pos, width, width)

    def cells(self) -> tuple[ViewCell, ...]:
        column, row = self.pos
        return tuple(
            (column + dx, row + dy) for dy in range(self.height) for dx in range(self.width)
        )

    def reach(self) -> tuple[ViewCell, ...]:
        """Return the cells next to the footprint that the sprite can cover.

        A sprite overflows into the cells above. A large sprite also covers the cells
        at its sides and diagonally above.
        """
        column, row = self.pos
        if self.width == 1:
            return ((column, row - 1),)
        return tuple(
            (column + dx, row + dy)
            for dx in range(-1, self.width + 1)
            for dy in range(-1, self.height)
            if not (0 <= dx < self.width and 0 <= dy)
        )


@dataclass(frozen=True)
class GridLines:
    rows: np.ndarray
    columns: np.ndarray


def read_units(
    image: np.ndarray, lattice: Lattice, rects: tuple[Rect, ...], view: TopView
) -> tuple[tuple[UnitReading, ...], dict[ViewCell, CellReading]]:
    visible = outside(image, rects, 0)
    frame_cells = lattice.cells()
    hud = frozenset(cell for cell in frame_cells if covered(lattice.center(cell), rects))
    # The panels have soft colored edges a few pixels past their rectangles.
    rings = ring_image(image, outside(image, rects, HUD_MARGIN))
    found = find_rings(rings, lattice, frame_cells)
    taken = {cell for ring in found for cell in ring.cells()}
    footprints = [_body(view, ring, taken) for ring in found]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    chevrons = (
        _chevrons(image, lattice, visible)
        if template_match(gray, PROMPT)[0] >= PROMPT.threshold
        else None
    )
    if chevrons is not None:
        footprints.extend(_chevron_units(chevrons, footprints))
    hidden = _hidden(
        lattice, grid_lines(image), rings.any_color, visible, frame_cells - hud, footprints
    )
    footprints.extend(hidden.units)
    # The overview screen draws the same glow around each unit that can act.
    selected = None if chevrons is not None else _selected(view, footprints)
    units = tuple(
        UnitReading(
            pos=footprint.pos,
            size=(footprint.width, footprint.height),
            controllable=None
            if chevrons is None
            else _controllable(lattice, visible, chevrons, footprint),
            selected=footprint == selected,
        )
        for footprint in sorted(footprints, key=lambda footprint: footprint.pos[::-1])
    )
    occupied = {cell for footprint in footprints for cell in footprint.cells()}
    cells: dict[ViewCell, CellReading] = {}
    for cell in frame_cells:
        if cell in hud or cell in hidden.unreadable:
            cells[cell] = CellReading.UNREADABLE
        elif cell in occupied:
            cells[cell] = CellReading.OCCUPIED
        else:
            cells[cell] = CellReading.EMPTY
    return units, cells


def _body(view: TopView, ring: Ring, taken: set[ViewCell]) -> _Footprint:
    """Return the footprint of the unit or object on the ring.

    A ring spans the width of the footprint and lies on its bottom row. The footprint is
    square, except for a long object that stands in front of the middle of its own ring:
    its body reaches further back than its width, and the footprint reaches to the back
    of the body. The footprint does not reach into the cells of another ring.
    """
    footprint = _Footprint.square(ring.pos, ring.width)
    if not ring.hidden_middle or ring.width == 1:
        return footprint
    top = _body_top(view, ring)
    if top is None:
        return footprint
    column, row = ring.pos
    bottom = row + ring.width - 1
    first = row
    while first > math.floor(top + BODY_REACH) and all(
        (column + dx, first - 1) not in taken for dx in range(ring.width)
    ):
        first -= 1
    taken.update((column + dx, line) for dx in range(ring.width) for line in range(first, row))
    return _Footprint((column, first), ring.width, bottom - first + 1)


def _body_top(view: TopView, ring: Ring) -> float | None:
    """Return the row coordinate of the back of the body in front of the ring."""
    column, row = ring.pos
    width = ring.width
    left, right = (column + width * share for share in BODY_SPAN)
    base = row + width - width * RING_DEPTH
    low, high = BODY_REFERENCE
    reference = _patch(view, left, right, base - width * high, base - width * low)
    if reference is None:
        return None
    color = np.median(reference.reshape(-1, 3), axis=0)
    top = y = base - width * low
    while top - y <= BODY_GAP:
        patch = _patch(view, left, right, y - BODY_STEP, y)
        if patch is None:
            break
        if (np.abs(patch.astype(np.int16) - color).max(axis=2) <= BODY_COLOR).mean() >= BODY_SHARE:
            top = y - BODY_STEP
        y -= BODY_STEP
    return top


def _patch(
    view: TopView, left: float, right: float, top: float, bottom: float
) -> np.ndarray | None:
    """Return the top-view pixels in the box of cell coordinates, or None if any is hidden."""
    x0, y0 = view.origin((0, 0))
    columns = slice(round(x0 + left * CELL), round(x0 + right * CELL))
    rows = slice(round(y0 + top * CELL), round(y0 + bottom * CELL))
    patch = view.image[rows, columns]
    if patch.size == 0 or not view.visible[rows, columns].all():
        return None
    return patch


def _selected(view: TopView, footprints: list[_Footprint]) -> _Footprint | None:
    """Return the unit with the selection circle, or None."""
    hsv = cv2.cvtColor(view.image, cv2.COLOR_BGR2HSV)
    hue, saturation, value = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    glow = (
        (hue >= GLOW_HUE[0])
        & (hue <= GLOW_HUE[1])
        & (saturation >= GLOW_SATURATION)
        & (value >= GLOW_VALUE)
    )
    x0, y0 = view.origin((0, 0))
    best: tuple[float, _Footprint | None] = (CIRCLE_ON, None)
    for footprint in footprints:
        column, row = footprint.pos
        width = footprint.width
        center_x = column + width / 2
        center_y = row + footprint.height - CIRCLE_RISE * width
        sides: list[float] = []
        for sign in (-1.0, 1.0):
            hits = np.zeros(len(CIRCLE_ANGLES), bool)
            shown = np.zeros(len(CIRCLE_ANGLES), bool)
            for radius in CIRCLE_RADII:
                xs = x0 + (center_x + sign * radius * width * np.cos(CIRCLE_ANGLES)) * CELL
                ys = y0 + (center_y + radius * width * np.sin(CIRCLE_ANGLES)) * CELL
                hit, seen = sample(glow, view.visible, xs, ys)
                hits |= hit
                shown |= seen
            if shown.sum() < len(CIRCLE_ANGLES) / 2:
                break
            sides.append(float(hits.sum()) / float(shown.sum()))
        if len(sides) < 2 or min(sides) < CIRCLE_SIDE:
            continue
        score = sum(sides) / 2
        if score >= best[0]:
            best = (score, footprint)
    return best[1]


def _visible(visible: np.ndarray, x: float, y: float) -> bool:
    height, width = visible.shape
    column, row = math.floor(x), math.floor(y)
    return 0 <= column < width and 0 <= row < height and bool(visible[row, column])


def grid_lines(image: np.ndarray) -> GridLines:
    white = image.min(axis=2).astype(np.int16)
    rows = cv2.dilate(ridge(white, axis=0), np.ones((LINE_NEAR, 1), np.uint8)) > LINE_RIDGE
    columns = cv2.dilate(ridge(white, axis=1), np.ones((1, LINE_NEAR), np.uint8)) > LINE_RIDGE
    return GridLines(rows, columns)


def _line_share(
    mask: np.ndarray, visible: np.ndarray, lattice: Lattice, us: np.ndarray, vs: np.ndarray
) -> float | None:
    """Return the share of the visible points that are on a visible grid line."""
    xs, ys = lattice.project_many(us, vs)
    hit, shown = sample(mask, visible, xs, ys)
    count = int(shown.sum())
    if count < LINE_VISIBLE * len(us):
        return None
    return float(hit.sum()) / count


@dataclass(frozen=True)
class _Hidden:
    units: list[_Footprint]
    unreadable: frozenset[ViewCell]


def _hidden(
    lattice: Lattice,
    lines: GridLines,
    arcs: np.ndarray,
    visible: np.ndarray,
    readable: frozenset[ViewCell],
    footprints: list[_Footprint],
) -> _Hidden:
    """Find the units that show no ring, from the grid lines that their sprites hide.

    The game draws the grid over the map art and under the sprites. A sprite overflows
    into the cell above, so it hides the middle of the top edge of its cell, and the
    grid lines at the two sides of its base stay visible. The rows go from the front to
    the back, because a sprite in front can also hide the top edge of the cell behind
    it. Such a cell is unreadable.
    """
    taken = {cell for footprint in footprints for cell in footprint.cells()}
    near = {cell for footprint in footprints for cell in footprint.reach()}
    units: list[_Footprint] = []
    unreadable: set[ViewCell] = set()
    for column, row in sorted(readable, key=lambda cell: (-cell[1], cell[0])):
        # The ring and the glow of a unit cover the edge below it, so that edge is no cue.
        if (column, row) in taken or (column, row - 1) in taken:
            continue
        if not _top_hidden(lattice, lines, arcs, visible, (column, row)):
            continue
        if (column, row) in near:
            unreadable.add((column, row))
            continue
        unit = _Footprint.square((column, row), 1)
        units.append(unit)
        taken.add((column, row))
        near.update(unit.reach())
    return _Hidden(units, frozenset(unreadable))


def _top_hidden(
    lattice: Lattice, lines: GridLines, arcs: np.ndarray, visible: np.ndarray, cell: ViewCell
) -> bool:
    """Return True when a sprite hides the middle of the top edge of the cell.

    The arc of a unit or an object in the row above can also hide that edge. So the
    hidden part must show more than the ring colors.
    """
    column, row = cell
    xs, ys = lattice.project_many(column + TOP_SPAN, np.full(len(TOP_SPAN), float(row)))
    shown_line, shown = sample(lines.rows, visible, xs, ys)
    if shown.sum() < LINE_VISIBLE * len(TOP_SPAN):
        return False
    hidden = shown & ~shown_line
    if hidden.sum() < TOP_HIDDEN * shown.sum():
        return False
    if sample(arcs, visible, xs, ys)[0][hidden].mean() >= TOP_ARC:
        return False
    sides = [
        _line_share(
            lines.columns,
            visible,
            lattice,
            np.full(len(SIDE_SPAN), float(column + side)),
            row + SIDE_SPAN,
        )
        for side in (0, 1)
    ]
    shares = [share for share in sides if share is not None]
    return len(shares) == 2 and min(shares) >= SIDE_SHOWN and max(shares) >= SIDE_CLEAR


@functools.cache
def _chevron(scale: float) -> np.ndarray:
    """Return the matching kernel of the chevron at this scale.

    The template marks the white arms of the upper chevron (255) and the darker pixels
    next to them (0). The role icon changes, so the template leaves it out (128).
    """
    path = TEMPLATES / "chevron.png"
    template = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise FileNotFoundError(path)
    resized = cv2.resize(template, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    arms = (resized == 255).astype(np.float32)
    gaps = (resized == 0).astype(np.float32)
    return arms / arms.sum() - gaps / gaps.sum()


def _chevrons(image: np.ndarray, lattice: Lattice, visible: np.ndarray) -> np.ndarray:
    """Return the (column, row) lattice coordinates of the center of each chevron."""
    white = (image.min(axis=2) > CHEVRON_WHITE).astype(np.float32)
    height = white.shape[0]
    left, _ = lattice.project(0.0, lattice.row_coordinate(height / 2))
    right, _ = lattice.project(1.0, lattice.row_coordinate(height / 2))
    pitch = right - left
    response = np.full(white.shape, -1.0, np.float32)
    for factor in CHEVRON_SCALES:
        kernel = _chevron(round(factor * pitch / CHEVRON_PITCH, 2))
        np.maximum(
            response, cv2.filter2D(white, -1, kernel, borderType=cv2.BORDER_CONSTANT), out=response
        )
    response[~visible] = -1.0
    radius = max(3, round(CHEVRON_SPACING * pitch))
    peaks = (response >= CHEVRON_SCORE) & (
        response >= cv2.dilate(response, np.ones((radius, radius), np.uint8))
    )
    ys, xs = np.nonzero(peaks)
    ys = ys.astype(np.float64)
    rows = (1.0 / (ys - lattice.horizon) - lattice.row_origin) / lattice.row_step
    columns = (
        (xs - lattice.apex) / (ys - lattice.horizon) - lattice.column_origin
    ) / lattice.column_step
    return np.stack([columns, rows], axis=1)


def _owns(footprint: _Footprint, chevron: np.ndarray) -> bool:
    column, row = footprint.pos
    across = chevron[0] - (column + footprint.width / 2)
    rise = row - chevron[1]
    return abs(across) <= CHEVRON_ACROSS and CHEVRON_RISE[0] <= rise <= CHEVRON_RISE[1]


def _chevron_units(chevrons: np.ndarray, footprints: list[_Footprint]) -> list[_Footprint]:
    """Return a unit under each chevron that no found unit owns.

    The ring of such a unit is under the HUD or under the sprite of a unit in front.
    """
    taken = {cell for footprint in footprints for cell in footprint.cells()}
    found: list[_Footprint] = []
    for chevron in chevrons:
        if any(_owns(footprint, chevron) for footprint in footprints + found):
            continue
        unit = _Footprint.square((math.floor(chevron[0]), math.floor(chevron[1]) + 1), 1)
        if unit.pos not in taken and _owns(unit, chevron):
            found.append(unit)
            taken.add(unit.pos)
    return found


def _controllable(
    lattice: Lattice, visible: np.ndarray, chevrons: np.ndarray, footprint: _Footprint
) -> bool | None:
    if any(_owns(footprint, chevron) for chevron in chevrons):
        return True
    column, row = footprint.pos
    middle = column + footprint.width / 2
    low, high = CHEVRON_RISE
    corners = [
        lattice.project(middle + across, row - rise)
        for across in (-CHEVRON_ACROSS, CHEVRON_ACROSS)
        for rise in (low, high)
    ]
    if all(_visible(visible, x, y) for x, y in corners):
        return False
    return None
