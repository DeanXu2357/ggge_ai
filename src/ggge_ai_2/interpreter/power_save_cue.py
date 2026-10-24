from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ggge_ai_2.interpreter.contract import Interpreter, Screen, Situation
from ggge_ai_2.stream.contract import Frame

LOCK_ICON_TEMPLATE = (
    Path(__file__).resolve().parents[3] / "assets" / "templates" / "elements" / "game_lock_icon.png"
)
LOCK_ICON_REGION = (1040, 320, 260, 230)
LOCK_ICON_THRESHOLD = 0.75
LOCK_MAX_MEAN = 40.0
DIM_MAX_MEAN = 20.0


@functools.cache
def _lock_icon() -> np.ndarray:
    template = cv2.imread(str(LOCK_ICON_TEMPLATE))
    if template is None:
        raise FileNotFoundError(LOCK_ICON_TEMPLATE)
    return np.asarray(template)


def lock_icon_score(image: np.ndarray) -> float:
    x, y, w, h = LOCK_ICON_REGION
    patch = image[y : y + h, x : x + w]
    _, best, _, _ = cv2.minMaxLoc(cv2.matchTemplate(patch, _lock_icon(), cv2.TM_CCOEFF_NORMED))
    return best


def power_save_screen(image: np.ndarray) -> Screen | None:
    mean = float(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).mean())
    if mean <= LOCK_MAX_MEAN and lock_icon_score(image) >= LOCK_ICON_THRESHOLD:
        return Screen.POWER_SAVE_LOCK
    if mean < DIM_MAX_MEAN:
        return Screen.POWER_SAVE_DIM
    return None


@dataclass(frozen=True)
class PowerSaveCueInterpreter:
    inner: Interpreter

    def interpret(self, frame: Frame, candidates: frozenset[Screen]) -> Situation | None:
        screen = power_save_screen(frame.image)
        if screen is not None:
            return Situation(frame.seq, screen, None)
        return self.inner.interpret(frame, candidates)
