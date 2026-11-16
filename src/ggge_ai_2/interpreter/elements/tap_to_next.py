from __future__ import annotations

import numpy as np

from ggge_ai_2.interpreter.elements.region import Region, match

TAP_TO_NEXT_REGION: Region = (0.440, 0.880, 0.568, 0.931)
TAP_TO_NEXT_MARGIN = 10
TAP_TO_NEXT_THRESHOLD = 0.6


def tap_to_next_score(image: np.ndarray) -> float:
    return match(image, TAP_TO_NEXT_REGION, "tap_to_next", TAP_TO_NEXT_MARGIN)


def has_tap_to_next(image: np.ndarray) -> bool:
    return tap_to_next_score(image) >= TAP_TO_NEXT_THRESHOLD
