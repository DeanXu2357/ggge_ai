from __future__ import annotations

import cv2
import numpy as np

from ggge_ai_2.interpreter.elements.region import Region, crop, template

SHAPE_DIRECTIONS = 4
SHAPE_TOLERANCE = 2
# The direction classes of 'direction_edges' for a straight side. The gradient of a vertical
# side points along x.
VERTICAL = 1
HORIZONTAL = 3


def direction_edges(image: np.ndarray) -> np.ndarray:
    """Return 0 off the Canny edges and the gradient direction class, 1 to 4, on them.

    A shape matches only edges of its own direction. Without this check, a frame full of
    edges matches every outline.
    """
    gray = cv2.GaussianBlur(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (3, 3), 0)
    edges = cv2.Canny(gray, 30, 90) > 0
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    step = 180 / SHAPE_DIRECTIONS
    angle = np.degrees(np.arctan2(gy, gx)) % 180
    direction = ((angle + step / 2) // step).astype(np.uint8) % SHAPE_DIRECTIONS + 1
    return np.where(edges, direction, 0).astype(np.uint8)


def edge_near(labels: np.ndarray, direction: int) -> np.ndarray:
    """Return True where an edge of the direction lies within SHAPE_TOLERANCE pixels."""
    size = 2 * SHAPE_TOLERANCE + 1
    return cv2.dilate((labels == direction).astype(np.uint8), np.ones((size, size), np.uint8)) > 0


def shape_score(image: np.ndarray, region: Region, name: str, margin: int) -> float:
    """Return the largest share of the template edges that lie on a frame edge of the same direction."""
    labels = direction_edges(crop(image, region, margin))
    shape = template(name)
    hits: np.ndarray | None = None
    for direction in range(1, SHAPE_DIRECTIONS + 1):
        edges = (shape == direction).astype(np.float32)
        if not edges.any():
            continue
        near = edge_near(labels, direction).astype(np.float32)
        found = cv2.matchTemplate(near, edges, cv2.TM_CCORR)
        hits = found if hits is None else hits + found
    if hits is None:
        return 0.0
    _, best, _, _ = cv2.minMaxLoc(hits)
    return float(best) / np.count_nonzero(shape)
