from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

RatioPoint = tuple[float, float]


@dataclass(frozen=True)
class RatioRect:
    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True)
class DangerBand:
    regions: tuple[RatioRect, ...] = ()


class UiScreen(StrEnum):
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


class UiOverlay(StrEnum):
    CARD_STRIP = "card_strip"
    CARD = "card"
    DIALOG = "dialog"


class UiMapMode(StrEnum):
    HUB = "hub"
    SELECTED = "selected"
    WEAPON_SELECT = "weapon_select"


@dataclass(frozen=True)
class UiState:
    screen: UiScreen
    overlays: frozenset[UiOverlay] = frozenset()
    map_mode: UiMapMode | None = None


@dataclass(frozen=True)
class Observed:
    screen: UiScreen
    overlays: frozenset[UiOverlay] = frozenset()
    map_mode: UiMapMode | None = None


@dataclass(frozen=True)
class UiTap:
    point: RatioPoint


@dataclass(frozen=True)
class UiSwipe:
    start: RatioPoint
    end: RatioPoint
    duration: float


@dataclass(frozen=True)
class UiKey:
    code: str


UiGesture = UiTap | UiSwipe | UiKey


@dataclass(frozen=True)
class Outcome:
    name: str
    then: UiState


@dataclass(frozen=True)
class Operation:
    name: str
    precondition: UiState
    gesture: UiGesture
    outcomes: tuple[Outcome, ...]
    deadline: float
    cost: float


class UiSim(Protocol):
    def successors(self, state: UiState) -> Sequence[Operation]: ...

    def predecessors(self, state: UiState) -> Sequence[tuple[UiState, Operation]]: ...

    def advance(self, state: UiState, outcome: Outcome) -> UiState: ...

    def sync(self, state: UiState, observed: Observed) -> UiState: ...

    def danger_band(self, state: UiState) -> DangerBand: ...
