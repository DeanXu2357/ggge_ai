from __future__ import annotations

import functools
from pathlib import Path

import cv2
import numpy as np

TEMPLATES = Path(__file__).resolve().parents[4] / "assets" / "templates" / "interpreter"

type Region = tuple[float, float, float, float]


def crop(image: np.ndarray, region: Region, margin: int = 0) -> np.ndarray:
    """Return the region (left, top, right, bottom as frame ratios), widened by margin pixels."""
    h, w = image.shape[:2]
    left, top, right, bottom = region
    return image[
        max(0, int(top * h) - margin) : min(h, int(bottom * h) + margin),
        max(0, int(left * w) - margin) : min(w, int(right * w) + margin),
    ]


def value(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[..., 2]


@functools.cache
def template(name: str) -> np.ndarray:
    path = TEMPLATES / f"{name}.png"
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FileNotFoundError(path)
    return np.asarray(image)


def match(image: np.ndarray, region: Region, name: str, margin: int) -> float:
    patch = value(crop(image, region, margin))
    _, best, _, _ = cv2.minMaxLoc(cv2.matchTemplate(patch, template(name), cv2.TM_CCOEFF_NORMED))
    return float(best)
