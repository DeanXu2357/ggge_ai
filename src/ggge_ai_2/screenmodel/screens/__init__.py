from __future__ import annotations

from ggge_ai_2.screenmodel.definition import ScreenDefinition
from ggge_ai_2.screenmodel.screens import (
    battle_info_preview,
    battle_prep_attack,
    battle_prep_response_attack,
    player_phase_overview,
    select_action_in_battle,
    select_weapon_in_attack_prepare,
    select_weapon_in_battle,
    select_weapon_in_battle_response,
    unit_detail_summary,
)

DEFINITIONS: tuple[ScreenDefinition, ...] = tuple(
    module.DEFINITION
    for module in (
        player_phase_overview,
        select_action_in_battle,
        select_weapon_in_battle,
        select_weapon_in_battle_response,
        select_weapon_in_attack_prepare,
        battle_prep_attack,
        battle_prep_response_attack,
        battle_info_preview,
        unit_detail_summary,
    )
)
