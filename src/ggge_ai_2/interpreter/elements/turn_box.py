from __future__ import annotations

import cv2
import numpy as np

from ggge_ai_2.interpreter.elements.region import Region, crop

TURN_BOX_REGION: Region = (0.072, 0.066, 0.14, 0.09)
TURN_BOX_WHITE_SHARE = 0.5


def turn_box_white_share(image: np.ndarray) -> float:
    hsv = cv2.cvtColor(crop(image, TURN_BOX_REGION), cv2.COLOR_BGR2HSV)
    return float(((hsv[..., 2] > 200) & (hsv[..., 1] < 50)).mean())


def has_turn_box(image: np.ndarray) -> bool:
    return turn_box_white_share(image) >= TURN_BOX_WHITE_SHARE
