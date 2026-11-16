from __future__ import annotations

import cv2
import numpy as np

from ggge_ai_2.interpreter.contract import Phase, Screen

# The band behind the title at the top left. Its color is the faction of the phase.
TITLE_BAND = (160, 30, 600, 60)
TITLE_WHITE = 190
BAND_SATURATION = 50
BAND_VALUE = 70
BAND_SHARE = 0.1
# OpenCV hues (0 to 179). The player is blue; another faction is red ('敵軍回合') or
# purple ('隱藏軍回合').
PLAYER_HUES = (100, 128)
OTHER_HUES = ((130, 179), (0, 8))

# The screens with the band. Other screens can have a blue or red area at the same place,
# for example the game title. Use 'phase' only on these screens.
PHASE_SCREENS = frozenset(
    {
        Screen.PLAYER_PHASE_OVERVIEW,
        Screen.NON_PLAYER_PHASE_BATTLE_VIEW,
        Screen.BATTLE_PREP_ATTACK,
        Screen.BATTLE_PREP_RESPONSE_ATTACK,
    }
)


def _band_hsv(image: np.ndarray) -> np.ndarray:
    left, top, right, bottom = TITLE_BAND
    crop = image[top:bottom, left:right]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)[crop.min(axis=2) < TITLE_WHITE]
    return hsv[(hsv[:, 1] >= BAND_SATURATION) & (hsv[:, 2] >= BAND_VALUE)]


def _share(hue: np.ndarray, total: int, low: int, high: int) -> float:
    return float(np.count_nonzero((hue >= low) & (hue <= high))) / total


def band_shares(image: np.ndarray) -> tuple[float, float]:
    """Return the shares of the band that are the player color and another faction's color."""
    left, top, right, bottom = TITLE_BAND
    total = (right - left) * (bottom - top)
    hue = _band_hsv(image)[:, 0]
    player = _share(hue, total, *PLAYER_HUES)
    other = sum(_share(hue, total, low, high) for low, high in OTHER_HUES)
    return player, other


def phase(image: np.ndarray) -> Phase | None:
    player, other = band_shares(image)
    if max(player, other) < BAND_SHARE:
        return None
    return Phase.PLAYER if player >= other else Phase.NON_PLAYER
