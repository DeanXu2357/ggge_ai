from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ggge_ai_2.stream.contract import Frame


class Screen(StrEnum):
    LOGIN_BONUS = "login_bonus"
    NOTICE = "notice"
    DATE_CHANGED = "date_changed"
    SERIES_SELECT = "series_select"
    SERIES_CONFIRM = "series_confirm"
    STAGE_TYPE_SELECT = "stage_type_select"
    STAGE_LIST = "stage_list"
    STAGE_INFO = "stage_info"
    SORTIE_PREP = "sortie_prep"
    BATTLE_PREP = "battle_prep"
    BATTLE_PREP_REACTION = "battle_prep_reaction"
    BATTLE_MAP = "battle_map"
    BATTLE_MAP_ENEMY = "battle_map_enemy"
    BATTLE_MENU = "battle_menu"
    BATTLE_SKILL = "battle_skill"
    BATTLE_SETTINGS = "battle_settings"
    TROOP_INFO = "troop_info"
    UNIT_DETAIL = "unit_detail"
    END_TURN_DIALOG = "end_turn_dialog"
    BATTLE_RESULT = "battle_result"
    BATTLE_DEFEAT = "battle_defeat"


class Overlay(StrEnum):
    CARD_STRIP = "card_strip"
    CARD = "card"
    DIALOG = "dialog"


class MapMode(StrEnum):
    HUB = "hub"
    SELECTED = "selected"
    WEAPON_SELECT = "weapon_select"


@dataclass(frozen=True)
class Situation:
    frame_seq: int
    screen: Screen
    overlays: frozenset[Overlay] = frozenset()
    map_mode: MapMode | None = None


class Interpreter(Protocol):
    def interpret(self, frame: Frame) -> Situation | None:
        """Return None when no screen is close enough to the frame.

        Do not return the closest screen when it is below the threshold. A popup that
        has no model then reads as a known screen, and the planner cannot stop on it.
        """
        ...
