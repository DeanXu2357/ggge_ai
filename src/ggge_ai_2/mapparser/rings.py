from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ggge_ai_2.mapparser.contract import ViewCell
from ggge_ai_2.mapparser.lattice import Lattice

SIZES = (1, 2, 3)


@dataclass(frozen=True)
class RingColor:
    # Each hue range is (low, high) on the OpenCV scale of 0 to 179.
    hues: tuple[tuple[int, int], ...]
    saturation: tuple[int, int]
    value: int


RED = ((0, 8), (170, 179))
# The selection screens dim the units and their rings, so the value bounds are low.
# The dark blue of the space background has a hue below the blue range.
# The ring of an enemy is light red, and a deep red glow surrounds it. The two are
# separate colors, so that the glow next to the ring does not count against the ring.
RING_COLORS = (
    RingColor(((107, 118),), (110, 255), 70),
    RingColor(((12, 35),), (120, 255), 40),
    RingColor(RED, (171, 255), 40),
    RingColor(RED, (90, 170), 40),
)
# In ring widths, measured from the left edge and up from the bottom edge of the ring.
RING_SPAN = (0.14, 0.86)
RING_SAMPLES = 21
# The ends of a ring that a body in front hides. They reach past RING_SPAN, because the
# body often hides all of the arc between them.
END_SPANS = ((0.1, 0.24), (0.76, 0.9))
END_SAMPLES = 9
RING_DEPTH = 0.09
RING_CURVE = 0.75
RING_THICKNESS = (-0.05, -0.025, 0.0, 0.025)
RING_BELOW = 0.18
RING_ABOVE = 0.2
RING_END = 0.22
RING_VISIBLE = 0.5
RING_ON = 0.6
END_ON = 0.4
RING_BELOW_OFF = 0.5
RING_ABOVE_OFF = 0.45
GAUGE_BELOW_OFF = 0.15
GAUGE_REST = 0.75
# The second check compares the ring colors with the drawn shape of the ring band. The
# band lies between two parabolas, in footprint widths across and back from the bottom
# edge of the footprint. The values come from 58 clear rings of width 1 in the ruled
# cases, and they also fit the rings of width 2. A ring of width 3 is not verified: the
# ruled cases have one.
BAND_FRONT = (-0.023, -0.782)
BAND_BACK = (-0.162, -0.557)
BAND_ENDS = (0.125, 0.91)
BAND_SAMPLES = 60
# The two end parts of the band. A sprite seldom hides both, and a speck, a role icon
# or a tile seldom fills both.
BAND_END_PART = 0.3
BAND_ENDS_ON = 0.4
HIDDEN_BAND_ENDS_ON = 0.25
# A gauge is one solid arc of ring color. The background can give ring colors in specks that
# pass the point samples (run 20261115-235743, frame 66). In ring widths across the arc, the
# band runs from GAUGE_TOP to GAUGE_BOTTOM. A component smaller than GAUGE_SPECK of the band
# is a speck, and a segment is solid when kept components fill GAUGE_FILL of it.
GAUGE_TOP, GAUGE_BOTTOM = 0.06, -0.16
GAUGE_SEGMENTS = 20
GAUGE_SPECK = 0.03
GAUGE_FILL = 0.3
GAUGE_END_PART = 0.15
SOLID_GAUGE_ON = 0.6
# A tall object shows only the tips of its gauge beside it (map20261026-40, the tower): its
# ends give 0.5. Specks around a hidden middle give at most 0.33.
HIDDEN_SOLID_GAUGE_ON = 0.5


@dataclass(frozen=True)
class Ring:
    # The anchor of the cells over the ring: the ring lies on the bottom row.
    pos: ViewCell
    width: int
    score: float
    # True when a body in front hides the middle of the ring and the two ends show.
    hidden_middle: bool

    def cells(self) -> tuple[ViewCell, ...]:
        column, row = self.pos
        return tuple(
            (column + dx, row + dy) for dy in range(self.width) for dx in range(self.width)
        )


@dataclass(frozen=True)
class RingImage:
    masks: tuple[np.ndarray, ...]
    value: np.ndarray
    # False under the HUD.
    visible: np.ndarray
    # All ring colors, also inside a region that 'clear_red' clears. The band check uses
    # them: the ring of a unit inside the move range of the selected enemy has red parts.
    drawn: np.ndarray

    @property
    def any_color(self) -> np.ndarray:
        return np.logical_or.reduce(self.masks)


def ring_image(image: np.ndarray, visible: np.ndarray) -> RingImage:
    value = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[..., 2]
    masks = _ring_colors(image)
    return RingImage(masks, value, visible, np.logical_or.reduce(masks))


def _ring_colors(image: np.ndarray) -> tuple[np.ndarray, ...]:
    """Return the mask of each ring color."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue, saturation, value = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    masks: list[np.ndarray] = []
    for color in RING_COLORS:
        mask = np.zeros(hue.shape, bool)
        for low, high in color.hues:
            mask |= (hue >= low) & (hue <= high)
        least, most = color.saturation
        masks.append(mask & (saturation >= least) & (saturation <= most) & (value > color.value))
    return tuple(masks)


def clear_red(rings: RingImage, region: np.ndarray) -> RingImage:
    """Return the ring image without the red ring colors inside the region."""
    masks = tuple(
        mask & ~region if color.hues == RED else mask
        for mask, color in zip(rings.masks, RING_COLORS, strict=True)
    )
    return RingImage(masks, rings.value, rings.visible, rings.drawn)


def find_rings(rings: RingImage, lattice: Lattice, frame_cells: frozenset[ViewCell]) -> list[Ring]:
    """Return the rings that do not overlap, best ring first."""
    columns = [column for column, _ in frame_cells]
    rows = [row for _, row in frame_cells]
    scored: list[Ring] = []
    for width in SIZES:
        grid = np.mgrid[
            min(rows) - width : max(rows) + 2, min(columns) - width : max(columns) + 2
        ].reshape(2, -1)
        scores, hidden = _scores(rings, lattice, grid[1], grid[0], width)
        scored.extend(
            Ring((int(column), int(row)), width, float(score), bool(middle))
            for score, middle, column, row in zip(scores, hidden, grid[1], grid[0], strict=True)
            if score > 0
        )
    taken: set[ViewCell] = set()
    found: list[Ring] = []
    for ring in sorted(scored, key=lambda ring: -ring.score):
        if taken.isdisjoint(ring.cells()) and _arc_shaped(rings, lattice, ring):
            found.append(ring)
            taken.update(ring.cells())
    return found


def _arc_shaped(rings: RingImage, lattice: Lattice, ring: Ring) -> bool:
    """Return True when the ring colors fill the two end parts of the drawn ring band."""
    least = HIDDEN_BAND_ENDS_ON if ring.hidden_middle else BAND_ENDS_ON
    return band_share(rings, lattice, ring.pos, ring.width) >= least


def band_share(rings: RingImage, lattice: Lattice, pos: ViewCell, width: int) -> float:
    """Return the share of the end parts of the ring band of the footprint in ring colors."""
    across, back = _BAND_POINTS
    xs, ys = lattice.project_many(pos[0] + width * across, pos[1] + width * (1.0 + back))
    hits, shown = sample(rings.drawn, rings.visible, xs, ys)
    if not shown.any():
        return 0.0
    return float(hits.sum()) / float(shown.sum())


def _band_points() -> tuple[np.ndarray, np.ndarray]:
    """Return the points of the two end parts of the ring band, in footprint widths."""
    step = 1.0 / BAND_SAMPLES
    across, back = np.meshgrid(
        np.arange(BAND_ENDS[0], BAND_ENDS[1], step) + step / 2,
        np.arange(-0.3, 0.0, step) + step / 2,
    )
    middle = across - 0.5
    inside = (back <= BAND_FRONT[0] + BAND_FRONT[1] * middle**2) & (
        back >= BAND_BACK[0] + BAND_BACK[1] * middle**2
    )
    ends = (across <= BAND_END_PART) | (across >= 1.0 - BAND_END_PART)
    return across[inside & ends], back[inside & ends]


_BAND_POINTS = _band_points()


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


@dataclass(frozen=True)
class _Arc:
    lattice: Lattice
    visible: np.ndarray
    us: np.ndarray
    bottoms: np.ndarray
    rise: np.ndarray
    width: int

    def points(self, shift: float) -> tuple[np.ndarray, np.ndarray]:
        return self.lattice.project_many(self.us, self.bottoms - self.width * (self.rise + shift))

    def band(self, mask: np.ndarray, shift: float) -> tuple[np.ndarray, np.ndarray]:
        hits = np.zeros(self.us.shape, bool)
        shown = np.zeros(self.us.shape, bool)
        for offset in RING_THICKNESS:
            hit, seen = sample(mask, self.visible, *self.points(offset + shift))
            hits |= hit
            shown |= seen
        return hits, shown


def _arc(
    lattice: Lattice,
    visible: np.ndarray,
    columns: np.ndarray,
    rows: np.ndarray,
    width: int,
    across: np.ndarray,
) -> _Arc:
    return _Arc(
        lattice,
        visible,
        columns[:, None] + width * across[None, :],
        (rows + width)[:, None],
        (RING_DEPTH + RING_CURVE * (across - 0.5) ** 2)[None, :],
        width,
    )


def _scores(
    rings: RingImage, lattice: Lattice, columns: np.ndarray, rows: np.ndarray, width: int
) -> tuple[np.ndarray, np.ndarray]:
    """Return the ring score and the hidden-middle flag of each anchor.

    The score is the share of arc points on the ring colors, less the share next to the
    arc. It is 0 when too little of the arc is visible or no color passes. A ring is a
    thin arc. A range effect fills the whole cell, so its color also shows below the arc
    and above the two ends of the arc, where the sprite seldom is.
    """
    across = np.linspace(*RING_SPAN, RING_SAMPLES)
    arc = _arc(lattice, rings.visible, columns, rows, width, across)
    ends = [
        _arc(lattice, rings.visible, columns, rows, width, np.linspace(*span, END_SAMPLES))
        for span in END_SPANS
    ]
    outer = np.abs(across - 0.5) >= RING_END
    bands = [arc.band(mask, 0.0) for mask in rings.masks]
    shown = bands[0][1]
    enough = shown.sum(axis=1) >= RING_VISIBLE * len(across)

    def share(mask: np.ndarray, on: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        sides = np.stack([_shares(*end.band(mask, 0.0)) for end in ends])
        whole = _shares(on, shown)
        hidden = (sides.min(axis=0) >= END_ON) & (whole < RING_ON)
        return np.where(hidden, np.maximum(whole, sides.mean(axis=0)), whole), hidden

    best = np.zeros(len(columns))
    hidden_middle = np.zeros(len(columns), bool)
    for mask, (on, _) in zip(rings.masks, bands, strict=True):
        on_arc, hidden = share(mask, on)
        below = _shares(arc.band(mask, -RING_BELOW)[0], shown)
        above = _shares(arc.band(mask, RING_ABOVE)[0][:, outer], shown[:, outer])
        passed = (
            enough & (on_arc >= RING_ON) & (below <= RING_BELOW_OFF) & (above <= RING_ABOVE_OFF)
        )
        score = on_arc - np.maximum(below, above)
        better = passed & (score > best)
        best = np.where(better, score, best)
        hidden_middle = np.where(better, hidden, hidden_middle)
    gauge = _gauge(rings, arc, np.stack([on for on, _ in bands]), shown, enough)
    better = gauge > best
    return np.where(better, gauge, best), hidden_middle & ~better


def _gauge(
    rings: RingImage, arc: _Arc, hits: np.ndarray, shown: np.ndarray, enough: np.ndarray
) -> np.ndarray:
    """Return the score of each anchor as a gauge of two colors.

    The ring is an HP gauge. One color fills it to the HP share and a darker color fills
    the rest. The sprite of the unit often has the color of the gauge above the arc
    ends, so only the clear ground below the arc separates the gauge from a range effect.
    """
    second = _second_run(hits)
    third = _second_run(np.where(second[None], hits, False))
    first = hits.any(axis=0) & ~second
    level = _values(rings.value, *arc.points(0.0))
    fill = (level * first).sum(axis=1) / np.maximum(first.sum(axis=1), 1)
    rest = (level * second).sum(axis=1) / np.maximum(second.sum(axis=1), 1)
    on_arc = _shares(hits.any(axis=0), shown)
    below = _shares(arc.band(rings.any_color, -RING_BELOW)[0], shown)
    passed = (
        enough
        & (on_arc >= RING_ON)
        & (below <= GAUGE_BELOW_OFF)
        & second.any(axis=1)
        & ~third.any(axis=1)
        & (rest <= GAUGE_REST * fill)
    )
    return np.where(passed, on_arc - below, 0.0)


def _second_run(hits: np.ndarray) -> np.ndarray:
    """Return the arc points after the first change of ring color, for each anchor."""
    labels = np.where(hits.any(axis=0), hits.argmax(axis=0), -1)
    on = labels >= 0
    steps: np.ndarray = np.indices(labels.shape)[1]
    last = np.maximum.accumulate(np.where(on, steps, 0), axis=1)
    filled = np.take_along_axis(labels, last, axis=1)
    started = np.logical_or.accumulate(on, axis=1)
    changes = np.zeros(on.shape, bool)
    changes[:, 1:] = (filled[:, 1:] != filled[:, :-1]) & on[:, 1:] & started[:, :-1]
    return np.logical_or.accumulate(changes, axis=1) & on


def _values(channel: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    height, width = channel.shape
    columns = np.clip(np.floor(xs).astype(int), 0, width - 1)
    rows = np.clip(np.floor(ys).astype(int), 0, height - 1)
    return channel[rows, columns].astype(np.float64)


def _shares(hits: np.ndarray, shown: np.ndarray) -> np.ndarray:
    """Return the share of the shown points that are hits, for each row."""
    return hits.sum(axis=1) / np.maximum(shown.sum(axis=1), 1)


def solid_gauge(
    mask: np.ndarray, visible: np.ndarray, lattice: Lattice, ring: Ring
) -> float | None:
    """Return the share of the shown segments along the gauge band that the large components
    of the mask fill, or None when too little of the band shows to judge. For a ring whose
    middle a body hides, only the end segments count."""
    height, width = mask.shape
    across = np.linspace(RING_SPAN[0], RING_SPAN[1], GAUGE_SEGMENTS + 1)
    arc = _arc(
        lattice, visible, np.array([ring.pos[0]]), np.array([ring.pos[1]]), ring.width, across
    )
    top = np.stack(arc.points(GAUGE_TOP), axis=-1)[0]
    bottom = np.stack(arc.points(GAUGE_BOTTOM), axis=-1)[0]
    corners = np.concatenate([top, bottom])
    x0 = int(max(0, corners[:, 0].min() - 2))
    x1 = int(min(width, corners[:, 0].max() + 3))
    y0 = int(max(0, corners[:, 1].min() - 2))
    y1 = int(min(height, corners[:, 1].max() + 3))
    if x0 >= x1 or y0 >= y1:
        return 0.0
    segments = np.zeros((y1 - y0, x1 - x0), np.int32)
    for index in range(GAUGE_SEGMENTS):
        quad = np.array([top[index], top[index + 1], bottom[index + 1], bottom[index]]) - (x0, y0)
        cv2.fillPoly(segments, [quad.astype(np.int32)], index + 1)
    band = segments > 0
    inside = mask[y0:y1, x0:x1] & band
    count, found, stats, _ = cv2.connectedComponentsWithStats(
        inside.astype(np.uint8), connectivity=8
    )
    labels = np.asarray(found, np.int32)
    large = np.zeros(count, bool)
    large[1:] = np.asarray(stats)[1:, cv2.CC_STAT_AREA] >= GAUGE_SPECK * band.sum()
    kept = np.take(large, labels)
    seen = visible[y0:y1, x0:x1]
    counted = range(1, GAUGE_SEGMENTS + 1)
    if ring.hidden_middle:
        ends = round(GAUGE_SEGMENTS * GAUGE_END_PART)
        counted = [*range(1, ends + 1), *range(GAUGE_SEGMENTS - ends + 1, GAUGE_SEGMENTS + 1)]
    solid = shown = 0
    for index in counted:
        area = segments == index
        if (area & seen).sum() < 0.5 * area.sum():
            continue
        shown += 1
        solid += int((kept & area).sum() >= GAUGE_FILL * area.sum())
    return solid / shown if shown >= len(counted) / 2 else None
