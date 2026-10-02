from __future__ import annotations

from ggge_ai_2.agent.loop import _situation_to_observed
from ggge_ai_2.interpreter.contract import MapMode, Overlay, Screen, Situation
from ggge_ai_2.uisim.contract import Observed, UiMapMode, UiOverlay, UiScreen


def observed(situation: Situation) -> Observed:
    converted = _situation_to_observed(situation)
    assert converted is not None
    return converted


def test_every_screen_of_the_interpreter_converts_to_one_screen_of_uisim():
    converted = {observed(Situation(1, screen)).screen for screen in Screen}

    assert converted == set(UiScreen)


def test_every_overlay_of_the_interpreter_converts_to_one_overlay_of_uisim():
    seen = observed(Situation(1, Screen.BATTLE_MAP, frozenset(Overlay)))

    assert seen.overlays == frozenset(UiOverlay)


def test_every_map_mode_of_the_interpreter_converts_to_one_map_mode_of_uisim():
    on_map = [Situation(1, Screen.BATTLE_MAP, map_mode=mode) for mode in MapMode]

    assert {observed(situation).map_mode for situation in on_map} == set(UiMapMode)


def test_situation_off_the_map_has_no_map_mode():
    assert observed(Situation(1, Screen.STAGE_LIST)).map_mode is None


def test_unread_frame_converts_to_nothing():
    assert _situation_to_observed(None) is None
