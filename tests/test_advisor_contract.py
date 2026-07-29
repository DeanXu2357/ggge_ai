"""Advisor 契約：只有介面、保守下界語意、注入即生效。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ggge_ai.sandbox.advise import Advisor, Appraisal, Guarantee, Pricing, Verdict
from ggge_ai.stage.actions import Action, Attack
from ggge_ai.stage.goals import Annihilation
from ggge_ai.stage.planner import Plan, plan
from ggge_ai.stage.state import StageState
from tests.fixtures.stage_offline import MockAdvisor, battle, kills_everything

ADVISE = Path(__file__).resolve().parents[1] / "src" / "ggge_ai" / "sandbox" / "advise.py"


def _is_interface_body(node: ast.FunctionDef) -> bool:
    body = [stmt for stmt in node.body if not _is_docstring(stmt)]
    return all(isinstance(stmt, ast.Expr) and _is_ellipsis(stmt.value) for stmt in body)


def _is_docstring(stmt: ast.stmt) -> bool:
    return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(
        stmt.value.value, str
    )


def _is_ellipsis(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is Ellipsis


def test_the_advise_module_carries_interface_only():
    tree = ast.parse(ADVISE.read_text(encoding="utf-8"))
    bodies = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]

    assert bodies, "契約模組至少要有介面方法"
    assert all(_is_interface_body(node) for node in bodies)


def test_the_pricing_default_promises_nothing():
    assert Pricing(1.0).guarantee is Guarantee.NONE
    assert {item.value for item in Guarantee} == {"none", "kill"}
    assert {item.value for item in Verdict} == {"pursue", "withdraw"}


def test_an_injected_advisor_satisfies_the_protocol_structurally():
    advisor: Advisor[StageState, Action] = MockAdvisor(kills_everything())

    state = battle(allies=["a1"], enemies=["e1"])
    prices = advisor.price(state, (Attack("a1", "e1"),))

    assert advisor.appraise(state) == Appraisal(Verdict.PURSUE)
    assert prices == (Pricing(1.0, Guarantee.KILL),)


def test_the_planner_takes_every_number_from_the_advisor():
    state = battle(allies=["a1"], enemies=["e1"])
    advisor = MockAdvisor(kills_everything(cost=7.5))

    result = plan(state, Annihilation(), advisor)

    assert isinstance(result, Plan)
    assert result.cost == pytest.approx(7.5)
    assert result.steps[0].pricing == Pricing(7.5, Guarantee.KILL)
    assert advisor.price_calls > 0
