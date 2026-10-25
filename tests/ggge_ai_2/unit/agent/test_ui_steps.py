from __future__ import annotations

from dataclasses import replace

from ggge_ai_2.agent.belief import Belief, UiBasis, UiSource
from ggge_ai_2.agent.ui_steps import first_move, operation_step
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
from tests.ggge_ai_2.fakes.domain import FakeDomain
from tests.ggge_ai_2.fakes.uisim import FakeUiSim

LIST = UiState(UiScreen.STORY_STAGE_LIST)
PREP = UiState(UiScreen.SORTIE_PREP)
SKIP = UiState(UiScreen.SKIP_STAGE_OVERLAY)
SCREEN = (2340, 1080)


def belief() -> Belief:
    return Belief(LIST, UiBasis(UiSource.SEEN, 1), None, KnownMap({}), FakeDomain(), None)


def open_prep(gesture: UiGesture | None, outcomes: tuple[Outcome, ...]) -> Operation:
    return Operation("open", LIST, gesture, outcomes, 2.0, 1.0)


def sim(operation: Operation) -> FakeUiSim:
    return FakeUiSim(
        bands={UiScreen.STORY_STAGE_LIST: DangerBand()},
        operations={UiScreen.STORY_STAGE_LIST: (operation,)},
    )


def test_operation_without_a_gesture_gives_a_wait_step():
    operation = open_prep(None, (Outcome("prep", PREP),))

    assert operation_step(operation, belief(), sim(operation), SCREEN).gesture is None


def test_operation_with_two_outcomes_expects_both_in_outcome_order():
    operation = open_prep(UiTap((0.5, 0.5)), (Outcome("skip", SKIP), Outcome("prep", PREP)))

    step = operation_step(operation, belief(), sim(operation), SCREEN)

    assert step.expected == (replace(belief(), ui=SKIP), replace(belief(), ui=PREP))


def test_first_move_is_the_first_operation_on_the_path_to_the_goal():
    operation = open_prep(UiTap((0.5, 0.5)), (Outcome("prep", PREP),))

    assert first_move(sim(operation), LIST, PREP) == (operation, Outcome("prep", PREP))


def test_first_move_without_a_path_is_none():
    operation = open_prep(UiTap((0.5, 0.5)), (Outcome("prep", PREP),))

    assert first_move(sim(operation), LIST, SKIP) is None
