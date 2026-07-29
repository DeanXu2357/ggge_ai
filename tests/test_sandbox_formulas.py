"""傷害與命中公式：逐項對 docs/combat-formulas.md 手算重推，防止搬遷漂移。"""

import math

import pytest

from ggge_ai.sandbox import model


def _manual_combat_base(power, pl_atk, pl_def, un_atk, un_def, terrain=1.0):
    term1 = max(0.0, (pl_atk - pl_def) / 5000)
    term2 = max(0.0, (un_atk / 10 - un_def / 10) / 5000)
    term3 = 1.0 / (math.exp(250 * (pl_def - pl_atk) / 100000) + 1.0)
    term4 = 1.0 / (math.exp(25 * (un_def - un_atk) / 100000) + 1.0)
    term5 = power * (term1 + term2 + term3 + term4)
    term6 = 100.0 / (math.exp((5000 - (un_atk + pl_atk * 2) / 10) * 30 / 100000) + 1.0)
    term7 = -40.0 / (math.exp((5000 - (un_def + pl_def * 2) / 10) * 3 / 100000) + 1.0)
    return term5 * (1.0 + term6 + term7) / terrain


ARGS = (2000, 4000, 1500, 6000, 3000)


def test_damage_terms_match_manual_derivation():
    assert math.isclose(
        model.expected_damage(*ARGS), _manual_combat_base(*ARGS), rel_tol=1e-9
    )


def test_defense_action_multipliers_scale_final_damage():
    plain = model.expected_damage(*ARGS)
    defended = model.expected_damage(*ARGS, defense_multiplier=model.DEFEND_MULTIPLIER)
    shielded = model.expected_damage(*ARGS, defense_multiplier=model.SHIELD_MULTIPLIER)
    assert model.NO_DEFENSE_MULTIPLIER == 1.0
    assert math.isclose(defended, plain * 0.8, rel_tol=1e-9)
    assert math.isclose(shielded, plain * 0.6, rel_tol=1e-9)


def test_terrain_divides_damage():
    plain = model.expected_damage(*ARGS)
    assert math.isclose(model.expected_damage(*ARGS, terrain=1.25), plain / 1.25, rel_tol=1e-9)


def test_bonuses_and_penalties_sum_before_multiplying():
    assert model.damage_scale(0.3, 0.1) == pytest.approx(1.2)
    plain = model.expected_damage(*ARGS)
    scaled = model.expected_damage(*ARGS, bonuses=0.5, penalties=0.2)
    assert math.isclose(scaled, plain * 1.3, rel_tol=1e-9)


def test_critical_multiplies_over_final_damage():
    combat_base = model.combat_base_damage(*ARGS)
    assert math.isclose(
        model.critical_damage(combat_base, critical=model.CRIT_NORMAL),
        combat_base * 1.1,
        rel_tol=1e-9,
    )
    assert (model.CRIT_NORMAL, model.CRIT_HIGH_MORALE, model.CRIT_SUPER) == (1.1, 1.2, 1.3)


def test_hit_rate_matches_manual_regression():
    atk_mob, def_mob, pl_atk, def_reaction = 1200.0, 900.0, 3000.0, 2500.0
    expected = 96.45 + 0.00732 * atk_mob - 0.00662 * def_mob + (pl_atk - def_reaction) / 25.0
    got = model.hit_rate_percent(atk_mob, def_mob, pl_atk, def_reaction, clamp=False)
    assert math.isclose(got, expected, rel_tol=1e-9)


def test_hit_probability_is_a_clamped_fraction():
    assert model.hit_probability(9999, 0, 999999, 0) == 1.0
    assert model.hit_probability(0, 9999, 0, 999999) == 0.0
