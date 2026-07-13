from ggge_ai.battle.actions import ActionKind
from ggge_ai.battle.sim import (
    DEFAULT_PARAMS,
    Decision,
    DefenseKind,
    DefenseResponse,
    Phase,
    SimState,
    SimUnit,
    SimWeapon,
    compute_damage,
    legal_attacks,
    standby,
    step,
)
from ggge_ai.battle.state import Faction


def _rifle(power=1500, en_cost=0, rmax=3, can_counter=True):
    return SimWeapon("rifle", power=power, range_min=1, range_max=rmax,
                     en_cost=en_cost, can_counter=can_counter)


def _ally(**kw):
    base = dict(unit_id="a", faction=Faction.ALLY, pos=(0, 0), hp=100, max_hp=100,
                en=20, en_max=20, unit_attack=5000, pilot_attack=5000, move_range=3)
    base.update(kw)
    return SimUnit(**base)


def _enemy(uid="e", pos=(2, 0), hp=100, **kw):
    base = dict(unit_id=uid, faction=Faction.ENEMY, pos=pos, hp=hp, max_hp=100,
                unit_defense=1000, pilot_defense=1000)
    base.update(kw)
    return SimUnit(**base)


def test_phase_rotates_when_faction_finishes_and_skips_empty_third_party():
    s = SimState(units=[_ally(weapons=[]), _enemy()])
    s2 = step(s, standby("a"))
    assert s2.phase is Phase.ENEMY
    assert s2.turn == 1


def test_charges_reset_at_own_phase_start():
    ally = _ally(weapons=[], react_charges=0, react_charges_max=2,
                 support_defend_charges=0, support_defend_charges_max=1,
                 support_attack_charges=0, support_attack_charges_max=1)
    enemy = _enemy()
    enemy.weapons = []
    s = SimState(units=[ally, enemy])
    s = step(s, standby("a"))       # -> enemy phase
    s = step(s, standby("e"))       # -> ally phase, turn 2
    assert s.phase is Phase.ALLY
    assert s.turn == 2
    a = s.unit("a")
    assert a.react_charges == 2
    assert a.support_defend_charges == 1
    assert a.support_attack_charges == 1


def test_kill_grants_reactivation_and_consumes_charge():
    ally = _ally(weapons=[_rifle(power=5000)], react_charges=2, react_charges_max=2)
    s = SimState(units=[ally, _enemy("e0", pos=(2, 0), hp=5), _enemy("e1", pos=(3, 0), hp=5)])
    s2 = step(s, Decision("a", ActionKind.ATTACK, target_id="e0", weapon="rifle", hit=True))
    assert s2.unit("e0") is None
    a = s2.unit("a")
    assert a.acted is False
    assert a.react_charges == 1
    assert s2.phase is Phase.ALLY


def test_dead_unit_is_removed():
    s = SimState(units=[_ally(weapons=[_rifle(power=5000)]), _enemy("e0", pos=(1, 0), hp=1)])
    s2 = step(s, Decision("a", ActionKind.ATTACK, target_id="e0", weapon="rifle", hit=True))
    assert all(u.unit_id != "e0" for u in s2.units)


def test_en_gate_blocks_attack():
    ally = _ally(en=0, en_max=20, weapons=[_rifle(power=5000, en_cost=10)])
    enemy = _enemy("e0", pos=(1, 0), hp=100)
    s = SimState(units=[ally, enemy])
    s2 = step(s, Decision("a", ActionKind.ATTACK, target_id="e0", weapon="rifle", hit=True))
    assert s2.unit("e0").hp == 100
    assert s2.unit("a").en == 0


def test_out_of_range_attack_does_nothing():
    ally = _ally(move_range=0, weapons=[_rifle(power=5000, rmax=1)])
    enemy = _enemy("e0", pos=(5, 0), hp=100)
    s = SimState(units=[ally, enemy])
    s2 = step(s, Decision("a", ActionKind.ATTACK, target_id="e0", weapon="rifle", hit=True))
    assert s2.unit("e0").hp == 100


def test_defense_multipliers_reduce_damage():
    attacker = _enemy("boss", pos=(1, 0), unit_attack=5000, pilot_attack=5000,
                      weapons=[_rifle(power=1500)])
    weapon = attacker.weapons[0]
    defender = _ally(unit_defense=2000, pilot_defense=2000)
    plain = compute_damage(attacker, defender, weapon, 1.0, DEFAULT_PARAMS)
    defended = compute_damage(attacker, defender, weapon, DEFAULT_PARAMS.defend_multiplier, DEFAULT_PARAMS)
    shielded = compute_damage(attacker, defender, weapon, DEFAULT_PARAMS.shield_multiplier, DEFAULT_PARAMS)
    assert defended < plain
    assert shielded < defended
    assert abs(defended - plain * 0.8) <= 1
    assert abs(shielded - plain * 0.6) <= 1


def test_defend_response_via_step_reduces_incoming_damage():
    attacker = _enemy("boss", pos=(1, 0), unit_attack=5000, pilot_attack=5000,
                      weapons=[_rifle(power=1500)])
    defender = _ally(hp=100000, max_hp=100000, unit_defense=2000, pilot_defense=2000, weapons=[])
    plain = SimState(units=[defender.clone(), attacker.clone()], phase=Phase.ENEMY)
    plain_after = step(plain, Decision("boss", ActionKind.ATTACK, target_id="a", hit=True))
    defended = SimState(units=[defender.clone(), attacker.clone()], phase=Phase.ENEMY)
    defended_after = step(
        defended,
        Decision("boss", ActionKind.ATTACK, target_id="a", hit=True,
                 defense=DefenseResponse(DefenseKind.DEFEND)),
    )
    dmg_plain = 100000 - plain_after.unit("a").hp
    dmg_defend = 100000 - defended_after.unit("a").hp
    assert dmg_defend < dmg_plain
    assert abs(dmg_defend - dmg_plain * 0.8) <= 1


def test_counter_response_damages_attacker():
    attacker = _enemy("boss", pos=(1, 0), hp=50, max_hp=50,
                      unit_attack=1000, pilot_attack=1000, weapons=[_rifle(power=200)])
    defender = _ally(hp=100000, max_hp=100000, unit_attack=5000, pilot_attack=5000,
                     weapons=[_rifle(power=2000)])
    s = SimState(units=[defender, attacker], phase=Phase.ENEMY)
    s2 = step(
        s,
        Decision("boss", ActionKind.ATTACK, target_id="a", weapon=None, hit=True,
                 defense=DefenseResponse(DefenseKind.COUNTER)),
    )
    # the defender survives the weak hit and its counter kills the attacker
    assert s2.unit("boss") is None


def test_support_defend_redirects_the_hit_and_consumes_supporter_charge():
    attacker = _enemy("boss", pos=(1, 0), unit_attack=5000, pilot_attack=5000,
                      weapons=[_rifle(power=1500)])
    defender = _ally(unit_id="a", pos=(3, 0), hp=100000, max_hp=100000, unit_defense=2000,
                     pilot_defense=2000, weapons=[])
    supporter = _ally(unit_id="s", pos=(4, 0), hp=100000, max_hp=100000, move_range=3,
                      support_defend_charges=1, support_defend_charges_max=1, weapons=[])
    lingering = _enemy("boss2", pos=(9, 9), hp=100)
    lingering.weapons = []
    s = SimState(units=[defender, supporter, attacker, lingering], phase=Phase.ENEMY)
    s2 = step(
        s,
        Decision("boss", ActionKind.ATTACK, target_id="a", hit=True,
                 defense=DefenseResponse(support_defend=True)),
    )
    # a second enemy keeps the phase in ENEMY so the ally charge is not reset yet
    assert s2.phase is Phase.ENEMY
    assert s2.unit("s").support_defend_charges == 0
    assert s2.unit("s").hp < 100000
    assert s2.unit("a").hp == 100000


def test_missed_attack_deals_no_damage():
    ally = _ally(weapons=[_rifle(power=5000)])
    enemy = _enemy("e0", pos=(1, 0), hp=100)
    s = SimState(units=[ally, enemy])
    s2 = step(s, Decision("a", ActionKind.ATTACK, target_id="e0", weapon="rifle", hit=False))
    assert s2.unit("e0").hp == 100


def test_legal_attacks_enumerates_reachable_targets():
    ally = _ally(weapons=[_rifle(rmax=2)], move_range=1)
    near = _enemy("near", pos=(2, 0))
    far = _enemy("far", pos=(9, 0))
    s = SimState(units=[ally, near, far])
    decisions = legal_attacks(s, ally)
    hit_ids = {d.target_id for d in decisions}
    assert "near" in hit_ids
    assert "far" not in hit_ids


def test_skill_en_refill_consumes_inventory_and_activation():
    from ggge_ai.battle.sim import SimSkill

    ally = _ally(en=0, weapons=[_rifle(en_cost=10)],
                 skills=[SimSkill(ActionKind.SKILL_EN_REFILL)])
    s = SimState(units=[ally, _enemy()])
    s2 = step(s, Decision("a", ActionKind.SKILL_EN_REFILL))
    u = s2.unit("a")
    assert u.en == 20
    assert u.skills[0].uses == 0
    assert u.acted is True
    assert s2.phase is Phase.ENEMY


def test_skill_without_inventory_is_a_wasted_activation():
    ally = _ally(en=0, weapons=[_rifle(en_cost=10)])
    s = SimState(units=[ally, _enemy()])
    s2 = step(s, Decision("a", ActionKind.SKILL_EN_REFILL))
    u = s2.unit("a")
    assert u.en == 0
    assert u.acted is True


def test_non_turn_ending_skill_keeps_unit_pending():
    from ggge_ai.battle.sim import SimSkill

    ally = _ally(en=0, weapons=[_rifle(en_cost=10)],
                 skills=[SimSkill(ActionKind.SKILL_EN_REFILL, ends_turn=False)])
    s = SimState(units=[ally, _enemy()])
    s2 = step(s, Decision("a", ActionKind.SKILL_EN_REFILL))
    u = s2.unit("a")
    assert u.en == 20
    assert u.acted is False
    assert s2.phase is Phase.ALLY


# Engagement-order cases observed live by the user (2026-07-13, with the
# case-2 correction), recorded in docs/combat-formulas.md: M is our attacker,
# A the target, B the support defender, C the support attacker. Cases 1 and 3
# are observations; the corrected case 2 is the same family as case 1. The
# target-kill test pins a conservative assumption whose original evidence was
# retracted by that correction.

HUGE = 10**9


def _mech(uid, faction, pos, hp, **kw):
    base = dict(unit_id=uid, faction=faction, pos=pos, hp=hp, max_hp=hp,
                en=50, en_max=50, unit_attack=5000, pilot_attack=5000,
                unit_defense=1000, pilot_defense=1000, move_range=0)
    base.update(kw)
    return SimUnit(**base)


def _m(hp=HUGE, **kw):
    return _mech("m", Faction.ALLY, (0, 0), hp, weapons=[_rifle(power=5000)], **kw)


def _a(hp=HUGE):
    return _mech("a_t", Faction.ENEMY, (2, 0), hp, weapons=[_rifle(power=5000)])


def _b(hp=1, charges=1):
    return _mech("b", Faction.ENEMY, (3, 0), hp, move_range=3,
                 support_defend_charges=charges, support_defend_charges_max=1)


def _c(rmax=3, charges=1):
    return _mech("c", Faction.ENEMY, (2, 1), HUGE, move_range=3,
                 support_attack_charges=charges, support_attack_charges_max=1,
                 weapons=[_rifle(power=5000, rmax=rmax)])


def _idle():
    # keeps the ally phase pending so _begin_phase does not refill the
    # enemy support charges the assertions below inspect
    return _mech("idle", Faction.ALLY, (9, 9), HUGE)


def _engagement(*units):
    return SimState(units=[*units, _idle()])


def _strike(state, support_defend):
    return step(
        state,
        Decision("m", ActionKind.ATTACK, target_id="a_t", weapon="rifle", hit=True,
                 defense=DefenseResponse(DefenseKind.COUNTER, support_defend=support_defend)),
    )


def test_case1_interceptor_dies_and_target_still_counters():
    s = _engagement(_m(), _a(), _b())
    s2 = _strike(s, support_defend=True)
    assert s2.unit("b") is None
    assert s2.unit("a_t").hp == HUGE
    assert s2.unit("m").hp < HUGE


def test_target_kill_cancels_counter_and_support_fire():
    s = _engagement(_m(hp=1), _a(hp=1), _b(hp=HUGE), _c())
    s2 = _strike(s, support_defend=False)
    assert s2.unit("a_t") is None
    assert s2.unit("m").hp == 1
    assert s2.unit("c").support_attack_charges == 1
    assert s2.unit("b").support_defend_charges == 1


def test_case3_interceptor_death_cancels_nothing_else():
    m, a, c = _m(), _a(), _c()
    dmg_a = compute_damage(a, m, a.weapons[0], 1.0, DEFAULT_PARAMS)
    dmg_c = compute_damage(c, m, c.weapons[0], 1.0, DEFAULT_PARAMS)
    assert dmg_a >= 1 and dmg_c >= 1
    m.hp = m.max_hp = dmg_a + 1
    s = _engagement(m, a, _b(), c)
    s2 = _strike(s, support_defend=True)
    assert s2.unit("b") is None
    assert s2.unit("m") is None
    assert s2.unit("a_t").hp == HUGE
    assert s2.unit("c").support_attack_charges == 0


def test_counter_kill_stops_support_fire():
    m, a = _m(), _a()
    dmg_a = compute_damage(a, m, a.weapons[0], 1.0, DEFAULT_PARAMS)
    m.hp = m.max_hp = dmg_a
    s = _engagement(m, a, _c())
    s2 = _strike(s, support_defend=False)
    assert s2.unit("m") is None
    assert s2.unit("c").support_attack_charges == 1


def test_interceptor_kill_grants_reactivation():
    s = _engagement(_m(react_charges=1, react_charges_max=1), _a(), _b())
    s2 = _strike(s, support_defend=True)
    m = s2.unit("m")
    assert m.acted is False
    assert m.react_charges == 0


def test_support_defend_without_eligible_supporter_falls_through_to_target():
    s = _engagement(_m(), _a(hp=1), _b(hp=HUGE, charges=0))
    s2 = _strike(s, support_defend=True)
    assert s2.unit("a_t") is None
    assert s2.unit("b").hp == HUGE


def test_support_fire_joins_even_without_target_counter():
    m, a, c = _m(), _a(), _c()
    dmg_c = compute_damage(c, m, c.weapons[0], 1.0, DEFAULT_PARAMS)
    s = _engagement(m, a, c)
    s2 = step(
        s,
        Decision("m", ActionKind.ATTACK, target_id="a_t", weapon="rifle", hit=True,
                 defense=DefenseResponse(DefenseKind.DEFEND)),
    )
    assert s2.unit("m").hp == HUGE - dmg_c
    assert s2.unit("c").support_attack_charges == 0


def test_support_attacker_out_of_weapon_reach_holds_fire():
    s = _engagement(_m(), _a(), _c(rmax=1))
    s2 = _strike(s, support_defend=False)
    assert s2.unit("m").hp < HUGE
    assert s2.unit("c").support_attack_charges == 1


def test_reposition_moves_offer_advance_and_retreat():
    from ggge_ai.battle.sim import chebyshev, reposition_moves

    ally = _ally(pos=(0, 0), move_range=2, weapons=[])
    enemy = _enemy(pos=(5, 0))
    s = SimState(units=[ally, enemy])
    moves = reposition_moves(s, ally)
    dests = {d.move_to for d in moves}
    assert (2, 0) in dests
    assert any(chebyshev(c, enemy.pos) > 5 for c in dests)
    assert all(d.kind == ActionKind.MOVE for d in moves)
