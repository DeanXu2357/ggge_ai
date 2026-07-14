from ggge_ai.battle.actions import ActionKind
from ggge_ai.battle.sim import (
    DEFAULT_PARAMS,
    Decision,
    DefenseKind,
    DefenseResponse,
    Phase,
    SimEvent,
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


# Engagement-order cases from the user's live observations (2026-07-13, with
# the case-2 correction), recorded in docs/combat-formulas.md: M is our
# attacker, A the target, B the support defender, C the support attacker.
# Killing the target cancels the whole counter phase including the support
# attacker, user-confirmed in both directions (the enemy-phase mirror is
# pinned below with our own units defending).

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


def test_support_volley_resolves_before_the_counter():
    m, a, c = _m(), _a(), _c()
    dmg_c = compute_damage(c, m, c.weapons[0], 1.0, DEFAULT_PARAMS)
    m.hp = m.max_hp = dmg_c
    a.weapons = [_rifle(power=5000, en_cost=10)]
    s = _engagement(m, a, c)
    s2 = _strike(s, support_defend=False)
    assert s2.unit("m") is None
    assert s2.unit("c").support_attack_charges == 0
    assert s2.unit("a_t").en == 50


def test_multiple_support_attackers_fire_together():
    m, a = _m(), _a()
    c1 = _c()
    c2 = _mech("c2", Faction.ENEMY, (3, 1), HUGE, move_range=3,
               support_attack_charges=1, support_attack_charges_max=1,
               weapons=[_rifle(power=5000)])
    dmg = compute_damage(c1, m, c1.weapons[0], 1.0, DEFAULT_PARAMS)
    s = _engagement(m, a, c1, c2)
    s2 = step(
        s,
        Decision("m", ActionKind.ATTACK, target_id="a_t", weapon="rifle", hit=True,
                 defense=DefenseResponse(DefenseKind.NONE)),
    )
    assert s2.unit("m").hp == HUGE - 2 * dmg
    assert s2.unit("c").support_attack_charges == 0
    assert s2.unit("c2").support_attack_charges == 0


def test_support_volley_respects_the_cap():
    m, a = _m(), _a()
    cs = [_mech(f"c{i}", Faction.ENEMY, pos, HUGE, move_range=3,
                support_attack_charges=1, support_attack_charges_max=1,
                weapons=[_rifle(power=5000)])
          for i, pos in enumerate([(2, 1), (3, 1), (1, 1), (1, 2)])]
    dmg = compute_damage(cs[0], m, cs[0].weapons[0], 1.0, DEFAULT_PARAMS)
    s = _engagement(m, a, *cs)
    s2 = step(
        s,
        Decision("m", ActionKind.ATTACK, target_id="a_t", weapon="rifle", hit=True,
                 defense=DefenseResponse(DefenseKind.NONE)),
    )
    assert s2.unit("m").hp == HUGE - 3 * dmg
    remaining = sum(s2.unit(f"c{i}").support_attack_charges for i in range(4))
    assert remaining == 1


def test_offense_volley_all_lands_on_the_interceptor():
    m = _m()
    n = _mech("n", Faction.ALLY, (0, 1), HUGE, move_range=3,
              support_attack_charges=1, support_attack_charges_max=1,
              weapons=[_rifle(power=5000)])
    s = _engagement(m, n, _a(), _b(hp=1))
    s2 = _strike(s, support_defend=True)
    assert s2.unit("b") is None
    assert s2.unit("a_t").hp == HUGE
    assert s2.unit("m").hp < HUGE
    assert s2.unit("n").support_attack_charges == 0


def test_interception_charge_spent_once_for_the_whole_volley():
    m = _m()
    n = _mech("n", Faction.ALLY, (0, 1), HUGE, move_range=3,
              support_attack_charges=1, support_attack_charges_max=1,
              weapons=[_rifle(power=5000)])
    b = _b(hp=HUGE)
    dmg = compute_damage(m, b, m.weapons[0], DEFAULT_PARAMS.support_defend_multiplier,
                         DEFAULT_PARAMS)
    s = _engagement(m, n, _a(), b)
    s2 = _strike(s, support_defend=True)
    assert s2.unit("b").hp == HUGE - 2 * dmg
    assert s2.unit("b").support_defend_charges == 0


def test_offense_volley_kill_still_cancels_return_fire():
    m = _m(hp=1)
    n = _mech("n", Faction.ALLY, (0, 1), HUGE, move_range=3,
              support_attack_charges=1, support_attack_charges_max=1,
              weapons=[_rifle(power=5000)])
    s = _engagement(m, n, _a(hp=1), _c())
    s2 = _strike(s, support_defend=False)
    assert s2.unit("a_t") is None
    assert s2.unit("m").hp == 1
    assert s2.unit("c").support_attack_charges == 1


def test_missed_strike_spares_the_interceptor_charge():
    s = _engagement(_m(), _a(), _b(hp=HUGE))
    s2 = step(
        s,
        Decision("m", ActionKind.ATTACK, target_id="a_t", weapon="rifle", hit=False,
                 defense=DefenseResponse(DefenseKind.COUNTER, support_defend=True)),
    )
    assert s2.unit("b").hp == HUGE
    assert s2.unit("b").support_defend_charges == 1
    assert s2.unit("a_t").hp == HUGE
    assert s2.unit("m").hp < HUGE


def test_counters_are_unlimited_within_a_phase():
    m1 = _m()
    m2 = _mech("m2", Faction.ALLY, (0, 1), HUGE, weapons=[_rifle(power=5000)])
    a = _a()
    a.weapons = [_rifle(power=5000, en_cost=10)]
    s = _engagement(m1, m2, a)
    s = step(s, Decision("m", ActionKind.ATTACK, target_id="a_t", weapon="rifle",
                         hit=True, defense=DefenseResponse(DefenseKind.COUNTER)))
    s = step(s, Decision("m2", ActionKind.ATTACK, target_id="a_t", weapon="rifle",
                         hit=True, defense=DefenseResponse(DefenseKind.COUNTER)))
    assert s.unit("m").hp < HUGE
    assert s.unit("m2").hp < HUGE
    assert s.unit("a_t").en == 30


def test_counter_falls_back_to_a_weapon_the_en_can_pay():
    m, a = _m(), _a()
    a.weapons = [
        SimWeapon("cannon", power=9000, range_min=1, range_max=3, en_cost=60),
        _rifle(power=5000, en_cost=10),
    ]
    s = _engagement(m, a)
    s2 = _strike(s, support_defend=False)
    assert s2.unit("m").hp < HUGE
    assert s2.unit("a_t").en == 40


def test_defender_kill_cancels_our_support_fire_in_the_enemy_phase():
    boss = _mech("boss", Faction.ENEMY, (2, 0), HUGE, weapons=[_rifle(power=5000)])
    m = _mech("m", Faction.ALLY, (0, 0), 1, weapons=[_rifle(power=5000)])
    n = _mech("n", Faction.ALLY, (0, 1), HUGE, move_range=3,
              support_attack_charges=1, support_attack_charges_max=1,
              weapons=[_rifle(power=5000)])
    lingering = _mech("boss2", Faction.ENEMY, (9, 9), HUGE)
    s = SimState(units=[boss, m, n, lingering], phase=Phase.ENEMY)
    s2 = step(
        s,
        Decision("boss", ActionKind.ATTACK, target_id="m", weapon="rifle", hit=True,
                 defense=DefenseResponse(DefenseKind.COUNTER)),
    )
    assert s2.unit("m") is None
    assert s2.unit("boss").hp == HUGE
    assert s2.unit("n").support_attack_charges == 1


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


def test_en_regenerates_at_own_phase_start():
    ally = _ally(en=0, en_max=20, weapons=[])
    topped = _ally(unit_id="a2", pos=(0, 5), en=19, en_max=20, weapons=[])
    enemy = _enemy(en=0, en_max=30)
    enemy.weapons = []
    s = SimState(units=[ally, topped, enemy])
    s = step(s, standby("a"))
    s = step(s, standby("a2"))
    assert s.unit("e").en == 3
    assert s.unit("a").en == 0
    s = step(s, standby("e"))
    assert s.phase is Phase.ALLY
    assert s.unit("a").en == 2
    assert s.unit("a2").en == 20


def test_shielded_interceptor_takes_shield_stance_damage():
    m, b = _m(), _b(hp=HUGE)
    dmg_defend = compute_damage(m, b, m.weapons[0],
                                DEFAULT_PARAMS.support_defend_multiplier, DEFAULT_PARAMS)
    dmg_shield = compute_damage(m, b, m.weapons[0],
                                DEFAULT_PARAMS.shield_multiplier, DEFAULT_PARAMS)
    assert dmg_shield < dmg_defend
    plain = _strike(_engagement(m, _a(), _b(hp=HUGE)), support_defend=True)
    assert HUGE - plain.unit("b").hp == dmg_defend
    shielded_b = _b(hp=HUGE)
    shielded_b.has_shield = True
    shielded = _strike(_engagement(_m(), _a(), shielded_b), support_defend=True)
    assert HUGE - shielded.unit("b").hp == dmg_shield


def test_attack_shield_intercepts_the_counter():
    m = _m()
    g = _mech("g", Faction.ALLY, (0, 1), HUGE, move_range=3,
              support_defend_charges=1, support_defend_charges_max=1,
              attack_shield=True)
    s = _engagement(m, g, _a())
    s2 = _strike(s, support_defend=False)
    assert s2.unit("m").hp == HUGE
    assert s2.unit("g").hp < HUGE
    assert s2.unit("g").support_defend_charges == 0


def test_plain_support_defender_does_not_intercept_the_counter():
    m = _m()
    g = _mech("g", Faction.ALLY, (0, 1), HUGE, move_range=3,
              support_defend_charges=1, support_defend_charges_max=1)
    s = _engagement(m, g, _a())
    s2 = _strike(s, support_defend=False)
    assert s2.unit("m").hp < HUGE
    assert s2.unit("g").hp == HUGE
    assert s2.unit("g").support_defend_charges == 1


def _map_gun(blast=1, en_cost=0):
    return SimWeapon("mapgun", power=5000, range_min=1, range_max=4,
                     en_cost=en_cost, map_weapon=True, blast=blast)


def test_map_attack_hits_every_enemy_in_blast_and_nothing_reacts():
    m = _m()
    m.weapons = [_map_gun()]
    m.weapon_ammo = {"mapgun": 1}
    a, c = _a(), _c()
    s = _engagement(m, a, c)
    s2 = step(
        s,
        Decision("m", ActionKind.MAP_ATTACK, weapon="mapgun", aim=(2, 0),
                 defense=DefenseResponse(DefenseKind.COUNTER)),
    )
    assert s2.unit("a_t").hp < HUGE
    assert s2.unit("c").hp < HUGE
    assert s2.unit("m").hp == HUGE
    assert s2.unit("c").support_attack_charges == 1
    assert s2.unit("m").weapon_ammo["mapgun"] == 0


def test_map_attack_spares_friendlies_and_grants_no_react():
    m = _m(react_charges=1, react_charges_max=1)
    m.weapons = [_map_gun()]
    m.weapon_ammo = {"mapgun": 1}
    buddy = _mech("buddy", Faction.ALLY, (2, 1), HUGE)
    a = _a(hp=1)
    s = _engagement(m, buddy, a)
    s2 = step(s, Decision("m", ActionKind.MAP_ATTACK, weapon="mapgun", aim=(2, 0)))
    assert s2.unit("a_t") is None
    assert s2.unit("buddy").hp == HUGE
    m2 = s2.unit("m")
    assert m2.acted is True
    assert m2.react_charges == 1


def test_map_attack_without_ammo_is_a_no_op():
    m = _m()
    m.weapons = [_map_gun()]
    m.weapon_ammo = {"mapgun": 0}
    a = _a(hp=1)
    s = _engagement(m, a)
    s2 = step(s, Decision("m", ActionKind.MAP_ATTACK, weapon="mapgun", aim=(2, 0)))
    assert s2.unit("a_t").hp == 1


def test_interception_reduction_trait_shrinks_the_hit():
    m, b = _m(), _b(hp=HUGE)
    base = compute_damage(m, b, m.weapons[0],
                          DEFAULT_PARAMS.support_defend_multiplier, DEFAULT_PARAMS)
    reduced_b = _b(hp=HUGE)
    reduced_b.interception_reduction = 0.5
    s2 = _strike(_engagement(_m(), _a(), reduced_b), support_defend=True)
    dealt = HUGE - s2.unit("b").hp
    assert dealt < base
    expected = compute_damage(m, b, m.weapons[0],
                              DEFAULT_PARAMS.support_defend_multiplier * 0.5,
                              DEFAULT_PARAMS)
    assert dealt == expected


def test_support_debuff_lands_before_and_amplifies_the_main_strike():
    m, a = _m(), _a()
    n = _mech("n", Faction.ALLY, (0, 1), HUGE, move_range=3,
              support_attack_charges=1, support_attack_charges_max=1,
              weapons=[SimWeapon("zapper", power=5000, range_min=1, range_max=3,
                                 debuff_kind="armor_down", debuff_magnitude=0.5)])
    from ggge_ai.battle.sim import SimDebuff

    dmg_support = compute_damage(n, a, n.weapons[0], 1.0, DEFAULT_PARAMS)
    probe = _a()
    probe.debuffs = [SimDebuff("armor_down", 0.5, 0)]
    dmg_main_debuffed = compute_damage(m, probe, m.weapons[0], 1.0, DEFAULT_PARAMS)
    dmg_main_clean = compute_damage(m, a, m.weapons[0], 1.0, DEFAULT_PARAMS)
    assert dmg_main_debuffed > dmg_main_clean
    s = _engagement(m, n, a)
    s2 = step(
        s,
        Decision("m", ActionKind.ATTACK, target_id="a_t", weapon="rifle", hit=True,
                 defense=DefenseResponse(DefenseKind.NONE)),
    )
    dealt = HUGE - s2.unit("a_t").hp
    assert dealt == dmg_support + dmg_main_debuffed
    assert [d.kind for d in s2.unit("a_t").debuffs] == ["armor_down"]


def test_debuff_expires_when_its_phase_kind_comes_back():
    ally = _ally(weapons=[_rifle(power=1500)])
    debuffed = _enemy("e0", pos=(1, 0), hp=10**9)
    debuffed.max_hp = 10**9
    debuffed.weapons = []
    ally.weapons[0] = SimWeapon("rifle", power=1500, range_min=1, range_max=3,
                                debuff_kind="armor_down", debuff_magnitude=0.3)
    s = SimState(units=[ally, debuffed])
    s = step(s, Decision("a", ActionKind.ATTACK, target_id="e0", weapon="rifle", hit=True))
    assert s.phase is Phase.ENEMY
    assert len(s.unit("e0").debuffs) == 1
    s = step(s, standby("e0"))
    assert s.phase is Phase.ALLY and s.turn == 2
    assert s.unit("e0").debuffs == []


def test_debuff_same_kind_keeps_the_larger_magnitude():
    m, a = _m(), _a()
    weak = SimWeapon("weak", power=100, range_min=1, range_max=3,
                     debuff_kind="armor_down", debuff_magnitude=0.5)
    strong = SimWeapon("strong", power=100, range_min=1, range_max=3,
                       debuff_kind="armor_down", debuff_magnitude=0.2)
    m.weapons = [weak, strong]
    s = _engagement(m, a)
    s = step(s, Decision("m", ActionKind.ATTACK, target_id="a_t", weapon="weak", hit=True,
                         defense=DefenseResponse(DefenseKind.NONE)))
    s = step(s, Decision("m", ActionKind.ATTACK, target_id="a_t", weapon="strong", hit=True,
                         defense=DefenseResponse(DefenseKind.NONE)))
    debuffs = s.unit("a_t").debuffs
    assert len(debuffs) == 1
    assert debuffs[0].magnitude == 0.5


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


def _kill_spawn_event(event_id="ev1", victim="e", within_turn=None, spawn_uid="e9",
                      spawn_pos=(5, 5), **spawn_kw):
    trigger = {"type": "kill", "uid": victim}
    if within_turn is not None:
        trigger["within_turn"] = within_turn
    template = _enemy(spawn_uid, pos=spawn_pos, **spawn_kw)
    return SimEvent(event_id=event_id, trigger=trigger,
                    effect={"type": "spawn", "units": [template]})


def test_kill_event_spawns_reinforcement():
    ally = _ally(weapons=[_rifle(power=99000)])
    event = _kill_spawn_event()
    events = {"ev1": event}
    s = SimState(units=[ally, _enemy(hp=1)], pending_events=("ev1",))
    s2 = step(s, Decision(unit_id="a", kind=ActionKind.ATTACK, target_id="e",
                          weapon="rifle", hit=True), events=events)
    spawned = s2.unit("e9")
    assert spawned is not None
    assert spawned.pos == (5, 5)
    assert s2.pending_events == ()
    assert s2.fired_events == ("ev1",)


def test_kill_event_does_not_fire_while_target_lives():
    ally = _ally(weapons=[_rifle(power=1)])
    events = {"ev1": _kill_spawn_event()}
    s = SimState(units=[ally, _enemy(hp=99999, max_hp=99999)], pending_events=("ev1",))
    s2 = step(s, Decision(unit_id="a", kind=ActionKind.ATTACK, target_id="e",
                          weapon="rifle", hit=True), events=events)
    assert s2.unit("e9") is None
    assert s2.pending_events == ("ev1",)


def test_kill_window_expires_at_turn_rotation():
    ally = _ally(weapons=[])
    enemy = _enemy(weapons=[])
    events = {"ev1": _kill_spawn_event(within_turn=1)}
    s = SimState(units=[ally, enemy], pending_events=("ev1",))
    s = step(s, standby("a"), events=events)
    s = step(s, standby("e"), events=events)
    assert s.turn == 2
    assert s.pending_events == ()
    assert s.fired_events == ()


def test_expired_window_never_fires_on_a_late_kill():
    ally = _ally(weapons=[_rifle(power=99000)])
    enemy = _enemy(hp=1, weapons=[])
    events = {"ev1": _kill_spawn_event(within_turn=1)}
    s = SimState(units=[ally, enemy], pending_events=("ev1",))
    s = step(s, standby("a"), events=events)
    s = step(s, standby("e"), events=events)
    s = step(s, Decision(unit_id="a", kind=ActionKind.ATTACK, target_id="e",
                         weapon="rifle", hit=True), events=events)
    assert s.unit("e9") is None
    assert s.fired_events == ()


def test_turn_start_event_fires_on_rotation():
    ally = _ally(weapons=[])
    enemy = _enemy(weapons=[])
    events = {
        "ev2": SimEvent(
            event_id="ev2",
            trigger={"type": "turn_start", "turn": 2},
            effect={"type": "spawn", "units": [_enemy("e9", pos=(7, 7))]},
        )
    }
    s = SimState(units=[ally, enemy], pending_events=("ev2",))
    s = step(s, standby("a"), events=events)
    assert s.unit("e9") is None
    s = step(s, standby("e"), events=events)
    assert s.turn == 2
    assert s.unit("e9") is not None
    assert s.fired_events == ("ev2",)


def test_weaken_event_multiplies_statics():
    ally = _ally(weapons=[_rifle(power=99000)])
    aura = _enemy("aura", pos=(2, 0), hp=1, weapons=[])
    grunt = _enemy("grunt", pos=(9, 9), hp=100, unit_attack=4000,
                   unit_defense=2000, weapons=[])
    events = {
        "ev3": SimEvent(
            event_id="ev3",
            trigger={"type": "kill", "uid": "aura"},
            effect={"type": "weaken", "uids": ["grunt"],
                    "attack_multiplier": 0.5, "defense_multiplier": 0.5},
        )
    }
    s = SimState(units=[ally, aura, grunt], pending_events=("ev3",))
    s2 = step(s, Decision(unit_id="a", kind=ActionKind.ATTACK, target_id="aura",
                          weapon="rifle", hit=True), events=events)
    weakened = s2.unit("grunt")
    assert weakened.unit_attack == 2000.0
    assert weakened.unit_defense == 1000.0


def test_key_distinguishes_fired_from_expired():
    # same board, same pending complement: one history fired the weaken,
    # the other let the window expire -- the statics differ while nothing
    # else in the unit tuple does, so fired_events must split the keys
    base = SimState(units=[_ally(weapons=[]), _enemy(weapons=[])])
    fired = base.clone()
    fired.fired_events = ("ev3",)
    expired = base.clone()
    assert fired.pending_events == expired.pending_events
    assert fired.key() != expired.key()


def test_key_distinguishes_pending_sets():
    a = SimState(units=[_ally(weapons=[])], pending_events=("ev1",))
    b = SimState(units=[_ally(weapons=[])])
    assert a.key() != b.key()


def test_clone_carries_event_state():
    s = SimState(units=[_ally(weapons=[])], pending_events=("ev1",),
                 fired_events=("ev0",))
    c = s.clone()
    assert c.pending_events == ("ev1",)
    assert c.fired_events == ("ev0",)


def test_spawn_never_duplicates_an_existing_uid():
    ally = _ally(weapons=[_rifle(power=99000)])
    events = {"ev1": _kill_spawn_event(spawn_uid="a")}
    s = SimState(units=[ally, _enemy(hp=1)], pending_events=("ev1",))
    s2 = step(s, Decision(unit_id="a", kind=ActionKind.ATTACK, target_id="e",
                          weapon="rifle", hit=True), events=events)
    assert len([u for u in s2.units if u.unit_id == "a"]) == 1
