from ggge_ai.battle.actions import ActionKind
from ggge_ai.battle.advisor import AdvisorConfig, advise
from ggge_ai.battle.bridge import UnitSpec, build_sim_state
from ggge_ai.sim import SimWeapon
from ggge_ai.battle.state import BattleState, Faction, UnitState
from ggge_ai.domain.roster import CapabilityType, UnitCapability


def _weapon(rmax=3, power=5000, en_cost=0):
    return SimWeapon("rifle", power=power, range_min=1, range_max=rmax, en_cost=en_cost)


def _spec(**kw):
    base = dict(max_hp=100, en_max=50, unit_attack=5000, unit_defense=1000,
                pilot_attack=9000, pilot_defense=1000, reaction=0.0, mobility=0.0,
                move_range=3, weapons=(_weapon(),))
    base.update(kw)
    return UnitSpec(**base)


def _board(enemy_world=(96.0, 0.0), enemy_hp=5):
    battle = BattleState()
    battle.add_unit(UnitState("a", Faction.ALLY, world_pos=(0.0, 0.0), hp=100, en=50))
    battle.add_unit(UnitState("e", Faction.ENEMY, world_pos=enemy_world, hp=enemy_hp, en=50))
    return battle


def test_bridge_quantizes_positions_and_injects_capabilities():
    battle = _board()
    ally = battle.unit("a")
    ally.capabilities = [
        UnitCapability(CapabilityType.KILL_REMOVE, charges=2),
        UnitCapability(CapabilityType.SKILL_EN_REFILL),
        UnitCapability(CapabilityType.SUPPORT_DEFEND),
        UnitCapability(CapabilityType.SUPPORT_ATTACK, charges=2),
        UnitCapability.unknown("mystery aura"),
    ]
    result = build_sim_state(battle, {"a": _spec(), "e": _spec()}, cell_size=48.0)
    sim_ally = result.state.unit("a")
    sim_enemy = result.state.unit("e")
    assert sim_ally.pos == (0, 0)
    assert sim_enemy.pos == (2, 0)
    assert sim_ally.react_charges == 2
    assert sim_ally.support_defend_charges == 1
    assert sim_ally.support_attack_charges == 2
    assert [s.kind for s in sim_ally.skills] == [ActionKind.SKILL_EN_REFILL]
    assert sim_ally.hp == 100
    assert result.to_world((2, 0)) == (96.0, 0.0)


def test_bridge_records_assumptions_for_unknown_numbers():
    battle = BattleState()
    battle.add_unit(UnitState("a", Faction.ALLY, world_pos=(0.0, 0.0)))
    battle.add_unit(UnitState("ghost", Faction.ENEMY))
    result = build_sim_state(battle, {}, cell_size=48.0)
    joined = "\n".join(result.assumptions)
    assert "a: HP unknown" in joined
    assert "a: no weapons known" in joined
    assert "ghost: no world position" in joined
    assert result.state.unit("ghost") is None


def test_bridge_nudges_cell_collisions():
    battle = BattleState()
    battle.add_unit(UnitState("a", Faction.ALLY, world_pos=(0.0, 0.0), hp=1))
    battle.add_unit(UnitState("b", Faction.ALLY, world_pos=(10.0, 0.0), hp=1))
    result = build_sim_state(battle, {}, cell_size=48.0)
    pos_a = result.state.unit("a").pos
    pos_b = result.state.unit("b").pos
    assert pos_a != pos_b
    assert any("nudged" in a for a in result.assumptions)


def test_advise_attacks_adjacent_weak_enemy():
    battle = _board(enemy_world=(48.0, 0.0))
    advice = advise(battle, {"a": _spec(), "e": _spec()},
                    AdvisorConfig(cell_size=48.0, time_budget_s=5.0, max_depth=2))
    assert advice is not None
    assert advice.kind == ActionKind.ATTACK
    assert advice.target_id == "e"
    assert advice.weapon == "rifle"
    assert not advice.assumptions


def test_advise_returns_world_coordinates_for_moves():
    battle = _board(enemy_world=(480.0, 0.0))
    specs = {
        "a": _spec(weapons=(_weapon(rmax=1),)),
        "e": _spec(weapons=(_weapon(rmax=1),), move_range=0),
    }
    advice = advise(battle, specs,
                    AdvisorConfig(cell_size=48.0, time_budget_s=5.0, max_depth=4))
    assert advice is not None
    assert advice.kind == ActionKind.MOVE
    assert advice.move_world == (144.0, 0.0)


def test_advise_none_when_no_enemies():
    battle = BattleState()
    battle.add_unit(UnitState("a", Faction.ALLY, world_pos=(0.0, 0.0), hp=100))
    assert advise(battle, {}) is None
