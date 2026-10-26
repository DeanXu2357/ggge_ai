from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ggge_ai_2.actuator.contract import Tap
from ggge_ai_2.agent.belief import Belief, Passing, ScreenLock, UiBasis, UiSource
from ggge_ai_2.agent.generic_plans import (
    AutoOffPhase,
    AutoOffPlan,
    PassingWaitPlan,
    PowerSaveLockPlan,
    TapToContinuePlan,
)
from ggge_ai_2.mapgeom.contract import KnownMap
from ggge_ai_2.stream.contract import StillWindow
from ggge_ai_2.uisim.contract import UiAutoMode, UiScreen, UiState
from ggge_ai_2.uisim.stage_sim import StageUiSim
from ggge_ai_2.uisim.stages import load_stages
from tests.ggge_ai_2.fakes.domain import FakeDomain

REAL_STAGES = Path(__file__).resolve().parents[4] / "assets" / "ui_stages" / "stages.json"
BATTLE_SIM = StageUiSim(load_stages(REAL_STAGES))
SCREEN = (2340, 1080)


def belief(screen_lock: ScreenLock | None = None) -> Belief:
    ui = UiState(UiScreen.STORY_STAGE_LIST)
    return Belief(
        ui, UiBasis(UiSource.SEEN, 1), None, KnownMap({}), FakeDomain(), None, screen_lock
    )


def passing(state: Passing | None) -> Belief:
    return replace(belief(), passing=state)


def test_belief_without_a_lock_gets_no_unlock():
    assert not PowerSaveLockPlan().still_valid(belief())


def test_dimmed_lock_gets_a_poke_that_expects_the_lock_icon():
    plan = PowerSaveLockPlan()

    assert plan.still_valid(belief(ScreenLock.DIM))
    step = plan.next(belief(ScreenLock.DIM))
    assert step.gesture == PowerSaveLockPlan.POKE_TOP_CENTRE
    assert step.expected == (belief(ScreenLock.ICON),)


def test_lock_icon_gets_a_drag_that_expects_no_lock():
    plan = PowerSaveLockPlan()

    assert plan.still_valid(belief(ScreenLock.ICON))
    step = plan.next(belief(ScreenLock.ICON))
    assert step.gesture == PowerSaveLockPlan.DRAG_UP_FROM_LOCK_ICON
    assert step.expected == (belief(),)


def test_wait_plan_waits_only_on_a_wait_frame():
    wait = PassingWaitPlan()

    assert [wait.still_valid(passing(state)) for state in (None, *Passing)] == [
        False,
        True,
        False,
    ]
    step = wait.next(passing(Passing.WAIT))
    assert step.gesture is None
    assert step.expected == (passing(Passing.WAIT),)


def test_tap_plan_taps_the_centre_only_on_a_tap_to_continue_frame():
    tap = TapToContinuePlan(SCREEN)

    assert [tap.still_valid(passing(state)) for state in (None, *Passing)] == [
        False,
        False,
        True,
    ]
    step = tap.next(passing(Passing.TAP_TO_CONTINUE))
    assert step.gesture == Tap((1170, 540))
    assert step.expected == (passing(Passing.TAP_TO_CONTINUE),)


def on(screen: UiScreen, auto: UiAutoMode | None, until: float = 10.0) -> Belief:
    return replace(
        belief(), ui=UiState(screen, None, auto), as_of=StillWindow(until - 0.5, until, 1)
    )


OVERVIEW = UiScreen.PLAYER_PHASE_OVERVIEW
TOGGLE = "player_phase_overview__auto"
FULL, SEMI, MANUAL = UiAutoMode.FULL, UiAutoMode.SEMI, UiAutoMode.MANUAL


def pending(at: float = 10.0) -> AutoOffPlan:
    plan = AutoOffPlan(BATTLE_SIM, SCREEN)
    plan.next(on(OVERVIEW, auto=FULL, until=at))
    return plan


def test_full_taps_the_toggle_without_a_prediction_and_becomes_pending():
    plan = AutoOffPlan(BATTLE_SIM, SCREEN)

    assert plan.phase() is AutoOffPhase.UNTOUCHED
    assert plan.still_valid(on(OVERVIEW, auto=FULL))
    step = plan.next(on(OVERVIEW, auto=FULL, until=10.0))
    assert step.name == TOGGLE
    assert step.gesture is not None
    assert step.expected == ()
    assert plan.phase() is AutoOffPhase.PENDING


def test_semi_with_untouched_is_valid_and_taps():
    plan = AutoOffPlan(BATTLE_SIM, SCREEN)

    assert plan.still_valid(on(OVERVIEW, auto=SEMI))
    assert plan.next(on(OVERVIEW, auto=SEMI)).name == TOGGLE
    assert plan.phase() is AutoOffPhase.PENDING


def test_manual_with_untouched_is_invalid():
    assert not AutoOffPlan(BATTLE_SIM, SCREEN).still_valid(on(OVERVIEW, auto=MANUAL))


def test_pending_with_the_tapped_mode_inside_the_deadline_waits():
    plan = pending(at=10.0)
    inside = 10.0 + AutoOffPlan.CONFIRM_DEADLINE - 0.1

    step = plan.next(on(OVERVIEW, auto=FULL, until=inside))

    assert (step.name, step.gesture, step.band, step.deadline, step.expected) == (
        "auto_off_wait",
        None,
        (),
        0.0,
        (),
    )
    assert plan.phase() is AutoOffPhase.PENDING
    assert plan.next(on(OVERVIEW, auto=FULL, until=inside)).name == "auto_off_wait"


def test_pending_with_the_tapped_mode_past_the_deadline_taps_again_and_restarts_the_deadline():
    plan = pending(at=10.0)
    past = 10.0 + AutoOffPlan.CONFIRM_DEADLINE

    assert plan.next(on(OVERVIEW, auto=FULL, until=past)).name == TOGGLE
    assert plan.phase() is AutoOffPhase.PENDING
    inside_new = past + AutoOffPlan.CONFIRM_DEADLINE - 0.1
    assert plan.next(on(OVERVIEW, auto=FULL, until=inside_new)).name == "auto_off_wait"


def test_pending_with_semi_after_a_tap_on_full_inside_the_deadline_taps_again():
    plan = pending(at=10.0)
    inside = 10.0 + AutoOffPlan.CONFIRM_DEADLINE - 0.1

    assert plan.next(on(OVERVIEW, auto=SEMI, until=inside)).name == TOGGLE
    assert plan.phase() is AutoOffPhase.PENDING
    assert plan.next(on(OVERVIEW, auto=SEMI, until=inside + 0.1)).name == "auto_off_wait"


def test_pending_with_semi_past_the_deadline_taps_again():
    plan = pending(at=10.0)
    past = 10.0 + AutoOffPlan.CONFIRM_DEADLINE

    assert plan.next(on(OVERVIEW, auto=SEMI, until=past)).name == TOGGLE
    assert plan.phase() is AutoOffPhase.PENDING


def test_only_pending_with_manual_awaits_confirmation():
    untouched = AutoOffPlan(BATTLE_SIM, SCREEN)
    confirmed = pending().confirmed(on(OVERVIEW, auto=MANUAL))

    assert pending().awaiting_confirmation(on(OVERVIEW, auto=MANUAL))
    assert not pending().awaiting_confirmation(on(OVERVIEW, auto=FULL))
    assert not pending().awaiting_confirmation(on(OVERVIEW, auto=SEMI))
    assert not untouched.awaiting_confirmation(on(OVERVIEW, auto=MANUAL))
    assert not confirmed.awaiting_confirmation(on(OVERVIEW, auto=MANUAL))


def test_confirmed_returns_a_confirmed_copy_and_keeps_the_original():
    plan = pending(at=10.0)

    copy = plan.confirmed(on(OVERVIEW, auto=MANUAL))

    assert copy.phase() is AutoOffPhase.CONFIRMED
    assert plan.phase() is AutoOffPhase.PENDING


def test_confirmed_copy_keeps_the_tap_time():
    copy = pending(at=10.0).confirmed(on(OVERVIEW, auto=MANUAL))

    assert copy == pending(at=10.0).confirmed(on(OVERVIEW, auto=MANUAL))
    assert copy != pending(at=20.0).confirmed(on(OVERVIEW, auto=MANUAL))


def test_confirmed_without_the_confirmation_returns_an_equal_copy():
    plan = pending(at=10.0)

    copy = plan.confirmed(on(OVERVIEW, auto=SEMI))

    assert copy == plan
    assert copy is not plan
    assert copy.phase() is AutoOffPhase.PENDING


def test_pending_on_a_screen_without_auto_stays_pending():
    plan = pending(at=10.0)
    no_auto = on(UiScreen.BATTLE_MAIN_SETTING, auto=None)

    assert not plan.still_valid(no_auto)
    assert not plan.awaiting_confirmation(no_auto)
    assert plan.confirmed(no_auto).phase() is AutoOffPhase.PENDING


def test_auto_plan_is_invalid_without_the_toggle_operation():
    plan = AutoOffPlan(BATTLE_SIM, SCREEN)

    assert not plan.still_valid(on(UiScreen.BATTLE_MAIN_SETTING, auto=FULL))
