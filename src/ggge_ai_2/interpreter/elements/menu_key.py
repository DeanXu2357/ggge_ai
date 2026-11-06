from __future__ import annotations

import cv2
import numpy as np

from ggge_ai_2.interpreter.elements.region import Region, crop, match

MENU_LINES_REGION: Region = (0.918, 0.032, 0.937, 0.067)
MENU_GLYPH_REGION: Region = (0.918, 0.031, 0.936, 0.067)
MENU_LIT_WHITE_SHARE = 0.1
MENU_GLYPH_MARGIN = 12
MENU_GLYPH_MIN_SCORE = 0.7


def menu_key_white_share(image: np.ndarray) -> float:
    hsv = cv2.cvtColor(crop(image, MENU_LINES_REGION), cv2.COLOR_BGR2HSV)
    return float(((hsv[..., 2] > 200) & (hsv[..., 1] < 60)).mean())


def menu_key_glyph_score(image: np.ndarray) -> float:
    return match(image, MENU_LINES_REGION, "key_menu", MENU_GLYPH_MARGIN)


def menu_key_lit(image: np.ndarray) -> bool:
    return (
        menu_key_white_share(image) >= MENU_LIT_WHITE_SHARE
        and menu_key_glyph_score(image) >= MENU_GLYPH_MIN_SCORE
    )
