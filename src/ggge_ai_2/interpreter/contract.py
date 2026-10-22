from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ggge_ai_2.stream.contract import Frame


class Screen(StrEnum):
    STAGE_CHOSEN = "stage_chosen"
    SERIES_LIST = "series_list"
    SERIES_STAGE_INFO = "series_stage_info"
    STORY_STAGE_LIST = "story_stage_list"
    SORTIE_PREP = "sortie_prep"
    BATTLE_INFO_PREVIEW = "battle_info_preview"
    PLAYER_PHASE_OVERVIEW = "player_phase_overview"
    SELECT_ACTION_IN_BATTLE = "select_action_in_battle"
    SELECT_WEAPON_IN_BATTLE = "select_weapon_in_battle"
    BATTLE_PREP_ATTACK = "battle_prep_attack"
    BATTLE_PREP_RESPONSE_ATTACK = "battle_prep_response_attack"
    NON_PLAYER_PHASE_BATTLE_VIEW = "non_player_phase_battle_view"
    BATTLE_MAIN_SETTING = "battle_main_setting"
    CHALLENGE_BATTLE_CHECK = "challenge_battle_check"
    BATTLE_SCORE_RESULT = "battle_score_result"
    EXP_REWARD_RESULT = "exp_reward_result"
    DROP_REWARD_RESULT = "drop_reward_result"
    POWER_SAVE_LOCK = "power_save_lock"
    POWER_SAVE_DIM = "power_save_dim"
    LOADING = "loading"
    SIMPLIFY_WEAPON_ANIME = "simplify_weapon_anime"
    EX_WEAPON_ANIME = "ex_weapon_anime"
    BATTLE_CLEAR_VIEW = "battle_clear_view"
    MAP_PASSING = "map_passing"


@dataclass(frozen=True)
class Situation:
    frame_seq: int
    screen: Screen
    auto: bool | None = None


class Interpreter(Protocol):
    def interpret(self, frame: Frame, candidates: frozenset[Screen]) -> Situation | None:
        """Return None when no screen is close enough to the frame.

        The candidates are the screens that the agent expects next. The interpreter can
        still return a screen outside the candidates, and the agent records it as a model
        mismatch.

        Do not return the closest screen when it is below the threshold. A popup that
        has no model then reads as a known screen, and the planner cannot stop on it.
        """
        ...
