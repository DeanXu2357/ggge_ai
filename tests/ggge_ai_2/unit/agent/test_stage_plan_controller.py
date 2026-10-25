from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ggge_ai_2.agent.belief import Belief, Passing, ScreenLock, UiBasis, UiSource
from ggge_ai_2.agent.generic_plans import AutoOffPhase, AutoOffPlan, TapToContinuePlan
from ggge_ai_2.agent.stage_plan_controller import GREEDY_BUTTONS, StagePlan, StagePlanController
from ggge_ai_2.agent.ui_steps import first_move
from ggge_ai_2.mapgeom.contract import KnownMap
from ggge_ai_2.stream.contract import StillWindow
from ggge_ai_2.uisim.contract import UiScreen, UiState
from ggge_ai_2.uisim.stage_sim import StageUiSim
from ggge_ai_2.uisim.stages import load_stages
from tests.ggge_ai_2.fakes.domain import FakeDomain

REAL_STAGES = Path(__file__).resolve().parents[4] / "assets" / "ui_stages" / "stages.json"
BATTLE_SIM = StageUiSim(load_stages(REAL_STAGES))
SCREEN = (2340, 1080)
GOAL = UiScreen.DROP_REWARD_RESULT
OVERVIEW = UiScreen.PLAYER_PHASE_OVERVIEW
WEAPON = UiScreen.SELECT_WEAPON_IN_BATTLE


def on(screen: UiScreen, auto: bool | None = False, until: float = 10.0) -> Belief:
    return Belief(
        UiState(screen, None, auto),
        UiBasis(UiSource.SEEN, 1),
        None,
        KnownMap({}),
        FakeDomain(),
        StillWindow(until - 0.5, until, 1),
    )


def untouched() -> AutoOffPlan:
    return AutoOffPlan(BATTLE_SIM, SCREEN)


def pending(at: float = 10.0) -> AutoOffPlan:
    plan = untouched()
    plan.next(on(OVERVIEW, auto=True, until=at))
    return plan


def confirmed(at: float = 10.0) -> AutoOffPlan:
    return pending(at).confirmed(on(OVERVIEW, auto=False, until=at + 1.0))


def plan(fallback: bool = False, auto: AutoOffPlan | None = None) -> StagePlan:
    return StagePlan(
        GOAL, BATTLE_SIM, SCREEN, auto or untouched(), TapToContinuePlan(SCREEN), fallback
    )


def stage(goal: UiScreen = GOAL) -> StagePlanController:
    return StagePlanController(goal, BATTLE_SIM, SCREEN)


@pytest.mark.parametrize(("screen", "name"), GREEDY_BUTTONS.items())
def test_greedy_part_takes_the_table_operation(screen: UiScreen, name: str):
    assert plan().still_valid(on(screen))
    assert plan().next(on(screen)).name == name


def test_greedy_part_follows_the_table_where_the_screen_has_no_auto_toggle():
    assert plan().next(on(UiScreen.BATTLE_MAIN_SETTING, auto=True)).name == (
        "battle_main_setting__close"
    )


def test_fallback_waits_on_the_weapon_screen():
    assert plan(fallback=True).still_valid(on(WEAPON))
    assert plan(fallback=True).next(on(WEAPON)).name == "select_weapon_in_battle__wait"


def test_fallback_is_invalid_off_the_weapon_screen():
    assert not plan(fallback=True).still_valid(on(OVERVIEW))


def test_battle_screen_with_auto_on_gives_the_toggle_and_not_the_greedy_step():
    step = plan().next(on(OVERVIEW, auto=True))

    assert step.name == "player_phase_overview__auto"
    assert step.expected == ()


def test_lock_frame_comes_before_the_auto_toggle():
    locked = replace(on(OVERVIEW, auto=True), screen_lock=ScreenLock.ICON)

    assert plan().next(locked).name == "power_save_unlock"


def test_passing_frames_come_before_the_auto_toggle():
    wait = replace(on(OVERVIEW, auto=True), passing=Passing.WAIT)
    tap = replace(on(OVERVIEW, auto=True), passing=Passing.TAP_TO_CONTINUE)

    assert plan().next(wait).name == "passing_wait"
    assert plan().next(tap).name == "tap_to_continue"


def test_other_screen_gives_the_first_move_to_the_goal():
    belief = on(UiScreen.STORY_STAGE_LIST, auto=None)
    move = first_move(BATTLE_SIM, belief.ui, UiState(GOAL))
    assert move is not None

    assert plan().still_valid(belief)
    assert plan().next(belief).name == move[0].name


def test_plan_is_invalid_on_the_auto_confirmation():
    waiting = plan(auto=pending(10.0))

    assert not waiting.still_valid(on(OVERVIEW, auto=False))


def test_stage_goal_is_reached_on_a_seen_goal_screen():
    assert stage().goal_reached(on(GOAL))


def test_stage_goal_is_not_reached_on_an_assumed_goal_screen():
    assumed = replace(on(GOAL), ui_basis=UiBasis(UiSource.ASSUMED))

    assert not stage().goal_reached(assumed)


def test_stage_goal_is_not_reached_on_a_passing_frame():
    assert not stage().goal_reached(replace(on(GOAL), passing=Passing.WAIT))


def test_stage_goal_is_not_reached_on_another_screen():
    assert not stage().goal_reached(on(UiScreen.STORY_STAGE_LIST))


def test_stage_think_without_history_gives_an_untouched_auto_plan():
    assert stage().think(on(WEAPON), []) == plan()


def test_stage_think_carries_the_auto_plan_from_history_and_confirms_it():
    previous = plan(auto=pending(10.0))

    thought = stage().think(on(OVERVIEW, auto=False, until=11.0), [previous])

    assert thought is not None
    assert thought.auto_off.phase() is AutoOffPhase.CONFIRMED
    assert thought.auto_off == confirmed(10.0)
    assert previous.auto_off.phase() is AutoOffPhase.PENDING


def test_stage_review_stores_a_copy_of_the_auto_plan():
    live = plan()
    reviewed = stage().review(live, on(OVERVIEW, auto=True))

    live.next(on(OVERVIEW, auto=True))

    assert isinstance(reviewed, StagePlan)
    assert live.auto_off.phase() is AutoOffPhase.PENDING
    assert reviewed.auto_off.phase() is AutoOffPhase.UNTOUCHED


def test_stage_weapon_screen_after_a_valid_greedy_plan_gets_the_fallback():
    assert stage().think(on(WEAPON), [plan()]) == plan(fallback=True)


def test_stage_weapon_screen_after_the_auto_confirmation_gets_no_fallback():
    previous = plan(auto=pending(10.0))

    thought = stage().think(on(WEAPON, auto=False), [previous])

    assert thought == plan(auto=confirmed(10.0))


def test_stage_weapon_screen_after_the_fallback_gets_the_greedy_plan():
    assert stage().think(on(WEAPON), [plan(fallback=True)]) == plan()


def test_stage_think_gives_none_when_no_part_is_valid():
    goal = UiScreen.STORY_STAGE_LIST

    assert stage(goal).think(on(goal, auto=None), []) is None


def test_stage_think_keeps_a_valid_generic_plan_on_the_goal_screen():
    goal = UiScreen.STORY_STAGE_LIST
    frame = replace(on(goal, auto=None), passing=Passing.WAIT)

    assert stage(goal).think(frame, []) is not None
