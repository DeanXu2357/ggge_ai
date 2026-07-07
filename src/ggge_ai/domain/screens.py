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

UNIT_SETUP: ScreenId = "unit_setup"
STAGE_INFO: ScreenId = "stage_info"
STORY: ScreenId = "story"
BATTLE_MAP: ScreenId = "battle_map"
BATTLE_RESULT: ScreenId = "battle_result"
BATTLE_FAILED: ScreenId = "battle_failed"
REWARD: ScreenId = "reward"

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
    UNIT_SETUP,
    STAGE_INFO,
    STORY,
    BATTLE_MAP,
    BATTLE_RESULT,
    BATTLE_FAILED,
    REWARD,
]
