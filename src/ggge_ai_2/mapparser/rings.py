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
    RingColor(((12, 35),), (150, 255), 40),
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

    @property
    def any_color(self) -> np.ndarray:
        return np.logical_or.reduce(self.masks)


def ring_image(image: np.ndarray, visible: np.ndarray) -> RingImage:
    value = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[..., 2]
    return RingImage(_ring_colors(image), value, visible)


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
        if taken.isdisjoint(ring.cells()):
            found.append(ring)
            taken.update(ring.cells())
    return found


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
