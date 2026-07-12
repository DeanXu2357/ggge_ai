"""Reconciliation logic: sim expectation vs game forecast vs 破壞數 verdict."""

from ggge_ai.battle import formulas, reconcile
from ggge_ai.battle.bridge import UnitSpec
from ggge_ai.battle.sim import SimWeapon
from ggge_ai.battle.vision import BattlePrepForecast, WeaponSelectForecast


def _forecast(**overrides):
    base = dict(
        target_name_sig="t" * 16,
        target_hp=8000,
        target_en=300,
        predicted_damage=9000,
        hit_pct=None,
        our_name_sig="a" * 16,
        our_hp=50000,
        our_en=400,
    )
    base.update(overrides)
    return WeaponSelectForecast(**base)


def _prep(**overrides):
    base = dict(
        is_reaction=False,
        attack_value=9000,
        defense_value=0,
        hit_pct=85,
        attacker_name_sig="a" * 16,
        attacker_hp=50000,
        attacker_en=400,
        defender_name_sig="t" * 16,
        defender_hp=8000,
        defender_en=300,
        defender_hp_delta=8000,
        support_defense=None,
    )
    base.update(overrides)
    return BattlePrepForecast(**base)


def _spec(**overrides):
    base = dict(
        max_hp=50000,
        en_max=400,
        unit_attack=3500.0,
        unit_defense=3000.0,
        pilot_shooting=200.0,
        pilot_melee=180.0,
        pilot_defense=200.0,
        reaction=220.0,
        mobility=3000.0,
        move_range=5,
        weapons=(
            SimWeapon(name="weapon_1_shooting", power=3200.0, range_min=1, range_max=3, en_cost=24),
        ),
    )
    base.update(overrides)
    return UnitSpec(**base)


def test_expectation_without_specs_is_uncreditable():
    exp = reconcile.compute_expectation(
        attacker_spec=None, target_spec=None, forecast=_forecast(), slot=1
    )
    assert exp.quality == "none"
    assert exp.source == "heuristic_v1"
    assert exp.expected_damage is None
    assert exp.expect_kill is None
    assert "no spec" in exp.assumptions[0]


def test_grounded_expectation_matches_formulas():
    attacker, target = _spec(), _spec()
    exp = reconcile.compute_expectation(
        attacker_spec=attacker, target_spec=target, forecast=_forecast(), slot=1
    )
    assert exp.quality == "grounded"
    assert exp.source == "formulas"
    expected = formulas.expected_damage(3200.0, 200.0, 200.0, 3500.0, 3000.0)
    assert exp.expected_damage == expected
    assert exp.expect_kill == (expected >= 8000)
    assert exp.hit_probability == formulas.hit_probability(3000.0, 3000.0, 200.0, 220.0)


def test_missing_stat_downgrades_to_assumed():
    exp = reconcile.compute_expectation(
        attacker_spec=_spec(unit_attack=None),
        target_spec=_spec(),
        forecast=_forecast(),
        slot=1,
    )
    assert exp.quality == "assumed"
    assert any("unit_attack" in a for a in exp.assumptions)


def test_screen_hp_beats_spec_hp():
    exp = reconcile.compute_expectation(
        attacker_spec=_spec(), target_spec=_spec(max_hp=1), forecast=_forecast(target_hp=8000),
        slot=1,
    )
    assert exp.target_hp_believed == 8000


def test_weapon_select_flags_sim_skip():
    exp = reconcile.compute_expectation(
        attacker_spec=None, target_spec=None, forecast=_forecast(), slot=1
    )
    _, divergences = reconcile.reconcile_weapon_select(exp, _forecast(), (0, 14))
    assert [d.tag for d in divergences] == ["sim_skip"]


def test_weapon_select_flags_damage_divergence():
    exp = reconcile.compute_expectation(
        attacker_spec=_spec(), target_spec=_spec(), forecast=_forecast(), slot=1
    )
    game = _forecast(predicted_damage=round(exp.expected_damage * 2))
    _, divergences = reconcile.reconcile_weapon_select(exp, game, None)
    assert any(d.tag == "sim_diverge" and d.kind == "damage" for d in divergences)


def test_weapon_select_flags_kill_flip():
    exp = reconcile.compute_expectation(
        attacker_spec=_spec(), target_spec=_spec(), forecast=_forecast(), slot=1
    )
    assert exp.expected_damage is not None
    hp_above_sim = round(exp.expected_damage) + 1000
    game = _forecast(
        target_hp=hp_above_sim, predicted_damage=hp_above_sim + 500
    )
    exp2 = reconcile.compute_expectation(
        attacker_spec=_spec(), target_spec=_spec(), forecast=game, slot=1
    )
    assert exp2.expect_kill is False
    _, divergences = reconcile.reconcile_weapon_select(exp2, game, None)
    assert any(d.kind == "kill_flip" for d in divergences)


def test_weapon_select_within_tolerance_is_silent():
    exp = reconcile.compute_expectation(
        attacker_spec=_spec(), target_spec=_spec(), forecast=_forecast(), slot=1
    )
    game = _forecast(
        predicted_damage=round(exp.expected_damage * 1.05),
        target_hp=round(exp.expected_damage * 0.5),
    )
    exp = reconcile.compute_expectation(
        attacker_spec=_spec(), target_spec=_spec(), forecast=game, slot=1
    )
    _, divergences = reconcile.reconcile_weapon_select(exp, game, (0, 14))
    assert divergences == []


def test_battle_prep_collapse_flags_support_defense():
    pending = reconcile.PendingOutcome(
        expectation=reconcile.compute_expectation(
            attacker_spec=None, target_spec=None, forecast=_forecast(), slot=1
        ),
        game_damage=9000,
        target_hp_game=8000,
        game_expect_kill=True,
        counter_before=(0, 14),
    )
    updated, divergences = reconcile.reconcile_battle_prep(
        pending, _prep(attack_value=4500)
    )
    assert any(d.kind == "support_defense" for d in divergences)
    assert updated.game_damage == 4500
    assert updated.game_expect_kill is False
    assert updated.hit_pct == 85


def test_battle_prep_matching_damage_is_silent():
    pending = reconcile.PendingOutcome(
        expectation=reconcile.compute_expectation(
            attacker_spec=None, target_spec=None, forecast=_forecast(), slot=1
        ),
        game_damage=9000,
        target_hp_game=8000,
        game_expect_kill=True,
        counter_before=(0, 14),
    )
    _, divergences = reconcile.reconcile_battle_prep(pending, _prep(attack_value=9000))
    assert divergences == []


def _pending(expect_kill, hit_pct, quality="grounded"):
    exp = reconcile.SimExpectation(
        attacker_sig="a" * 16,
        target_sig="t" * 16,
        weapon_slot=1,
        expected_damage=9000.0,
        target_hp_believed=8000,
        expect_kill=expect_kill,
        hit_probability=0.8,
        source="formulas",
        quality=quality,
    )
    return reconcile.PendingOutcome(
        expectation=exp,
        game_damage=9000,
        target_hp_game=8000,
        game_expect_kill=expect_kill,
        counter_before=(3, 14),
        hit_pct=hit_pct,
        armed=True,
    )


def test_outcome_confirmed_on_kill():
    result, divergences = reconcile.judge_outcome(_pending(True, 85), (4, 14))
    assert result == "confirmed"
    assert divergences == []


def test_outcome_confirmed_on_expected_no_kill():
    result, _ = reconcile.judge_outcome(_pending(False, 85), (3, 14))
    assert result == "confirmed"


def test_missed_kill_below_certain_hit_is_rng_branch():
    result, divergences = reconcile.judge_outcome(_pending(True, 62), (3, 14))
    assert result == "rng_branch"
    assert divergences[0].tag == "rng_branch"


def test_missed_kill_at_certain_hit_is_model_divergence():
    result, divergences = reconcile.judge_outcome(_pending(True, 100), (3, 14))
    assert result == "model_diverge"
    assert divergences[0].tag == "model_diverge"


def test_missed_kill_with_unknown_hit_stays_unattributed():
    result, divergences = reconcile.judge_outcome(_pending(True, None), (3, 14))
    assert result == "unverified_hit_unknown"
    assert divergences == []


def test_unexpected_kill_is_reported():
    result, _ = reconcile.judge_outcome(_pending(False, 85), (4, 14))
    assert result == "unexpected_kill"


def test_no_baseline_counter_is_unverifiable():
    pending = _pending(True, 85)
    pending.counter_before = None
    result, _ = reconcile.judge_outcome(pending, (4, 14))
    assert result == "unverified_no_baseline"
