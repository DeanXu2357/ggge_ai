from __future__ import annotations

from ..perception.base import ScreenId

UNKNOWN: ScreenId = "unknown"
MAIN_MENU: ScreenId = "main_menu"
MISSION: ScreenId = "mission"
ENHANCE: ScreenId = "enhance"
DEVELOP: ScreenId = "develop"
STAGE_TYPE_SELECT: ScreenId = "stage_type_select"
SERIES_SELECT: ScreenId = "series_select"
SERIES_CONFIRM: ScreenId = "series_confirm"
STAGE_LIST: ScreenId = "stage_list"
BASE: ScreenId = "base"
SUPPLY: ScreenId = "supply"
MENU: ScreenId = "menu"

# 尚未取得樣板，待實機探索
UNIT_SETUP: ScreenId = "unit_setup"
BATTLE_MAP: ScreenId = "battle_map"
BATTLE_RESULT: ScreenId = "battle_result"

ALL_SCREENS = [
    MAIN_MENU,
    MISSION,
    ENHANCE,
    DEVELOP,
    STAGE_TYPE_SELECT,
    SERIES_SELECT,
    SERIES_CONFIRM,
    STAGE_LIST,
    BASE,
    SUPPLY,
    MENU,
]
