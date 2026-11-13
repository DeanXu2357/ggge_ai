from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

# A rectangle is (left, top, right, bottom) in frame pixels. Right and bottom are excluded.
Rect = tuple[int, int, int, int]


class ModelScreen(StrEnum):
    PLAYER_PHASE_OVERVIEW = "player_phase_overview"
    SELECT_ACTION_IN_BATTLE = "select_action_in_battle"
    SELECT_WEAPON_IN_BATTLE = "select_weapon_in_battle"
    SELECT_WEAPON_IN_BATTLE_RESPONSE = "select_weapon_in_battle_response"
    SELECT_WEAPON_IN_ATTACK_PREPARE = "select_weapon_in_attack_prepare"
    BATTLE_PREP_ATTACK = "battle_prep_attack"
    BATTLE_PREP_RESPONSE_ATTACK = "battle_prep_response_attack"
    BATTLE_INFO_PREVIEW = "battle_info_preview"
    UNIT_DETAIL_SUMMARY = "unit_detail_summary"


class ModelElement(StrEnum):
    TURN_BOX = "turn_box"
    TOP_LEFT_TITLE = "top_left_title"
    TITLE_BAND = "title_band"
    ROUND_BUTTON = "round_button"
    FAST_FORWARD = "fast_forward"
    TAP_TO_NEXT = "tap_to_next"


class ModelPhase(StrEnum):
    PLAYER = "player"
    NON_PLAYER = "non_player"


@dataclass(frozen=True)
class SeenElement:
    element: ModelElement
    # None when the element has only a shape and no content to read.
    content: str | None
    box: Rect


@dataclass(frozen=True)
class MapRequest:
    chevrons: bool


@dataclass(frozen=True)
class ScreenJudgment:
    screen: ModelScreen | None
    matched: frozenset[ModelScreen]
    phase: ModelPhase | None
    turn: int | None
    occlusion: tuple[Rect, ...]
    map: MapRequest | None


class ScreenModel(Protocol):
    def judge(self, elements: Sequence[SeenElement]) -> ScreenJudgment:
        """Return the screen only when exactly one screen matches the elements.

        'matched' lists every screen that matches, also when the screen is None. A popup
        that has no model then reads as no screen, and the agent cannot act on a wrong
        screen.
        """
        ...
