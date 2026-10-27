from __future__ import annotations

import functools
import math
from dataclasses import dataclass

import cv2
import numpy as np

from ggge_ai_2.mapparser.contract import CellReading, UnitReading, ViewCell
from ggge_ai_2.mapparser.hud import PROMPT, TEMPLATES, Rect, covered, template_match
from ggge_ai_2.mapparser.lattice import Lattice, ridge

SIZES = (1, 2)
HUD_MARGIN = 8


@dataclass(frozen=True)
class RingColor:
    # Each hue range is (low, high) on the OpenCV scale of 0 to 179.
    hues: tuple[tuple[int, int], ...]
    saturation: tuple[int, int]
    value: int


RED = ((0, 8), (170, 179))
# The selection screens dim the units and their rings, so the value bounds are low.
# The dark blue of the space background stays below the blue bound.
# The ring of an enemy is light red, and a deep red glow surrounds it. The two are
# separate colors, so that the glow next to the ring does not count against the ring.
RING_COLORS = (
    RingColor(((95, 125),), (110, 255), 70),
    RingColor(((12, 35),), (150, 255), 40),
    RingColor(RED, (171, 255), 40),
    RingColor(RED, (90, 170), 40),
)
# In footprint units, measured from the left edge and up from the bottom edge of the footprint.
RING_SPAN = (0.14, 0.86)
RING_DEPTH = 0.09
RING_CURVE = 0.75
RING_THICKNESS = (-0.05, -0.025, 0.0, 0.025)
RING_BELOW = 0.18
RING_ABOVE = 0.2
RING_END = 0.22
RING_END_ON = 0.4
RING_SAMPLES = 21
RING_VISIBLE = 0.5
RING_ON = 0.6
RING_BELOW_OFF = 0.5
RING_ABOVE_OFF = 0.45

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


@dataclass(frozen=True)
class _Footprint:
    pos: ViewCell
    size: int

    def cells(self) -> tuple[ViewCell, ...]:
        column, row = self.pos
        return tuple((column + dx, row + dy) for dy in range(self.size) for dx in range(self.size))

    def reach(self) -> tuple[ViewCell, ...]:
        """Return the cells next to the footprint that the sprite can cover.

        A sprite overflows into the cells above. A large sprite also covers the cells
        at its sides and diagonally above.
        """
        column, row = self.pos
        if self.size == 1:
            return ((column, row - 1),)
        return tuple(
            (column + dx, row + dy)
            for dx in range(-1, self.size + 1)
            for dy in range(-1, self.size)
            if not (0 <= dx < self.size and 0 <= dy)
        )


@dataclass(frozen=True)
class GridLines:
    rows: np.ndarray
    columns: np.ndarray


def read_units(
    image: np.ndarray, lattice: Lattice, rects: tuple[Rect, ...]
) -> tuple[tuple[UnitReading, ...], dict[ViewCell, CellReading]]:
    visible = outside(image, rects, 0)
    frame_cells = lattice.cells()
    hud = frozenset(cell for cell in frame_cells if covered(lattice.center(cell), rects))
    masks = _ring_masks(image)
    # The panels have soft colored edges a few pixels past their rectangles.
    footprints = _rings(masks, lattice, outside(image, rects, HUD_MARGIN), frame_cells)
    arcs = np.logical_or.reduce(masks)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    chevrons = (
        _chevrons(image, lattice, visible)
        if template_match(gray, PROMPT)[0] >= PROMPT.threshold
        else None
    )
    if chevrons is not None:
        footprints.extend(_chevron_units(chevrons, footprints))
    hidden = _hidden(lattice, grid_lines(image), arcs, visible, frame_cells - hud, footprints)
    footprints.extend(hidden.units)
    units = tuple(
        UnitReading(
            pos=footprint.pos,
            size=(footprint.size, footprint.size),
            controllable=None
            if chevrons is None
            else _controllable(lattice, visible, chevrons, footprint),
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


def outside(image: np.ndarray, rects: tuple[Rect, ...], margin: int) -> np.ndarray:
    """Return the mask of the pixels outside the HUD rectangles grown by the margin."""
    outside = np.ones(image.shape[:2], bool)
    for left, top, right, bottom in rects:
        outside[max(top - margin, 0) : bottom + margin, max(left - margin, 0) : right + margin] = (
            False
        )
    return outside


def _visible(visible: np.ndarray, x: float, y: float) -> bool:
    height, width = visible.shape
    column, row = math.floor(x), math.floor(y)
    return 0 <= column < width and 0 <= row < height and bool(visible[row, column])


def sample(
    mask: np.ndarray, visible: np.ndarray, xs: np.ndarray, ys: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Return the mask value and the visibility at each point."""
    height, width = mask.shape
    columns = np.floor(xs).astype(int)
    rows = np.floor(ys).astype(int)
    inside = (columns >= 0) & (columns < width) & (rows >= 0) & (rows < height)
    columns, rows = np.clip(columns, 0, width - 1), np.clip(rows, 0, height - 1)
    shown = inside & visible[rows, columns]
    return mask[rows, columns] & shown, shown


def _ring_masks(image: np.ndarray) -> list[np.ndarray]:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue, saturation, value = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    masks: list[np.ndarray] = []
    for color in RING_COLORS:
        mask = np.zeros(hue.shape, bool)
        for low, high in color.hues:
            mask |= (hue >= low) & (hue <= high)
        least, most = color.saturation
        masks.append(mask & (saturation >= least) & (saturation <= most) & (value > color.value))
    return masks


def _rings(
    masks: list[np.ndarray],
    lattice: Lattice,
    visible: np.ndarray,
    frame_cells: frozenset[ViewCell],
) -> list[_Footprint]:
    """Find the ring or arc under each unit and return the footprints, best ring first.

    The arc lies on the ground in front of the unit and spans the footprint width.
    Its color shows the HP, so any of the ring hues counts.
    """
    columns = [column for column, _ in frame_cells]
    rows = [row for _, row in frame_cells]
    scored: list[tuple[float, _Footprint]] = []
    for size in SIZES:
        grid = np.mgrid[
            min(rows) - size : max(rows) + 2, min(columns) - size : max(columns) + 2
        ].reshape(2, -1)
        scores = _ring_scores(masks, lattice, visible, grid[1], grid[0], size)
        scored.extend(
            (float(score), _Footprint((int(column), int(row)), size))
            for score, column, row in zip(scores, grid[1], grid[0], strict=True)
            if score > 0
        )
    taken: set[ViewCell] = set()
    found: list[_Footprint] = []
    for _, footprint in sorted(scored, key=lambda item: -item[0]):
        if taken.isdisjoint(footprint.cells()):
            found.append(footprint)
            taken.update(footprint.cells())
    return found


def _ring_scores(
    masks: list[np.ndarray],
    lattice: Lattice,
    visible: np.ndarray,
    columns: np.ndarray,
    rows: np.ndarray,
    size: int,
) -> np.ndarray:
    """Return the ring score of each anchor.

    The score is the best share of arc points on one ring color, less the share next to
    the arc. It is 0 when too little of the arc is visible or no color passes. A ring is
    a thin arc. A range effect fills the whole cell, so its color also shows below the
    arc and above the two ends of the arc, where the sprite seldom is.
    """
    across = np.linspace(*RING_SPAN, RING_SAMPLES)
    rise = RING_DEPTH + RING_CURVE * (across - 0.5) ** 2
    us = columns[:, None] + size * across[None, :]
    bottoms = (rows + size)[:, None]

    def band(mask: np.ndarray, shift: float) -> tuple[np.ndarray, np.ndarray]:
        hits = np.zeros(us.shape, bool)
        shown = np.zeros(us.shape, bool)
        for offset in RING_THICKNESS:
            xs, ys = lattice.project_many(us, bottoms - size * (rise + offset + shift))
            hit, seen = sample(mask, visible, xs, ys)
            hits |= hit
            shown |= seen
        return hits, shown

    ends = np.abs(across - 0.5) >= RING_END
    left = across <= 0.5 - RING_END
    right = across >= 0.5 + RING_END
    best = np.zeros(len(columns))
    for mask in masks:
        on, shown = band(mask, 0.0)
        arc = _shares(on, shown)
        if size > 1:
            # An object can stand in front of the middle of its own arc.
            sides = np.stack(
                [_shares(on[:, left], shown[:, left]), _shares(on[:, right], shown[:, right])]
            )
            arc = np.where(
                sides.min(axis=0) >= RING_END_ON, np.maximum(arc, sides.mean(axis=0)), arc
            )
        below = _shares(band(mask, -RING_BELOW)[0], shown)
        above = _shares(band(mask, RING_ABOVE)[0][:, ends], shown[:, ends])
        passed = (
            (shown.sum(axis=1) >= RING_VISIBLE * len(across))
            & (arc >= RING_ON)
            & (below <= RING_BELOW_OFF)
            & (above <= RING_ABOVE_OFF)
        )
        best = np.where(passed, np.maximum(best, arc - np.maximum(below, above)), best)
    return best


def _shares(hits: np.ndarray, shown: np.ndarray) -> np.ndarray:
    """Return the share of the shown points that are hits, for each row."""
    return hits.sum(axis=1) / np.maximum(shown.sum(axis=1), 1)


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
        unit = _Footprint((column, row), 1)
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
    across = chevron[0] - (column + footprint.size / 2)
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
        unit = _Footprint((math.floor(chevron[0]), math.floor(chevron[1]) + 1), 1)
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
    middle = column + footprint.size / 2
    low, high = CHEVRON_RISE
    corners = [
        lattice.project(middle + across, row - rise)
        for across in (-CHEVRON_ACROSS, CHEVRON_ACROSS)
        for rise in (low, high)
    ]
    if all(_visible(visible, x, y) for x, y in corners):
        return False
    return None
