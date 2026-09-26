from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, Self

from ggge_ai_2.actuator.contract import Gesture


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
class ScreenIs:
    screen: Screen
    overlays: frozenset[Overlay] = frozenset()


@dataclass(frozen=True)
class MapModeIs:
    mode: MapMode


UiFact = ScreenIs | MapModeIs


@dataclass(frozen=True)
class UiState:
    screen: Screen
    overlays: frozenset[Overlay] = frozenset()
    map_mode: MapMode | None = None

    def facts(self) -> tuple[UiFact, ...]:
        screen = ScreenIs(self.screen, self.overlays)
        return (screen,) if self.map_mode is None else (screen, MapModeIs(self.map_mode))


@dataclass(frozen=True)
class Outcome:
    name: str
    fact: UiFact
    then: UiState


@dataclass(frozen=True)
class Operation:
    name: str
    # Always include a ScreenIs fact for the screen and the overlays that the gesture
    # assumes. The guard checks only the facts that a step declares, so a missing
    # domain fact can then at worst tap the wrong place on the right screen.
    precondition: tuple[UiFact, ...]
    gesture: Gesture
    outcomes: tuple[Outcome, ...]
    deadline: float
    cost: float


class UiSim(Protocol):
    # An instance must not change after it is made. The agent keeps an instance in its
    # belief and the planner reads the belief as a pure input; a change in place would
    # change the belief behind the planner and break the replay of a run.

    @property
    def state(self) -> UiState: ...

    def successors(self) -> Sequence[Operation]: ...

    def predecessors(self) -> Sequence[tuple[UiState, Operation]]: ...

    def advance(self, outcome: Outcome) -> Self: ...

    def sync(self, observed: UiState) -> Self: ...
