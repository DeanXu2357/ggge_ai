from ggge_ai.battle.state import (
    BattleState,
    Faction,
    ThirdPartyControl,
    UnitState,
)


def test_defaults_are_optional_and_unknown():
    unit = UnitState(unit_id="ally1", faction=Faction.ALLY)
    assert unit.world_pos is None
    assert unit.hp is None
    assert unit.en is None
    assert unit.acted is False
    assert unit.hp_known is False
    assert unit.capabilities == []


def test_global_predicate_defaults():
    state = BattleState()
    assert state.turn == 1
    assert state.roster_verified is False
    assert state.third_party_control is ThirdPartyControl.UNKNOWN


def test_faction_partitioning_and_lookup():
    state = BattleState()
    a = state.add_unit(UnitState("ally1", Faction.ALLY))
    e = state.add_unit(UnitState("enemy1", Faction.ENEMY, hp=120))
    t = state.add_unit(UnitState("tp1", Faction.THIRD_PARTY))

    assert state.allies() == [a]
    assert state.enemies() == [e]
    assert state.third_party() == [t]
    assert state.unit("enemy1") is e
    assert state.unit("enemy1").hp_known is True
    assert state.unit("missing") is None
