from __future__ import annotations

import pytest

from ggge_ai_2.uisim.chart import Chart, Gesture, ScreenChart, Target, Transition
from ggge_ai_2.uisim.chart_data import CHART
from ggge_ai_2.uisim.chart_sim import LONG_PRESS_SECONDS, SWIPE_SECONDS, WAIT_SECONDS, ChartUiSim
from ggge_ai_2.uisim.contract import (
    DangerBand,
    Observed,
    OpenGroup,
    Operation,
    Outcome,
    RatioRect,
    UiAutoMode,
    UiGesture,
    UiScreen,
    UiState,
    UiSwipe,
    UiTap,
)

SIM = ChartUiSim(CHART)

ACTION = UiScreen.SELECT_ACTION_IN_BATTLE
WEAPON = UiScreen.SELECT_WEAPON_IN_BATTLE
MENU = UiScreen.BATTLE_MAIN_SETTING
ALLY = UiScreen.ROSTER_LIST_ALLY
STATE_ROSTER = UiScreen.UNIT_DETAIL_STATE_ROSTER
MENU_FROM_ACTION = OpenGroup("battle_menu", ACTION)
DETAIL_FROM_ALLY = OpenGroup("unit_detail", ALLY)
NESTED = (MENU_FROM_ACTION, DETAIL_FROM_ALLY)


def _operation(state: UiState, name: str) -> Operation:
    return next(operation for operation in SIM.successors(state) if operation.name == name)


def _names(state: UiState) -> list[str]:
    return [operation.name for operation in SIM.successors(state)]


def _thens(state: UiState, name: str) -> list[UiState]:
    return [outcome.then for outcome in _operation(state, name).outcomes]


def test_start_battle_outcomes_hop_through_the_clear_view() -> None:
    operation = _operation(UiState(UiScreen.BATTLE_PREP_ATTACK), "battle_prep_attack__start_battle")

    assert [outcome.name for outcome in operation.outcomes] == [
        "challenge_battle_check",
        "non_player_phase_battle_view",
        "player_phase_overview",
        "select_action_in_battle",
        "battle_score_result",
    ]


def test_battle_menu_opens_with_the_screen_before_as_the_caller() -> None:
    assert _thens(UiState(WEAPON), "select_weapon_in_battle__battle_menu") == [
        UiState(MENU, (OpenGroup("battle_menu", WEAPON),))
    ]


def test_battle_menu_close_returns_only_to_the_caller() -> None:
    state = UiState(MENU, (OpenGroup("battle_menu", WEAPON),))

    assert _operation(state, "battle_main_setting__close").outcomes == (
        Outcome("select_weapon_in_battle", UiState(WEAPON)),
    )


def test_unit_detail_close_returns_only_to_the_caller() -> None:
    state = UiState(UiScreen.UNIT_DETAIL_ACTION, (OpenGroup("unit_detail", ACTION),))

    assert _operation(state, "unit_detail_action__close").outcomes == (
        Outcome("select_action_in_battle", UiState(ACTION)),
    )


def test_close_with_an_unknown_caller_gives_every_target_and_pops_the_group() -> None:
    state = UiState(UiScreen.BATTLE_PREP_DETAIL, (OpenGroup("battle_prep_detail", None),))

    assert _thens(state, "battle_prep_detail__cancel") == [
        UiState(UiScreen.BATTLE_PREP_ATTACK),
        UiState(UiScreen.BATTLE_PREP_RESPONSE_ATTACK),
    ]


def test_screen_inside_the_top_group_keeps_the_stack() -> None:
    state = UiState(MENU, (MENU_FROM_ACTION,))

    assert _thens(state, "battle_main_setting__settings") == [
        UiState(UiScreen.BATTLE_SETTINGS_IN_BATTLE, (MENU_FROM_ACTION,))
    ]
    assert _thens(state, "battle_main_setting__squad_info") == [UiState(ALLY, (MENU_FROM_ACTION,))]


def test_entry_reached_from_inside_a_group_that_is_not_open_has_an_unknown_caller() -> None:
    assert _thens(UiState(UiScreen.WIN_CONDITION_OVERLAY), "win_condition_overlay__close") == [
        UiState(MENU, (OpenGroup("battle_menu", None),))
    ]


def test_roster_card_opens_every_roster_page_of_the_unit_detail() -> None:
    state = UiState(ALLY, (MENU_FROM_ACTION,))

    assert _thens(state, "roster_list_ally__mech_card") == [
        UiState(UiScreen.UNIT_DETAIL_STATE_ROSTER, NESTED),
        UiState(UiScreen.UNIT_DETAIL_ACTION_ROSTER, NESTED),
        UiState(UiScreen.UNIT_DETAIL_ABILITY_ROSTER, NESTED),
        UiState(UiScreen.UNIT_DETAIL_SUMMARY_ROSTER, NESTED),
    ]


def test_ally_tab_switches_to_the_enemy_roster_inside_the_battle_menu() -> None:
    state = UiState(ALLY, (MENU_FROM_ACTION,))

    assert _thens(state, "roster_list_ally__tab_enemy") == [
        UiState(UiScreen.ROSTER_LIST_ENEMY, (MENU_FROM_ACTION,))
    ]


def test_transitions_without_a_rect_give_no_operation() -> None:
    assert "select_action_in_battle__ally_unit_icon" not in _names(UiState(ACTION))
    assert SIM.successors(UiState(STATE_ROSTER, NESTED)) == ()
    assert SIM.successors(UiState(UiScreen.ROSTER_LIST_ENEMY, (MENU_FROM_ACTION,))) == ()


def test_unit_detail_through_the_roster_returns_to_the_screen_that_opened_the_menu() -> None:
    state = UiState(ACTION)
    visited: list[UiState] = []
    for name, screen in (
        ("select_action_in_battle__battle_menu", MENU),
        ("battle_main_setting__squad_info", ALLY),
        ("roster_list_ally__mech_card", STATE_ROSTER),
    ):
        outcome = next(o for o in _operation(state, name).outcomes if o.then.screen == screen)
        state = SIM.advance(state, outcome)
        visited.append(state)
    state = SIM.sync(state, Observed(ALLY))
    visited.append(state)
    for name in ("roster_list_ally__close", "battle_main_setting__close"):
        (outcome,) = _operation(state, name).outcomes
        state = SIM.advance(state, outcome)
        visited.append(state)

    assert visited == [
        UiState(MENU, (MENU_FROM_ACTION,)),
        UiState(ALLY, (MENU_FROM_ACTION,)),
        UiState(STATE_ROSTER, NESTED),
        UiState(ALLY, (MENU_FROM_ACTION,)),
        UiState(MENU, (MENU_FROM_ACTION,)),
        UiState(ACTION),
    ]


def test_sync_on_the_same_screen_keeps_the_stack_and_takes_the_auto_mode() -> None:
    state = UiState(STATE_ROSTER, NESTED)

    assert SIM.sync(state, Observed(STATE_ROSTER, UiAutoMode.FULL)) == UiState(
        STATE_ROSTER, NESTED, UiAutoMode.FULL
    )


def test_sync_takes_the_stack_of_the_outcome_with_the_observed_screen() -> None:
    state = UiState(ALLY, (MENU_FROM_ACTION,))

    synced = SIM.sync(state, Observed(UiScreen.UNIT_DETAIL_SUMMARY_ROSTER))

    assert synced == UiState(UiScreen.UNIT_DETAIL_SUMMARY_ROSTER, NESTED)


@pytest.mark.parametrize(
    "state",
    [
        UiState(ACTION, auto=UiAutoMode.MANUAL),
        UiState(MENU, (MENU_FROM_ACTION,)),
        UiState(ALLY, (MENU_FROM_ACTION,)),
        UiState(UiScreen.NON_PLAYER_PHASE_BATTLE_VIEW, auto=UiAutoMode.FULL),
    ],
)
def test_sync_equals_the_outcome_that_advance_gives(state: UiState) -> None:
    for operation in SIM.successors(state):
        for outcome in operation.outcomes:
            then = SIM.advance(state, outcome)
            assert SIM.sync(state, Observed(then.screen, then.auto)) == then


def test_sync_outside_the_outcomes_pushes_the_only_group_of_an_entry() -> None:
    synced = SIM.sync(UiState(ACTION), Observed(UiScreen.UNIT_DETAIL_ABILITY))

    assert synced == UiState(UiScreen.UNIT_DETAIL_ABILITY, (OpenGroup("unit_detail", ACTION),))


def test_sync_outside_the_outcomes_pops_every_group_that_does_not_hold_the_screen() -> None:
    assert SIM.sync(UiState(STATE_ROSTER, NESTED), Observed(ACTION)) == UiState(ACTION)


def test_sync_outside_the_outcomes_pops_to_the_group_that_holds_the_screen() -> None:
    synced = SIM.sync(UiState(STATE_ROSTER, NESTED), Observed(MENU))

    assert synced == UiState(MENU, (MENU_FROM_ACTION,))


def test_auto_is_carried_only_into_screens_with_an_auto_button() -> None:
    state = UiState(ACTION, auto=UiAutoMode.SEMI)

    assert _thens(state, "select_action_in_battle__select_weapon") == [
        UiState(WEAPON, auto=UiAutoMode.SEMI)
    ]
    assert _thens(state, "select_action_in_battle__battle_menu") == [
        UiState(MENU, (MENU_FROM_ACTION,))
    ]


@pytest.mark.parametrize(
    ("mode", "then", "label"),
    [
        (UiAutoMode.FULL, UiAutoMode.SEMI, "auto_semi"),
        (UiAutoMode.SEMI, UiAutoMode.MANUAL, "auto_manual"),
        (UiAutoMode.MANUAL, UiAutoMode.FULL, "auto_full"),
    ],
)
def test_auto_toggle_moves_to_the_next_mode_in_the_cycle(
    mode: UiAutoMode, then: UiAutoMode, label: str
) -> None:
    state = UiState(UiScreen.PLAYER_PHASE_OVERVIEW, auto=mode)

    operation = _operation(state, "player_phase_overview__auto")

    assert operation.gesture == UiTap(((0.743 + 0.812) / 2, (0.016 + 0.079) / 2))
    assert operation.outcomes == (
        Outcome(label, UiState(UiScreen.PLAYER_PHASE_OVERVIEW, auto=then)),
    )


def test_auto_toggle_needs_a_known_auto_mode() -> None:
    assert "player_phase_overview__auto" not in _names(UiState(UiScreen.PLAYER_PHASE_OVERVIEW))


def test_wait_lists_the_game_moves_then_the_stay() -> None:
    state = UiState(UiScreen.NON_PLAYER_PHASE_BATTLE_VIEW)

    (operation,) = SIM.successors(state)

    assert operation.name == "non_player_phase_battle_view__wait"
    assert operation.gesture is None
    assert operation.deadline == WAIT_SECONDS
    assert [outcome.name for outcome in operation.outcomes] == [
        "battle_prep_response_attack",
        "exp_reward_result",
        "player_phase_overview",
        "battle_score_result",
        "non_player_phase_battle_view",
    ]


@pytest.mark.parametrize(
    ("gesture", "expected"),
    [
        (Gesture.TAP, UiTap((0.5, 0.5))),
        (Gesture.LONG_PRESS, UiSwipe((0.5, 0.5), (0.5, 0.5), LONG_PRESS_SECONDS)),
        (Gesture.SWIPE_X, UiSwipe((0.8, 0.5), (0.2, 0.5), SWIPE_SECONDS)),
        (Gesture.SWIPE_Y, UiSwipe((0.5, 0.8), (0.5, 0.2), SWIPE_SECONDS)),
    ],
)
def test_gesture_acts_inside_the_rect(gesture: Gesture, expected: UiGesture) -> None:
    rect = RatioRect(0.0, 0.0, 1.0, 1.0)
    transition = Transition("scroll", rect, (Target(UiScreen.SERIES_LIST),), 5.0, gesture)
    sim = ChartUiSim(Chart({UiScreen.SERIES_LIST: ScreenChart((transition,))}, ()))

    (operation,) = sim.successors(UiState(UiScreen.SERIES_LIST))

    assert operation.gesture == expected


def test_danger_band_holds_the_forbidden_diamond_row() -> None:
    band = SIM.danger_band(UiState(UiScreen.AP_RECOVERY_OVERLAY))

    assert band == DangerBand((RatioRect(0.309, 0.529, 0.703, 0.802),))
    assert "ap_recovery_overlay__diamond" not in _names(UiState(UiScreen.AP_RECOVERY_OVERLAY))


def test_danger_band_is_empty_without_forbidden_buttons() -> None:
    assert SIM.danger_band(UiState(MENU)) == DangerBand()
