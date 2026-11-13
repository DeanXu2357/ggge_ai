from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ggge_ai_2.mapparser.contract import (
    MechPanel,
    NameTemplate,
    PanelIcon,
    PilotPanel,
    PilotState,
    UnitPanel,
)

PANEL_TEMPLATES = (
    Path(__file__).resolve().parents[3] / "assets" / "templates" / "mapparser" / "unit_panel"
)
Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class PanelLayout:
    lines: tuple[int, ...]
    mech_icon: Box
    mech_name: Box
    hp: Box
    en: Box
    hp_change: Box
    en_change: Box
    pilot_icon: Box
    pilot_name: Box
    mp: Box
    state: Box
    damage: Box
    chance_banner: Box
    chance_count: Box
    overlay_area: Box


PANEL_ROWS = (135, 255)
# The panel of the selected unit at the top right. The lines are the left edge of the mech
# block, the left edge of the pilot block and the left edge of the portrait frame.
SELECTED = PanelLayout(
    lines=(1381, 1798, 2077),
    mech_icon=(1395, 135, 1425, 165),
    mech_name=(1428, 133, 1785, 170),
    hp=(1500, 183, 1632, 221),
    en=(1690, 183, 1772, 221),
    hp_change=(1395, 222, 1640, 278),
    en_change=(1678, 222, 1780, 278),
    pilot_icon=(1812, 135, 1842, 165),
    pilot_name=(1845, 133, 2065, 170),
    mp=(1870, 183, 1958, 221),
    state=(1960, 184, 2068, 220),
    damage=(1846, 226, 2018, 264),
    chance_banner=(2010, 262, 2150, 286),
    chance_count=(2168, 258, 2205, 290),
    overlay_area=(1380, 120, 2210, 300),
)
# The enemy panel at the top left shows the two blocks of the selected panel in the other
# order: the pilot block is left of the mech block. Each block keeps its inner layout.
ENEMY_PILOT_SHIFT = 146 - 1798
ENEMY_MECH_SHIFT = 563 - 1381


def _shift(box: Box, dx: int) -> Box:
    left, top, right, bottom = box
    return (left + dx, top, right + dx, bottom)


# The enemy panel uses the right edge of the pilot block and the right edge of the mech
# block. The left edges are weak on a dark map, because the panel is dark too. A panel
# with mech art in the left block has no edge at the right of the art.
ENEMY = PanelLayout(
    lines=(554, 971),
    mech_icon=_shift(SELECTED.mech_icon, ENEMY_MECH_SHIFT),
    mech_name=_shift(SELECTED.mech_name, ENEMY_MECH_SHIFT),
    hp=_shift(SELECTED.hp, ENEMY_MECH_SHIFT),
    en=_shift(SELECTED.en, ENEMY_MECH_SHIFT),
    hp_change=_shift(SELECTED.hp_change, ENEMY_MECH_SHIFT),
    en_change=_shift(SELECTED.en_change, ENEMY_MECH_SHIFT),
    pilot_icon=_shift(SELECTED.pilot_icon, ENEMY_PILOT_SHIFT),
    pilot_name=_shift(SELECTED.pilot_name, ENEMY_PILOT_SHIFT),
    mp=_shift(SELECTED.mp, ENEMY_PILOT_SHIFT),
    state=_shift(SELECTED.state, ENEMY_PILOT_SHIFT),
    damage=_shift(SELECTED.damage, ENEMY_PILOT_SHIFT),
    chance_banner=_shift(SELECTED.chance_banner, ENEMY_PILOT_SHIFT),
    chance_count=_shift(SELECTED.chance_count, ENEMY_PILOT_SHIFT),
    overlay_area=(130, 120, 985, 300),
)
# A straight line is a sharp peak of the mean horizontal gradient. Map art, mech art and
# menus have edges too, but the edges are not straight, so the gradient has no peak.
LINE_PEAK_HALF = 3
LINE_AROUND = (5, 20)
LINE_PEAK_RATIO = 5.0

# The preview numbers over the HP and EN bars cross the bottom row of the bars. The white
# part of the HP bar and the EN bar end above this row, so a shape that crosses it is a
# digit.
BAR_BOTTOM = 249
CHANGE_WHITE = 215
# Over the red edge of a bar and over the red 'KILL' badge, the video compression tints the
# white digits pink. The mask also takes these pale pixels.
CHANGE_PALE_VALUE = 190
CHANGE_PALE_SATURATION = 90
CHANGE_YELLOW_HUES = (22, 35)
CHANGE_MIN_HEIGHT = 15
# The minus sign is a flat shape just left of the first digit.
MINUS_WIDTH = (4, 16)
MINUS_HEIGHT = (2, 8)
MINUS_GAP = 8
OVERLAY_SCORE = 0.8

WHITE = 170
GLYPH_HEIGHT = 24
GLYPH_WIDTH = 20
GLYPH_MIN_AREA = 12
GLYPH_SCORE = 0.5
# A digit is about 0.6 times as wide as it is tall. Only full-height glyphs are split.
DIGIT_ASPECT = 0.62
GLYPH_TALL = 0.8
GLYPH_LABELS = {"slash": "/", "times": "x"}

ICON_SATURATION = 120
ICON_VALUE = 110
ICON_SHARE = 0.15
# OpenCV hues (0 to 179) of the icons before the names.
ICON_HUES = {
    PanelIcon.RED: ((0, 10), (165, 179)),
    PanelIcon.YELLOW: ((15, 40),),
    PanelIcon.BLUE: ((95, 130),),
}
# The gray icon of an enemy has no strong hue. The test for the gray icon comes after the
# test for the hues, because the dark panel behind a colored icon is gray too.
# The panels are see-through, so the corners of the icon box show the map behind the
# panel, for example the red move range of an enemy (map20261112-4). Only the round
# middle of the box, inside the octagon of the icon, counts.
ICON_RADIUS = 0.42
GRAY_SATURATION = 40
GRAY_VALUES = (60, 150)
GRAY_SHARE = 0.3
STATE_SATURATION = 90
STATE_VALUE = 150
STATE_SCORE = 0.6
DAMAGE_SCORE = 0.6
# The red banner of 'CHANCE STEP'.
BANNER_HUES = ((0, 10), (165, 179))
BANNER_SHARE = 0.2


def panel_line_peaks(image: np.ndarray, layout: PanelLayout) -> tuple[float, ...]:
    """Return the peak ratio of each panel line: the gradient at the line over the median
    gradient beside it."""
    top, bottom = PANEL_ROWS
    gray = cv2.cvtColor(image[top:bottom], cv2.COLOR_BGR2GRAY).astype(np.float32)
    gradient = np.abs(np.diff(gray, axis=1)).mean(axis=0)
    near, far = LINE_AROUND
    peaks: list[float] = []
    for x in layout.lines:
        peak = gradient[x - LINE_PEAK_HALF : x + LINE_PEAK_HALF].max()
        around = np.concatenate([gradient[x - far : x - near], gradient[x + near : x + far]])
        peaks.append(float(peak / (np.median(around) + 1.0)))
    return tuple(peaks)


def has_panel(image: np.ndarray, layout: PanelLayout) -> bool:
    return min(panel_line_peaks(image, layout)) >= LINE_PEAK_RATIO


def read_panel(image: np.ndarray, layout: PanelLayout) -> UnitPanel | None:
    if not has_panel(image, layout):
        return None
    mp = read_text(crop(image, layout.mp))
    mp_now, _, mp_max = (mp or "").partition("/")
    chance = (
        read_text(crop(image, layout.chance_count))
        if has_banner(crop(image, layout.chance_banner))
        else None
    )
    return UnitPanel(
        MechPanel(
            icon=read_icon(crop(image, layout.mech_icon)),
            name=read_name(crop(image, layout.mech_name)),
            hp=_number(read_text(crop(image, layout.hp))),
            en=_number(read_text(crop(image, layout.en))),
            hp_change=read_change(
                change_mask(crop(image, layout.hp_change), yellow=False), layout.hp_change
            ),
            en_change=read_change(
                change_mask(crop(image, layout.en_change), yellow=True), layout.en_change
            ),
            overlay=read_overlay(crop(image, layout.overlay_area)),
        ),
        PilotPanel(
            icon=read_icon(crop(image, layout.pilot_icon)),
            name=read_name(crop(image, layout.pilot_name)),
            mp=_number(mp_now),
            mp_max=_number(mp_max),
            state=read_state(crop(image, layout.state)),
            damage=read_damage(crop(image, layout.damage)),
            chance_step=None if chance is None else _number(chance.removeprefix("x")),
        ),
    )


def crop(image: np.ndarray, box: Box) -> np.ndarray:
    left, top, right, bottom = box
    return image[top:bottom, left:right]


def white_mask(area: np.ndarray) -> np.ndarray:
    return ((area.min(axis=2) >= WHITE) * 255).astype(np.uint8)


def glyph_boxes(mask: np.ndarray) -> list[Box]:
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    boxes = [
        (int(x), int(y), int(x + w), int(y + h))
        for x, y, w, h, area in stats[1:count]
        if area >= GLYPH_MIN_AREA
    ]
    tallest = max((bottom - top for _, top, _, bottom in boxes), default=0)
    return sorted(part for box in boxes for part in _split(box, tallest))


def _split(box: Box, tallest: int) -> list[Box]:
    """Split a box of touching digits: the game draws '44' as one connected shape."""
    left, top, right, bottom = box
    height, width = bottom - top, right - left
    if height < GLYPH_TALL * tallest:
        return [box]
    parts = max(1, round(width / (DIGIT_ASPECT * height)))
    edges = [left + round(width * k / parts) for k in range(parts + 1)]
    return [(edges[k], top, edges[k + 1], bottom) for k in range(parts)]


def glyph_image(mask: np.ndarray, box: Box) -> np.ndarray:
    """Scale a glyph to the glyph height and center it in the glyph width, so that a narrow
    glyph such as '1' stays narrow."""
    left, top, right, bottom = box
    glyph = mask[top:bottom, left:right]
    width = max(1, min(GLYPH_WIDTH, round(glyph.shape[1] * GLYPH_HEIGHT / glyph.shape[0])))
    scaled = cv2.resize(glyph, (width, GLYPH_HEIGHT), interpolation=cv2.INTER_AREA)
    out = np.zeros((GLYPH_HEIGHT, GLYPH_WIDTH), np.uint8)
    start = (GLYPH_WIDTH - width) // 2
    out[:, start : start + width] = scaled
    return out


def _load(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    assert image is not None, path
    return image


@functools.cache
def glyph_templates() -> dict[str, np.ndarray]:
    templates: dict[str, np.ndarray] = {}
    for path in sorted(PANEL_TEMPLATES.glob("glyph_*.png")):
        name = path.stem.removeprefix("glyph_")
        templates[GLYPH_LABELS.get(name, name)] = _load(path)
    return templates


# The preview numbers over the bars use a narrower font than HP, EN and MP.
@functools.cache
def change_templates() -> dict[str, np.ndarray]:
    return {
        path.stem.removeprefix("change_"): _load(path)
        for path in sorted(PANEL_TEMPLATES.glob("change_*.png"))
    }


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    _, best, _, _ = cv2.minMaxLoc(cv2.matchTemplate(a, b, cv2.TM_CCOEFF_NORMED))
    return float(best)


def read_text(area: np.ndarray) -> str | None:
    """Return the digits, '/' and 'x' of a white text line, or None when a glyph matches no
    template."""
    mask = white_mask(area)
    labels: list[str] = []
    for box in glyph_boxes(mask):
        glyph = glyph_image(mask, box)
        label, score = max(
            ((label, similarity(glyph, template)) for label, template in glyph_templates().items()),
            key=lambda item: item[1],
        )
        if score < GLYPH_SCORE:
            return None
        labels.append(label)
    return "".join(labels) or None


def _number(text: str | None) -> int | None:
    return int(text) if text and text.isdigit() else None


def _hue_share(
    area: np.ndarray, hues: tuple[tuple[int, int], ...], saturation: int, value: int
) -> float:
    hsv = cv2.cvtColor(area, cv2.COLOR_BGR2HSV)
    strong = (hsv[:, :, 1] >= saturation) & (hsv[:, :, 2] >= value)
    hue = hsv[:, :, 0]
    inside = np.zeros_like(strong)
    for low, high in hues:
        inside |= (hue >= low) & (hue <= high)
    return float(np.count_nonzero(strong & inside)) / strong.size


def read_icon(area: np.ndarray) -> PanelIcon | None:
    height, width = area.shape[:2]
    rows, columns = np.mgrid[:height, :width]
    middle = (columns - (width - 1) / 2) ** 2 + (rows - (height - 1) / 2) ** 2 <= (
        ICON_RADIUS * min(height, width)
    ) ** 2
    hsv = cv2.cvtColor(area, cv2.COLOR_BGR2HSV)
    hue, saturation, value = (hsv[:, :, channel][middle] for channel in range(3))
    strong = (saturation >= ICON_SATURATION) & (value >= ICON_VALUE)
    shares: dict[PanelIcon, float] = {}
    for icon, hues in ICON_HUES.items():
        inside = np.zeros(hue.shape, bool)
        for low, high in hues:
            inside |= (hue >= low) & (hue <= high)
        shares[icon] = float((strong & inside).mean())
    icon, share = max(shares.items(), key=lambda item: item[1])
    if share >= ICON_SHARE:
        return icon
    low, high = GRAY_VALUES
    gray = (saturation < GRAY_SATURATION) & (value >= low) & (value <= high)
    return PanelIcon.GRAY if gray.mean() >= GRAY_SHARE else None


def color_mask(area: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(area, cv2.COLOR_BGR2HSV)
    return (((hsv[:, :, 1] >= STATE_SATURATION) & (hsv[:, :, 2] >= STATE_VALUE)) * 255).astype(
        np.uint8
    )


def read_state(area: np.ndarray) -> PilotState | None:
    mask = color_mask(area)
    best, score = None, STATE_SCORE
    for state in PilotState:
        template = _load(PANEL_TEMPLATES / f"state_{state.name.lower()}.png")
        found = similarity(mask, template)
        if found >= score:
            best, score = state, found
    return best


def read_damage(area: np.ndarray) -> int | None:
    mask = white_mask(area)
    best, score = None, DAMAGE_SCORE
    for path in sorted(PANEL_TEMPLATES.glob("damage_*.png")):
        found = similarity(mask, _load(path))
        if found >= score:
            best, score = int(path.stem.removeprefix("damage_")), found
    return best


def has_banner(area: np.ndarray) -> bool:
    return _hue_share(area, BANNER_HUES, ICON_SATURATION, ICON_VALUE) >= BANNER_SHARE


def text_crop(area: np.ndarray) -> np.ndarray | None:
    """Return the white mask of a name cut to the box around its white pixels."""
    mask = white_mask(area)
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        return None
    return mask[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]


def read_name(area: np.ndarray) -> NameTemplate | None:
    found = text_crop(area)
    return None if found is None else NameTemplate(found)


def change_mask(area: np.ndarray, yellow: bool) -> np.ndarray:
    hsv = cv2.cvtColor(area, cv2.COLOR_BGR2HSV)
    if not yellow:
        pale = (hsv[:, :, 2] >= CHANGE_PALE_VALUE) & (hsv[:, :, 1] <= CHANGE_PALE_SATURATION)
        return (((area.min(axis=2) >= CHANGE_WHITE) | pale) * 255).astype(np.uint8)
    low, high = CHANGE_YELLOW_HUES
    inside = (hsv[:, :, 0] >= low) & (hsv[:, :, 0] <= high)
    strong = (hsv[:, :, 1] >= STATE_SATURATION) & (hsv[:, :, 2] >= STATE_VALUE)
    return ((inside & strong) * 255).astype(np.uint8)


def change_glyphs(mask: np.ndarray, box: Box) -> tuple[list[np.ndarray], bool]:
    """Return the glyph images of a preview number and whether a minus sign is before them.

    The edge of the bar and the red 'KILL' badge cut a digit into parts. A glyph joins the
    part that crosses the bottom row of the bar with the other parts in the same columns,
    and it keeps the rows of the full digits, so a missing stroke stays missing and does
    not stretch the rest.
    """
    cross = BAR_BOTTOM - box[1]
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
    shapes = {
        index: (int(x), int(y), int(x + w), int(y + h))
        for index, (x, y, w, h, _) in enumerate(stats[1:count], start=1)
    }
    digits = sorted(
        (shape, index)
        for index, shape in shapes.items()
        if shape[1] < cross < shape[3] and shape[3] - shape[1] >= CHANGE_MIN_HEIGHT
    )
    if not digits:
        return [], False
    top = min(shape[1] for shape, _ in digits)
    bottom = max(shape[3] for shape, _ in digits)
    digit_indexes = {index for _, index in digits}
    glyphs: list[np.ndarray] = []
    for (left, _, right, _), index in digits:
        parts = [index] + [
            other
            for other, (o_left, o_top, o_right, o_bottom) in shapes.items()
            if other not in digit_indexes
            and left <= (o_left + o_right) / 2 < right
            and o_top >= top
            and o_bottom <= bottom
        ]
        own = (np.isin(labels, parts) * 255).astype(np.uint8)
        glyphs.append(glyph_image(own, (left, top, right, bottom)))
    first = digits[0][0][0]
    minus = any(
        MINUS_WIDTH[0] <= right - left <= MINUS_WIDTH[1]
        and MINUS_HEIGHT[0] <= bottom - top <= MINUS_HEIGHT[1]
        and 0 <= first - right <= MINUS_GAP
        for left, top, right, bottom in shapes.values()
    )
    return glyphs, minus


def read_change(mask: np.ndarray, box: Box) -> int | None:
    glyphs, minus = change_glyphs(mask, box)
    if not glyphs:
        return None
    labels: list[str] = []
    for glyph in glyphs:
        label, score = max(
            (
                (label, similarity(glyph, template))
                for label, template in change_templates().items()
            ),
            key=lambda item: item[1],
        )
        if score < GLYPH_SCORE:
            return None
        labels.append(label)
    value = int("".join(labels))
    return -value if minus else value


@functools.cache
def overlay_templates() -> tuple[tuple[str, np.ndarray], ...]:
    index_path = PANEL_TEMPLATES / "overlays.json"
    if not index_path.exists():
        return ()
    index: dict[str, str] = json.loads(index_path.read_text(encoding="utf-8"))
    return tuple((text, _load(PANEL_TEMPLATES / file)) for file, text in index.items())


def read_overlay(area: np.ndarray) -> str | None:
    """Return the text of a saved overlay that shows over the panel, or None."""
    mask = color_mask(area)
    best, score = None, OVERLAY_SCORE
    for text, template in overlay_templates():
        found = similarity(mask, template)
        if found >= score:
            best, score = text, found
    return best
