"""狀態轉移與交戰結算：逐條釘住 docs/reference/combat-formulas.md 的機制。"""

from ggge_ai.sandbox.model import (
    DEFAULT_RULES,
    BattleState,
    Debuff,
    Decision,
    Faction,
    ActionKind,
    Reaction,
    Skill,
    Stance,
    StageEvent,
    Unit,
    Weapon,
    decision_hit_probability,
    legal_reactions,
    standby,
    step,
    strike_damage,
)

HUGE = 10**9


def _rifle(power=1500, en_cost=0, rmax=3, can_counter=True):
    return Weapon(
        "rifle", power=power, range_min=1, range_max=rmax, en_cost=en_cost,
        can_counter=can_counter,
    )


def _ally(**kw):
    base = dict(unit_id="a", faction=Faction.ALLY, pos=(0, 0), hp=100, max_hp=100,
                en=20, en_max=20, unit_attack=5000, pilot_attack=5000, move_range=3)
    base.update(kw)
    return Unit(**base)


def _enemy(uid="e", pos=(2, 0), hp=100, **kw):
    base = dict(unit_id=uid, faction=Faction.ENEMY, pos=pos, hp=hp, max_hp=100,
                unit_defense=1000, pilot_defense=1000)
    base.update(kw)
    return Unit(**base)


def _attack(unit_id, target_id, weapon="rifle", **kw):
    return Decision(unit_id, ActionKind.ATTACK, target_id=target_id, weapon=weapon, **kw)




def test_phase_rotates_when_a_faction_finishes_and_skips_the_empty_third_party():
    state = BattleState(units=[_ally(weapons=[]), _enemy()])
    after = step(state, standby("a"))
    assert after.phase is Faction.ENEMY
    assert after.turn == 1


def test_charges_reset_at_own_phase_start():
    ally = _ally(weapons=[], chance_steps=0, chance_steps_max=2,
                 support_defend_charges=0, support_defend_charges_max=1,
                 support_attack_charges=0, support_attack_charges_max=1)
    state = BattleState(units=[ally, _enemy()])
    state = step(state, standby("a"))
    state = step(state, standby("e"))
    assert state.phase is Faction.ALLY
    assert state.turn == 2
    a = state.unit("a")
    assert a.chance_steps == 2
    assert a.support_defend_charges == 1
    assert a.support_attack_charges == 1


def test_en_regenerates_one_tenth_of_max_at_own_phase_start():
    ally = _ally(en=0, en_max=20, weapons=[])
    topped = _ally(unit_id="a2", pos=(0, 5), en=19, en_max=20, weapons=[])
    state = BattleState(units=[ally, topped, _enemy(en=0, en_max=30)])
    state = step(state, standby("a"))
    state = step(state, standby("a2"))
    assert state.unit("e").en == 3
    assert state.unit("a").en == 0
    state = step(state, standby("e"))
    assert state.phase is Faction.ALLY
    assert state.unit("a").en == 2
    assert state.unit("a2").en == 20


def test_en_gate_blocks_an_unaffordable_weapon():
    ally = _ally(en=0, en_max=20, weapons=[_rifle(power=5000, en_cost=10)])
    state = BattleState(units=[ally, _enemy("e0", pos=(1, 0), hp=100)])
    after = step(state, _attack("a", "e0", hit=True))
    assert after.unit("e0").hp == 100
    assert after.unit("a").en == 0


def test_out_of_range_attack_does_nothing():
    ally = _ally(move_range=0, weapons=[_rifle(power=5000, rmax=1)])
    state = BattleState(units=[ally, _enemy("e0", pos=(5, 0), hp=100)])
    assert step(state, _attack("a", "e0", hit=True)).unit("e0").hp == 100


def test_missed_attack_deals_no_damage():
    state = BattleState(units=[_ally(weapons=[_rifle(power=5000)]), _enemy("e0", pos=(1, 0))])
    assert step(state, _attack("a", "e0", hit=False)).unit("e0").hp == 100


def test_dead_unit_leaves_the_board():
    state = BattleState(
        units=[_ally(weapons=[_rifle(power=5000)]), _enemy("e0", pos=(1, 0), hp=1)]
    )
    assert step(state, _attack("a", "e0", hit=True)).unit("e0") is None




def test_kill_grants_a_chance_step_and_spends_one_charge():
    ally = _ally(weapons=[_rifle(power=5000)], chance_steps=2, chance_steps_max=2)
    state = BattleState(
        units=[ally, _enemy("e0", pos=(2, 0), hp=5), _enemy("e1", pos=(3, 0), hp=5)]
    )
    after = step(state, _attack("a", "e0", hit=True))
    assert after.unit("e0") is None
    assert after.unit("a").acted is False
    assert after.unit("a").chance_steps == 1
    assert after.phase is Faction.ALLY


def test_kill_without_a_chance_step_charge_ends_the_activation():
    ally = _ally(weapons=[_rifle(power=5000)], chance_steps=0, chance_steps_max=0)
    state = BattleState(
        units=[ally, _enemy("e0", pos=(2, 0), hp=5), _enemy("e1", pos=(9, 9))]
    )
    after = step(state, _attack("a", "e0", hit=True))
    assert after.unit("e0") is None
    assert after.phase is Faction.ENEMY




def _reaction_board(**kw):
    pistol = Weapon("pistol", power=800, range_min=1, range_max=3, can_counter=False)
    defender = _ally(weapons=[_rifle(), pistol], **kw)
    guard = _ally(unit_id="g", pos=(0, 1), weapons=[], move_range=3,
                  support_defend_charges=1, support_defend_charges_max=1)
    attacker = _enemy("boss", pos=(9, 0), weapons=[_rifle(rmax=1)], move_range=8)
    return BattleState(units=[defender, guard, attacker], phase=Faction.ENEMY), attacker, defender


def test_legal_reactions_read_the_counter_from_the_post_move_cell():
    state, attacker, defender = _reaction_board()
    weapon = attacker.weapons[0]

    far = legal_reactions(state, defender, attacker, weapon)
    near = legal_reactions(state, defender, attacker, weapon, attacker_pos=(1, 0))

    assert not any(r.stance is Stance.COUNTER for r in far)
    counters = [r for r in near if r.stance is Stance.COUNTER and not r.support_defend]
    assert [r.weapon for r in counters] == ["rifle"]


def test_support_defense_pairs_only_with_dodge_and_counter_and_none():
    state, attacker, defender = _reaction_board(has_shield=True)

    options = legal_reactions(state, defender, attacker, attacker.weapons[0], attacker_pos=(1, 0))

    assert {r.stance for r in options if r.support_defend} == {
        Stance.NONE, Stance.DODGE, Stance.COUNTER
    }
    assert Stance.SHIELD in {r.stance for r in options}


def test_a_map_weapon_offers_no_reaction():
    state, attacker, defender = _reaction_board()
    map_gun = Weapon("mapgun", power=5000, range_min=1, range_max=4, map_weapon=True, blast=1)

    assert legal_reactions(state, defender, attacker, map_gun) == []


def test_defense_action_multipliers_reduce_damage():
    attacker = _enemy("boss", pos=(1, 0), unit_attack=5000, pilot_attack=5000,
                      weapons=[_rifle(power=1500)])
    defender = _ally(unit_defense=2000, pilot_defense=2000)
    weapon = attacker.weapons[0]
    plain = strike_damage(attacker, defender, weapon)
    defended = strike_damage(attacker, defender, weapon,
                             defense_multiplier=DEFAULT_RULES.defend_multiplier)
    shielded = strike_damage(attacker, defender, weapon,
                             defense_multiplier=DEFAULT_RULES.shield_multiplier)
    assert shielded < defended < plain
    assert abs(defended - plain * 0.8) <= 1
    assert abs(shielded - plain * 0.6) <= 1


def test_defend_stance_through_step_reduces_incoming_damage():
    attacker = _enemy("boss", pos=(1, 0), unit_attack=5000, pilot_attack=5000,
                      weapons=[_rifle(power=1500)])
    defender = _ally(hp=100000, max_hp=100000, unit_defense=2000, pilot_defense=2000,
                     weapons=[])
    plain = BattleState(units=[defender.clone(), attacker.clone()], phase=Faction.ENEMY)
    guarded = BattleState(units=[defender.clone(), attacker.clone()], phase=Faction.ENEMY)
    dealt_plain = 100000 - step(plain, _attack("boss", "a", weapon=None, hit=True)).unit("a").hp
    dealt_guard = 100000 - step(
        guarded,
        _attack("boss", "a", weapon=None, hit=True, reaction=Reaction(stance=Stance.DEFEND)),
    ).unit("a").hp
    assert dealt_guard < dealt_plain
    assert abs(dealt_guard - dealt_plain * 0.8) <= 1


def test_dodge_stance_lowers_the_attacker_hit_chance():
    attacker = _enemy("boss", pos=(1, 0), pilot_attack=1000, mobility=500,
                      weapons=[_rifle()])
    defender = _ally(reaction=1000, mobility=500, weapons=[])
    state = BattleState(units=[defender, attacker], phase=Faction.ENEMY)
    plain = _attack("boss", "a", weapon="rifle")
    dodging = _attack("boss", "a", weapon="rifle", reaction=Reaction(stance=Stance.DODGE))
    assert decision_hit_probability(state, dodging) < decision_hit_probability(state, plain)


def test_counter_stance_damages_the_attacker():
    attacker = _enemy("boss", pos=(1, 0), hp=50, max_hp=50, unit_attack=1000,
                      pilot_attack=1000, weapons=[_rifle(power=200)])
    defender = _ally(hp=100000, max_hp=100000, unit_attack=5000, pilot_attack=5000,
                     weapons=[_rifle(power=2000)])
    state = BattleState(units=[defender, attacker], phase=Faction.ENEMY)
    after = step(
        state,
        _attack("boss", "a", weapon=None, hit=True, reaction=Reaction(stance=Stance.COUNTER)),
    )
    assert after.unit("boss") is None




def _mech(uid, faction, pos, hp, **kw):
    base = dict(unit_id=uid, faction=faction, pos=pos, hp=hp, max_hp=hp,
                en=50, en_max=50, unit_attack=5000, pilot_attack=5000,
                unit_defense=1000, pilot_defense=1000, move_range=0)
    base.update(kw)
    return Unit(**base)


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


def _n():
    return _mech("n", Faction.ALLY, (0, 1), HUGE, move_range=3,
                 support_attack_charges=1, support_attack_charges_max=1,
                 weapons=[_rifle(power=5000)])


def _idle():
    # 讓我方相位保持未結束，敵方支援次數才不會在斷言前被相位開始重置
    return _mech("idle", Faction.ALLY, (9, 9), HUGE)


def _engagement(*units):
    return BattleState(units=[*units, _idle()])


def _strike(state, support_defend, **kw):
    return step(
        state,
        _attack("m", "a_t", hit=True,
                reaction=Reaction(stance=Stance.COUNTER, support_defend=support_defend),
                **kw),
    )


def test_interceptor_dies_and_the_target_still_counters():
    after = _strike(_engagement(_m(), _a(), _b()), support_defend=True)
    assert after.unit("b") is None
    assert after.unit("a_t").hp == HUGE
    assert after.unit("m").hp < HUGE


def test_killing_the_target_cancels_the_counter_and_the_support_fire():
    after = _strike(_engagement(_m(hp=1), _a(hp=1), _b(hp=HUGE), _c()), support_defend=False)
    assert after.unit("a_t") is None
    assert after.unit("m").hp == 1
    assert after.unit("c").support_attack_charges == 1
    assert after.unit("b").support_defend_charges == 1


def test_interceptor_death_cancels_nothing_that_follows():
    m, a, c = _m(), _a(), _c()
    dmg_a = strike_damage(a, m, a.weapons[0])
    dmg_c = strike_damage(c, m, c.weapons[0])
    assert dmg_a >= 1 and dmg_c >= 1
    m.hp = m.max_hp = dmg_a + 1
    after = _strike(_engagement(m, a, _b(), c), support_defend=True)
    assert after.unit("b") is None
    assert after.unit("m") is None
    assert after.unit("a_t").hp == HUGE
    assert after.unit("c").support_attack_charges == 0


def test_defender_support_volley_resolves_before_the_counter():
    m, a, c = _m(), _a(), _c()
    m.hp = m.max_hp = strike_damage(c, m, c.weapons[0])
    a.weapons = [_rifle(power=5000, en_cost=10)]
    after = _strike(_engagement(m, a, c), support_defend=False)
    assert after.unit("m") is None
    assert after.unit("c").support_attack_charges == 0
    assert after.unit("a_t").en == 50


def test_multiple_support_attackers_fire_together():
    m, a, c1 = _m(), _a(), _c()
    c2 = _mech("c2", Faction.ENEMY, (3, 1), HUGE, move_range=3,
               support_attack_charges=1, support_attack_charges_max=1,
               weapons=[_rifle(power=5000)])
    dmg = strike_damage(c1, m, c1.weapons[0])
    after = step(
        _engagement(m, a, c1, c2),
        _attack("m", "a_t", hit=True, reaction=Reaction(stance=Stance.NONE)),
    )
    assert after.unit("m").hp == HUGE - 2 * dmg
    assert after.unit("c").support_attack_charges == 0
    assert after.unit("c2").support_attack_charges == 0


def test_support_volley_respects_the_cap():
    m, a = _m(), _a()
    cs = [_mech(f"c{i}", Faction.ENEMY, pos, HUGE, move_range=3,
                support_attack_charges=1, support_attack_charges_max=1,
                weapons=[_rifle(power=5000)])
          for i, pos in enumerate([(2, 1), (3, 1), (1, 1), (1, 2)])]
    dmg = strike_damage(cs[0], m, cs[0].weapons[0])
    after = step(
        _engagement(m, a, *cs),
        _attack("m", "a_t", hit=True, reaction=Reaction(stance=Stance.NONE)),
    )
    assert after.unit("m").hp == HUGE - DEFAULT_RULES.max_support_attackers * dmg
    assert sum(after.unit(f"c{i}").support_attack_charges for i in range(4)) == 1


def test_support_fire_joins_even_when_the_target_does_not_counter():
    m, a, c = _m(), _a(), _c()
    dmg_c = strike_damage(c, m, c.weapons[0])
    after = step(
        _engagement(m, a, c),
        _attack("m", "a_t", hit=True, reaction=Reaction(stance=Stance.DEFEND)),
    )
    assert after.unit("m").hp == HUGE - dmg_c
    assert after.unit("c").support_attack_charges == 0


def test_support_attacker_out_of_weapon_reach_holds_fire():
    after = _strike(_engagement(_m(), _a(), _c(rmax=1)), support_defend=False)
    assert after.unit("m").hp < HUGE
    assert after.unit("c").support_attack_charges == 1


def test_the_counter_only_ever_hits_the_main_attacker():
    n = _n()
    after = _strike(_engagement(_m(), n, _a()), support_defend=False)
    assert after.unit("m").hp < HUGE
    assert after.unit("n").hp == HUGE
    assert after.unit("n").support_attack_charges == 0


def test_counters_are_unlimited_within_a_phase():
    m2 = _mech("m2", Faction.ALLY, (0, 1), HUGE, weapons=[_rifle(power=5000)])
    a = _a()
    a.weapons = [_rifle(power=5000, en_cost=10)]
    state = _engagement(_m(), m2, a)
    state = step(state, _attack("m", "a_t", hit=True,
                                reaction=Reaction(stance=Stance.COUNTER)))
    state = step(state, _attack("m2", "a_t", hit=True,
                                reaction=Reaction(stance=Stance.COUNTER)))
    assert state.unit("m").hp < HUGE
    assert state.unit("m2").hp < HUGE
    assert state.unit("a_t").en == 30


def test_counter_falls_back_to_a_weapon_the_en_can_pay():
    a = _a()
    a.weapons = [
        Weapon("cannon", power=9000, range_min=1, range_max=3, en_cost=60),
        _rifle(power=5000, en_cost=10),
    ]
    after = _strike(_engagement(_m(), a), support_defend=False)
    assert after.unit("m").hp < HUGE
    assert after.unit("a_t").en == 40


def test_offense_volley_all_lands_on_the_interceptor():
    after = _strike(_engagement(_m(), _n(), _a(), _b(hp=1)), support_defend=True)
    assert after.unit("b") is None
    assert after.unit("a_t").hp == HUGE
    assert after.unit("m").hp < HUGE
    assert after.unit("n").support_attack_charges == 0


def test_the_interception_charge_is_spent_once_for_the_whole_volley():
    m, b = _m(), _b(hp=HUGE)
    dmg = strike_damage(m, b, m.weapons[0],
                        defense_multiplier=DEFAULT_RULES.support_defend_multiplier)
    after = _strike(_engagement(m, _n(), _a(), b), support_defend=True)
    assert after.unit("b").hp == HUGE - 2 * dmg
    assert after.unit("b").support_defend_charges == 0


def test_a_missed_strike_spares_the_interception_charge():
    after = step(
        _engagement(_m(), _a(), _b(hp=HUGE)),
        _attack("m", "a_t", hit=False,
                reaction=Reaction(stance=Stance.COUNTER, support_defend=True)),
    )
    assert after.unit("b").hp == HUGE
    assert after.unit("b").support_defend_charges == 1
    assert after.unit("a_t").hp == HUGE
    assert after.unit("m").hp < HUGE


def test_an_offense_volley_kill_still_cancels_return_fire():
    after = _strike(_engagement(_m(hp=1), _n(), _a(hp=1), _c()), support_defend=False)
    assert after.unit("a_t") is None
    assert after.unit("m").hp == 1
    assert after.unit("c").support_attack_charges == 1


def test_killing_our_defender_cancels_our_support_fire_in_the_enemy_phase():
    boss = _mech("boss", Faction.ENEMY, (2, 0), HUGE, weapons=[_rifle(power=5000)])
    m = _mech("m", Faction.ALLY, (0, 0), 1, weapons=[_rifle(power=5000)])
    lingering = _mech("boss2", Faction.ENEMY, (9, 9), HUGE)
    state = BattleState(units=[boss, m, _n(), lingering], phase=Faction.ENEMY)
    after = step(
        state,
        _attack("boss", "m", hit=True, reaction=Reaction(stance=Stance.COUNTER)),
    )
    assert after.unit("m") is None
    assert after.unit("boss").hp == HUGE
    assert after.unit("n").support_attack_charges == 1


def test_an_interceptor_kill_grants_the_main_attacker_a_chance_step():
    after = _strike(
        _engagement(_m(chance_steps=1, chance_steps_max=1), _a(), _b()), support_defend=True
    )
    assert after.unit("m").acted is False
    assert after.unit("m").chance_steps == 0


def test_support_defend_without_an_eligible_supporter_falls_through_to_the_target():
    after = _strike(_engagement(_m(), _a(hp=1), _b(hp=HUGE, charges=0)), support_defend=True)
    assert after.unit("a_t") is None
    assert after.unit("b").hp == HUGE


def test_support_defend_redirects_the_hit_and_spends_the_supporter_charge():
    attacker = _enemy("boss", pos=(1, 0), unit_attack=5000, pilot_attack=5000,
                      weapons=[_rifle(power=1500)])
    defender = _ally(unit_id="a", pos=(3, 0), hp=100000, max_hp=100000,
                     unit_defense=2000, pilot_defense=2000, weapons=[])
    supporter = _ally(unit_id="s", pos=(4, 0), hp=100000, max_hp=100000, move_range=3,
                      support_defend_charges=1, support_defend_charges_max=1, weapons=[])
    lingering = _enemy("boss2", pos=(9, 9))
    state = BattleState(
        units=[defender, supporter, attacker, lingering], phase=Faction.ENEMY
    )
    after = step(
        state,
        _attack("boss", "a", weapon=None, hit=True, reaction=Reaction(support_defend=True)),
    )
    assert after.phase is Faction.ENEMY
    assert after.unit("s").support_defend_charges == 0
    assert after.unit("s").hp < 100000
    assert after.unit("a").hp == 100000


def test_a_shielded_interceptor_takes_the_shield_stance_damage():
    m, b = _m(), _b(hp=HUGE)
    dmg_defend = strike_damage(m, b, m.weapons[0],
                               defense_multiplier=DEFAULT_RULES.support_defend_multiplier)
    dmg_shield = strike_damage(m, b, m.weapons[0],
                               defense_multiplier=DEFAULT_RULES.shield_multiplier)
    assert dmg_shield < dmg_defend
    plain = _strike(_engagement(_m(), _a(), _b(hp=HUGE)), support_defend=True)
    assert HUGE - plain.unit("b").hp == dmg_defend
    shielded_b = _b(hp=HUGE)
    shielded_b.has_shield = True
    shielded = _strike(_engagement(_m(), _a(), shielded_b), support_defend=True)
    assert HUGE - shielded.unit("b").hp == dmg_shield


def test_the_interception_reduction_trait_shrinks_the_hit():
    m, b = _m(), _b(hp=HUGE)
    base = strike_damage(m, b, m.weapons[0],
                         defense_multiplier=DEFAULT_RULES.support_defend_multiplier)
    reduced = _b(hp=HUGE)
    reduced.interception_reduction = 0.5
    after = _strike(_engagement(_m(), _a(), reduced), support_defend=True)
    dealt = HUGE - after.unit("b").hp
    assert dealt < base
    assert dealt == strike_damage(
        m, b, m.weapons[0],
        defense_multiplier=DEFAULT_RULES.support_defend_multiplier * 0.5,
    )


def test_an_attack_shield_intercepts_the_counter():
    guard = _mech("g", Faction.ALLY, (0, 1), HUGE, move_range=3,
                  support_defend_charges=1, support_defend_charges_max=1,
                  attack_shield=True)
    after = _strike(_engagement(_m(), guard, _a()), support_defend=False)
    assert after.unit("m").hp == HUGE
    assert after.unit("g").hp < HUGE
    assert after.unit("g").support_defend_charges == 0


def test_a_plain_support_defender_does_not_intercept_the_counter():
    guard = _mech("g", Faction.ALLY, (0, 1), HUGE, move_range=3,
                  support_defend_charges=1, support_defend_charges_max=1)
    after = _strike(_engagement(_m(), guard, _a()), support_defend=False)
    assert after.unit("m").hp < HUGE
    assert after.unit("g").hp == HUGE
    assert after.unit("g").support_defend_charges == 1




def _map_gun(blast=1, en_cost=0):
    return Weapon("mapgun", power=5000, range_min=1, range_max=4, en_cost=en_cost,
                  map_weapon=True, blast=blast)


def _map_shooter(**kw):
    m = _m(**kw)
    m.weapons = [_map_gun()]
    m.ammo = {"mapgun": 1}
    return m


def test_map_weapon_hits_every_enemy_in_blast_and_allows_no_reaction():
    after = step(
        _engagement(_map_shooter(), _a(), _c()),
        Decision("m", ActionKind.MAP_ATTACK, weapon="mapgun", aim=(2, 0),
                 reaction=Reaction(stance=Stance.COUNTER)),
    )
    assert after.unit("a_t").hp < HUGE
    assert after.unit("c").hp < HUGE
    assert after.unit("m").hp == HUGE
    assert after.unit("c").support_attack_charges == 1
    assert after.unit("m").ammo["mapgun"] == 0


def test_map_weapon_spares_friendlies_and_grants_no_chance_step():
    buddy = _mech("buddy", Faction.ALLY, (2, 1), HUGE)
    after = step(
        _engagement(_map_shooter(chance_steps=1, chance_steps_max=1), buddy, _a(hp=1)),
        Decision("m", ActionKind.MAP_ATTACK, weapon="mapgun", aim=(2, 0)),
    )
    assert after.unit("a_t") is None
    assert after.unit("buddy").hp == HUGE
    assert after.unit("m").acted is True
    assert after.unit("m").chance_steps == 1


def test_map_weapon_is_pre_move_only():
    shooter = _map_shooter()
    shooter.move_range = 3
    after = step(
        _engagement(shooter, _a(hp=1)),
        Decision("m", ActionKind.MAP_ATTACK, weapon="mapgun", aim=(2, 0), move_to=(1, 0)),
    )
    assert after.unit("m").pos == (0, 0)


def test_map_weapon_without_ammo_is_a_no_op():
    shooter = _map_shooter()
    shooter.ammo = {"mapgun": 0}
    after = step(
        _engagement(shooter, _a(hp=1)),
        Decision("m", ActionKind.MAP_ATTACK, weapon="mapgun", aim=(2, 0)),
    )
    assert after.unit("a_t").hp == 1




def test_a_support_debuff_lands_before_and_amplifies_the_main_strike():
    m, a = _m(), _a()
    zapper = Weapon("zapper", power=5000, range_min=1, range_max=3,
                    debuff_kind="armor_down", debuff_magnitude=0.5)
    n = _mech("n", Faction.ALLY, (0, 1), HUGE, move_range=3,
              support_attack_charges=1, support_attack_charges_max=1, weapons=[zapper])
    dmg_support = strike_damage(n, a, zapper)
    probe = _a()
    probe.debuffs = [Debuff("armor_down", 0.5, 0)]
    dmg_main_debuffed = strike_damage(m, probe, m.weapons[0])
    assert dmg_main_debuffed > strike_damage(m, a, m.weapons[0])
    after = step(
        _engagement(m, n, a),
        _attack("m", "a_t", hit=True, reaction=Reaction(stance=Stance.NONE)),
    )
    assert HUGE - after.unit("a_t").hp == dmg_support + dmg_main_debuffed
    assert [d.kind for d in after.unit("a_t").debuffs] == ["armor_down"]


def test_a_debuff_expires_when_its_own_phase_kind_comes_back():
    ally = _ally(weapons=[Weapon("rifle", power=1500, range_min=1, range_max=3,
                                 debuff_kind="armor_down", debuff_magnitude=0.3)])
    victim = _enemy("e0", pos=(1, 0), hp=HUGE, max_hp=HUGE)
    state = BattleState(units=[ally, victim])
    state = step(state, _attack("a", "e0", hit=True))
    assert state.phase is Faction.ENEMY
    assert len(state.unit("e0").debuffs) == 1
    state = step(state, standby("e0"))
    assert state.phase is Faction.ALLY and state.turn == 2
    assert state.unit("e0").debuffs == []


def test_the_larger_magnitude_of_the_same_debuff_kind_wins():
    m = _m()
    m.weapons = [
        Weapon("weak", power=100, range_min=1, range_max=3,
               debuff_kind="armor_down", debuff_magnitude=0.5),
        Weapon("strong", power=100, range_min=1, range_max=3,
               debuff_kind="armor_down", debuff_magnitude=0.2),
    ]
    state = _engagement(m, _a())
    for name in ("weak", "strong"):
        state = step(state, _attack("m", "a_t", weapon=name, hit=True,
                                    reaction=Reaction(stance=Stance.NONE)))
    debuffs = state.unit("a_t").debuffs
    assert len(debuffs) == 1
    assert debuffs[0].magnitude == 0.5




def test_en_refill_skill_spends_a_use_and_the_activation():
    ally = _ally(en=0, weapons=[_rifle(en_cost=10)],
                 skills=[Skill(ActionKind.SKILL_EN_REFILL)])
    after = step(BattleState(units=[ally, _enemy()]),
                 Decision("a", ActionKind.SKILL_EN_REFILL))
    assert after.unit("a").en == 20
    assert after.unit("a").skills[0].uses == 0
    assert after.unit("a").acted is True
    assert after.phase is Faction.ENEMY


def test_a_skill_the_unit_does_not_own_wastes_the_activation():
    ally = _ally(en=0, weapons=[_rifle(en_cost=10)])
    after = step(BattleState(units=[ally, _enemy()]),
                 Decision("a", ActionKind.SKILL_EN_REFILL))
    assert after.unit("a").en == 0
    assert after.unit("a").acted is True


def test_a_non_activation_ending_skill_keeps_the_unit_pending():
    ally = _ally(en=0, weapons=[_rifle(en_cost=10)],
                 skills=[Skill(ActionKind.SKILL_EN_REFILL, ends_activation=False)])
    after = step(BattleState(units=[ally, _enemy()]),
                 Decision("a", ActionKind.SKILL_EN_REFILL))
    assert after.unit("a").en == 20
    assert after.unit("a").acted is False
    assert after.phase is Faction.ALLY




def _kill_spawn_event(event_id="ev1", victim="e", within_turn=None, spawn_uid="e9",
                      spawn_pos=(5, 5)):
    trigger = {"type": "kill", "uid": victim}
    if within_turn is not None:
        trigger["within_turn"] = within_turn
    return StageEvent(event_id=event_id, trigger=trigger,
                      effect={"type": "spawn", "units": [_enemy(spawn_uid, pos=spawn_pos)]})


def test_a_kill_event_spawns_its_reinforcement():
    events = {"ev1": _kill_spawn_event()}
    state = BattleState(units=[_ally(weapons=[_rifle(power=99000)]), _enemy(hp=1)],
                        pending_events=("ev1",))
    after = step(state, _attack("a", "e", hit=True), events=events)
    assert after.unit("e9") is not None
    assert after.unit("e9").pos == (5, 5)
    assert after.pending_events == ()
    assert after.fired_events == ("ev1",)


def test_a_kill_event_does_not_fire_while_its_target_lives():
    events = {"ev1": _kill_spawn_event()}
    state = BattleState(units=[_ally(weapons=[_rifle(power=1)]),
                               _enemy(hp=99999, max_hp=99999)],
                        pending_events=("ev1",))
    after = step(state, _attack("a", "e", hit=True), events=events)
    assert after.unit("e9") is None
    assert after.pending_events == ("ev1",)


def test_a_kill_window_expires_at_turn_rotation():
    events = {"ev1": _kill_spawn_event(within_turn=1)}
    state = BattleState(units=[_ally(weapons=[]), _enemy()], pending_events=("ev1",))
    state = step(state, standby("a"), events=events)
    state = step(state, standby("e"), events=events)
    assert state.turn == 2
    assert state.pending_events == ()
    assert state.fired_events == ()


def test_an_expired_window_never_fires_on_a_late_kill():
    events = {"ev1": _kill_spawn_event(within_turn=1)}
    state = BattleState(units=[_ally(weapons=[_rifle(power=99000)]), _enemy(hp=1)],
                        pending_events=("ev1",))
    state = step(state, standby("a"), events=events)
    state = step(state, standby("e"), events=events)
    state = step(state, _attack("a", "e", hit=True), events=events)
    assert state.unit("e9") is None
    assert state.fired_events == ()


def test_a_turn_start_event_fires_on_rotation():
    events = {
        "ev2": StageEvent(event_id="ev2", trigger={"type": "turn_start", "turn": 2},
                          effect={"type": "spawn", "units": [_enemy("e9", pos=(7, 7))]})
    }
    state = BattleState(units=[_ally(weapons=[]), _enemy()], pending_events=("ev2",))
    state = step(state, standby("a"), events=events)
    assert state.unit("e9") is None
    state = step(state, standby("e"), events=events)
    assert state.turn == 2
    assert state.unit("e9") is not None
    assert state.fired_events == ("ev2",)


def test_a_weaken_event_multiplies_statics():
    events = {
        "ev3": StageEvent(event_id="ev3", trigger={"type": "kill", "uid": "aura"},
                          effect={"type": "weaken", "uids": ["grunt"],
                                  "attack_multiplier": 0.5, "defense_multiplier": 0.5})
    }
    grunt = _enemy("grunt", pos=(9, 9), unit_attack=4000, unit_defense=2000)
    state = BattleState(
        units=[_ally(weapons=[_rifle(power=99000)]), _enemy("aura", pos=(2, 0), hp=1), grunt],
        pending_events=("ev3",),
    )
    after = step(state, _attack("a", "aura", hit=True), events=events)
    assert after.unit("grunt").unit_attack == 2000.0
    assert after.unit("grunt").unit_defense == 1000.0


def test_a_spawn_never_duplicates_an_existing_uid():
    events = {"ev1": _kill_spawn_event(spawn_uid="a")}
    state = BattleState(units=[_ally(weapons=[_rifle(power=99000)]), _enemy(hp=1)],
                        pending_events=("ev1",))
    after = step(state, _attack("a", "e", hit=True), events=events)
    assert len([u for u in after.units if u.unit_id == "a"]) == 1


def test_the_key_tells_a_fired_event_from_an_expired_one():
    base = BattleState(units=[_ally(weapons=[]), _enemy()])
    fired = base.clone()
    fired.fired_events = ("ev3",)
    expired = base.clone()
    assert fired.pending_events == expired.pending_events
    assert fired.key() != expired.key()


def test_the_key_tells_pending_sets_apart():
    a = BattleState(units=[_ally(weapons=[])], pending_events=("ev1",))
    b = BattleState(units=[_ally(weapons=[])])
    assert a.key() != b.key()


def test_clone_carries_the_event_state():
    clone = BattleState(units=[_ally(weapons=[])], pending_events=("ev1",),
                        fired_events=("ev0",)).clone()
    assert clone.pending_events == ("ev1",)
    assert clone.fired_events == ("ev0",)


def test_step_never_mutates_the_input_state():
    state = BattleState(units=[_ally(weapons=[_rifle(power=5000)]),
                               _enemy("e0", pos=(1, 0), hp=5)])
    before = state.key()
    step(state, _attack("a", "e0", hit=True))
    assert state.key() == before
