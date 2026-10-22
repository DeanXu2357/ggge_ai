from __future__ import annotations

from pathlib import Path

from ggge_ai_2.uisim.contract import (
    Operation,
    Outcome,
    RatioRect,
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

    operation = _operation(sim, UiState(UiScreen.BATTLE_PREP_ATTACK, auto=True), "go")

    assert [outcome.then for outcome in operation.outcomes] == [
        UiState(UiScreen.PLAYER_PHASE_OVERVIEW, None, True),
        UiState(UiScreen.BATTLE_SCORE_RESULT, None, None),
    ]


def test_auto_toggle_flips_the_known_auto_state() -> None:
    sim = _sim(_screen("battle_prep_attack", (_button("battle_prep_attack__auto"),)))
    state = UiState(UiScreen.BATTLE_PREP_ATTACK, auto=False)

    operation = _operation(sim, state, "battle_prep_attack__auto")

    assert operation.gesture == UiTap((0.5, 0.5))
    assert operation.outcomes == (
        Outcome("auto_on", UiState(UiScreen.BATTLE_PREP_ATTACK, None, True)),
    )
    assert sim.advance(state, operation.outcomes[0]) == UiState(
        UiScreen.BATTLE_PREP_ATTACK, None, True
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
