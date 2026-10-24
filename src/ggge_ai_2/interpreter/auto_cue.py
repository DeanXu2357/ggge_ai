from __future__ import annotations

from dataclasses import dataclass, replace

import cv2
import numpy as np

from ggge_ai_2.interpreter.contract import Interpreter, Screen, Situation
from ggge_ai_2.stream.contract import Frame

AUTO_RECT = (0.743, 0.016, 0.811, 0.081)
AUTO_THRESHOLD = 0.2

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
    h, w = image.shape[:2]
    left, top, right, bottom = AUTO_RECT
    crop = image[int(top * h) : int(bottom * h), int(left * w) : int(right * w)]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    blue = (hue >= 90) & (hue <= 115) & (sat > 120) & (val > 150)
    return float(blue.mean())


def auto_lit(image: np.ndarray) -> bool:
    return auto_blue_fraction(image) >= AUTO_THRESHOLD


@dataclass(frozen=True)
class AutoCueInterpreter:
    inner: Interpreter

    def interpret(self, frame: Frame, candidates: frozenset[Screen]) -> Situation | None:
        situation = self.inner.interpret(frame, candidates)
        if situation is None:
            return None
        auto = auto_lit(frame.image) if situation.screen in AUTO_SCREENS else None
        return replace(situation, auto=auto)
