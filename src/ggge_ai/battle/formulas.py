"""Damage and hit formulas for tree-internal combat simulation.

These implement the community-reverse-engineered formulas transcribed in
docs/combat-formulas.md (damage terms 1-11, plus the hit-rate regression).
They are pure functions: every game number (pilot attack/defence, unit
attack/defence, weapon power, mobility, reaction) is a parameter supplied by
the caller, never baked in. Only the *mechanism* constants (the divisors and
coefficients that make up the formula shape, and the defence/critical
multipliers) live here, and each is exposed as an overridable keyword so the
caller can recalibrate against on-device attack-prediction values.

Authority note (docs/agent-architecture.md): the current step's hit and
damage are read from the game's attack-prediction UI. These formulas only
approximate hypothetical engagements deeper in the search tree. Several
inputs are still community-fitted and await on-device calibration: the
hit-rate constants, the dodge-action modifier, the terrain divisor table and
the critical-rate model are all flagged in docs/combat-formulas.md.
"""

from __future__ import annotations

import math

# Defence-action damage multipliers (docs/combat-formulas.md).
NO_DEFENSE_MULTIPLIER = 1.0
DEFEND_MULTIPLIER = 0.8
SHIELD_MULTIPLIER = 0.6

# Critical multipliers (occurrence rate is not yet known; see the doc).
CRIT_NORMAL = 1.1
CRIT_HIGH_MORALE = 1.2
CRIT_SUPER = 1.3

# Hit-rate regression constants (community-fitted, low precision).
HIT_BASE = 96.45
HIT_ATK_MOBILITY_COEF = 0.00732
HIT_DEF_MOBILITY_COEF = 0.00662
HIT_PILOT_DIVISOR = 25.0


def pilot_ratio_correction(pl_atk: float, pl_def: float) -> float:
    """Term 1: pilot ratio correction."""
    return max(0.0, (pl_atk - pl_def) / 5000)


def unit_ratio_correction(un_atk: float, un_def: float) -> float:
    """Term 2: unit ratio correction."""
    return max(0.0, (un_atk / 10 - un_def / 10) / 5000)


def pilot_function_correction(pl_atk: float, pl_def: float) -> float:
    """Term 3: pilot sigmoid correction."""
    return 1.0 / (math.exp(250 * (pl_def - pl_atk) / 100000) + 1.0)


def unit_function_correction(un_atk: float, un_def: float) -> float:
    """Term 4: unit sigmoid correction."""
    return 1.0 / (math.exp(25 * (un_def - un_atk) / 100000) + 1.0)


def base_damage(
    power: float, pl_atk: float, pl_def: float, un_atk: float, un_def: float
) -> float:
    """Term 5: base damage = POW * (term1 + term2 + term3 + term4)."""
    return power * (
        pilot_ratio_correction(pl_atk, pl_def)
        + unit_ratio_correction(un_atk, un_def)
        + pilot_function_correction(pl_atk, pl_def)
        + unit_function_correction(un_atk, un_def)
    )


def attack_correction(un_atk: float, pl_atk: float) -> float:
    """Term 6: attack correction."""
    return 100.0 / (math.exp((5000 - (un_atk + pl_atk * 2) / 10) * 30 / 100000) + 1.0)


def defense_correction(un_def: float, pl_def: float) -> float:
    """Term 7: defence correction (negative)."""
    return -40.0 / (math.exp((5000 - (un_def + pl_def * 2) / 10) * 3 / 100000) + 1.0)


def combat_base_damage(
    power: float,
    pl_atk: float,
    pl_def: float,
    un_atk: float,
    un_def: float,
    *,
    terrain: float = 1.0,
) -> float:
    """Term 8: base damage * (1 + term6 + term7) / terrain divisor."""
    base = base_damage(power, pl_atk, pl_def, un_atk, un_def)
    factor = 1.0 + attack_correction(un_atk, pl_atk) + defense_correction(un_def, pl_def)
    return base * factor / terrain


def damage_scale(bonuses: float = 0.0, penalties: float = 0.0) -> float:
    """Term 9: 1 + sum(bonuses) - sum(penalties), summed before multiplying."""
    return 1.0 + bonuses - penalties


def final_damage(
    combat_base: float,
    *,
    scale: float = 1.0,
    defense_multiplier: float = NO_DEFENSE_MULTIPLIER,
) -> float:
    """Term 10: combat base * damage scale * defence-action multiplier."""
    return combat_base * scale * defense_multiplier


def critical_damage(
    combat_base: float,
    *,
    scale: float = 1.0,
    defense_multiplier: float = NO_DEFENSE_MULTIPLIER,
    critical: float = CRIT_NORMAL,
) -> float:
    """Term 11: term 10 further multiplied by the critical multiplier."""
    return combat_base * scale * defense_multiplier * critical


def expected_damage(
    power: float,
    pl_atk: float,
    pl_def: float,
    un_atk: float,
    un_def: float,
    *,
    terrain: float = 1.0,
    bonuses: float = 0.0,
    penalties: float = 0.0,
    defense_multiplier: float = NO_DEFENSE_MULTIPLIER,
) -> float:
    """Terms 5-10 composed: the non-critical final damage of one hit."""
    combat_base = combat_base_damage(
        power, pl_atk, pl_def, un_atk, un_def, terrain=terrain
    )
    return final_damage(
        combat_base,
        scale=damage_scale(bonuses, penalties),
        defense_multiplier=defense_multiplier,
    )


def hit_rate_percent(
    atk_mobility: float,
    def_mobility: float,
    pl_atk: float,
    def_reaction: float,
    *,
    ability_correction: float = 0.0,
    base: float = HIT_BASE,
    clamp: bool = True,
) -> float:
    """Hit rate as a percentage (0-100 when clamped)."""
    rate = (
        base
        + HIT_ATK_MOBILITY_COEF * atk_mobility
        - HIT_DEF_MOBILITY_COEF * def_mobility
        + (pl_atk - def_reaction) / HIT_PILOT_DIVISOR
        + ability_correction
    )
    if clamp:
        return max(0.0, min(100.0, rate))
    return rate


def hit_probability(
    atk_mobility: float,
    def_mobility: float,
    pl_atk: float,
    def_reaction: float,
    *,
    ability_correction: float = 0.0,
    base: float = HIT_BASE,
) -> float:
    """Hit rate as a probability in [0, 1]."""
    return hit_rate_percent(
        atk_mobility,
        def_mobility,
        pl_atk,
        def_reaction,
        ability_correction=ability_correction,
        base=base,
    ) / 100.0
