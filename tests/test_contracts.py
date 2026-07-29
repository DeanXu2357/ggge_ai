"""跨層契約的建構與不可變性。"""

from __future__ import annotations

import dataclasses

import pytest

from ggge_ai.contracts import (
    Bottleneck,
    Constraint,
    Diagnosis,
    Ending,
    GoalSpec,
    HiddenPolicy,
    IntelDelta,
    Objective,
    StageOrder,
    StageReport,
)


def test_enum_values_are_the_cli_spellings():
    assert {item.value for item in Objective} == {"clear", "score", "achievement", "hidden"}
    assert {item.value for item in Constraint} == {"split", "single"}
    assert {item.value for item in HiddenPolicy} == {"enter", "decline"}
    assert {item.value for item in Ending} == {"victory", "defeat", "stuck", "withdrew"}


def test_goal_spec_is_frozen():
    goal = GoalSpec(
        stage="demo",
        objectives=frozenset({Objective.CLEAR, Objective.SCORE}),
        constraint=Constraint.SINGLE,
    )

    assert Objective.CLEAR in goal.objectives
    assert goal.constraint is Constraint.SINGLE
    with pytest.raises(dataclasses.FrozenInstanceError):
        goal.stage = "other"


def test_stage_order_carries_policy_and_budget():
    order = StageOrder(
        stage="demo",
        objectives=frozenset({Objective.HIDDEN}),
        hidden_policy=HiddenPolicy.ENTER,
        max_ticks=400,
    )

    assert order.hidden_policy is HiddenPolicy.ENTER
    assert order.max_ticks == 400
    with pytest.raises(dataclasses.FrozenInstanceError):
        order.max_ticks = 1


def test_stage_report_defaults_to_an_empty_intel_delta():
    report = StageReport(ending=Ending.WITHDREW, achieved={Objective.CLEAR: False})

    assert report.ending is Ending.WITHDREW
    assert report.achieved[Objective.CLEAR] is False
    assert report.intel.facts == {}


def test_intel_deltas_do_not_share_state():
    first = IntelDelta()
    first.facts["enemy_range"] = 5

    assert IntelDelta().facts == {}


def test_diagnosis_holds_win_rate_and_bottlenecks():
    diagnosis = Diagnosis(win_rate=0.35, bottlenecks=(Bottleneck(kind="firepower", gap=1200.0),))

    assert diagnosis.win_rate == pytest.approx(0.35)
    assert diagnosis.bottlenecks[0].kind == "firepower"
    assert diagnosis.bottlenecks[0].gap == pytest.approx(1200.0)
