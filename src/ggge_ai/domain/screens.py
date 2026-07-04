from __future__ import annotations

from ..perception.base import ScreenId

UNKNOWN: ScreenId = "unknown"
TITLE: ScreenId = "title"
MAIN_MENU: ScreenId = "main_menu"
STAGE_SELECT: ScreenId = "stage_select"
UNIT_SETUP: ScreenId = "unit_setup"
BATTLE_MAP: ScreenId = "battle_map"
BATTLE_RESULT: ScreenId = "battle_result"

ALL_SCREENS = [TITLE, MAIN_MENU, STAGE_SELECT, UNIT_SETUP, BATTLE_MAP, BATTLE_RESULT]
