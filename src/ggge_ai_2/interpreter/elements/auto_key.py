from __future__ import annotations

import cv2
import numpy as np

from ggge_ai_2.interpreter.contract import AutoMode

AUTO_RECT = (0.743, 0.016, 0.811, 0.081)
AUTO_THRESHOLD = 0.2
AUTO_RED_THRESHOLD = 0.4


def auto_blue_fraction(image: np.ndarray) -> float:
    hue, sat, val = _auto_hsv(image)
    blue = (hue >= 90) & (hue <= 115) & (sat > 120) & (val > 150)
    return float(blue.mean())


def auto_red_fraction(image: np.ndarray) -> float:
    hue, sat, val = _auto_hsv(image)
    red = ((hue <= 10) | (hue >= 160)) & (sat > 100) & (val > 120)
    return float(red.mean())


def auto_mode(image: np.ndarray) -> AutoMode:
    if auto_blue_fraction(image) >= AUTO_THRESHOLD:
        return AutoMode.FULL
    if auto_red_fraction(image) >= AUTO_RED_THRESHOLD:
        return AutoMode.SEMI
    return AutoMode.MANUAL


def _auto_hsv(image: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    h, w = image.shape[:2]
    left, top, right, bottom = AUTO_RECT
    crop = image[int(top * h) : int(bottom * h), int(left * w) : int(right * w)]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    return hsv[..., 0], hsv[..., 1], hsv[..., 2]
