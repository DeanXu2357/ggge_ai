from ggge_ai.domain.roster import CapabilityType, UnitCapability
from ggge_ai.battle.actions import ActionCatalog, ActionKind, build_attack_action
from ggge_ai.battle.planner import (
    ThresholdKillEstimator,
    plan_activation,
)
from ggge_ai.battle.state import BattleState, Faction, UnitState


class AlwaysKillEstimator:
    def is_kill(self, action, target):
        return True


def _board(enemy_hps):
    state = BattleState()
    state.add_unit(UnitState("ally1", Faction.ALLY))
    for i, hp in enumerate(enemy_hps):
        state.add_unit(UnitState(f"enemy{i}", Faction.ENEMY, hp=hp))
    return state


def test_double_react_chains_three_kills():
    state = _board([100, 100, 100])
    unit = state.unit("ally1")
    unit.capabilities.append(UnitCapability(CapabilityType.KILL_REMOVE, charges=2))
    attacks = [
        build_attack_action("ally1", "enemy0", expected_damage=150),
        build_attack_action("ally1", "enemy1", expected_damage=150),
        build_attack_action("ally1", "enemy2", expected_damage=150),
    ]
    catalog = ActionCatalog(actions=attacks)

    chain = plan_activation(state, unit, catalog, ThresholdKillEstimator())
    assert len(chain) == 3
    assert all(a.kind == ActionKind.ATTACK for a in chain)
    assert {a.target_id for a in chain} == {"enemy0", "enemy1", "enemy2"}


def test_react_budget_caps_depth_at_three():
    # 5 charges would suggest depth 6, but the cap is 3 steps
    state = _board([10, 10, 10, 10, 10])
    unit = state.unit("ally1")
    unit.capabilities.append(UnitCapability(CapabilityType.KILL_REMOVE, charges=5))
    attacks = [build_attack_action("ally1", f"enemy{i}", expected_damage=999) for i in range(5)]
    catalog = ActionCatalog(actions=attacks)

    chain = plan_activation(state, unit, catalog, ThresholdKillEstimator())
    assert len(chain) == 3


def test_no_capability_degrades_to_greedy_max_damage():
    state = _board([100, 100])
    unit = state.unit("ally1")  # no capabilities
    attacks = [
        build_attack_action("ally1", "enemy0", expected_damage=30),
        build_attack_action("ally1", "enemy1", expected_damage=70),
    ]
    catalog = ActionCatalog(actions=attacks)

    # even an estimator that would call everything a kill must not chain
    # without a re-act capability
    chain = plan_activation(state, unit, catalog, AlwaysKillEstimator())
    assert len(chain) == 1
    assert chain[0].target_id == "enemy1"


def test_unknown_hp_never_kills_never_chains():
    state = _board([None, None, None])
    unit = state.unit("ally1")
    unit.capabilities.append(UnitCapability(CapabilityType.KILL_REMOVE, charges=2))
    attacks = [
        build_attack_action("ally1", "enemy0", expected_damage=40),
        build_attack_action("ally1", "enemy1", expected_damage=80),
        build_attack_action("ally1", "enemy2", expected_damage=60),
    ]
    catalog = ActionCatalog(actions=attacks)

    chain = plan_activation(state, unit, catalog, ThresholdKillEstimator())
    # no numeric HP -> no kill claim -> single best-damage attack, no chain
    assert len(chain) == 1
    assert chain[0].target_id == "enemy1"


def test_no_targets_stands_by():
    state = _board([])
    unit = state.unit("ally1")
    catalog = ActionCatalog(actions=[])

    chain = plan_activation(state, unit, catalog, ThresholdKillEstimator())
    assert len(chain) == 1
    assert chain[0].kind == ActionKind.STANDBY


def test_unknown_capability_is_inert_for_planner():
    state = _board([100])
    unit = state.unit("ally1")
    unit.capabilities.append(UnitCapability.unknown("phase shift"))
    attacks = [build_attack_action("ally1", "enemy0", expected_damage=50)]
    catalog = ActionCatalog(actions=attacks)

    # unknown capability must not raise and must not grant re-activation
    chain = plan_activation(state, unit, catalog, ThresholdKillEstimator())
    assert len(chain) == 1
    assert chain[0].target_id == "enemy0"
