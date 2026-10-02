from ggge_ai_2.uisim.contract import MapMode, MapModeIs, Overlay, Screen, ScreenIs, UiState


def test_state_off_the_map_is_one_screen_fact():
    state = UiState(Screen.STAGE_LIST, frozenset({Overlay.DIALOG}))

    assert state.facts() == (ScreenIs(Screen.STAGE_LIST, frozenset({Overlay.DIALOG})),)


def test_state_on_the_map_adds_the_map_mode_fact():
    state = UiState(Screen.BATTLE_MAP, map_mode=MapMode.SELECTED)

    assert state.facts() == (ScreenIs(Screen.BATTLE_MAP), MapModeIs(MapMode.SELECTED))
