from __future__ import annotations

import numpy as np

from ggge_ai_2.interpreter.contract import Screen
from ggge_ai_2.interpreter.elements.fast_forward import has_fast_forward
from ggge_ai_2.interpreter.elements.tap_to_next import has_tap_to_next

SCREEN = Screen.BATTLE_INFO_PREVIEW


def quick_check(image: np.ndarray) -> bool:
    return has_fast_forward(image) and has_tap_to_next(image)
