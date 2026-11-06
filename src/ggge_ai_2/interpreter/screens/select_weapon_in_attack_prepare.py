from __future__ import annotations

import numpy as np

from ggge_ai_2.interpreter.contract import Screen
from ggge_ai_2.interpreter.elements.round_button import RoundButton, round_button
from ggge_ai_2.interpreter.elements.top_left_title import TopLeftTitle, top_left_title
from ggge_ai_2.interpreter.elements.turn_box import has_turn_box

SCREEN = Screen.SELECT_WEAPON_IN_ATTACK_PREPARE


def quick_check(image: np.ndarray) -> bool:
    return (
        has_turn_box(image)
        and top_left_title(image) is TopLeftTitle.BATTLE_PREP_ATTACK
        and round_button(image) is RoundButton.SELECT_ACTION
    )
