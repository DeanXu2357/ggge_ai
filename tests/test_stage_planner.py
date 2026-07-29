"""GOAP A*：計價驅動的前向搜尋、回合交界截斷、規劃失敗即值。"""

from __future__ import annotations

import pytest

from ggge_ai.sandbox.advise import Guarantee, Pricing
from ggge_ai.stage.actions import Attack, Standby, Withdraw
from ggge_ai.stage.goals import Annihilation, LeftStage
from ggge_ai.stage.planner import NoPlan, Plan, PlannerConfig, plan
from tests.fixtures.stage_offline import (
    KindPricer,
    MockAdvisor,
    battle,
    exit_only,
    kills_everything,
    never_kills,
)


def _labels(result: Plan) -> list[str]:
    return [step.action.label for step in result.steps]


def test_a_guaranteed_kill_chain_is_the_plan():
    state = battle(allies=["a1", "a2"], enemies=["e1", "e2"])

    result = plan(state, Annihilation(), MockAdvisor(kills_everything()))

    assert isinstance(result, Plan)
    assert {step.action.unit for step in result.steps} == {"a1", "a2"}
    assert {step.action.target for step in result.steps} == {"e1", "e2"}
    assert result.cost == pytest.approx(2.0)
    assert not result.truncated


def test_an_already_annihilated_board_plans_nothing():
    result = plan(battle(allies=["a1"], enemies=[]), Annihilation(), MockAdvisor(kills_everything()))

    assert isinstance(result, Plan)
    assert result.steps == ()
    assert result.cost == pytest.approx(0.0)
    assert result.expanded == 0


def test_without_a_kill_guarantee_annihilation_is_unreachable():
    state = battle(allies=["a1"], enemies=["e1", "e2"])

    result = plan(state, Annihilation(), MockAdvisor(never_kills()))

    assert isinstance(result, NoPlan)
    assert result.reason == "search space exhausted"
    assert result.expanded > 0


def test_the_planner_commits_only_the_prefix_before_the_phase_boundary():
    # 一機兩敵：這回合殺得掉一個，另一個要等下個我方回合。
    state = battle(allies=["a1"], enemies=["e1", "e2"])

    result = plan(state, Annihilation(), MockAdvisor(kills_everything()))

    assert isinstance(result, Plan)
    assert len(result.steps) == 1
    assert _labels(result)[0].startswith("attack:a1->")
    assert result.truncated
    assert result.cost == pytest.approx(3.0)


def test_a_refused_price_takes_the_candidate_out_of_the_search():
    state = battle(allies=["a1"], enemies=["e1"])
    only_standby = KindPricer(standby=Pricing(1.0))

    assert isinstance(plan(state, Annihilation(), MockAdvisor(only_standby)), NoPlan)


def test_the_planner_prefers_the_cheaper_priced_route():
    state = battle(allies=["a1", "a2"], enemies=["e1"])

    def pricer(_state, action):
        if isinstance(action, Attack):
            return Pricing(1.0 if action.unit == "a2" else 9.0, Guarantee.KILL)
        if isinstance(action, Standby):
            return Pricing(1.0)
        return None

    result = plan(state, Annihilation(), MockAdvisor(pricer))

    assert isinstance(result, Plan)
    assert _labels(result) == ["attack:a2->e1"]
    assert result.cost == pytest.approx(1.0)


def test_the_withdrawal_goal_is_reached_by_the_leave_action():
    state = battle(allies=["a1"], enemies=["e1"])

    result = plan(state, LeftStage(), MockAdvisor(exit_only()))

    assert isinstance(result, Plan)
    assert _labels(result) == ["withdraw"]
    assert isinstance(result.steps[0].action, Withdraw)


def test_a_negative_price_is_rejected_because_a_star_needs_non_negative_edges():
    state = battle(allies=["a1"], enemies=["e1"])
    bad = KindPricer(attack=Pricing(-1.0, Guarantee.KILL), standby=Pricing(1.0))

    with pytest.raises(ValueError, match="負計價"):
        plan(state, Annihilation(), MockAdvisor(bad))


def test_a_misaligned_price_list_is_rejected():
    class Sloppy:
        def appraise(self, state):
            raise AssertionError("規劃不該問建議")

        def price(self, state, candidates):
            return (Pricing(1.0),)

    with pytest.raises(ValueError, match="逐位對齊"):
        plan(battle(allies=["a1"], enemies=["e1"]), Annihilation(), Sloppy())


def test_the_expansion_limit_ends_the_search_as_a_value():
    state = battle(allies=[f"a{i}" for i in range(6)], enemies=[f"e{i}" for i in range(6)])

    result = plan(
        state,
        Annihilation(),
        MockAdvisor(never_kills()),
        PlannerConfig(max_expansions=5),
    )

    assert isinstance(result, NoPlan)
    assert result.reason == "expansion limit reached"


def test_an_admissible_heuristic_finds_the_same_optimal_cost():
    state = battle(allies=["a1", "a2"], enemies=["e1", "e2"])
    advisor = MockAdvisor(kills_everything())

    blind = plan(state, Annihilation(), advisor, PlannerConfig())
    guided = plan(state, Annihilation(), advisor, PlannerConfig(min_action_cost=1.0))

    assert isinstance(blind, Plan) and isinstance(guided, Plan)
    assert guided.cost == pytest.approx(blind.cost)
    assert guided.expanded <= blind.expanded
