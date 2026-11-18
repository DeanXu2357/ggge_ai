from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ggge_ai_2.mapparser.contract import TapMarkReading, Terrain, ViewCell
from ggge_ai_2.mapparser.lattice import Lattice
from ggge_ai_2.mapparser.region import Region
from ggge_ai_2.mapparser.topview import CELL, TopView

TERRAIN_TEMPLATES = (
    Path(__file__).resolve().parents[3] / "assets" / "templates" / "mapparser" / "terrain"
)

# The fill of the tapped cell is a translucent overlay: inside = share * FILL_COLOR +
# (1 - share) * outside. Each side of the cell compares a strip inside with a strip outside,
# in top view pixels from the side. FILL_COLOR is fitted to the ruled frames map20261112-5
# to -34 and the frames of run 20261116-134032; a fitted channel can be above 255.
FILL_COLOR = np.array([285.0, 211.0, 23.0])
FILL_STRIP = (10, 20)
FILL_SIDES_MIN = 3
FILL_VISIBLE = 0.8
# A strong fill counts alone. A weak fill counts only with the triangle above the cell: on
# grass, a gray cell inside a red move range fits the overlay as well as a faint fill.
FILL_SHARE_MIN = 0.18
FILL_RESIDUAL_MAX = 0.6
STRONG_SHARE_MIN = 0.3
STRONG_RESIDUAL_MAX = 0.35

# The terrain box and its triangle are screen UI of a fixed size. All positions are in
# frame pixels from the tip of the triangle. The values come from the ruled frames
# map20261112-5 to -30 of the test phone R5CRC37JBYJ (2340x1080).
TRIANGLE = (33.0, 26.0)
# The tip is this far above the middle of the top edge of the marked cell.
TIP_ABOVE = 4.0
# In run 20261116-134032 the tip was up to 6 px off the projected top edge, in x and in y.
TIP_SEARCH = 8
BOX_GAP = 11.0
BOX_BOTTOM_HALF = 36.0
BOX_SIDE_SPAN = (-88.0, -44.0)
# The width of the box for one, two and three icons.
BOX_WIDTHS = (84.0, 146.0, 211.0)
ICON_CENTER_Y = -62.0
ICON_PITCH = 63.0
ICON_SEARCH = 4
# The (width, height) of an icon template.
ICON_SIZE = (48, 34)

SIDE_SAMPLES = 20
SIDE_SPAN = (0.12, 0.88)
# In frame pixels along the normal of a side.
SIDE_REACH = np.arange(-3, 4)
BOX_REACH = np.arange(-4, 5)
# An edge pixel has a gradient of at least EDGE_MIN across the side, and the gradient
# points across the side within the share EDGE_ALIGN of its length.
EDGE_MIN = 30.0
EDGE_ALIGN = 0.8
# The role icon and the chevrons above a unit also have the two slanted sides, so a
# triangle needs the bottom edge of the box above it. Only a box outside the frame
# lets a triangle count alone, with a higher score.
TRIANGLE_WITH_BOX = 0.55
BOX_BOTTOM_MIN = 0.85
TRIANGLE_ALONE = 0.85
BOX_SIDE_MIN = 0.8
ICON_MIN = 0.6


@dataclass(frozen=True)
class _Segment:
    # The points are relative to the tip of the triangle.
    points: np.ndarray
    normal: np.ndarray


@dataclass(frozen=True)
class _Edges:
    gx: np.ndarray
    gy: np.ndarray
    magnitude: np.ndarray


def _segment(
    start: tuple[float, float], end: tuple[float, float], samples: int, span: tuple[float, float]
) -> _Segment:
    p, q = np.array(start), np.array(end)
    direction = (q - p) / np.linalg.norm(q - p)
    t = np.linspace(span[0], span[1], samples)
    return _Segment(p[None] + (q - p)[None] * t[:, None], np.array([-direction[1], direction[0]]))


def _triangle_sides() -> tuple[_Segment, ...]:
    width, height = TRIANGLE
    left, right, tip = (-width / 2, -height), (width / 2, -height), (0.0, 0.0)
    return tuple(
        _segment(start, end, SIDE_SAMPLES, SIDE_SPAN)
        for start, end in ((left, right), (right, tip), (tip, left))
    )


SIDES = _triangle_sides()
BOX_BOTTOM_Y = -TRIANGLE[1] - BOX_GAP
BOX_BOTTOM = _segment((-BOX_BOTTOM_HALF, BOX_BOTTOM_Y), (BOX_BOTTOM_HALF, BOX_BOTTOM_Y), 24, (0, 1))


def read_tap_mark(
    image: np.ndarray,
    lattice: Lattice,
    region: Region,
    view: TopView,
    empty: frozenset[ViewCell],
) -> TapMarkReading | None:
    """Return the tapped cell by its fill, and its terrain by the box above it.

    'empty' holds the lattice cells without a unit; only an empty cell takes the mark.
    """
    edges = _edges(image)
    marked: list[tuple[ViewCell, np.ndarray | None]] = []
    for cell in sorted(region.lattice_cells & empty):
        fill = _fill(view, cell)
        if fill is None:
            continue
        share, residual = fill
        if share < FILL_SHARE_MIN or residual > FILL_RESIDUAL_MAX:
            continue
        tip = _tip(edges, lattice, cell)
        if tip is not None or (share >= STRONG_SHARE_MIN and residual <= STRONG_RESIDUAL_MAX):
            marked.append((cell, tip))
    if len(marked) != 1:
        return None
    cell, tip = marked[0]
    return TapMarkReading(
        region.to_view(cell), None if tip is None else _terrain(image, edges, tip)
    )


def find_tip(image: np.ndarray, lattice: Lattice, region: Region) -> np.ndarray | None:
    """Return the tip of the triangle of the tap mark in frame pixels."""
    edges = _edges(image)
    tips = [
        tip
        for cell in sorted(region.lattice_cells)
        if (tip := _tip(edges, lattice, cell)) is not None
    ]
    return tips[0] if len(tips) == 1 else None


def _fill(view: TopView, cell: ViewCell) -> tuple[float, float] | None:
    """Return the overlay share of the fill and the residual of the fit over the rise, or
    None when fewer than FILL_SIDES_MIN sides show."""
    left, top = view.origin(cell)
    height, width = view.visible.shape
    near, far = FILL_STRIP
    along_x = slice(left + far, left + CELL - far)
    along_y = slice(top + far, top + CELL - far)
    spans = (
        ((slice(top + near, top + far), along_x), (slice(top - far, top - near), along_x)),
        (
            (slice(top + CELL - far, top + CELL - near), along_x),
            (slice(top + CELL + near, top + CELL + far), along_x),
        ),
        ((along_y, slice(left + near, left + far)), (along_y, slice(left - far, left - near))),
        (
            (along_y, slice(left + CELL - far, left + CELL - near)),
            (along_y, slice(left + CELL + near, left + CELL + far)),
        ),
    )
    rises: list[np.ndarray] = []
    toward: list[np.ndarray] = []
    for inner, outer in spans:
        if min(span.start for span in (*inner, *outer)) < 0:
            continue
        if max(inner[0].stop, outer[0].stop) > height or max(inner[1].stop, outer[1].stop) > width:
            continue
        shown_in, shown_out = view.visible[inner], view.visible[outer]
        if shown_in.mean() < FILL_VISIBLE or shown_out.mean() < FILL_VISIBLE:
            continue
        inside = view.image[inner][shown_in].astype(np.float32).mean(axis=0)
        outside = view.image[outer][shown_out].astype(np.float32).mean(axis=0)
        rises.append(inside - outside)
        toward.append(FILL_COLOR - outside)
    if len(rises) < FILL_SIDES_MIN:
        return None
    rise: np.ndarray = np.array(rises)
    base: np.ndarray = np.array(toward)
    share = float((rise * base).sum()) / max(float((base * base).sum()), 1e-6)
    left_over = float(np.sqrt(((rise - share * base) ** 2).sum()))
    residual = left_over / max(float(np.sqrt((rise * rise).sum())), 1e-6)
    return share, residual


def _tip(edges: _Edges, lattice: Lattice, cell: ViewCell) -> np.ndarray | None:
    """Return the tip of the triangle above the cell, or None."""
    top = np.array(lattice.project(cell[0] + 0.5, cell[1]))
    shifts = np.array(
        [
            (dx, dy)
            for dy in range(-TIP_SEARCH, TIP_SEARCH + 1)
            for dx in range(-TIP_SEARCH, TIP_SEARCH + 1)
        ],
        float,
    )
    candidates = (top + np.array([0.0, -TIP_ABOVE]) + shifts)[None]
    # The three sides share one shift along the normals and one sign of the gradient:
    # edges of a busy background match the slant of a side, but not one outline.
    scores = np.min(np.stack([_support(edges, candidates, side, SIDE_REACH) for side in SIDES]), 0)
    triangle = scores.reshape(len(shifts), -1).max(axis=1)
    # A grid line next to the triangle can score higher at a shift without the box, so
    # each shift is tried from the best down.
    for index in np.argsort(-triangle, kind="stable"):
        score = float(triangle[index])
        if score < TRIANGLE_WITH_BOX:
            return None
        if _counts(edges, candidates[0, index], score):
            return candidates[0, index]
    return None


def _counts(edges: _Edges, tip: np.ndarray, triangle: float) -> bool:
    if not _inside(edges, tip, BOX_BOTTOM, BOX_REACH):
        return triangle >= TRIANGLE_ALONE
    box = _support(edges, tip[None, None], BOX_BOTTOM, BOX_REACH).max()
    return triangle >= TRIANGLE_WITH_BOX and box >= BOX_BOTTOM_MIN


def _edges(image: np.ndarray) -> _Edges:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1)
    return _Edges(gx, gy, np.hypot(gx, gy))


def _support(edges: _Edges, tips: np.ndarray, segment: _Segment, reach: np.ndarray) -> np.ndarray:
    """Return the share of the sample points on an edge, with the shape
    tips.shape[:-1] + (2, len(reach)): one share for each sign of the gradient and
    each shift of the segment along its normal."""
    height, width = edges.magnitude.shape
    points = (
        tips[..., None, None, :]
        + segment.points[:, None, :]
        + reach[None, :, None] * segment.normal[None, None, :]
    )
    xs = np.rint(points[..., 0]).astype(int)
    ys = np.rint(points[..., 1]).astype(int)
    inside = (xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)
    xs, ys = np.clip(xs, 0, width - 1), np.clip(ys, 0, height - 1)
    across = edges.gx[ys, xs] * segment.normal[0] + edges.gy[ys, xs] * segment.normal[1]
    strong = (
        inside
        & (np.abs(across) >= EDGE_MIN)
        & (np.abs(across) >= EDGE_ALIGN * edges.magnitude[ys, xs])
    )
    rising = (strong & (across > 0)).mean(axis=-2)
    falling = (strong & (across < 0)).mean(axis=-2)
    return np.stack([rising, falling], axis=-2)


def _inside(edges: _Edges, tip: np.ndarray, segment: _Segment, reach: np.ndarray) -> bool:
    height, width = edges.magnitude.shape
    points = tip[None, None] + segment.points[:, None] + reach[None, :, None] * segment.normal
    return bool(
        (points[..., 0] >= 0).all()
        and (points[..., 0] < width).all()
        and (points[..., 1] >= 0).all()
        and (points[..., 1] < height).all()
    )


# A vertical grid line can stand where a box side would stand, so a box width counts
# only together with the icons in its slots.
def _terrain(image: np.ndarray, edges: _Edges, tip: np.ndarray) -> tuple[Terrain, ...] | None:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    best: tuple[float, tuple[Terrain, ...]] | None = None
    for count, width in enumerate(BOX_WIDTHS, 1):
        if not _box_sides(edges, tip, width):
            continue
        icons = [
            _icon(gray, tip + np.array([(slot - (count - 1) / 2) * ICON_PITCH, ICON_CENTER_Y]))
            for slot in range(count)
        ]
        if any(icon is None for icon in icons):
            continue
        score = min(icon[0] for icon in icons if icon is not None)
        if best is None or score > best[0]:
            best = (score, tuple(icon[1] for icon in icons if icon is not None))
    return None if best is None else best[1]


def _box_sides(edges: _Edges, tip: np.ndarray, width: float) -> bool:
    sides = [
        _segment((x, BOX_SIDE_SPAN[0]), (x, BOX_SIDE_SPAN[1]), 16, (0, 1))
        for x in (-width / 2, width / 2)
    ]
    return all(
        _inside(edges, tip, side, SIDE_REACH)
        and float(_support(edges, tip[None, None], side, SIDE_REACH).max()) >= BOX_SIDE_MIN
        for side in sides
    )


def _icon(gray: np.ndarray, center: np.ndarray) -> tuple[float, Terrain] | None:
    best: tuple[float, Terrain] | None = None
    for terrain, template in terrain_templates().items():
        height, width = template.shape
        left = int(round(center[0] - width / 2)) - ICON_SEARCH
        top = int(round(center[1] - height / 2)) - ICON_SEARCH
        right, bottom = left + width + 2 * ICON_SEARCH, top + height + 2 * ICON_SEARCH
        if left < 0 or top < 0 or right > gray.shape[1] or bottom > gray.shape[0]:
            return None
        window = gray[top:bottom, left:right]
        score = float(cv2.minMaxLoc(cv2.matchTemplate(window, template, cv2.TM_CCOEFF_NORMED))[1])
        if best is None or score > best[0]:
            best = (score, terrain)
    if best is None or best[0] < ICON_MIN:
        return None
    return best


@functools.cache
def terrain_templates() -> dict[Terrain, np.ndarray]:
    templates: dict[Terrain, np.ndarray] = {}
    for terrain in Terrain:
        image = cv2.imread(str(TERRAIN_TEMPLATES / f"{terrain.value}.png"), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise FileNotFoundError(TERRAIN_TEMPLATES / f"{terrain.value}.png")
        templates[terrain] = image
    return templates
