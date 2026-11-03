from __future__ import annotations

from pathlib import Path

import pytest

from ggge_ai_2.uisim.contract import (
    DangerBand,
    Observed,
    OpenGroup,
    Operation,
    Outcome,
    RatioRect,
    UiAutoMode,
    UiScreen,
    UiState,
    UiSwipe,
    UiTap,
)
from ggge_ai_2.uisim.stage_sim import LONG_PRESS_SECONDS, WAIT_SECONDS, StageUiSim
from ggge_ai_2.uisim.stages import ButtonDef, CallerGroup, ScreenDef, Stages, load_stages

REAL_STAGES = Path(__file__).resolve().parents[4] / "assets" / "ui_stages" / "stages.json"

RECT = RatioRect(0.25, 0.25, 0.75, 0.75)


def _button(
    name: str,
    to: tuple[str, ...] = (),
    rect: RatioRect | None = RECT,
    gesture: str | None = None,
    forbidden: bool = False,
) -> ButtonDef:
    return ButtonDef(
        name=name,
        to=to,
        rect=rect,
        gesture=gesture,
        dynamic=False,
        forbidden=forbidden,
        deadline=5.0,
    )


def _screen(
    name: str,
    buttons: tuple[ButtonDef, ...] = (),
    kind: str = "page",
    game_to: tuple[str, ...] = (),
) -> ScreenDef:
    return ScreenDef(name=name, kind=kind, control="player", buttons=buttons, game_to=game_to)


def _sim(*screens: ScreenDef, groups: tuple[CallerGroup, ...] = ()) -> StageUiSim:
    return StageUiSim(
        Stages(
            screens={screen.name: screen for screen in screens},
            groups={group.name: group for group in groups},
        )
    )


def _operation(sim: StageUiSim, state: UiState, name: str) -> Operation:
    return next(op for op in sim.successors(state) if op.name == name)


def _outcome_names(operation: Operation) -> list[str]:
    return [outcome.name for outcome in operation.outcomes]


def test_tap_outcomes_hop_through_an_animation_screen() -> None:
    sim = _sim(
        _screen(
            "battle_prep_attack",
            (_button("start", ("challenge_battle_check", "battle_clear_view")),),
        ),
        _screen(
            "battle_clear_view",
            (_button("tap_next", ("battle_score_result",)),),
            kind="animation",
        ),
    )
    state = UiState(UiScreen.BATTLE_PREP_ATTACK)

    operation = _operation(sim, state, "start")

    assert operation == Operation(
        name="start",
        precondition=state,
        gesture=UiTap((0.5, 0.5)),
        outcomes=(
            Outcome("challenge_battle_check", UiState(UiScreen.CHALLENGE_BATTLE_CHECK)),
            Outcome("battle_score_result", UiState(UiScreen.BATTLE_SCORE_RESULT)),
        ),
        deadline=5.0,
        cost=1.0,
    )


def test_group_target_resolves_to_the_entry_screens() -> None:
    sim = _sim(
        _screen("battle_prep_attack", (_button("menu", ("battle_menu@battle_prep_attack",)),)),
        groups=(CallerGroup("battle_menu", ("battle_main_setting",), ("win_condition_overlay",)),),
    )

    operation = _operation(sim, UiState(UiScreen.BATTLE_PREP_ATTACK), "menu")

    assert _outcome_names(operation) == ["battle_main_setting"]


def test_target_without_group_uses_the_screen_before_the_caller() -> None:
    sim = _sim(
        _screen(
            "battle_prep_attack",
            (_button("detail", ("battle_prep_detail@battle_prep_attack",)),),
        ),
    )

    operation = _operation(sim, UiState(UiScreen.BATTLE_PREP_ATTACK), "detail")

    assert _outcome_names(operation) == ["battle_prep_detail"]


def test_out_of_scope_targets_are_dropped() -> None:
    sim = _sim(
        _screen(
            "battle_prep_attack",
            (
                _button("mixed", ("unit_detail_state", "select_skill_in_battle")),
                _button("outside", ("home_screen",)),
            ),
        ),
    )

    operations = sim.successors(UiState(UiScreen.BATTLE_PREP_ATTACK))

    assert [op.name for op in operations] == ["mixed"]
    assert _outcome_names(operations[0]) == ["select_skill_in_battle"]


def test_forbidden_and_rectless_buttons_are_skipped() -> None:
    sim = _sim(
        _screen(
            "battle_prep_attack",
            (
                _button("forbidden", ("select_skill_in_battle",), forbidden=True),
                _button("rectless", ("select_skill_in_battle",), rect=None),
                _button("kept", ("select_skill_in_battle",)),
            ),
        ),
    )

    operations = sim.successors(UiState(UiScreen.BATTLE_PREP_ATTACK))

    assert [op.name for op in operations] == ["kept"]


def test_auto_is_carried_only_into_screens_with_an_auto_button() -> None:
    sim = _sim(
        _screen(
            "battle_prep_attack",
            (
                _button("battle_prep_attack__auto"),
                _button("go", ("player_phase_overview", "battle_score_result")),
            ),
        ),
        _screen("player_phase_overview", (_button("player_phase_overview__auto"),)),
        _screen("battle_score_result"),
    )

    state = UiState(UiScreen.BATTLE_PREP_ATTACK, auto=UiAutoMode.SEMI)
    operation = _operation(sim, state, "go")

    assert [outcome.then for outcome in operation.outcomes] == [
        UiState(UiScreen.PLAYER_PHASE_OVERVIEW, auto=UiAutoMode.SEMI),
        UiState(UiScreen.BATTLE_SCORE_RESULT),
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
    sim = _sim(_screen("battle_prep_attack", (_button("battle_prep_attack__auto"),)))
    state = UiState(UiScreen.BATTLE_PREP_ATTACK, auto=mode)

    operation = _operation(sim, state, "battle_prep_attack__auto")

    assert operation.gesture == UiTap((0.5, 0.5))
    assert operation.outcomes == (Outcome(label, UiState(UiScreen.BATTLE_PREP_ATTACK, auto=then)),)
    assert sim.advance(state, operation.outcomes[0]) == UiState(
        UiScreen.BATTLE_PREP_ATTACK, auto=then
    )


def test_auto_toggle_needs_a_known_auto_state() -> None:
    sim = _sim(_screen("battle_prep_attack", (_button("battle_prep_attack__auto"),)))

    assert sim.successors(UiState(UiScreen.BATTLE_PREP_ATTACK)) == ()


def test_wait_operation_lists_the_game_moves_then_the_stay() -> None:
    sim = _sim(
        _screen(
            "non_player_phase_battle_view",
            game_to=("player_phase_overview", "battle_clear_view"),
        ),
        _screen(
            "battle_clear_view",
            (_button("tap_next", ("battle_score_result",)),),
            kind="animation",
        ),
    )
    state = UiState(UiScreen.NON_PLAYER_PHASE_BATTLE_VIEW)

    (operation,) = sim.successors(state)

    assert operation.name == "non_player_phase_battle_view__wait"
    assert operation.gesture is None
    assert operation.deadline == WAIT_SECONDS
    assert _outcome_names(operation) == [
        "player_phase_overview",
        "battle_score_result",
        "non_player_phase_battle_view",
    ]


def test_long_press_is_a_swipe_with_equal_start_and_end() -> None:
    sim = _sim(
        _screen(
            "battle_prep_attack",
            (_button("hold", ("select_skill_in_battle",), gesture="long_press"),),
        ),
    )

    operation = _operation(sim, UiState(UiScreen.BATTLE_PREP_ATTACK), "hold")

    assert isinstance(operation.gesture, UiSwipe)
    assert operation.gesture.start == operation.gesture.end
    assert operation.gesture.duration == LONG_PRESS_SECONDS


def test_real_start_battle_outcomes() -> None:
    sim = StageUiSim(load_stages(REAL_STAGES))

    operation = _operation(
        sim, UiState(UiScreen.BATTLE_PREP_ATTACK), "battle_prep_attack__start_battle"
    )

    assert _outcome_names(operation) == [
        "challenge_battle_check",
        "non_player_phase_battle_view",
        "player_phase_overview",
        "select_action_in_battle",
        "battle_score_result",
    ]


def test_real_battle_menu_opens_with_the_caller() -> None:
    sim = StageUiSim(load_stages(REAL_STAGES))
    state = UiState(UiScreen.SELECT_WEAPON_IN_BATTLE)

    operation = _operation(sim, state, "select_weapon_in_battle__battle_menu")

    assert [outcome.then.stack for outcome in operation.outcomes] == [
        (OpenGroup("battle_menu", UiScreen.SELECT_WEAPON_IN_BATTLE),)
    ]


def test_real_battle_menu_close_returns_to_the_caller() -> None:
    sim = StageUiSim(load_stages(REAL_STAGES))
    state = UiState(
        UiScreen.BATTLE_MAIN_SETTING,
        (OpenGroup("battle_menu", UiScreen.SELECT_WEAPON_IN_BATTLE),),
    )

    operation = _operation(sim, state, "battle_main_setting__close")

    assert operation.outcomes == (
        Outcome("select_weapon_in_battle", UiState(UiScreen.SELECT_WEAPON_IN_BATTLE)),
    )


# UiScreen has no unit detail screens and no roster screen yet, so these
# tests use other screens in their place.
ROSTER = UiScreen.WIN_CONDITION_OVERLAY
DETAIL_STATE = UiScreen.REWARD_DETAIL
DETAIL_ACTION = UiScreen.DROP_REWARD_RESULT
OVERVIEW = UiScreen.PLAYER_PHASE_OVERVIEW
MENU = UiScreen.BATTLE_MAIN_SETTING
SETTINGS = UiScreen.BATTLE_SETTINGS_IN_BATTLE
MENU_FROM_OVERVIEW = OpenGroup("battle_menu", OVERVIEW)
DETAIL_FROM_ROSTER = OpenGroup("unit_detail", ROSTER)


def _detail_screen(name: UiScreen, tab: UiScreen) -> ScreenDef:
    return _screen(
        name.value,
        (
            _button("tab", (tab.value,)),
            _button("close", (ROSTER.value, "select_action_in_battle")),
        ),
    )


def _nested_sim() -> StageUiSim:
    return _sim(
        _screen("player_phase_overview", (_button("menu", ("battle_main_setting",)),)),
        _screen(
            "battle_prep_attack",
            (
                _button("menu", ("battle_main_setting",)),
                _button("plain_detail", (DETAIL_STATE.value,)),
            ),
        ),
        _screen("select_weapon_in_battle"),
        _screen(
            "battle_main_setting",
            (
                _button("settings", ("battle_settings_in_battle",)),
                _button("squad", (ROSTER.value,)),
                _button(
                    "close",
                    ("select_weapon_in_battle", "player_phase_overview", "battle_prep_attack"),
                ),
                _button("give_up", ("battle_score_result",)),
            ),
        ),
        _screen("battle_settings_in_battle", (_button("close", ("battle_main_setting",)),)),
        _screen(
            ROSTER.value,
            (
                _button("card", (f"unit_detail@{ROSTER.value}",)),
                _button("back", ("battle_main_setting",)),
            ),
        ),
        _detail_screen(DETAIL_STATE, DETAIL_ACTION),
        _detail_screen(DETAIL_ACTION, DETAIL_STATE),
        groups=(
            CallerGroup("battle_menu", ("battle_main_setting",), (SETTINGS.value, ROSTER.value)),
            CallerGroup("unit_detail", (DETAIL_STATE.value, DETAIL_ACTION.value), ()),
            CallerGroup("unit_info", (DETAIL_STATE.value, DETAIL_ACTION.value), ()),
        ),
    )


def _thens(sim: StageUiSim, state: UiState, name: str) -> list[UiState]:
    return [outcome.then for outcome in _operation(sim, state, name).outcomes]


def test_push_opens_the_group_of_a_plain_entry_with_the_screen_before() -> None:
    assert _thens(_nested_sim(), UiState(OVERVIEW), "menu") == [
        UiState(MENU, (MENU_FROM_OVERVIEW,))
    ]


def test_push_takes_the_group_named_by_the_target_on_top_of_an_open_group() -> None:
    state = UiState(ROSTER, (MENU_FROM_OVERVIEW,))

    assert _thens(_nested_sim(), state, "card") == [
        UiState(DETAIL_STATE, (MENU_FROM_OVERVIEW, DETAIL_FROM_ROSTER)),
        UiState(DETAIL_ACTION, (MENU_FROM_OVERVIEW, DETAIL_FROM_ROSTER)),
    ]


def test_push_skips_a_plain_entry_of_two_groups() -> None:
    assert _thens(_nested_sim(), UiState(UiScreen.BATTLE_PREP_ATTACK), "plain_detail") == [
        UiState(DETAIL_STATE)
    ]


def test_push_from_a_screen_of_the_group_has_an_unknown_caller() -> None:
    assert _thens(_nested_sim(), UiState(SETTINGS), "close") == [
        UiState(MENU, (OpenGroup("battle_menu", None),))
    ]


def test_moving_inside_the_top_group_keeps_the_stack() -> None:
    sim = _nested_sim()
    nested = (MENU_FROM_OVERVIEW, DETAIL_FROM_ROSTER)

    assert _thens(sim, UiState(MENU, (MENU_FROM_OVERVIEW,)), "settings") == [
        UiState(SETTINGS, (MENU_FROM_OVERVIEW,))
    ]
    assert _thens(sim, UiState(DETAIL_STATE, nested), "tab") == [UiState(DETAIL_ACTION, nested)]


def test_return_to_caller_gives_only_the_caller_and_pops_its_group() -> None:
    state = UiState(DETAIL_ACTION, (MENU_FROM_OVERVIEW, DETAIL_FROM_ROSTER))

    operation = _operation(_nested_sim(), state, "close")

    assert operation.outcomes == (Outcome(ROSTER.value, UiState(ROSTER, (MENU_FROM_OVERVIEW,))),)


def test_return_to_an_unknown_caller_gives_every_target() -> None:
    state = UiState(MENU, (OpenGroup("battle_menu", None),))

    assert _thens(_nested_sim(), state, "close") == [
        UiState(UiScreen.SELECT_WEAPON_IN_BATTLE),
        UiState(OVERVIEW),
        UiState(UiScreen.BATTLE_PREP_ATTACK),
    ]


def test_pop_clears_the_groups_that_do_not_hold_the_target() -> None:
    state = UiState(MENU, (MENU_FROM_OVERVIEW,))

    assert _thens(_nested_sim(), state, "give_up") == [UiState(UiScreen.BATTLE_SCORE_RESULT)]


def test_nested_path_through_two_groups_returns_to_the_first_caller() -> None:
    sim = _nested_sim()
    state = UiState(OVERVIEW)
    visited: list[UiState] = []

    for name in ("menu", "squad", "card", "tab", "close", "back", "close"):
        outcome = _operation(sim, state, name).outcomes[0]
        state = sim.advance(state, outcome)
        visited.append(state)

    nested = (MENU_FROM_OVERVIEW, DETAIL_FROM_ROSTER)
    assert visited == [
        UiState(MENU, (MENU_FROM_OVERVIEW,)),
        UiState(ROSTER, (MENU_FROM_OVERVIEW,)),
        UiState(DETAIL_STATE, nested),
        UiState(DETAIL_ACTION, nested),
        UiState(ROSTER, (MENU_FROM_OVERVIEW,)),
        UiState(MENU, (MENU_FROM_OVERVIEW,)),
        UiState(OVERVIEW),
    ]


def test_sync_takes_the_stack_of_the_outcome_with_the_observed_screen() -> None:
    state = UiState(ROSTER, (MENU_FROM_OVERVIEW,))

    synced = _nested_sim().sync(state, Observed(DETAIL_STATE, auto=UiAutoMode.FULL))

    assert synced == UiState(
        DETAIL_STATE, (MENU_FROM_OVERVIEW, DETAIL_FROM_ROSTER), UiAutoMode.FULL
    )


def test_sync_equals_the_outcome_that_advance_gives() -> None:
    sim = _nested_sim()
    state = UiState(ROSTER, (MENU_FROM_OVERVIEW,))

    for operation in sim.successors(state):
        for outcome in operation.outcomes:
            then = sim.advance(state, outcome)
            assert sim.sync(state, Observed(then.screen, then.auto)) == then


def test_sync_on_the_same_screen_keeps_the_stack() -> None:
    state = UiState(DETAIL_STATE, (MENU_FROM_OVERVIEW, DETAIL_FROM_ROSTER))

    assert _nested_sim().sync(state, Observed(DETAIL_STATE)) == state


def test_sync_outside_the_outcomes_pushes_the_only_group_of_an_entry() -> None:
    state = UiState(UiScreen.SELECT_WEAPON_IN_BATTLE, auto=UiAutoMode.MANUAL)

    synced = _nested_sim().sync(state, Observed(MENU, auto=UiAutoMode.SEMI))

    assert synced == UiState(
        MENU, (OpenGroup("battle_menu", UiScreen.SELECT_WEAPON_IN_BATTLE),), UiAutoMode.SEMI
    )


def test_sync_outside_the_outcomes_does_not_push_an_entry_of_two_groups() -> None:
    state = UiState(UiScreen.SELECT_WEAPON_IN_BATTLE)

    assert _nested_sim().sync(state, Observed(DETAIL_STATE)) == UiState(DETAIL_STATE)


def test_sync_outside_the_outcomes_pops_to_the_group_that_holds_the_screen() -> None:
    sim = _nested_sim()
    nested = UiState(DETAIL_ACTION, (MENU_FROM_OVERVIEW, DETAIL_FROM_ROSTER))
    menu = UiState(SETTINGS, (MENU_FROM_OVERVIEW,))

    assert sim.sync(nested, Observed(MENU)) == UiState(MENU, (MENU_FROM_OVERVIEW,))
    assert sim.sync(menu, Observed(UiScreen.BATTLE_SCORE_RESULT)) == UiState(
        UiScreen.BATTLE_SCORE_RESULT
    )


def test_danger_band_holds_the_forbidden_button_rect() -> None:
    forbidden_rect = RatioRect(0.0, 0.0, 0.1, 0.1)
    sim = _sim(
        _screen(
            "battle_prep_attack",
            (
                _button("kept", ("select_skill_in_battle",)),
                _button("retreat", ("player_phase_overview",), forbidden_rect, forbidden=True),
            ),
        ),
    )

    band = sim.danger_band(UiState(UiScreen.BATTLE_PREP_ATTACK))

    assert band == DangerBand((forbidden_rect,))


def test_danger_band_is_empty_without_forbidden_buttons() -> None:
    sim = _sim(_screen("battle_prep_attack", (_button("kept", ("select_skill_in_battle",)),)))

    assert sim.danger_band(UiState(UiScreen.BATTLE_PREP_ATTACK)) == DangerBand()
