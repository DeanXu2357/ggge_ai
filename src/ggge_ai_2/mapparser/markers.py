from __future__ import annotations

import functools
from collections.abc import Iterable
from dataclasses import dataclass

import cv2
import numpy as np

from ggge_ai_2.mapparser.contract import Marker, ViewCell
from ggge_ai_2.mapparser.hud import BACK, PREP_LIST, SWITCH_UNIT, template_match
from ggge_ai_2.mapparser.topview import CELL, TopView

SIDE_SPAN = (0.3, 0.7)
SIDE_DEPTH = 0.38
SIDE_INSET = (0.05, 0.3)
SIDE_VISIBLE = 0.6
# In top-view pixels: a line is brighter than the dips on its two sides within this reach.
SIDE_REACH = 8
# A frame shows one strong line, or four faint lines at matching gaps from the sides.
# Each threshold is (prominence, white level) of the line.
STRONG_LINE = (70.0, 180.0)
FAINT_LINE = (15.0, 0.0)
FAINT_GAP_DIFFERENCE = 8
# In top-view pixels: each search box is (left, top, right, bottom) in the cell.
FLAG_LEG = 6
FLAG_MARGIN = 3
FLAG_BOXES = {"top_right": (74, 0, 94, 20), "bottom_left": (9, 64, 29, 86)}
FLAG_SCORE = 0.65

# In top-view pixels: the bar is (width, height), the dot is (left, top, width, height)
# from the top left of the bar.
GLYPH_BAR = (13, 23)
GLYPH_DOT = (3, 28, 7, 7)
GLYPH_MARGIN = 7
GLYPH_CENTER = (0.52, 0.44)
GLYPH_SEARCH = 0.12
GLYPH_SCORE = 0.6
GLYPH_CONTRAST = 25.0

TINT_SPAN = (0.15, 0.85)
TINT_HUES = ((0, 10), (165, 179))
TINT_SATURATION = 90
TINT_VALUE = 110
TINT_SHARE = 0.5
# In top-view pixels: the range of a map weapon has diagonal stripes about twice this
# shift apart.
HATCH_SHIFT = 6
HATCH_RATIO = 2.5
HATCH_CONTRAST = 6.0


@dataclass(frozen=True)
class _Line:
    prominence: float
    white: float
    # The distance from the side in top-view pixels.
    gap: int


def read_markers(
    image: np.ndarray, view: TopView, cells: Iterable[ViewCell]
) -> dict[ViewCell, frozenset[Marker]]:
    """Return the markers on each cell.

    Each cell gets an entry, also a cell without markers. The game draws the move
    range and the weapon range only after the player selects a unit, so the other
    screens give no markers.
    """
    cells = tuple(cells)
    found: dict[ViewCell, frozenset[Marker]] = dict.fromkeys(cells, frozenset())
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    shown = {
        panel
        for panel in (BACK, PREP_LIST, SWITCH_UNIT)
        if template_match(gray, panel)[0] >= panel.threshold
    }
    if BACK not in shown or PREP_LIST in shown or not cells:
        return found
    # The enemy range on the overview has the same red tint as the weapon range.
    # Only the weapon screens show the back button without the switching-unit arrows.
    weapon_screen = SWITCH_UNIT not in shown
    for cell in cells:
        tile, white, visible = view.cell(cell)
        markers: set[Marker] = set()
        if _flagged(white, visible) or _framed(white, visible):
            markers.add(Marker.MOVE_RANGE)
            if _glyph(white, visible):
                markers.add(Marker.THREAT)
        if weapon_screen and _tinted(tile, visible):
            markers.add(Marker.WEAPON_RANGE)
        found[cell] = frozenset(markers)
    return found


@functools.cache
def _flag_template(corner: str) -> np.ndarray:
    """Return the white right triangle of the corner, in a dark margin."""
    leg, margin = FLAG_LEG, FLAG_MARGIN
    template = np.zeros((leg + 2 * margin, leg + 2 * margin), np.float32)
    for dy in range(leg):
        for dx in range(leg):
            if (dx <= dy) if corner == "top_right" else (dx >= dy):
                template[margin + dy, margin + dx] = 255.0
    return template


def _flagged(white: np.ndarray, visible: np.ndarray) -> bool:
    """Return True when a corner of the cell shows the white triangle of the move range.

    The frame of the move range has a small white triangle at its top-right corner and
    at its bottom-left corner. A sprite or a preview panel can hide one or both.
    """
    for corner, (left, top, right, bottom) in FLAG_BOXES.items():
        if not visible[top:bottom, left:right].all():
            continue
        scores = cv2.matchTemplate(
            white[top:bottom, left:right], _flag_template(corner), cv2.TM_CCOEFF_NORMED
        )
        if scores.max() >= FLAG_SCORE:
            return True
    return False


def _framed(white: np.ndarray, visible: np.ndarray) -> bool:
    """Return True when the cell shows the inner frame of the move range.

    The frame is a thin white line inside each side of the cell, apart from the grid
    line. The gap to the grid line differs between the sides and between frames.
    At a small gap, the frame line merges with the grid line.
    """
    low, high = (round(bound * CELL) for bound in SIDE_SPAN)
    depth = round(SIDE_DEPTH * CELL)
    sides = (
        (white[low:high, :depth], visible[low:high, :depth]),
        (white[low:high, ::-1][:, :depth], visible[low:high, ::-1][:, :depth]),
        (white[:depth, low:high].T, visible[:depth, low:high].T),
        (white[::-1][:depth, low:high].T, visible[::-1][:depth, low:high].T),
    )
    left, right, top, bottom = (_side_line(values, shown) for values, shown in sides)
    if any(_passes(line, STRONG_LINE) for line in (left, right, top, bottom)):
        return True
    # A small frame can be faint. Then each side must show its line, at a matching gap.
    return _faint_pair(left, right) and _faint_pair(top, bottom)


def _passes(line: _Line | None, threshold: tuple[float, float]) -> bool:
    return line is not None and line.prominence >= threshold[0] and line.white >= threshold[1]


def _faint_pair(first: _Line | None, second: _Line | None) -> bool:
    if first is None or second is None:
        return False
    if not (_passes(first, FAINT_LINE) and _passes(second, FAINT_LINE)):
        return False
    return abs(first.gap - second.gap) <= FAINT_GAP_DIFFERENCE


def _side_line(values: np.ndarray, shown: np.ndarray) -> _Line | None:
    """Return the most prominent line along the side.

    Each row of the arrays goes inward from the side. The line must be apart from
    the grid line on the side. The result is None when the HUD hides the side.
    """
    rows = shown.all(axis=1)
    if rows.mean() < SIDE_VISIBLE:
        return None
    profile = values[rows].mean(axis=0)
    low, high = (round(bound * CELL) for bound in SIDE_INSET)
    reach = SIDE_REACH
    prominence = np.array(
        [
            min(
                profile[inset] - profile[max(0, inset - reach) : inset].min(),
                profile[inset] - profile[inset + 1 : inset + reach + 1].min(),
            )
            for inset in range(low, high)
        ]
    )
    best = int(np.argmax(prominence))
    return _Line(float(prominence[best]), float(profile[low + best]), low + best)


@functools.cache
def _glyph_template() -> tuple[np.ndarray, np.ndarray]:
    """Return the exclamation mark and the mask of its glyph pixels."""
    bar_width, bar_height = GLYPH_BAR
    dot_left, dot_top, dot_width, dot_height = GLYPH_DOT
    margin = GLYPH_MARGIN
    width = bar_width + 2 * margin
    height = dot_top + dot_height + 2 * margin
    template = np.zeros((height, width), np.float32)
    template[margin : margin + bar_height, margin : margin + bar_width] = 255.0
    template[
        margin + dot_top : margin + dot_top + dot_height,
        margin + dot_left : margin + dot_left + dot_width,
    ] = 255.0
    return template, template > 0


def _glyph(white: np.ndarray, visible: np.ndarray) -> bool:
    """Return True when an exclamation mark shows at the middle of the frame."""
    template, glyph = _glyph_template()
    height, width = template.shape
    center_x, center_y = (round(bound * CELL) for bound in GLYPH_CENTER)
    reach = round(GLYPH_SEARCH * CELL)
    top = max(0, center_y - height // 2 - reach)
    left = max(0, center_x - width // 2 - reach)
    window = white[top : center_y + height // 2 + reach, left : center_x + width // 2 + reach]
    if not visible[top : top + window.shape[0], left : left + window.shape[1]].all():
        return False
    scores = cv2.matchTemplate(window, template, cv2.TM_CCOEFF_NORMED)
    _, best, _, (x, y) = cv2.minMaxLoc(scores)
    patch = window[y : y + height, x : x + width]
    contrast = float(patch[glyph].mean() - patch[~glyph].mean())
    return best >= GLYPH_SCORE and contrast >= GLYPH_CONTRAST


def _tinted(tile: np.ndarray, visible: np.ndarray) -> bool:
    """Return True when the red tint of the weapon range covers the cell.

    The range of a map weapon has an orange tint with diagonal stripes. It is not
    a weapon range.
    """
    low, high = (round(bound * CELL) for bound in TINT_SPAN)
    inner = tile[low:high, low:high]
    shown = visible[low:high, low:high]
    if not shown.any():
        return False
    hsv = cv2.cvtColor(inner, cv2.COLOR_BGR2HSV)
    hue = hsv[..., 0]
    red = np.zeros(hue.shape, bool)
    for first, last in TINT_HUES:
        red |= (hue >= first) & (hue <= last)
    red &= (hsv[..., 1] >= TINT_SATURATION) & (hsv[..., 2] >= TINT_VALUE)
    return float(red[shown].mean()) >= TINT_SHARE and not _hatched(hsv[..., 2])


def _hatched(value: np.ndarray) -> bool:
    """Return True when the value changes much more across one diagonal than along it."""
    shift = HATCH_SHIFT
    value = value.astype(np.float32)
    along = float(np.abs(value[:-shift, :-shift] - value[shift:, shift:]).mean())
    across = float(np.abs(value[:-shift, shift:] - value[shift:, :-shift]).mean())
    low, high = sorted((along, across))
    return high >= HATCH_CONTRAST and high >= HATCH_RATIO * low
