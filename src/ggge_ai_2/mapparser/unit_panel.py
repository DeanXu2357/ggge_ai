from __future__ import annotations

import functools
import json
from pathlib import Path

import cv2
import numpy as np

from ggge_ai_2.mapparser.contract import MechPanel, PanelIcon, PilotPanel, PilotState, UnitPanel
from ggge_ai_2.mapparser.hud import TEMPLATES

PANEL_TEMPLATES = TEMPLATES / "unit_panel"
Box = tuple[int, int, int, int]

# The panel of the selected unit at the top right: the left edge of the mech block, the
# left edge of the pilot block and the left edge of the portrait frame. Each edge is a
# straight vertical line between these rows.
PANEL_LINES = (1381, 1798, 2077)
PANEL_ROWS = (135, 255)
# A straight line is a sharp peak of the mean horizontal gradient. Map art, mech art and
# menus have edges too, but the edges are not straight, so the gradient has no peak.
LINE_PEAK_HALF = 3
LINE_AROUND = (5, 20)
LINE_PEAK_RATIO = 5.0

MECH_ICON: Box = (1395, 135, 1425, 165)
MECH_NAME: Box = (1428, 133, 1785, 170)
HP: Box = (1500, 183, 1632, 221)
EN: Box = (1690, 183, 1772, 221)
PILOT_ICON: Box = (1812, 135, 1842, 165)
PILOT_NAME: Box = (1845, 133, 2065, 170)
MP: Box = (1870, 183, 1958, 221)
STATE: Box = (1960, 184, 2068, 220)
DAMAGE: Box = (1846, 226, 2018, 264)
CHANCE_BANNER: Box = (2010, 262, 2150, 286)
CHANCE_COUNT: Box = (2168, 258, 2205, 290)
HP_CHANGE: Box = (1395, 222, 1640, 278)
EN_CHANGE: Box = (1678, 222, 1780, 278)
OVERLAY_AREA: Box = (1380, 120, 2210, 300)
# The preview numbers over the HP and EN bars cross the bottom row of the bars. The white
# part of the HP bar and the EN bar end above this row, so a shape that crosses it is a
# digit.
BAR_BOTTOM = 249
CHANGE_WHITE = 215
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
STATE_SATURATION = 90
STATE_VALUE = 150
STATE_SCORE = 0.6
DAMAGE_SCORE = 0.6
# The red banner of 'CHANCE STEP'.
BANNER_HUES = ((0, 10), (165, 179))
BANNER_SHARE = 0.2
NAME_SCORE = 0.85
NAME_SLACK = (4, 3)


def panel_line_peaks(image: np.ndarray) -> tuple[float, ...]:
    """Return the peak ratio of each panel line: the gradient at the line over the median
    gradient beside it."""
    top, bottom = PANEL_ROWS
    gray = cv2.cvtColor(image[top:bottom], cv2.COLOR_BGR2GRAY).astype(np.float32)
    gradient = np.abs(np.diff(gray, axis=1)).mean(axis=0)
    near, far = LINE_AROUND
    peaks: list[float] = []
    for x in PANEL_LINES:
        peak = gradient[x - LINE_PEAK_HALF : x + LINE_PEAK_HALF].max()
        around = np.concatenate([gradient[x - far : x - near], gradient[x + near : x + far]])
        peaks.append(float(peak / (np.median(around) + 1.0)))
    return tuple(peaks)


def has_unit_panel(image: np.ndarray) -> bool:
    return min(panel_line_peaks(image)) >= LINE_PEAK_RATIO


def read_unit_panel(image: np.ndarray) -> UnitPanel | None:
    if not has_unit_panel(image):
        return None
    mp = read_text(crop(image, MP))
    mp_now, _, mp_max = (mp or "").partition("/")
    chance = read_text(crop(image, CHANCE_COUNT)) if has_banner(image) else None
    return UnitPanel(
        MechPanel(
            icon=read_icon(crop(image, MECH_ICON)),
            name=read_name(crop(image, MECH_NAME), "mech"),
            hp=_number(read_text(crop(image, HP))),
            en=_number(read_text(crop(image, EN))),
            hp_change=read_change(change_mask(crop(image, HP_CHANGE), yellow=False), HP_CHANGE),
            en_change=read_change(change_mask(crop(image, EN_CHANGE), yellow=True), EN_CHANGE),
            overlay=read_overlay(crop(image, OVERLAY_AREA)),
        ),
        PilotPanel(
            icon=read_icon(crop(image, PILOT_ICON)),
            name=read_name(crop(image, PILOT_NAME), "pilot"),
            mp=_number(mp_now),
            mp_max=_number(mp_max),
            state=read_state(crop(image, STATE)),
            damage=read_damage(crop(image, DAMAGE)),
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
    shares = {
        icon: _hue_share(area, hues, ICON_SATURATION, ICON_VALUE)
        for icon, hues in ICON_HUES.items()
    }
    icon, share = max(shares.items(), key=lambda item: item[1])
    return icon if share >= ICON_SHARE else None


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


def has_banner(image: np.ndarray) -> bool:
    return (
        _hue_share(crop(image, CHANCE_BANNER), BANNER_HUES, ICON_SATURATION, ICON_VALUE)
        >= BANNER_SHARE
    )


def text_crop(area: np.ndarray) -> np.ndarray | None:
    """Return the white mask of a name cut to the box around its white pixels."""
    mask = white_mask(area)
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        return None
    return mask[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]


@functools.cache
def name_templates(kind: str) -> tuple[tuple[str, np.ndarray], ...]:
    index_path = PANEL_TEMPLATES / "names.json"
    if not index_path.exists():
        return ()
    index: dict[str, str] = json.loads(index_path.read_text(encoding="utf-8"))
    return tuple(
        (name, _load(PANEL_TEMPLATES / file))
        for file, name in index.items()
        if Path(file).stem.startswith(f"name_{kind}_")
    )


def read_name(area: np.ndarray, kind: str) -> str | None:
    """Return the name whose saved crop matches the name on the panel, or None for a name
    that has no saved crop."""
    found = text_crop(area)
    if found is None:
        return None
    slack_x, slack_y = NAME_SLACK
    best, score = None, NAME_SCORE
    for name, template in name_templates(kind):
        if (
            abs(template.shape[1] - found.shape[1]) > slack_x
            or abs(template.shape[0] - found.shape[0]) > slack_y
        ):
            continue
        pad_y = slack_y + max(0, template.shape[0] - found.shape[0])
        pad_x = slack_x + max(0, template.shape[1] - found.shape[1])
        padded = cv2.copyMakeBorder(
            found, slack_y, pad_y, slack_x, pad_x, cv2.BORDER_CONSTANT, value=0
        )
        match = similarity(padded, template)
        if match >= score:
            best, score = name, match
    return best


def change_mask(area: np.ndarray, yellow: bool) -> np.ndarray:
    if not yellow:
        return ((area.min(axis=2) >= CHANGE_WHITE) * 255).astype(np.uint8)
    hsv = cv2.cvtColor(area, cv2.COLOR_BGR2HSV)
    low, high = CHANGE_YELLOW_HUES
    inside = (hsv[:, :, 0] >= low) & (hsv[:, :, 0] <= high)
    strong = (hsv[:, :, 1] >= STATE_SATURATION) & (hsv[:, :, 2] >= STATE_VALUE)
    return ((inside & strong) * 255).astype(np.uint8)


def change_parts(mask: np.ndarray, box: Box) -> tuple[list[Box], bool]:
    """Return the digit boxes of a preview number and whether a minus sign is before them."""
    cross = BAR_BOTTOM - box[1]
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
    shapes = [(int(x), int(y), int(x + w), int(y + h)) for x, y, w, h, _ in stats[1:count]]
    digits = sorted(
        shape
        for shape in shapes
        if shape[1] < cross < shape[3] and shape[3] - shape[1] >= CHANGE_MIN_HEIGHT
    )
    if not digits:
        return [], False
    first = digits[0][0]
    minus = any(
        MINUS_WIDTH[0] <= right - left <= MINUS_WIDTH[1]
        and MINUS_HEIGHT[0] <= bottom - top <= MINUS_HEIGHT[1]
        and 0 <= first - right <= MINUS_GAP
        for left, top, right, bottom in shapes
    )
    return digits, minus


def read_change(mask: np.ndarray, box: Box) -> int | None:
    digits, minus = change_parts(mask, box)
    if not digits:
        return None
    labels: list[str] = []
    for digit in digits:
        label, score = max(
            (
                (label, similarity(glyph_image(mask, digit), template))
                for label, template in glyph_templates().items()
            ),
            key=lambda item: item[1],
        )
        if score < GLYPH_SCORE or not label.isdigit():
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
