from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

import cv2
import numpy as np

from ggge_ai_2.mapparser.contract import ScreenPoint, ViewCell

RIDGE_OFFSETS = (6, 12)
RIDGE_CLIP = 60
SEGMENT_RIDGE = 25
SEGMENT_MIN_LENGTH = 120
SEGMENT_MAX_GAP = 12
SEGMENT_MAX_TILT = 0.35
MIN_SEGMENTS = 8
MIN_CONVERGENCE = 1e-5
MIN_PITCH = 40.0
MAX_PITCH = 700.0
LINE_MERGE = 6.0
LINE_WEIGHT_CAP = 300.0
ROW_TO_COLUMN_PITCH = (0.5, 1.6)
ROW_PEAK = 0.08
COMB_TOLERANCE = 5.0
SUPPORT_RIDGE = 20
SUPPORT_RADIUS = 3
LINE_SUPPORTED = 0.3
MIN_SUPPORTED_COLUMNS = 5
MIN_SUPPORTED_ROWS = 3
MIN_SUPPORTED_SHARE = 0.5


@dataclass(frozen=True)
class Lattice:
    # The camera tilts down and does not roll. So the row lines stay horizontal, the column
    # lines meet at (apex, horizon), and 1 / (y - horizon) is linear in the row.

    width: int
    height: int
    horizon: float
    apex: float
    row_origin: float
    row_step: float
    column_origin: float
    column_step: float

    def project(self, column: float, row: float) -> tuple[float, float]:
        y = self.horizon + 1.0 / (self.row_origin + self.row_step * row)
        x = self.apex + (y - self.horizon) * (self.column_origin + self.column_step * column)
        return x, y

    def project_many(self, columns: np.ndarray, rows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        ys = self.horizon + 1.0 / (self.row_origin + self.row_step * rows)
        xs = self.apex + (ys - self.horizon) * (self.column_origin + self.column_step * columns)
        return xs, ys

    def center(self, cell: ViewCell) -> ScreenPoint:
        x, y = self.project(cell[0] + 0.5, cell[1] + 0.5)
        return round(x), round(y)

    def cell_at(self, point: ScreenPoint) -> ViewCell | None:
        x, y = point
        if y <= self.horizon:
            return None
        return math.floor(self.column_coordinate(x, y)), math.floor(self.row_coordinate(y))

    def inside(self, cell: ViewCell) -> bool:
        x, y = self.project(cell[0] + 0.5, cell[1] + 0.5)
        return 0 <= x < self.width and 0 <= y < self.height

    def cells(self) -> frozenset[ViewCell]:
        top = math.ceil(self.row_coordinate(0.0) - 0.5)
        bottom = math.ceil(self.row_coordinate(float(self.height)) - 0.5)
        found: set[ViewCell] = set()
        for row in range(top, bottom):
            _, y = self.project(0.0, row + 0.5)
            left = math.ceil(self.column_coordinate(0.0, y) - 0.5)
            right = math.ceil(self.column_coordinate(float(self.width), y) - 0.5)
            found.update((column, row) for column in range(left, right))
        return frozenset(cell for cell in found if self.inside(cell))

    def row_coordinate(self, y: float) -> float:
        return (1.0 / (y - self.horizon) - self.row_origin) / self.row_step

    def column_coordinate(self, x: float, y: float) -> float:
        return ((x - self.apex) / (y - self.horizon) - self.column_origin) / self.column_step


def read_lattice(image: np.ndarray) -> Lattice | None:
    height, width = image.shape[:2]
    middle = height / 2
    white = image.min(axis=2).astype(np.int16)
    column_ridge = ridge(white, axis=1)
    row_ridge = ridge(white, axis=0)
    segments = _vertical_segments(column_ridge)
    if len(segments) < MIN_SEGMENTS:
        return None
    vanishing = _vanishing_point(segments, middle)
    if vanishing is None:
        return None
    apex, horizon = vanishing
    scale = middle - horizon
    lines, weights = _merged((segments[:, 0] - apex) / scale, segments[:, 2], LINE_MERGE / scale)
    columns = _comb(lines, weights, MIN_PITCH / scale, MAX_PITCH / scale, COMB_TOLERANCE / scale)
    if columns is None:
        return None
    column_origin, column_step = columns
    near_column = _near(column_ridge, (1, 2 * SUPPORT_RADIUS + 1))
    first, last = _column_span(near_column, apex, horizon, column_origin, column_step)
    if last - first + 1 < MIN_SUPPORTED_COLUMNS:
        return None
    left = max(0, round(apex + scale * (column_origin + column_step * first)))
    right = min(width, round(apex + scale * (column_origin + column_step * last)))
    rows = _rows(row_ridge[:, left:right], horizon, column_step * scale, middle)
    if rows is None:
        return None
    lattice = Lattice(width, height, horizon, apex, rows[0], rows[1], column_origin, column_step)
    near_row = _near(row_ridge, (2 * SUPPORT_RADIUS + 1, 1))
    if not _rows_supported(lattice, near_row, first, last):
        return None
    return _normalized(lattice)


def _near(ridge: np.ndarray, kernel: tuple[int, int]) -> np.ndarray:
    return cv2.dilate(ridge, np.ones(kernel, np.uint8)) > SUPPORT_RIDGE


def _column_span(
    near_column: np.ndarray, apex: float, horizon: float, origin: float, step: float
) -> tuple[int, int]:
    """Return the first and the last column line that the frame shows.

    The span is empty (last < first) when too few lines in it show a ridge.
    The map can fill only a part of the frame, so lines outside the map
    do not count against the grid.
    """
    height, width = near_column.shape
    ys = np.linspace(0.0, float(height - 1), 120, dtype=np.float64)
    reach = [(x - apex) / (y - horizon) for x in (0, width - 1) for y in (0, height - 1)]
    lines = range(math.floor((min(reach) - origin) / step), math.ceil((max(reach) - origin) / step))
    supported = [
        line
        for line in lines
        if _share(near_column, apex + (ys - horizon) * (origin + step * line), ys) >= LINE_SUPPORTED
    ]
    return _dense_span(supported)


def _rows_supported(lattice: Lattice, near_row: np.ndarray, first: int, last: int) -> bool:
    height = near_row.shape[0]
    top = math.floor(lattice.row_coordinate(0.0))
    bottom = math.ceil(lattice.row_coordinate(height - 1.0))
    supported: list[int] = []
    for row in range(top, bottom + 1):
        columns = np.linspace(first, last, 120)
        points = [lattice.project(column, row) for column in columns]
        xs = np.array([x for x, _ in points])
        ys = np.array([y for _, y in points])
        if _share(near_row, xs, ys) >= LINE_SUPPORTED:
            supported.append(row)
    start, end = _dense_span(supported)
    return end - start + 1 >= MIN_SUPPORTED_ROWS


def _dense_span(supported: list[int]) -> tuple[int, int]:
    if not supported:
        return 0, -1
    first, last = supported[0], supported[-1]
    if len(supported) < MIN_SUPPORTED_SHARE * (last - first + 1):
        return 0, -1
    return first, last


def _share(near: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> float:
    height, width = near.shape
    column = np.round(xs).astype(int)
    row = np.round(ys).astype(int)
    inside = (column >= 0) & (column < width) & (row >= 0) & (row < height)
    if not inside.any():
        return 0.0
    return float(near[row[inside], column[inside]].mean())


def ridge(white: np.ndarray, axis: int) -> np.ndarray:
    ridge = np.zeros(white.shape, np.int16)
    for offset in RIDGE_OFFSETS:
        before = np.roll(white, offset, axis)
        after = np.roll(white, -offset, axis)
        ridge = np.maximum(ridge, np.minimum(white - before, white - after))
    return np.clip(ridge, 0, RIDGE_CLIP).astype(np.uint8)


def _vertical_segments(column_ridge: np.ndarray) -> np.ndarray:
    """Return rows of (x at the frame middle, dx/dy, length)."""
    mask = np.where(column_ridge > SEGMENT_RIDGE, 255, 0).astype(np.uint8)
    found = cv2.HoughLinesP(
        mask, 1, np.pi / 360, 80, minLineLength=SEGMENT_MIN_LENGTH, maxLineGap=SEGMENT_MAX_GAP
    )
    if found is None:
        return np.zeros((0, 3))
    ends = np.asarray(found, np.float64).reshape(-1, 4)
    x1, y1, x2, y2 = ends.T
    dy = y2 - y1
    keep = np.abs(x2 - x1) <= SEGMENT_MAX_TILT * np.abs(dy)
    x1, y1, x2, y2, dy = x1[keep], y1[keep], x2[keep], y2[keep], dy[keep]
    slope = (x2 - x1) / dy
    middle = column_ridge.shape[0] / 2
    return np.stack([x1 + slope * (middle - y1), slope, np.hypot(x2 - x1, dy)], axis=1)


def _vanishing_point(segments: np.ndarray, middle: float) -> tuple[float, float] | None:
    """Fit slope = convergence * (x - apex) to the segments with reweighted least squares.

    A grid line through the vanishing point (apex, horizon) has
    dx/dy = (x - apex) / (middle - horizon) at the frame middle.
    """
    x, slope, length = segments.T
    weight = length.copy()
    design = np.stack([x, np.ones_like(x)], axis=1)
    coefficients = np.zeros(2)
    for _ in range(8):
        root = np.sqrt(weight)
        coefficients = cast(
            np.ndarray, np.linalg.lstsq(design * root[:, None], slope * root, rcond=None)[0]
        )
        residual = np.abs(slope - design @ coefficients)
        scale = max(float(np.median(residual)) * 3.0, 0.002)
        weight = length * np.clip(1.0 - (residual / scale) ** 2, 0.0, None) ** 2
        if weight.sum() <= 0:
            return None
    convergence, intercept = float(coefficients[0]), float(coefficients[1])
    if convergence < MIN_CONVERGENCE:
        return None
    return -intercept / convergence, middle - 1.0 / convergence


def _merged(
    positions: np.ndarray, lengths: np.ndarray, gap: float
) -> tuple[np.ndarray, np.ndarray]:
    """Merge segments of one line, and cap the weight of each line.

    Without the cap, a few long lines of the background art outweigh
    the grid lines that units cut into short segments.
    """
    order = np.argsort(positions)
    positions, lengths = positions[order], lengths[order]
    groups = np.cumsum(np.concatenate([[0], np.diff(positions) > gap]))
    total = np.bincount(groups, lengths)
    centers = np.bincount(groups, lengths * positions) / total
    return centers, np.minimum(total, LINE_WEIGHT_CAP) / LINE_WEIGHT_CAP


def _comb(
    positions: np.ndarray, weights: np.ndarray, least: float, most: float, tolerance: float
) -> tuple[float, float] | None:
    """Fit equally spaced lines to weighted 1D positions.

    Return (origin, step) or None. Each candidate puts one line on one of the
    positions. The score of a candidate is the mean evidence on each of its
    lines times the share of all evidence that is on its lines. The first
    factor is low for a step that is a fraction of the true step, because
    some of its lines fall between the true lines. The second factor is low
    for a step that is a multiple of the true step, because some true lines
    fall between its lines.
    """
    if len(positions) < 3 or weights.sum() <= 0:
        return None
    span = float(positions.max() - positions.min()) + least
    steps = np.geomspace(least, most, 400)
    distance = positions[None, None, :] - positions[None, :, None]
    distance = distance - np.round(distance / steps[:, None, None]) * steps[:, None, None]
    on_line = np.exp(-0.5 * (distance / tolerance) ** 2) @ weights
    score = on_line * on_line * (steps / span / weights.sum())[:, None]
    best_step, anchor = divmod(int(np.argmax(score)), score.shape[1])
    step = float(steps[best_step])
    index = cast(np.ndarray, np.round((positions - positions[anchor]) / step))
    near = np.abs(positions - positions[anchor] - index * step) < 2 * tolerance
    if len(np.unique(index[near])) < 3:
        return None
    root = np.sqrt(weights[near])
    design = np.stack([np.ones(int(near.sum())), index[near]], axis=1)
    fit = np.linalg.lstsq(design * root[:, None], positions[near] * root, rcond=None)[0]
    return float(fit[0]), float(fit[1])


def _rows(
    row_ridge: np.ndarray, horizon: float, column_pitch: float, middle: float
) -> tuple[float, float] | None:
    profile = row_ridge.mean(axis=1) / RIDGE_CLIP
    profile = np.convolve(profile, np.ones(3) / 3, mode="same")
    ys = np.arange(len(profile))
    peak = (profile >= np.maximum.reduce([np.roll(profile, shift) for shift in range(-3, 4)])) & (
        profile > ROW_PEAK
    )
    peaks = ys[peak]
    if len(peaks) < 3:
        return None
    depth = 1.0 / (peaks - horizon)
    scale = (middle - horizon) ** 2
    least, most = (bound * column_pitch / scale for bound in ROW_TO_COLUMN_PITCH)
    fit = _comb(depth, profile[peaks], least, most, COMB_TOLERANCE / scale)
    if fit is None:
        return None
    origin, step = fit
    return origin, -step


def _normalized(lattice: Lattice) -> Lattice:
    raw = lattice.cells()
    if not raw:
        return lattice
    first_column = min(column for column, _ in raw)
    first_row = min(row for _, row in raw)
    return Lattice(
        lattice.width,
        lattice.height,
        lattice.horizon,
        lattice.apex,
        lattice.row_origin + lattice.row_step * first_row,
        lattice.row_step,
        lattice.column_origin + lattice.column_step * first_column,
        lattice.column_step,
    )
