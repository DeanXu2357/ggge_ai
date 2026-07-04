from __future__ import annotations

import time
from collections.abc import Callable

import cv2
import numpy as np

from .base import Image

_SMALL = (192, 108)


def frame_diff(a: Image, b: Image) -> float:
    """Mean absolute luma difference between two frames, normalized to [0, 1].
    Downscaled first so it reflects overall scene change, not pixel noise."""
    ga = cv2.resize(cv2.cvtColor(a, cv2.COLOR_BGR2GRAY), _SMALL)
    gb = cv2.resize(cv2.cvtColor(b, cv2.COLOR_BGR2GRAY), _SMALL)
    return float(np.mean(cv2.absdiff(ga, gb))) / 255.0


def is_static(
    capture: Callable[[], Image],
    threshold: float = 0.012,
    gap_s: float = 0.4,
) -> bool:
    """True when two frames captured gap_s apart barely differ, i.e. the
    screen is settled rather than mid-cutscene, attack or transition
    animation. Used to tell a controllable battle turn from the intro /
    action animations that also show battle-map UI."""
    first = capture()
    time.sleep(gap_s)
    second = capture()
    return frame_diff(first, second) <= threshold
