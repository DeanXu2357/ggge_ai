from __future__ import annotations

from collections.abc import Callable, Mapping

import numpy as np

from ggge_ai_2.interpreter.contract import Screen
from ggge_ai_2.interpreter.screens import (
    battle_prep_attack,
    battle_prep_response_attack,
    player_phase_overview,
    select_action_in_battle,
    select_weapon_in_attack_prepare,
    select_weapon_in_battle,
    select_weapon_in_battle_response,
)

type QuickCheck = Callable[[np.ndarray], bool]

QUICK_CHECKS: Mapping[Screen, QuickCheck] = {
    module.SCREEN: module.quick_check
    for module in (
        player_phase_overview,
        select_action_in_battle,
        select_weapon_in_battle,
        select_weapon_in_battle_response,
        select_weapon_in_attack_prepare,
        battle_prep_attack,
        battle_prep_response_attack,
    )
}
