"""Pixel-level helpers for the manual battle controller.

All coordinates are in the 2340x1080 landscape reference frame.
"""

from __future__ import annotations

import cv2
import numpy as np

ATTACK_BUTTON_BOX = (1990, 900, 240, 160)
UNIT_CARD_STRIP_BOX = (170, 840, 900, 200)
FIRST_UNIT_CARD = (300, 930)

# map area free of HUD overlays, used when scanning for cells / units
MAP_REGION = (150, 250, 1600, 700)


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
