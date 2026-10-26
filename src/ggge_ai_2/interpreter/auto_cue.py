from __future__ import annotations

from dataclasses import dataclass, replace

import cv2
import numpy as np

from ggge_ai_2.interpreter.contract import AutoMode, Interpreter, Screen, Situation
from ggge_ai_2.stream.contract import Frame

AUTO_RECT = (0.743, 0.016, 0.811, 0.081)
AUTO_THRESHOLD = 0.2
AUTO_RED_THRESHOLD = 0.4

# The enemy turn is left out because the button can look lit there.
AUTO_SCREENS = frozenset(
    {
        Screen.PLAYER_PHASE_OVERVIEW,
        Screen.SELECT_ACTION_IN_BATTLE,
        Screen.SELECT_WEAPON_IN_BATTLE,
        Screen.BATTLE_PREP_ATTACK,
        Screen.BATTLE_PREP_RESPONSE_ATTACK,
        Screen.BATTLE_INFO_PREVIEW,
        Screen.CHALLENGE_BATTLE_CHECK,
    }
)


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


@dataclass(frozen=True)
class AutoCueInterpreter:
    inner: Interpreter

    def interpret(self, frame: Frame, candidates: frozenset[Screen]) -> Situation | None:
        situation = self.inner.interpret(frame, candidates)
        if situation is None:
            return None
        auto = auto_mode(frame.image) if situation.screen in AUTO_SCREENS else None
        return replace(situation, auto=auto)
