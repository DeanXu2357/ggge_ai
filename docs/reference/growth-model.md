# Growth model

> Type: reference—drift is a bug

This document states how the datamine values of a mech, a pilot, a
weapon and a support crew grow with the level, the limit break and
the upgrades `mech_sp` and `mech_ssp`. The source is the site code
of soshage, read on 2026-09-03 at the data version stamp
202609010310. The module `src/ggge_ai/gamedata/growth.py` holds the
constants and the formulas; `holding.py` assembles one holding into
the engine payload. This document is the reference for both.

The site chunks that hold the facts (all under
`https://soshage.com/_app/immutable/`):

| Fact | Chunk |
|---|---|
| Level curve, 100 values | `chunks/BF720UQY2.js` |
| Level cap by rarity | `chunks/DqyRWwcW.js` |
| Mech stat assembly | `chunks/C5zmT3sP2.js` |
| Support crew bonus | `chunks/DHxa5-D42.js` |

## Level curve

One table of 100 rates grows a stat from its base value at level 1
to its max value at level 100. The rate at level L is the entry
L−1. The first entry is 0 and the last is 10000. The table is not
linear: the entry at level 50 is 4989, not 5000.

    value(level) = floor(base + (max − base) × rate(level) / 10000)

A mech and a pilot share this table. The level is clamped to the
cap before the lookup. The table `level_curve` of the game data
store holds the 100 rows; `growth.LEVEL_CURVE` holds the same
values.

## Level cap

| Rarity | Cap |
|---|---|
| 1 | 60 |
| 2 | 70 |
| 3 | 80 |
| 4 | 90 |
| 5 | 100 |

The cap becomes 100 when the mech has `mech_sp` or `mech_ssp`. The
table `rarity_level_cap` holds the five rows.

## Mech stats

The datamine carries, for each of hp, en, attack, defense, mobility
and movement, the four values `base`, `max`, `sp_base`, `sp_max`.
The SSP block `ssp_config.stats` carries `ssp_` and `ssp_max_` for
hp, en, attack, defense and mobility; movement has no SSP value.

The assembly, in order:

1. Value group. When the mech has `mech_sp` and its rarity is below
   5, read `sp_base` and `sp_max`. In every other case read `base`
   and `max`. A UR mech carries `sp_` values equal to its plain
   values, so the rule gives the same result either way.
2. Level. Apply the level curve with the cap of the step above.
3. SSP addition. When the mech has `mech_ssp`, add `ssp_max_` of
   the stat (user ruling 2026-09-03: one stage, take the max). Then
   add every `status_up` release of `ssp_config` whose
   `unit_status_type_index` names the stat. Type 6 is movement; the
   others are 1 hp, 2 en, 3 attack, 4 defense, 5 mobility. At stamp
   202609010310 every `status_up` release is type 6.
4. Limit break. Multiply hp, en, attack, defense and mobility by the
   rate of the star count and floor. Movement is not scaled.

| Stars | Rate |
|---|---|
| 0 | 1.0 |
| 1 | 1.2 |
| 2 | 1.3 |
| 3 | 1.4 |

The table `limit_break_rate` holds the four rows as percents.

Example, Zeong 1001003000 (rarity 4, `mech_sp`, `mech_ssp`, level
100, three stars): the sp group HP 8936 to 64337 gives 64337 at
level 100; plus ssp_max_hp 4577 gives 68914; times 1.4 gives
96479. Without `mech_sp` the plain group 8032 to 57831 stops at
the cap 90. Zeong (EX) 1001003050 (rarity 5, level 100, three
stars): 71770 times 1.4 gives 100478, the value that the site
shows (issue #92).

Hypothesis (source: `C5zmT3sP2.js` sets the star select to '3'
when `mech_sp` and rarity below 5, and to '0' when `ult`): the game
gives a below-UR mech its three stars as part of `mech_sp`, and an
ult mech has no limit break. The loader takes the star count from
the holding row and does not force it. Verify on the device before
you depend on it.

## Weapons

A weapon row carries the level-1 values `power`, `en`, `hit_rate`,
`critical_rate` and the growth block `wsc`, five rows with the
percent of each value at weapon level 1 to 5.

    value(level) = floor(base × rate(level) / 100)

The loader takes the weapon level from the holding row. The default
is 5, the full value.

A mech with `mech_ssp` gets its SSP releases in core order (initial
release first, then the cores at level 1, 5, 10, 15, 20), each core
in `sort_order`:

- `weapon_change`: `before_weapon_id` 0 adds the weapon
  `after_weapon_id` (at the stamp above every row adds; none
  replaces).
- `weapon_enhance`: `weapon_enhance_type_index` 1 adds `value` to
  the power, 3 adds `value` to the ammo, 4 adds `value` to
  `range_max`. Type 2 does not occur at the stamp above.
- `weapon_effect` and `ability_change`: stored, not applied. The
  engine has no field for them (issue #72).

The weapons with `is_ssp` true in the weapon table are the SSP
weapons that a `weapon_change` release adds. The loader takes the
non-SSP weapons of the unit first, then applies the releases.

## Pilot stats

A pilot row carries `ranged`, `melee`, `defense`, `reaction`,
`awaken`, each with `base`, `max`, `sp_base`, `sp_max`. The pilot
follows the same level curve as the mech. A pilot has no limit
break. The `sp_` group of a pilot is not the pilot's skill-point
pool; the loader reads the plain group.

Hypothesis (source: the pilot row carries `rarity` and the site
uses one cap table): the pilot cap follows the rarity table above.
The loader applies the rarity cap to the pilot level.

## Support crew

A support crew row carries `max_hp_addition_value` and
`max_attack_addition_value`. The table `supporter_growth` (400
rows: level 1–100, limit break 0–3) gives `correction_rate`.

    bonus = floor(max_addition × correction_rate / 10000)

Example: a crew with max HP addition 2000 at level 1, zero stars
(rate 2000) adds 400 HP; at level 100 with three stars (rate 14000)
adds 2800.

The engine payload has no field for the crew bonus. The loader
writes the bonus beside the payload for issue #72.
