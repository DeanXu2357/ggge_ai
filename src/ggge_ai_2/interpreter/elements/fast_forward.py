from __future__ import annotations

import cv2
import numpy as np

from ggge_ai_2.interpreter.elements.region import Region, match

FAST_FORWARD_BOX: Region = (0.828, 0.0185, 0.898, 0.0787)
FAST_FORWARD_OUTLINE_TOLERANCE = 3
FAST_FORWARD_OUTLINE_COVERAGE = 0.7
FAST_FORWARD_GLYPH_REGION: Region = (0.848, 0.033, 0.878, 0.065)
FAST_FORWARD_GLYPH_MARGIN = 12
FAST_FORWARD_GLYPH_SCORE = 0.7

_STEPS = 120


def _outline_points(w: int, h: int) -> tuple[np.ndarray, np.ndarray]:
    """Return points on the capsule outline: two half circles joined by two straight edges."""
    left, top, right, bottom = (
        FAST_FORWARD_BOX[0] * w,
        FAST_FORWARD_BOX[1] * h,
        FAST_FORWARD_BOX[2] * w,
        FAST_FORWARD_BOX[3] * h,
    )
    radius = (bottom - top) / 2
    cy = (top + bottom) / 2
    left_cx, right_cx = left + radius, right - radius
    t = np.linspace(-np.pi / 2, np.pi / 2, _STEPS // 4)
    xs = np.concatenate(
        [
            right_cx + radius * np.cos(t),
            left_cx - radius * np.cos(t),
            np.linspace(left_cx, right_cx, _STEPS // 4),
            np.linspace(left_cx, right_cx, _STEPS // 4),
        ]
    )
    ys = np.concatenate(
        [
            cy + radius * np.sin(t),
            cy + radius * np.sin(t),
            np.full(_STEPS // 4, top),
            np.full(_STEPS // 4, bottom),
        ]
    )
    return np.clip(xs.astype(int), 0, w - 1), np.clip(ys.astype(int), 0, h - 1)


def fast_forward_outline_coverage(image: np.ndarray) -> float:
    """Return the share of the capsule outline that lies on an edge."""
    h, w = image.shape[:2]
    # The blue capsule and a beige map have the same brightness, so the saturation
    # edges find the outline where the gray edges do not (map20261026-40).
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    saturation = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[..., 1]
    edges = np.maximum(
        cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120),
        cv2.Canny(cv2.GaussianBlur(saturation, (5, 5), 0), 40, 120),
    )
    size = 2 * FAST_FORWARD_OUTLINE_TOLERANCE + 1
    edges = cv2.dilate(edges, np.ones((size, size), np.uint8))
    xs, ys = _outline_points(w, h)
    return float((edges[ys, xs] > 0).mean())


def fast_forward_glyph_score(image: np.ndarray) -> float:
    return match(image, FAST_FORWARD_GLYPH_REGION, "fast_forward_glyph", FAST_FORWARD_GLYPH_MARGIN)


def has_fast_forward(image: np.ndarray) -> bool:
    # Other screens put a different capsule button at the same place
    # (supporter_enhance, loading, series_list), so the shape alone is not enough.
    return (
        fast_forward_outline_coverage(image) >= FAST_FORWARD_OUTLINE_COVERAGE
        and fast_forward_glyph_score(image) >= FAST_FORWARD_GLYPH_SCORE
    )
