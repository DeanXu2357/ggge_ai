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
    STAGE_CHOSEN = "stage_chosen"
    SERIES_LIST = "series_list"
    SERIES_STAGE_INFO = "series_stage_info"
    STORY_STAGE_LIST = "story_stage_list"
    ETERNAL_STAGE_LIST = "eternal_stage_list"
    EVENT_STAGE_LIST = "event_stage_list"
    SKIP_STAGE_OVERLAY = "skip_stage_overlay"
    SKIP_RESULT_LIST = "skip_result_list"
    SORTIE_PREP = "sortie_prep"
    ROSTER_ALL_EDIT = "roster_all_edit"
    TRAINING_STAGE_LIST = "training_stage_list"
    BATCH_SKIP_OVERLAY = "batch_skip_overlay"
    AP_RECOVERY_OVERLAY = "ap_recovery_overlay"
    AP_RECOVERY_ITEM_CHECK = "ap_recovery_item_check"
    STAGE_ALLOW_LIST = "stage_allow_list"
    DROP_REWARD_RESULT = "drop_reward_result"
    REWARD_DETAIL = "reward_detail"
    PLAYER_PHASE_OVERVIEW = "player_phase_overview"
    SELECT_ACTION_IN_BATTLE = "select_action_in_battle"
    SELECT_SKILL_IN_BATTLE = "select_skill_in_battle"
    SELECT_WEAPON_IN_BATTLE = "select_weapon_in_battle"
    BATTLE_PREP_ATTACK = "battle_prep_attack"
    NON_PLAYER_PHASE_BATTLE_VIEW = "non_player_phase_battle_view"
    BATTLE_PREP_RESPONSE_ATTACK = "battle_prep_response_attack"
    SELECT_WEAPON_IN_BATTLE_RESPONSE = "select_weapon_in_battle_response"
    BATTLE_MAIN_SETTING = "battle_main_setting"
    BATTLE_SETTINGS_IN_BATTLE = "battle_settings_in_battle"
    BATTLE_PREP_DETAIL = "battle_prep_detail"
    BATTLE_INFO_PREVIEW = "battle_info_preview"
    CHALLENGE_BATTLE_CHECK = "challenge_battle_check"
    EXP_REWARD_RESULT = "exp_reward_result"
    BATTLE_SCORE_RESULT = "battle_score_result"
    WIN_CONDITION_OVERLAY = "win_condition_overlay"


class UiAutoMode(StrEnum):
    FULL = "full"
    SEMI = "semi"
    MANUAL = "manual"


@dataclass(frozen=True)
class UiState:
    screen: UiScreen
    caller: UiScreen | None = None
    auto: UiAutoMode | None = None


@dataclass(frozen=True)
class Observed:
    screen: UiScreen
    auto: UiAutoMode | None = None


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
    gesture: UiGesture | None
    outcomes: tuple[Outcome, ...]
    deadline: float
    cost: float


class UiSim(Protocol):
    def successors(self, state: UiState) -> Sequence[Operation]: ...

    def predecessors(self, state: UiState) -> Sequence[tuple[UiState, Operation]]: ...

    def advance(self, state: UiState, outcome: Outcome) -> UiState: ...

    def sync(self, state: UiState, observed: Observed) -> UiState: ...

    def danger_band(self, state: UiState) -> DangerBand: ...
