"""Pixel-level helpers for the manual battle controller.

All coordinates are in the 2340x1080 landscape reference frame.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

STORY_MENU_TEMPLATE = (
    Path(__file__).resolve().parents[3] / "assets" / "templates" / "screens" / "story.png"
)

ATTACK_BUTTON_BOX = (1990, 900, 240, 160)
UNIT_CARD_STRIP_BOX = (170, 840, 900, 200)
FIRST_UNIT_CARD = (300, 930)

# map area free of HUD overlays, used when scanning for cells / units.
# bottom capped above the MP/skill/support button row (y>=880) so their
# bright circular rims are never mistaken for movable cells
MAP_REGION = (150, 250, 1600, 620)

# wider scan for unit HP arcs: units drift into the strip above MAP_REGION
# (below the turn banner); the right edge stops short of the unit info
# panel whose EN bar is a wide flat orange strip
UNIT_SCAN_REGION = (150, 90, 1510, 780)

# on the our-turn hub the actable-unit card strip (bright portraits with
# HP bars) fills the bottom, so scouting there must stop above it
HUB_SCAN_REGION = (150, 90, 1510, 700)


def _crop(frame: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    x, y, w, h = box
    return frame[y : y + h, x : x + w]


def attack_enabled(frame: np.ndarray) -> bool:
    """The attack button ring is saturated blue when a target is locked,
    near-black when the selected weapon is out of range (射程外)."""
    hsv = cv2.cvtColor(_crop(frame, ATTACK_BUTTON_BOX), cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    blue = (h > 90) & (h < 130) & (s > 80) & (v > 80)
    return float(blue.mean()) > 0.3


def unit_cards_present(frame: np.ndarray) -> bool:
    """Actable-unit cards render as bright framed portraits above a blue
    HP bar; an empty strip is dim background."""
    hsv = cv2.cvtColor(_crop(frame, UNIT_CARD_STRIP_BOX), cv2.COLOR_BGR2HSV)
    bright = hsv[..., 2] > 140
    return float(bright.mean()) > 0.08


def find_threat_cells(frame: np.ndarray) -> list[tuple[int, int]]:
    """Movable cells inside enemy attack range carry a translucent red fill
    with a red "!" marker. Their centroid points toward the enemy force."""
    x0, y0, w, h = MAP_REGION
    hsv = cv2.cvtColor(_crop(frame, MAP_REGION), cv2.COLOR_BGR2HSV)
    red = cv2.inRange(hsv, (0, 90, 60), (10, 255, 255)) | cv2.inRange(
        hsv, (170, 90, 60), (180, 255, 255)
    )
    red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    n, _, stats, cents = cv2.connectedComponentsWithStats(red)
    out = []
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        bw = stats[i, cv2.CC_STAT_WIDTH]
        bh = stats[i, cv2.CC_STAT_HEIGHT]
        # one grid cell is ~90px; accept cell-sized red patches only, so
        # solid range overlays and unit bodies are ignored
        if 400 <= area <= 6000 and bw < 140 and bh < 140:
            out.append((x0 + int(cents[i][0]), y0 + int(cents[i][1])))
    return out


def find_move_cells(frame: np.ndarray) -> list[tuple[int, int]]:
    """Reachable cells are drawn as bright white rounded-square outlines."""
    x0, y0, w, h = MAP_REGION
    hsv = cv2.cvtColor(_crop(frame, MAP_REGION), cv2.COLOR_BGR2HSV)
    white = cv2.inRange(hsv, (0, 0, 180), (180, 60, 255))
    white = cv2.morphologyEx(white, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in contours:
        bx, by, bw, bh = cv2.boundingRect(c)
        if 55 <= bw <= 130 and 55 <= bh <= 130:
            out.append((x0 + bx + bw // 2, y0 + by + bh // 2))
    return out


def _ring_blobs(mask: np.ndarray, region: tuple[int, int, int, int]) -> list[tuple[int, int]]:
    """HP arcs render as wide flat ellipse arcs at a unit's feet; the
    aspect filter rejects unit bodies, threat "!" marks and shield icons.
    The lower width bound stays small because the colored part of the arc
    shrinks as the unit takes damage."""
    x0, y0 = region[0], region[1]
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _, stats, cents = cv2.connectedComponentsWithStats(mask)
    out = []
    for i in range(1, n):
        bw = stats[i, cv2.CC_STAT_WIDTH]
        bh = stats[i, cv2.CC_STAT_HEIGHT]
        area = stats[i, cv2.CC_STAT_AREA]
        if 35 <= bw <= 160 and 12 <= bh <= 70 and bw / bh >= 1.6 and area >= 120:
            out.append((x0 + int(cents[i][0]), y0 + int(cents[i][1])))
    return out


def _dedupe(points: list[tuple[int, int]], radius: int = 70) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for p in points:
        for i, q in enumerate(merged):
            if (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 < radius * radius:
                merged[i] = ((p[0] + q[0]) // 2, (p[1] + q[1]) // 2)
                break
        else:
            merged.append(p)
    return merged


# the arc under every unit is its HP bar and its color encodes the faction:
# red = enemy, teal = third party (not controllable), blue = our own units.
# arcs glow but are not fully saturated (S<=210, V>=155), which separates
# them from unit-body paint (darker) and HUD bars (fully saturated)
def find_enemy_units(
    frame: np.ndarray, region: tuple[int, int, int, int] = UNIT_SCAN_REGION
) -> list[tuple[int, int]]:
    hsv = cv2.cvtColor(_crop(frame, region), cv2.COLOR_BGR2HSV)
    red = cv2.inRange(hsv, (0, 100, 155), (25, 210, 255)) | cv2.inRange(
        hsv, (168, 100, 155), (180, 210, 255)
    )
    return _dedupe(_ring_blobs(red, region))


def find_ally_units(
    frame: np.ndarray, region: tuple[int, int, int, int] = UNIT_SCAN_REGION
) -> list[tuple[int, int]]:
    hsv = cv2.cvtColor(_crop(frame, region), cv2.COLOR_BGR2HSV)
    blue = cv2.inRange(hsv, (100, 100, 155), (125, 210, 255))
    return _dedupe(_ring_blobs(blue, region))


def find_third_party_units(
    frame: np.ndarray, region: tuple[int, int, int, int] = UNIT_SCAN_REGION
) -> list[tuple[int, int]]:
    hsv = cv2.cvtColor(_crop(frame, region), cv2.COLOR_BGR2HSV)
    teal = cv2.inRange(hsv, (78, 100, 155), (97, 210, 255))
    return _dedupe(_ring_blobs(teal, region))


def measure_camera_shift(
    prev: np.ndarray,
    cur: np.ndarray,
    region: tuple[int, int, int, int] = MAP_REGION,
) -> tuple[tuple[float, float], float]:
    """How far the camera moved between two frames, in screen pixels,
    with the phase-correlation response as confidence (near 0 on
    featureless views like open space). Camera shift is the negation of
    the content shift: panning east makes the terrain slide west."""
    a = cv2.cvtColor(_crop(prev, region), cv2.COLOR_BGR2GRAY).astype(np.float32)
    b = cv2.cvtColor(_crop(cur, region), cv2.COLOR_BGR2GRAY).astype(np.float32)
    window = cv2.createHanningWindow((a.shape[1], a.shape[0]), cv2.CV_32F)
    (sx, sy), response = cv2.phaseCorrelate(a, b, window)
    return (-sx, -sy), response


def locate_story_menu(frame: np.ndarray, threshold: float = 0.6) -> tuple[int, int] | None:
    """Find the story MENU button wherever it sits: mid-battle stories add
    a ☰ button that shifts MENU left of its pre-battle position."""
    template = cv2.imread(str(STORY_MENU_TEMPLATE))
    if template is None:
        return None
    result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(result)
    if score < threshold:
        return None
    h, w = template.shape[:2]
    return (loc[0] + w // 2, loc[1] + h // 2)


def nearest_point(points: list[tuple[int, int]], target: tuple[int, int]) -> tuple[int, int] | None:
    if not points:
        return None
    tx, ty = target
    return min(points, key=lambda p: (p[0] - tx) ** 2 + (p[1] - ty) ** 2)


def centroid(points: list[tuple[int, int]]) -> tuple[int, int] | None:
    if not points:
        return None
    xs, ys = zip(*points)
    return (sum(xs) // len(points), sum(ys) // len(points))
