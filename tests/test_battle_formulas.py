import math

from ggge_ai.sim import formulas


def _manual_expected_damage(power, pl_atk, pl_def, un_atk, un_def):
    term1 = max(0.0, (pl_atk - pl_def) / 5000)
    term2 = max(0.0, (un_atk / 10 - un_def / 10) / 5000)
    term3 = 1.0 / (math.exp(250 * (pl_def - pl_atk) / 100000) + 1.0)
    term4 = 1.0 / (math.exp(25 * (un_def - un_atk) / 100000) + 1.0)
    base = power * (term1 + term2 + term3 + term4)
    term6 = 100.0 / (math.exp((5000 - (un_atk + pl_atk * 2) / 10) * 30 / 100000) + 1.0)
    term7 = -40.0 / (math.exp((5000 - (un_def + pl_def * 2) / 10) * 3 / 100000) + 1.0)
    combat_base = base * (1.0 + term6 + term7)
    return combat_base


def test_damage_terms_match_manual_derivation():
    power, pl_atk, pl_def, un_atk, un_def = 2000, 4000, 1500, 6000, 3000
    expected = _manual_expected_damage(power, pl_atk, pl_def, un_atk, un_def)
    got = formulas.expected_damage(power, pl_atk, pl_def, un_atk, un_def)
    assert math.isclose(got, expected, rel_tol=1e-9)


def test_defense_multiplier_scales_final_damage():
    args = (2000, 4000, 1500, 6000, 3000)
    plain = formulas.expected_damage(*args)
    defended = formulas.expected_damage(*args, defense_multiplier=formulas.DEFEND_MULTIPLIER)
    shielded = formulas.expected_damage(*args, defense_multiplier=formulas.SHIELD_MULTIPLIER)
    assert math.isclose(defended, plain * 0.8, rel_tol=1e-9)
    assert math.isclose(shielded, plain * 0.6, rel_tol=1e-9)


def test_terrain_divides_damage():
    args = (2000, 4000, 1500, 6000, 3000)
    plain = formulas.expected_damage(*args)
    on_terrain = formulas.expected_damage(*args, terrain=1.25)
    assert math.isclose(on_terrain, plain / 1.25, rel_tol=1e-9)


def test_critical_multiplies_over_final_damage():
    combat_base = formulas.combat_base_damage(2000, 4000, 1500, 6000, 3000)
    normal = formulas.critical_damage(combat_base, critical=formulas.CRIT_NORMAL)
    assert math.isclose(normal, combat_base * 1.1, rel_tol=1e-9)


def test_hit_rate_matches_manual_regression():
    atk_mob, def_mob, pl_atk, def_reaction = 1200.0, 900.0, 3000.0, 2500.0
    expected = (
        96.45
        + 0.00732 * atk_mob
        - 0.00662 * def_mob
        + (pl_atk - def_reaction) / 25.0
    )
    got = formulas.hit_rate_percent(atk_mob, def_mob, pl_atk, def_reaction, clamp=False)
    assert math.isclose(got, expected, rel_tol=1e-9)


def test_hit_probability_is_clamped_fraction():
    prob = formulas.hit_probability(9999, 0, 999999, 0)
    assert prob == 1.0
    prob_low = formulas.hit_probability(0, 9999, 0, 999999)
    assert prob_low == 0.0
