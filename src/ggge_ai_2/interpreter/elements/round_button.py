from __future__ import annotations

from enum import StrEnum

import cv2
import numpy as np

from ggge_ai_2.interpreter.elements.region import Region, match


class RoundButton(StrEnum):
    SELECT_WEAPON = "select_weapon"
    ATTACK = "attack"
    ATTACK_OUT_OF_RANGE = "attack_out_of_range"
    SELECT_ACTION = "select_action"
    ACTIVATE = "activate"
    START_BATTLE = "start_battle"


ROUND_CENTER = (0.878, 0.847)
ROUND_RADII = (0.109, 0.135)
ROUND_RING_TOLERANCE = 3
ROUND_RING_COVERAGE = 0.8
ROUND_TEXT_REGION: Region = (0.835, 0.86, 0.92, 0.915)
ROUND_TEXT_MARGIN = 12

_ANGLES = np.deg2rad(np.arange(0, 360, 2))


def round_ring_coverage(image: np.ndarray) -> float:
    """Return the largest share of the circle around the button center that lies on an edge."""
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120)
    size = 2 * ROUND_RING_TOLERANCE + 1
    edges = cv2.dilate(edges, np.ones((size, size), np.uint8))
    cx, cy = ROUND_CENTER[0] * w, ROUND_CENTER[1] * h
    best = 0.0
    for radius in range(int(ROUND_RADII[0] * h), int(ROUND_RADII[1] * h) + 1):
        xs = np.clip((cx + radius * np.cos(_ANGLES)).astype(int), 0, w - 1)
        ys = (cy + radius * np.sin(_ANGLES)).astype(int)
        inside = ys < h
        best = max(best, float((edges[ys[inside], xs[inside]] > 0).mean()))
    return best


def has_round_button(image: np.ndarray) -> bool:
    return round_ring_coverage(image) >= ROUND_RING_COVERAGE


def round_text_scores(image: np.ndarray) -> dict[RoundButton, float]:
    return {
        kind: match(image, ROUND_TEXT_REGION, f"round_{kind.value}", ROUND_TEXT_MARGIN)
        for kind in RoundButton
    }


def round_button(image: np.ndarray) -> RoundButton | None:
    if not has_round_button(image):
        return None
    scores = round_text_scores(image)
    return max(scores, key=lambda kind: scores[kind])
