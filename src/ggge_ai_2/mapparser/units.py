from __future__ import annotations

import functools
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ggge_ai_2.mapparser.contract import CellReading, Rect, ScreenPoint, UnitReading, ViewCell
from ggge_ai_2.mapparser.lattice import Lattice, ridge
from ggge_ai_2.mapparser.markers import enemy_move_range
from ggge_ai_2.mapparser.rings import (
    RING_DEPTH,
    Ring,
    RingImage,
    band_share,
    clear_red,
    find_rings,
    ring_image,
    sample,
)
from ggge_ai_2.mapparser.topview import CELL, TopView, outside

CHEVRON_TEMPLATE = (
    Path(__file__).resolve().parents[3] / "assets" / "templates" / "mapparser" / "chevron.png"
)
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
# A unit that hides the grid lines also shows a part of its ring, for example beside an
# attack preview (map20261026-40). A building hides the grid lines and shows no ring
# (map20261112-3).
HIDDEN_RING_ON = 0.25
# A body in front hides the middle of a wide ring, and with it the grid line between the
# columns of the ring. When that line shows, the two ring ends are two other objects, for
# example grass and the head of a unit (map20261112-1, map20261112-3).
MIDDLE_SPAN = np.linspace(-0.25, -0.02, 9)
MIDDLE_LINE_OFF = 0.5

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
# The rise comes from the brightest ring on 17 frames with a selected enemy: the ring
# centers 0.46 cells below the top edge of the cell (run 20261115-213514).
CIRCLE_RISE = 0.54
CIRCLE_RADII = (0.55, 0.62, 0.69)
CIRCLE_ANGLES = np.radians(np.linspace(-60.0, 40.0, 11))
GLOW_HUE = (95, 118)
GLOW_SATURATION = 25
GLOW_VALUE = 225
CIRCLE_SIDE = 0.4
CIRCLE_ON = 0.5
# A tap on an enemy unit while no unit of the player is selected draws a red circle around
# the enemy. The red tint of the enemy's move range is darker than the glow of the circle.
RED_GLOW_HUES = ((0, 10), (165, 179))
RED_GLOW_SATURATION = 25
RED_GLOW_VALUE = 240
# The circle is dashed and the sprite hides part of it, so a side shows glow in at most
# about 0.8 of the angles. On the frames that the agent reads, a circle around a selected
# enemy gives at least 0.36, and a cell without one gives at most 0.27.
RED_CIRCLE_ON = 0.32
# The sprite of a wide unit can hide most of the red circle (map20261112-1, -4). The move
# range of the selected enemy lies around its cell, so a weaker circle counts in a cell
# near the center of the range. The value lies between the best circle share of a
# frame without a selected enemy (0.09) and of a hidden circle (0.27).
RANGE_CENTER_REACH = 1.0
RED_CIRCLE_AT_CENTER = 0.18


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
    image: np.ndarray, lattice: Lattice, rects: tuple[Rect, ...], view: TopView, chevrons: bool
) -> tuple[tuple[UnitReading, ...], dict[ViewCell, CellReading]]:
    """Return the units and the reading of each frame cell.

    The controllable state of every unit is None when 'chevrons' is False.
    """
    visible = outside(image, rects, 0)
    frame_cells = lattice.cells()
    hud = frozenset(cell for cell in frame_cells if covered(lattice.center(cell), rects))
    # The panels have soft colored edges a few pixels past their rectangles.
    rings = ring_image(image, outside(image, rects, HUD_MARGIN))
    enemy = _enemy_selected(view, frame_cells - hud)
    if enemy is not None:
        # The move range of the selected enemy has the colors of the red rings, so a red
        # ring inside it cannot be told from the tint.
        # Warning: other enemy units inside the range are not found by their rings.
        tint = _cells_region(image.shape[:2], lattice, enemy_move_range(view, frame_cells))
        rings = clear_red(rings, tint)
    lines = grid_lines(image)
    found = [
        ring
        for ring in find_rings(rings, lattice, frame_cells)
        if not _middle_shown(lattice, lines, visible, ring)
    ]
    taken = {cell for ring in found for cell in ring.cells()}
    footprints = [_body(view, ring, taken) for ring in found]
    if enemy is not None:
        # The sprite of a wide unit can make its ring body wider than its cell
        # (map20261112-1). The red circle marks the cell of the unit.
        footprints = [footprint for footprint in footprints if enemy.pos not in footprint.cells()]
        footprints.append(enemy)
    white = (image.min(axis=2) > CHEVRON_WHITE).astype(np.float32)
    middle_row = lattice.row_coordinate(image.shape[0] / 2)
    pitch = lattice.project(1.0, middle_row)[0] - lattice.project(0.0, middle_row)[0]
    kernels = tuple(_chevron(round(factor * pitch / CHEVRON_PITCH, 2)) for factor in CHEVRON_SCALES)
    if chevrons:
        # Warning: this search finds the units that show only their chevron. Roadmap
        # section 8.14 rules to delete it. Without it, the parser loses 4 ruled units
        # (map20261112-4, map20261026-51, rec20261014-639). The user decides at the review
        # of task B2.
        marks = _chevrons(white, kernels, pitch, lattice, visible)
        footprints.extend(_chevron_units(marks, footprints))
    hidden = _hidden(lattice, lines, rings, visible, frame_cells - hud, footprints)
    footprints.extend(hidden.units)
    selected = _selected(view, footprints)
    units = tuple(
        UnitReading(
            pos=footprint.pos,
            size=(footprint.width, footprint.height),
            controllable=_controllable(white, kernels, lattice, visible, footprint)
            if chevrons
            else None,
            selected=footprint == selected,
            enemy_selected=footprint == enemy,
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


def covered(point: ScreenPoint, rects: tuple[Rect, ...]) -> bool:
    x, y = point
    return any(left <= x < right and top <= y < bottom for left, top, right, bottom in rects)


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
    best: tuple[float, _Footprint | None] = (CIRCLE_ON, None)
    for footprint in footprints:
        sides = _circle_sides(view, glow, footprint)
        if len(sides) < 2 or min(sides) < CIRCLE_SIDE:
            continue
        score = sum(sides) / 2
        if score >= best[0]:
            best = (score, footprint)
    return best[1]


def _enemy_selected(view: TopView, cells: frozenset[ViewCell]) -> _Footprint | None:
    """Return the one-cell footprint in the red selection circle, or None."""
    hsv = cv2.cvtColor(view.image, cv2.COLOR_BGR2HSV)
    hue, saturation, value = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    red = np.zeros(hue.shape, bool)
    for low, high in RED_GLOW_HUES:
        red |= (hue >= low) & (hue <= high)
    glow = red & (saturation >= RED_GLOW_SATURATION) & (value >= RED_GLOW_VALUE)
    circle = _red_circle(view, glow, cells, RED_CIRCLE_ON)
    if circle is not None:
        return circle
    tinted = enemy_move_range(view, cells)
    if not tinted:
        return None
    center_x = sum(column for column, _ in tinted) / len(tinted)
    center_y = sum(row for _, row in tinted) / len(tinted)
    near = frozenset(
        cell
        for cell in cells - tinted
        if math.hypot(cell[0] - center_x, cell[1] - center_y) <= RANGE_CENTER_REACH
    )
    return _red_circle(view, glow, near, RED_CIRCLE_AT_CENTER)


def _red_circle(
    view: TopView, glow: np.ndarray, cells: frozenset[ViewCell], least: float
) -> _Footprint | None:
    best: tuple[float, _Footprint | None] = (least, None)
    for cell in sorted(cells):
        footprint = _Footprint.square(cell, 1)
        sides = _circle_sides(view, glow, footprint)
        if len(sides) == 2 and min(sides) >= best[0]:
            best = (min(sides), footprint)
    return best[1]


def _circle_sides(view: TopView, glow: np.ndarray, footprint: _Footprint) -> list[float]:
    """Return the share of glow on the left and the right side of the selection circle
    around the footprint. The list is shorter when too little of a side shows."""
    x0, y0 = view.origin((0, 0))
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
    return sides


def _cells_region(
    shape: tuple[int, int], lattice: Lattice, cells: frozenset[ViewCell]
) -> np.ndarray:
    """Return the screen pixels inside the cells."""
    region = np.zeros(shape, np.uint8)
    for column, row in cells:
        corners = [
            lattice.project(column + dx, row + dy) for dx, dy in ((0, 0), (1, 0), (1, 1), (0, 1))
        ]
        cv2.fillConvexPoly(region, np.round(np.array(corners)).astype(np.int32), 1)
    return region.astype(bool)


def _visible(visible: np.ndarray, x: float, y: float) -> bool:
    height, width = visible.shape
    column, row = math.floor(x), math.floor(y)
    return 0 <= column < width and 0 <= row < height and bool(visible[row, column])


def grid_lines(image: np.ndarray) -> GridLines:
    white = image.min(axis=2).astype(np.int16)
    rows = cv2.dilate(ridge(white, axis=0), np.ones((LINE_NEAR, 1), np.uint8)) > LINE_RIDGE
    columns = cv2.dilate(ridge(white, axis=1), np.ones((1, LINE_NEAR), np.uint8)) > LINE_RIDGE
    return GridLines(rows, columns)


def _middle_shown(lattice: Lattice, lines: GridLines, visible: np.ndarray, ring: Ring) -> bool:
    """Return True when a wide ring with a hidden middle shows the grid line in the middle."""
    if not ring.hidden_middle or ring.width < 2:
        return False
    rows = ring.pos[1] + ring.width + MIDDLE_SPAN
    for step in range(1, ring.width):
        column = np.full(len(MIDDLE_SPAN), float(ring.pos[0] + step))
        share = _line_share(lines.columns, visible, lattice, column, rows)
        if share is not None and share >= MIDDLE_LINE_OFF:
            return True
    return False


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
    rings: RingImage,
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
        if not _top_hidden(lattice, lines, rings.any_color, visible, (column, row)):
            continue
        if (column, row) in near:
            unreadable.add((column, row))
            continue
        if band_share(rings, lattice, (column, row), 1) < HIDDEN_RING_ON:
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
    template = cv2.imread(str(CHEVRON_TEMPLATE), cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise FileNotFoundError(CHEVRON_TEMPLATE)
    resized = cv2.resize(template, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    arms = (resized == 255).astype(np.float32)
    gaps = (resized == 0).astype(np.float32)
    return arms / arms.sum() - gaps / gaps.sum()


def _chevrons(
    white: np.ndarray,
    kernels: tuple[np.ndarray, ...],
    pitch: float,
    lattice: Lattice,
    visible: np.ndarray,
) -> np.ndarray:
    """Return the (column, row) lattice coordinates of the center of each chevron."""
    response = np.full(white.shape, -1.0, np.float32)
    for kernel in kernels:
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
    white: np.ndarray,
    kernels: tuple[np.ndarray, ...],
    lattice: Lattice,
    visible: np.ndarray,
    footprint: _Footprint,
) -> bool | None:
    """Return True when the chevron of a unit that can act shows above the footprint, False when
    the frame shows the place of the chevron without it, and None otherwise."""
    column, row = footprint.pos
    middle = column + footprint.width / 2
    low, high = CHEVRON_RISE
    corners = [
        lattice.project(middle + across, row - rise)
        for across in (-CHEVRON_ACROSS, CHEVRON_ACROSS)
        for rise in (low, high)
    ]
    reach = max(max(kernel.shape) for kernel in kernels)
    height, width = white.shape
    left = max(0, math.floor(min(x for x, _ in corners)) - reach)
    right = min(width, math.ceil(max(x for x, _ in corners)) + reach + 1)
    top = max(0, math.floor(min(y for _, y in corners)) - reach)
    bottom = min(height, math.ceil(max(y for _, y in corners)) + reach + 1)
    if left < right and top < bottom:
        window = white[top:bottom, left:right]
        response = np.full(window.shape, -1.0, np.float32)
        for kernel in kernels:
            np.maximum(
                response,
                cv2.filter2D(window, -1, kernel, borderType=cv2.BORDER_CONSTANT),
                out=response,
            )
        response[~visible[top:bottom, left:right]] = -1.0
        ys, xs = np.nonzero(response >= CHEVRON_SCORE)
        ys = ys.astype(np.float64) + top
        columns = (
            (xs + left - lattice.apex) / (ys - lattice.horizon) - lattice.column_origin
        ) / lattice.column_step
        rises = row - (1.0 / (ys - lattice.horizon) - lattice.row_origin) / lattice.row_step
        if ((np.abs(columns - middle) <= CHEVRON_ACROSS) & (rises >= low) & (rises <= high)).any():
            return True
    if all(_visible(visible, x, y) for x, y in corners):
        return False
    return None
