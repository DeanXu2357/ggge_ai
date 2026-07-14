from ggge_ai.battle.reconcile import PendingOutcome, SimExpectation
from ggge_ai.battle.scout_intel import StageIntel
from ggge_ai.battle.state import BattleState, Faction, UnitState
from ggge_ai.battle.tracker import BoardTracker
from ggge_ai.battle.vision import BattlePrepForecast, EnemySummary, WeaponSelectForecast

ENEMY_SIG = "e" * 16
ALLY_SIG = "a" * 16


def _forecast(**overrides):
    base = dict(
        target_name_sig=ENEMY_SIG, target_hp=8000, target_en=120,
        predicted_damage=5000, hit_pct=None,
        our_name_sig=ALLY_SIG, our_hp=30000, our_en=250,
    )
    base.update(overrides)
    return WeaponSelectForecast(**base)


def _prep(**overrides):
    base = dict(
        is_reaction=False, attack_value=5000, defense_value=1000, hit_pct=100,
        attacker_name_sig=ALLY_SIG, attacker_hp=30000, attacker_en=240,
        defender_name_sig=ENEMY_SIG, defender_hp=8000, defender_en=120,
        defender_hp_delta=None, support_defense=None,
    )
    base.update(overrides)
    return BattlePrepForecast(**base)


def _pending(*, expect_kill=None, quality="grounded", game_damage=5000,
             target_hp_game=8000, game_expect_kill=None, hit_pct=None):
    expectation = SimExpectation(
        attacker_sig=ALLY_SIG, target_sig=ENEMY_SIG, weapon_slot=1,
        expected_damage=float(game_damage), target_hp_believed=target_hp_game,
        expect_kill=expect_kill, hit_probability=0.9,
        source="formulas", quality=quality,
    )
    return PendingOutcome(
        expectation=expectation, game_damage=game_damage,
        target_hp_game=target_hp_game, game_expect_kill=game_expect_kill,
        counter_before=(0, 14), hit_pct=hit_pct,
    )


def test_weapon_select_updates_both_sides():
    t = BoardTracker()
    t.on_weapon_select(_forecast(), our_world=(10.0, 20.0), target_world=(400.0, 20.0))
    ours = t.beliefs[ALLY_SIG]
    enemy = t.beliefs[ENEMY_SIG]
    assert (ours.faction, ours.hp, ours.en) == (Faction.ALLY, 30000, 250)
    assert (enemy.faction, enemy.hp, enemy.en) == (Faction.ENEMY, 8000, 120)
    assert enemy.world_pos == (400.0, 20.0)
    assert ours.source == enemy.source == "forecast"


def test_battle_prep_reaction_swaps_the_direction():
    t = BoardTracker()
    t.on_battle_prep(_prep(is_reaction=True, attacker_name_sig=ENEMY_SIG,
                           attacker_hp=7000, defender_name_sig=ALLY_SIG,
                           defender_hp=29000))
    assert t.beliefs[ENEMY_SIG].faction is Faction.ENEMY
    assert t.beliefs[ENEMY_SIG].hp == 7000
    assert t.beliefs[ALLY_SIG].faction is Faction.ALLY
    assert t.beliefs[ALLY_SIG].hp == 29000


def test_kill_outcome_marks_dead_and_drops_position():
    t = BoardTracker()
    t.on_weapon_select(_forecast(), target_world=(400.0, 20.0))
    t.on_outcome(_pending(expect_kill=True), "confirmed", delta=1)
    belief = t.beliefs[ENEMY_SIG]
    assert belief.alive is False
    assert belief.hp == 0
    assert ENEMY_SIG not in t.sig_positions()


def test_certain_hit_no_kill_estimates_hp():
    t = BoardTracker()
    t.on_weapon_select(_forecast(target_hp=8000))
    t.on_outcome(_pending(expect_kill=False, game_damage=5000, hit_pct=100),
                 "confirmed", delta=0)
    belief = t.beliefs[ENEMY_SIG]
    assert belief.hp == 3000
    assert belief.source == "estimate"


def test_uncertain_no_kill_keeps_hp():
    t = BoardTracker()
    t.on_weapon_select(_forecast(target_hp=8000))
    t.on_outcome(_pending(expect_kill=True, hit_pct=85), "rng_branch")
    assert t.beliefs[ENEMY_SIG].hp == 8000


def test_result_string_fallback_without_delta():
    t = BoardTracker()
    t.on_weapon_select(_forecast(target_hp=8000))
    t.on_outcome(_pending(expect_kill=True), "confirmed")
    assert t.beliefs[ENEMY_SIG].alive is False

    t2 = BoardTracker()
    t2.on_weapon_select(_forecast(target_hp=8000))
    t2.on_outcome(_pending(expect_kill=True, hit_pct=100), "model_diverge")
    assert t2.beliefs[ENEMY_SIG].alive is True


def test_screen_read_overwrites_estimate():
    t = BoardTracker()
    t.on_weapon_select(_forecast(target_hp=8000))
    t.on_outcome(_pending(expect_kill=False, game_damage=5000, hit_pct=100),
                 "confirmed", delta=0)
    assert t.beliefs[ENEMY_SIG].source == "estimate"
    t.on_weapon_select(_forecast(target_hp=2800))
    assert t.beliefs[ENEMY_SIG].hp == 2800
    assert t.beliefs[ENEMY_SIG].source == "forecast"


def test_intel_seeds_enemy_beliefs():
    t = BoardTracker()
    intel = StageIntel()
    intel.summaries[ENEMY_SIG] = EnemySummary(name_sig=ENEMY_SIG, hp=51349, en=300)
    intel.positions[ENEMY_SIG] = (420, 30)
    t.on_intel(intel)
    belief = t.beliefs[ENEMY_SIG]
    assert (belief.hp, belief.en, belief.world_pos) == (51349, 300, (420.0, 30.0))
    assert belief.source == "intel"


def test_sig_positions_excludes_allies_and_the_dead():
    t = BoardTracker()
    t.on_sig_position(ENEMY_SIG, (400.0, 0.0))
    t.on_sig_position(ALLY_SIG, (0.0, 0.0), faction=Faction.ALLY)
    assert set(t.sig_positions()) == {ENEMY_SIG}
    t.beliefs[ENEMY_SIG].alive = False
    assert t.sig_positions() == {}


def test_apply_fills_sig_matched_enemy_and_radius_matched_ally():
    t = BoardTracker()
    t.on_turn(2)
    t.on_weapon_select(_forecast(), our_world=(10.0, 20.0))
    battle = BattleState()
    battle.add_unit(UnitState("ally_1", Faction.ALLY, world_pos=(50.0, 20.0)))
    battle.add_unit(UnitState(ENEMY_SIG, Faction.ENEMY, world_pos=(400.0, 20.0)))
    notes = t.apply(battle)
    assert battle.unit(ENEMY_SIG).hp == 8000
    assert battle.unit("ally_1").hp == 30000
    assert any(ENEMY_SIG in n for n in notes)
    assert any("ally_1" in n for n in notes)


def test_apply_never_overwrites_a_scan_value():
    t = BoardTracker()
    t.on_weapon_select(_forecast(target_hp=8000))
    battle = BattleState()
    battle.add_unit(UnitState(ENEMY_SIG, Faction.ENEMY, world_pos=(400.0, 20.0), hp=7500))
    notes = t.apply(battle)
    assert battle.unit(ENEMY_SIG).hp == 7500
    assert not any("HP" in n for n in notes)
    assert battle.unit(ENEMY_SIG).en == 120


def test_jittered_sig_resolves_to_the_same_belief():
    # live corpus 20260713-225448: one unit's sig differs by 3-5 bits
    # between the weapon-select and battle-prep panels
    t = BoardTracker()
    t.on_weapon_select(_forecast(our_name_sig="9115599951d15595", our_hp=89311))
    t.on_battle_prep(_prep(is_reaction=True, attacker_name_sig=None,
                           defender_name_sig="9119599551d155d5", defender_hp=74000))
    assert "9119599551d155d5" not in t.beliefs
    assert t.beliefs["9115599951d15595"].hp == 74000


def test_distant_sig_creates_a_new_belief():
    t = BoardTracker()
    t.on_weapon_select(_forecast())
    t.on_weapon_select(_forecast(target_name_sig="0" * 16, target_hp=123))
    assert t.beliefs["0" * 16].hp == 123
    assert t.beliefs[ENEMY_SIG].hp == 8000


def test_apply_skips_far_ally_beliefs():
    t = BoardTracker()
    t.on_weapon_select(_forecast(), our_world=(10.0, 20.0))
    battle = BattleState()
    battle.add_unit(UnitState("ally_1", Faction.ALLY, world_pos=(900.0, 900.0)))
    t.apply(battle)
    assert battle.unit("ally_1").hp is None
