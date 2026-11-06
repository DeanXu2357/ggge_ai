from __future__ import annotations

import numpy as np

from ggge_ai_2.interpreter.contract import Screen
from ggge_ai_2.interpreter.elements.top_left_title import TopLeftTitle, top_left_title
from ggge_ai_2.interpreter.elements.turn_box import has_turn_box

SCREEN = Screen.PLAYER_PHASE_OVERVIEW


# The check does not use the lit menu key of section 2.4 rule 3. With AUTO on, the menu
# key is dark on this screen too (4 of 4 labeled frames).
def quick_check(image: np.ndarray) -> bool:
    return has_turn_box(image) and top_left_title(image) is TopLeftTitle.PLAYER_PHASE
