from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from ggge_ai_2.actuator.contract import Tap
from ggge_ai_2.agent.belief import Belief, Passing, ScreenLock, UiBasis, UiSource
from ggge_ai_2.agent.contract import Step
from ggge_ai_2.agent.plan_controller import (
    GREEDY_BUTTONS,
    GreedyBattlePlan,
    PassingWait,
    PowerSaveUnlock,
    ReflexPlan,
    TapToContinue,
    UiShiftPlan,
    operation_step,
)
from ggge_ai_2.mapgeom.contract import KnownMap
from ggge_ai_2.uisim.contract import (
    DangerBand,
    Operation,
    Outcome,
    UiGesture,
    UiScreen,
    UiState,
    UiTap,
)
from ggge_ai_2.uisim.stage_sim import StageUiSim
from ggge_ai_2.uisim.stages import load_stages
from tests.ggge_ai_2.fakes.domain import FakeDomain
from tests.ggge_ai_2.fakes.uisim import FakeUiSim


def belief(screen_lock: ScreenLock | None = None) -> Belief:
    ui = UiState(UiScreen.STORY_STAGE_LIST)
    return Belief(
        ui, UiBasis(UiSource.SEEN, 1), None, KnownMap({}), FakeDomain(), None, screen_lock
    )


PLAN_STEP = Step("plan", Tap((1, 1)), (), 1.0, (belief(),))
REFLEX_STEP = Step("reflex", Tap((2, 2)), (), 1.0, (belief(),))


@dataclass(frozen=True)
class StubPlan:
    valid: bool

    def still_valid(self, belief: Belief) -> bool:
        return self.valid

    def next(self, belief: Belief) -> Step:
        return PLAN_STEP


@dataclass(frozen=True)
class StubReflex:
    step: Step | None

    def still_valid(self, belief: Belief) -> bool:
        return self.step is not None

    def react(self, belief: Belief) -> Step | None:
        return self.step


def test_belief_without_a_lock_gets_no_unlock():
    unlock = PowerSaveUnlock()

    assert not unlock.still_valid(belief())
    assert unlock.react(belief()) is None


def test_dimmed_lock_gets_a_poke_that_expects_the_lock_icon():
    step = PowerSaveUnlock().react(belief(ScreenLock.DIM))

    assert step is not None
    assert step.gesture == PowerSaveUnlock.POKE_TOP_CENTRE
    assert step.expected == (belief(ScreenLock.ICON),)


def test_lock_icon_gets_a_drag_that_expects_no_lock():
    step = PowerSaveUnlock().react(belief(ScreenLock.ICON))

    assert step is not None
    assert step.gesture == PowerSaveUnlock.DRAG_UP_FROM_LOCK_ICON
    assert step.expected == (belief(),)


def test_reflex_step_comes_before_the_plan_and_keeps_the_plan_valid():
    plan = ReflexPlan((StubReflex(REFLEX_STEP),), StubPlan(valid=False))

    assert plan.next(belief()) == REFLEX_STEP
    assert plan.still_valid(belief())


def test_without_a_reflex_the_plan_gives_the_step_and_the_validity():
    plan = ReflexPlan((StubReflex(None),), StubPlan(valid=False))

    assert plan.next(belief()) == PLAN_STEP
    assert not plan.still_valid(belief())


LIST = UiState(UiScreen.STORY_STAGE_LIST)
PREP = UiState(UiScreen.SORTIE_PREP)
SKIP = UiState(UiScreen.SKIP_STAGE_OVERLAY)


def shift_to_prep(gesture: UiGesture | None, outcomes: tuple[Outcome, ...]) -> UiShiftPlan:
    operation = Operation("open", LIST, gesture, outcomes, 2.0, 1.0)
    uisim = FakeUiSim(
        bands={UiScreen.STORY_STAGE_LIST: DangerBand()},
        operations={UiScreen.STORY_STAGE_LIST: (operation,)},
    )
    return UiShiftPlan(PREP, uisim, (2340, 1080))


def test_operation_without_a_gesture_gives_a_wait_step():
    step = shift_to_prep(None, (Outcome("prep", PREP),)).next(belief())

    assert step.gesture is None


def test_operation_with_two_outcomes_expects_both_in_outcome_order():
    outcomes = (Outcome("skip", SKIP), Outcome("prep", PREP))
    step = shift_to_prep(UiTap((0.5, 0.5)), outcomes).next(belief())

    assert step.expected == (replace(belief(), ui=SKIP), replace(belief(), ui=PREP))


def passing(state: Passing | None) -> Belief:
    return replace(belief(), passing=state)


def test_wait_reflex_waits_only_on_a_wait_frame():
    wait = PassingWait()

    assert [wait.still_valid(passing(state)) for state in (None, *Passing)] == [
        False,
        True,
        False,
    ]
    assert wait.react(passing(None)) is None
    assert wait.react(passing(Passing.TAP_TO_CONTINUE)) is None
    step = wait.react(passing(Passing.WAIT))
    assert step is not None
    assert step.gesture is None


def test_tap_reflex_taps_the_centre_only_on_a_tap_to_continue_frame():
    tap = TapToContinue((2340, 1080))

    assert [tap.still_valid(passing(state)) for state in (None, *Passing)] == [
        False,
        False,
        True,
    ]
    assert tap.react(passing(None)) is None
    assert tap.react(passing(Passing.WAIT)) is None
    step = tap.react(passing(Passing.TAP_TO_CONTINUE))
    assert step is not None
    assert step.gesture == Tap((1170, 540))


def test_shift_plan_step_is_the_step_of_its_first_operation():
    plan = shift_to_prep(UiTap((0.5, 0.5)), (Outcome("prep", PREP),))
    move = plan.first_move(LIST)
    assert move is not None

    assert plan.next(belief()) == operation_step(move[0], belief(), plan.uisim, plan.screen)


REAL_STAGES = Path(__file__).resolve().parents[4] / "assets" / "ui_stages" / "stages.json"
BATTLE_SIM = StageUiSim(load_stages(REAL_STAGES))


def on(screen: UiScreen, auto: bool | None = False) -> Belief:
    return replace(belief(), ui=UiState(screen, None, auto))


@pytest.mark.parametrize(("screen", "name"), GREEDY_BUTTONS.items())
def test_greedy_plan_takes_the_table_operation(screen: UiScreen, name: str):
    plan = GreedyBattlePlan(BATTLE_SIM, (2340, 1080))

    assert plan.still_valid(on(screen))
    assert plan.next(on(screen)).name == name


def test_greedy_plan_turns_auto_off_first():
    plan = GreedyBattlePlan(BATTLE_SIM, (2340, 1080))
    step = plan.next(on(UiScreen.PLAYER_PHASE_OVERVIEW, auto=True))

    assert step.name == "player_phase_overview__auto"
    assert step.expected == (on(UiScreen.PLAYER_PHASE_OVERVIEW, auto=False),)


def test_greedy_plan_follows_the_table_where_the_screen_has_no_auto_toggle():
    plan = GreedyBattlePlan(BATTLE_SIM, (2340, 1080))

    assert plan.next(on(UiScreen.BATTLE_MAIN_SETTING, auto=True)).name == (
        "battle_main_setting__close"
    )


def test_fallback_waits_on_the_weapon_screen():
    plan = GreedyBattlePlan(BATTLE_SIM, (2340, 1080), fallback=True)

    assert plan.still_valid(on(UiScreen.SELECT_WEAPON_IN_BATTLE))
    assert plan.next(on(UiScreen.SELECT_WEAPON_IN_BATTLE)).name == ("select_weapon_in_battle__wait")


def test_fallback_is_invalid_off_the_weapon_screen():
    plan = GreedyBattlePlan(BATTLE_SIM, (2340, 1080), fallback=True)

    assert not plan.still_valid(on(UiScreen.PLAYER_PHASE_OVERVIEW))


def test_greedy_plan_is_invalid_outside_the_table():
    plan = GreedyBattlePlan(BATTLE_SIM, (2340, 1080))

    assert not plan.still_valid(on(UiScreen.STORY_STAGE_LIST))
