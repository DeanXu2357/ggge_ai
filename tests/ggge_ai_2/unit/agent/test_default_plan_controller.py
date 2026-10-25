from __future__ import annotations

from dataclasses import dataclass, replace

from ggge_ai_2.actuator.contract import Tap
from ggge_ai_2.agent.belief import Belief, Passing, UiBasis, UiSource
from ggge_ai_2.agent.contract import Step
from ggge_ai_2.agent.default_plan_controller import PlanReflex, ReflexPlan, UiShiftPlan
from ggge_ai_2.agent.generic_plans import PassingWaitPlan
from ggge_ai_2.agent.ui_steps import first_move, operation_step
from ggge_ai_2.mapgeom.contract import KnownMap
from ggge_ai_2.uisim.contract import DangerBand, Operation, Outcome, UiScreen, UiState, UiTap
from tests.ggge_ai_2.fakes.domain import FakeDomain
from tests.ggge_ai_2.fakes.uisim import FakeUiSim

LIST = UiState(UiScreen.STORY_STAGE_LIST)
PREP = UiState(UiScreen.SORTIE_PREP)


def belief() -> Belief:
    return Belief(LIST, UiBasis(UiSource.SEEN, 1), None, KnownMap({}), FakeDomain(), None)


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


def test_reflex_step_comes_before_the_plan_and_keeps_the_plan_valid():
    plan = ReflexPlan((StubReflex(REFLEX_STEP),), StubPlan(valid=False))

    assert plan.next(belief()) == REFLEX_STEP
    assert plan.still_valid(belief())


def test_without_a_reflex_the_plan_gives_the_step_and_the_validity():
    plan = ReflexPlan((StubReflex(None),), StubPlan(valid=False))

    assert plan.next(belief()) == PLAN_STEP
    assert not plan.still_valid(belief())


def test_plan_reflex_adapts_a_generic_plan():
    reflex = PlanReflex(PassingWaitPlan())
    wait = replace(belief(), passing=Passing.WAIT)

    assert not reflex.still_valid(belief())
    assert reflex.react(belief()) is None
    assert reflex.still_valid(wait)
    assert reflex.react(wait) == PassingWaitPlan().next(wait)
    assert ReflexPlan((reflex,), StubPlan(valid=True)).next(wait) == PassingWaitPlan().next(wait)


def test_shift_plan_step_is_the_step_of_its_first_operation():
    operation = Operation("open", LIST, UiTap((0.5, 0.5)), (Outcome("prep", PREP),), 2.0, 1.0)
    uisim = FakeUiSim(
        bands={UiScreen.STORY_STAGE_LIST: DangerBand()},
        operations={UiScreen.STORY_STAGE_LIST: (operation,)},
    )
    plan = UiShiftPlan(PREP, uisim, (2340, 1080))
    move = first_move(uisim, LIST, PREP)
    assert move is not None

    assert plan.still_valid(belief())
    assert plan.next(belief()) == operation_step(move[0], belief(), uisim, plan.screen)
