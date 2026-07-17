import pytest

from ggge_ai.goap.action import Action, Goal
from ggge_ai.goap.planner import PlanNotFound, plan
from ggge_ai.goap.state import WorldState


def nav(name, from_screen, to_screen, cost=1.0):
    a = Action()
    a.name = name
    a.cost = cost
    a.preconditions = {"screen": from_screen}
    a.effects = {"screen": to_screen}
    return a


def goal_screen(screen):
    g = Goal()
    g.name = f"reach:{screen}"
    g.conditions = {"screen": screen}
    return g


NAV_ACTIONS = [
    nav("title->main", "title", "main_menu"),
    nav("main->stage", "main_menu", "stage_select"),
    nav("stage->setup", "stage_select", "unit_setup"),
    nav("setup->battle", "unit_setup", "battle_map"),
]


def test_multi_step_navigation():
    result = plan(WorldState(screen="title"), goal_screen("battle_map"), NAV_ACTIONS)
    assert [a.name for a in result.actions] == [
        "title->main",
        "main->stage",
        "stage->setup",
        "setup->battle",
    ]
    assert result.total_cost == 4.0


def test_prefers_cheaper_path():
    actions = NAV_ACTIONS + [nav("shortcut", "title", "battle_map", cost=10.0)]
    result = plan(WorldState(screen="title"), goal_screen("battle_map"), actions)
    assert "shortcut" not in [a.name for a in result.actions]

    actions = NAV_ACTIONS + [nav("shortcut", "title", "battle_map", cost=2.0)]
    result = plan(WorldState(screen="title"), goal_screen("battle_map"), actions)
    assert [a.name for a in result.actions] == ["shortcut"]


def test_already_satisfied_returns_empty_plan():
    result = plan(WorldState(screen="battle_map"), goal_screen("battle_map"), NAV_ACTIONS)
    assert result.actions == []
    assert result.total_cost == 0.0


def test_unreachable_goal_raises():
    with pytest.raises(PlanNotFound) as exc_info:
        plan(WorldState(screen="battle_map"), goal_screen("title"), NAV_ACTIONS)
    assert exc_info.value.exhausted


def test_compound_goal():
    deploy = Action()
    deploy.name = "deploy"
    deploy.preconditions = {"screen": "battle_map"}
    deploy.effects = {"deployed": True}

    g = Goal()
    g.conditions = {"screen": "battle_map", "deployed": True}

    result = plan(WorldState(screen="title"), g, NAV_ACTIONS + [deploy])
    assert result.actions[-1].name == "deploy"
    assert len(result.actions) == 5
