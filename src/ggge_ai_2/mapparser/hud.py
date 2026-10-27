from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ggge_ai_2.mapparser.contract import ScreenPoint, ViewCell
from ggge_ai_2.mapparser.lattice import Lattice

# A rectangle is (left, top, right, bottom) in frame pixels. Right and bottom are excluded.
Rect = tuple[int, int, int, int]

TEMPLATES = Path(__file__).resolve().parents[3] / "assets" / "templates" / "mapparser"
TEMPLATE_MARGIN = 16

CARD_LEFT = 218
CARD_PITCH = 175
CARD_SLOTS = 12
CARD_RECT = (-3, 808, 160, 1025)
CARD_BAR = (4, 996, 36, 1006)
CARD_BAR_HUE = (100, 122)
CARD_BAR_SHARE = 0.8

BUTTON_ROW = (880, 840, 1650, 1080)
BUTTON_CENTERS = (619, 804, 988, 1173, 1357, 1550)
RIGHT_BUTTON_LEFT = 1357
BUTTON_CENTER_Y = 932
BUTTON_RADII = (68, 84)
BUTTON_SEARCH = 16
BUTTON_EDGE = 20.0
BUTTON_SHARE = 0.85
BUTTON_RECT = (-96, -92, 96, 148)

ACTION_RECT = (1700, 765, 2340, 1080)
ACTION_ARC_RECT = (1700, 545, 2340, 870)
PREP_ROW = (-10, 830, 0, 1080)
PREP_ROW_CENTER = 965
BANNER_RECT = (975, 50, 1385, 295)
BANNER_PROBE = (990, 95, 1370, 260)
BANNER_SHARE = 0.2
INFO_PANEL_RECT = (1538, 280, 2216, 545)


@dataclass(frozen=True)
class TemplatePanel:
    template: str
    # The template is searched within TEMPLATE_MARGIN of this rectangle.
    anchor: Rect
    threshold: float
    covers: tuple[Rect, ...]


MENU = TemplatePanel("menu", (2140, 26, 2200, 86), 0.7, ((1735, 10, 2218, 98),))
TURN = TemplatePanel("turn", (172, 74, 262, 101), 0.7, ((150, 5, 800, 112),))
END_TURN = TemplatePanel("end_turn", (240, 165, 360, 202), 0.7, ((150, 145, 442, 222),))
CHANGE_DEPLOY = TemplatePanel("change_deploy", (235, 268, 405, 296), 0.7, ((150, 245, 442, 318),))
PROMPT = TemplatePanel("prompt", (220, 752, 540, 792), 0.7, ((195, 738, 1240, 802),))
UNIT_LIST = TemplatePanel("unit_list", (1830, 740, 2020, 790), 0.7, ((1798, 728, 2170, 802),))
BACK = TemplatePanel("back", (1765, 930, 1845, 1015), 0.7, ())
STANDBY = TemplatePanel("standby", (2060, 615, 2140, 690), 0.7, (ACTION_ARC_RECT,))
# The arrows are thin lines over the map, so the match score stays lower than for other panels.
SWITCH_UNIT = TemplatePanel("switch_unit", (200, 895, 260, 965), 0.5, ((168, 868, 422, 1068),))
PREP_LIST = TemplatePanel("prep_list", (440, 898, 760, 948), 0.7, ())
LEFT_UNIT = TemplatePanel("hp", (575, 198, 800, 214), 0.8, ((145, 118, 978, 295),))
RIGHT_UNIT = TemplatePanel("hp", (1390, 198, 1450, 214), 0.8, ((1382, 118, 2215, 295),))

TEMPLATE_PANELS = (
    MENU,
    TURN,
    END_TURN,
    CHANGE_DEPLOY,
    PROMPT,
    UNIT_LIST,
    BACK,
    STANDBY,
    SWITCH_UNIT,
    PREP_LIST,
    LEFT_UNIT,
    RIGHT_UNIT,
)


def hud_rects(image: np.ndarray) -> tuple[Rect, ...]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    matches = {panel: template_match(gray, panel) for panel in TEMPLATE_PANELS}
    shown = {panel for panel, (score, _) in matches.items() if score >= panel.threshold}
    rects = [rect for panel in shown for rect in panel.covers]
    rects.extend(_card_rects(image))
    buttons = _button_centers(gray)
    rects.extend(_button_rect(x) for x in buttons)
    if BACK in shown or PREP_LIST in shown:
        rects.append(ACTION_RECT)
    if PREP_LIST in shown:
        rects.append(_prep_row(matches[PREP_LIST][1]))
        if _banner(image):
            rects.append(BANNER_RECT)
    elif BACK in shown:
        rects.extend((BUTTON_ROW, ACTION_ARC_RECT))
    # The description panel at the right is translucent and has no fixed content.
    # It shows with the weapons, the skills and the support choices, which all have
    # the back button or a round button at the right of the bottom row.
    right_button = any(x >= RIGHT_BUTTON_LEFT for x in buttons)
    if SWITCH_UNIT not in shown and ((BACK in shown and PREP_LIST not in shown) or right_button):
        rects.append(INFO_PANEL_RECT)
    return tuple(rects)


def hud_cells(image: np.ndarray, lattice: Lattice) -> frozenset[ViewCell]:
    rects = hud_rects(image)
    return frozenset(cell for cell in lattice.cells() if covered(lattice.center(cell), rects))


def covered(point: ScreenPoint, rects: tuple[Rect, ...]) -> bool:
    x, y = point
    return any(left <= x < right and top <= y < bottom for left, top, right, bottom in rects)


@functools.cache
def _template(name: str) -> np.ndarray:
    path = TEMPLATES / f"{name}.png"
    template = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise FileNotFoundError(path)
    return np.asarray(template)


def template_match(gray: np.ndarray, panel: TemplatePanel) -> tuple[float, int]:
    """Return the best match score and the left x of the best match in the frame."""
    left, top, right, bottom = panel.anchor
    height, width = gray.shape
    template = _template(panel.template)
    window_left = max(0, left - TEMPLATE_MARGIN)
    window = gray[
        max(0, top - TEMPLATE_MARGIN) : min(height, bottom + TEMPLATE_MARGIN),
        window_left : min(width, right + TEMPLATE_MARGIN),
    ]
    if window.shape[0] < template.shape[0] or window.shape[1] < template.shape[1]:
        return 0.0, left
    _, best, _, (x, _) = cv2.minMaxLoc(cv2.matchTemplate(window, template, cv2.TM_CCOEFF_NORMED))
    return best, window_left + x


def _prep_row(list_left: int) -> Rect:
    """Return the pilot row of the battle prep screens.

    The pilot circles center on PREP_ROW_CENTER, and the list button sits left of them.
    """
    left, top, _, bottom = PREP_ROW
    return list_left + left, top, 2 * PREP_ROW_CENTER - list_left - left, bottom


def _banner(image: np.ndarray) -> bool:
    """Return True when the attack banner shows between the two unit panels.

    The banner has saturated red and blue bars.
    """
    left, top, right, bottom = BANNER_PROBE
    hsv = cv2.cvtColor(image[top:bottom, left:right], cv2.COLOR_BGR2HSV)
    hue = hsv[..., 0]
    red_or_blue = (hue <= 8) | (hue >= 170) | ((hue >= 100) & (hue <= 125))
    colored = red_or_blue & (hsv[..., 1] > 150) & (hsv[..., 2] > 150)
    return float(colored.mean()) >= BANNER_SHARE


def _card_rects(image: np.ndarray) -> list[Rect]:
    """Return the unit card slots whose HP bar starts with its blue fill.

    The HP bar fills from its left end while the unit is alive.
    """
    left, top, right, bottom = CARD_RECT
    bar_left, bar_top, bar_right, bar_bottom = CARD_BAR
    hsv = cv2.cvtColor(image[bar_top:bar_bottom], cv2.COLOR_BGR2HSV)
    low, high = CARD_BAR_HUE
    blue = (hsv[..., 0] >= low) & (hsv[..., 0] <= high) & (hsv[..., 1] > 120) & (hsv[..., 2] > 170)
    rects: list[Rect] = []
    for slot in range(CARD_SLOTS):
        x = CARD_LEFT + CARD_PITCH * slot
        if x + right > image.shape[1]:
            break
        if blue[:, x + bar_left : x + bar_right].mean() >= CARD_BAR_SHARE:
            rects.append((x + left, top, x + right, bottom))
    return rects


def _button_centers(gray: np.ndarray) -> list[int]:
    """Return the x of each round button in the bottom row: weapons, skills, support choices."""
    smooth = cv2.GaussianBlur(gray, (5, 5), 0).astype(np.float32)
    gradient_x = cv2.Sobel(smooth, cv2.CV_32F, 1, 0, ksize=3) / 4
    gradient_y = cv2.Sobel(smooth, cv2.CV_32F, 0, 1, ksize=3) / 4
    found: list[int] = []
    for x in BUTTON_CENTERS:
        centers = np.array(
            [
                (x + dx, BUTTON_CENTER_Y + dy)
                for dx in range(-BUTTON_SEARCH, BUTTON_SEARCH + 1, 2)
                for dy in (-4, 0, 4)
            ]
        )
        if ring_share(gradient_x, gradient_y, centers, BUTTON_RADII).max() >= BUTTON_SHARE:
            found.append(x)
    return found


def _button_rect(x: int) -> Rect:
    left, top, right, bottom = BUTTON_RECT
    return x + left, BUTTON_CENTER_Y + top, x + right, BUTTON_CENTER_Y + bottom


def ring_share(
    gradient_x: np.ndarray, gradient_y: np.ndarray, centers: np.ndarray, radii: tuple[int, int]
) -> np.ndarray:
    """Return, for each center, the best share of directions with a radial edge at one radius.

    A direction counts when the radial gradient is strong within one pixel of the radius.
    """
    angles = np.linspace(0, 2 * np.pi, 72, endpoint=False)
    radius = np.arange(radii[0] - 1, radii[1] + 2)
    cos, sin = np.cos(angles), np.sin(angles)
    height, width = gradient_x.shape
    xs = np.round(centers[:, 0, None, None] + radius[None, :, None] * cos).astype(int)
    ys = np.round(centers[:, 1, None, None] + radius[None, :, None] * sin).astype(int)
    inside = (xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)
    xs, ys = np.clip(xs, 0, width - 1), np.clip(ys, 0, height - 1)
    radial = np.abs(gradient_x[ys, xs] * cos + gradient_y[ys, xs] * sin)
    strong = (radial > BUTTON_EDGE) & inside
    near = strong[:, :-2] | strong[:, 1:-1] | strong[:, 2:]
    return near.mean(axis=2).max(axis=1)
