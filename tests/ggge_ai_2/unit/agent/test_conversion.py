from __future__ import annotations

from ggge_ai_2.agent.loop import (
    PASSING_SCREENS,
    _situation_to_observed,
)
from ggge_ai_2.interpreter.contract import AutoMode, Screen, Situation
from ggge_ai_2.uisim.contract import Observed, UiAutoMode, UiScreen


def observed(situation: Situation) -> Observed:
    converted = _situation_to_observed(situation)
    assert converted is not None
    return converted


LOCKS = {Screen.POWER_SAVE_LOCK, Screen.POWER_SAVE_DIM}


def test_every_game_screen_of_the_interpreter_converts_to_one_screen_of_uisim():
    game_screens = [
        screen for screen in Screen if screen not in LOCKS and screen not in PASSING_SCREENS
    ]

    assert [observed(Situation(1, screen)).screen for screen in game_screens] == [
        UiScreen(screen.value) for screen in game_screens
    ]


def test_every_auto_mode_of_the_interpreter_converts_to_the_same_auto_mode_of_uisim():
    on_map = [Situation(1, Screen.PLAYER_PHASE_OVERVIEW, mode) for mode in AutoMode]

    assert [observed(situation).auto for situation in on_map] == [
        UiAutoMode(mode.value) for mode in AutoMode
    ]
    assert observed(Situation(1, Screen.PLAYER_PHASE_OVERVIEW, None)).auto is None


def test_situation_without_an_auto_button_has_no_auto_state():
    assert observed(Situation(1, Screen.STORY_STAGE_LIST)).auto is None


def test_unread_frame_converts_to_nothing():
    assert _situation_to_observed(None) is None
