"""HTN 引擎的合成任務域：有序分解、方法回溯、無適用方法。"""

from __future__ import annotations

import pytest

from ggge_ai.strategy.htn import (
    Decomposition,
    Domain,
    Method,
    NoApplicableMethod,
    Operator,
    State,
    Task,
    decompose,
)


def _with(state: State, **changes: object) -> dict[str, object]:
    return {**state, **changes}


def travel_domain() -> Domain:
    domain = Domain()
    domain.add_operator(
        Operator("call_taxi", effect=lambda state, task: _with(state, taxi=True)),
    )
    domain.add_operator(Operator("swipe_card"))
    domain.add_operator(
        Operator(
            "hand_cash",
            precondition=lambda state, task: state.get("cash", 0) >= 10,
            effect=lambda state, task: _with(state, cash=state["cash"] - 10),
        )
    )
    domain.add_operator(
        Operator(
            "ride",
            precondition=lambda state, task: bool(state.get("taxi")),
            effect=lambda state, task: _with(state, at="dest"),
        )
    )
    domain.add_operator(
        Operator(
            "walk",
            precondition=lambda state, task: bool(state.get("legs_ok")),
            effect=lambda state, task: _with(state, at="dest"),
        )
    )
    domain.add_operator(
        Operator(
            "tip",
            precondition=lambda state, task: state.get("cash", 0) >= 5,
            effect=lambda state, task: _with(state, cash=state["cash"] - 5),
        )
    )
    domain.add_method(
        Method(
            name="by_taxi",
            task="travel",
            subtasks=lambda state, task: [Task("call_taxi"), Task("pay"), Task("ride")],
            precondition=lambda state, task: state.get("distance", 0) > 2,
        )
    )
    domain.add_method(
        Method(
            name="on_foot",
            task="travel",
            subtasks=lambda state, task: [Task("walk")],
            precondition=lambda state, task: bool(state.get("legs_ok")),
        )
    )
    domain.add_method(
        Method(
            name="with_card",
            task="pay",
            subtasks=lambda state, task: [Task("swipe_card")],
            precondition=lambda state, task: bool(state.get("card")),
        )
    )
    domain.add_method(
        Method(
            name="with_cash",
            task="pay",
            subtasks=lambda state, task: [Task("hand_cash")],
            precondition=lambda state, task: state.get("cash", 0) >= 10,
        )
    )
    return domain


def _names(result: Decomposition) -> tuple[str, ...]:
    return tuple(step.name for step in result.plan)


def test_ordered_decomposition_threads_operator_effects():
    result = decompose(travel_domain(), {"distance": 5, "card": True}, [Task("travel")])

    assert isinstance(result, Decomposition)
    assert _names(result) == ("call_taxi", "swipe_card", "ride")
    assert result.state["at"] == "dest"


def test_backtracks_to_the_next_method_when_a_subtask_dead_ends():
    state = {"distance": 5, "card": False, "cash": 0, "legs_ok": True}

    result = decompose(travel_domain(), state, [Task("travel")])

    assert isinstance(result, Decomposition)
    assert _names(result) == ("walk",)


def test_backtracks_when_a_method_starves_the_tasks_that_follow():
    state = {"distance": 5, "card": False, "cash": 10, "legs_ok": True}

    result = decompose(travel_domain(), state, [Task("travel"), Task("tip")])

    assert isinstance(result, Decomposition)
    assert _names(result) == ("walk", "tip")
    assert result.state["cash"] == 5


def test_no_applicable_method_is_a_value_with_the_candidates_it_tried():
    state = {"distance": 5, "card": False, "cash": 0, "legs_ok": False}

    result = decompose(travel_domain(), state, [Task("travel")])

    assert isinstance(result, NoApplicableMethod)
    assert result.task.name == "travel"
    assert result.tried == ("by_taxi", "on_foot")
    assert result.cause is not None and result.cause.task.name == "pay"
    assert "travel: no applicable method" in result.describe()
    assert "<- pay" in result.describe()


def test_unknown_task_reports_no_method_declared():
    result = decompose(travel_domain(), {}, [Task("fly")])

    assert isinstance(result, NoApplicableMethod)
    assert result.reason == "no method declared"
    assert result.tried == ()


def test_operator_precondition_failure_is_reported_on_the_operator():
    result = decompose(travel_domain(), {}, [Task("ride")])

    assert isinstance(result, NoApplicableMethod)
    assert result.task.name == "ride"
    assert result.reason == "operator precondition unmet"


def test_empty_task_list_decomposes_to_an_empty_plan():
    result = decompose(travel_domain(), {"cash": 1}, [])

    assert isinstance(result, Decomposition)
    assert result.plan == ()
    assert result.state == {"cash": 1}


def test_a_name_cannot_be_both_operator_and_compound_task():
    domain = travel_domain()

    with pytest.raises(ValueError):
        domain.add_method(Method("silly", "walk", subtasks=lambda state, task: []))
    with pytest.raises(ValueError):
        domain.add_operator(Operator("travel"))
