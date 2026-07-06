from ggge_ai.domain.roster import CapabilityType, TeamRoster, UnitCapability
from ggge_ai.battle.actions import (
    ActionCatalog,
    ActionKind,
    BattleAction,
    actions_from_capabilities,
    build_attack_action,
)
from ggge_ai.battle.state import BattleState, Faction, UnitState


class FakeScanProvider:
    def __init__(self, actions):
        self._actions = actions

    def scan(self, state, unit):
        return list(self._actions)


def _board_with_enemy(hp=100):
    state = BattleState()
    state.add_unit(UnitState("ally1", Faction.ALLY))
    state.add_unit(UnitState("enemy1", Faction.ENEMY, hp=hp))
    return state


def test_ability_injection_generates_actions_from_roster():
    roster = TeamRoster()
    roster.add_capability("ally1", UnitCapability(CapabilityType.SKILL_EN_REFILL))
    roster.add_capability("ally1", UnitCapability(CapabilityType.SUPPORT_ATTACK))

    injected = actions_from_capabilities("ally1", roster.capabilities("ally1"))
    kinds = {a.kind for a in injected}
    assert kinds == {ActionKind.SKILL_EN_REFILL, ActionKind.SUPPORT_ATTACK}


def test_kill_remove_and_unknown_are_lazy_no_action():
    caps = [
        UnitCapability(CapabilityType.KILL_REMOVE, charges=2),
        UnitCapability.unknown("mystery burst"),
    ]
    # neither maps onto a pressable action; injection must not raise or emit
    assert actions_from_capabilities("ally1", caps) == []


def test_catalog_merges_both_sources():
    state = _board_with_enemy()
    unit = state.unit("ally1")
    scan = FakeScanProvider([build_attack_action("ally1", "enemy1", expected_damage=40)])
    caps = [UnitCapability(CapabilityType.SKILL_EN_REFILL)]

    catalog = ActionCatalog.build(state, unit, scan_provider=scan, capabilities=caps)
    kinds = sorted(a.kind for a in catalog.actions)
    assert kinds == [ActionKind.ATTACK, ActionKind.SKILL_EN_REFILL]


def test_catalog_dedup_on_id_collision():
    state = _board_with_enemy()
    unit = state.unit("ally1")
    # a scan-sourced action colliding by id with an injected one
    collide = BattleAction(
        action_id=f"{ActionKind.SKILL_EN_REFILL}:ally1",
        kind=ActionKind.SKILL_EN_REFILL,
    )
    scan = FakeScanProvider([collide])
    caps = [UnitCapability(CapabilityType.SKILL_EN_REFILL)]

    catalog = ActionCatalog.build(state, unit, scan_provider=scan, capabilities=caps)
    matching = [a for a in catalog.actions if a.action_id == f"{ActionKind.SKILL_EN_REFILL}:ally1"]
    assert len(matching) == 1
    # scan is authority: its entry wins
    assert matching[0] is collide


def test_attack_precondition_reflects_target_state():
    state = _board_with_enemy(hp=0)
    unit = state.unit("ally1")
    attack = build_attack_action("ally1", "enemy1", expected_damage=40)
    assert attack.is_applicable(state, unit) is False

    state.unit("enemy1").hp = 50
    assert attack.is_applicable(state, unit) is True
