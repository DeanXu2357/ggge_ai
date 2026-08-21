# The soshage datamine

> Type: reference—drift is a bug

The site soshage publishes master data of this game over a public
JSON API. The crawler `scripts/crawl_datamine.py` stores that data
in `data/datamine/<data version stamp>/`.

The store is a second channel. It is not an authority. The screen
stays the authority for every live decision. No value of the store
enters a decision until the project's own intel store
(`src/ggge_ai/stage/intel.py`) confirms it against the device.

`docs/reference/combat-formulas.md` cites the same source at one
field. That document keeps its own citation. This document records
the source itself.

## The source

- Base address: `https://soshage.com`. The game section is `/gget`.
- The site states in its own footer that it has no affiliation with
  the publisher of the game.
- The licence is not stated on the site. Not verified.
- The rate limit is not stated on the site. Not verified. One run of
  the crawler makes five requests and downloads 57 MB.

## The data version stamp

`GET /ggetapi/version` gives the stamp:

```
{"version":"202608161248"}
```

The same value is in the payload of every rendered page, in the
field `remoteVersion`. The three data addresses carry no stamp of
their own.

The crawler names the dump directory with the stamp. A game patch
changes the stamp, so a new dump lands beside the old one.

## The four sources

The row counts come from a crawl on 2026-08-22, at the stamp
`202608161248`.

| Name | Address | Form | Rows |
|---|---|---|---|
| unit | `/ggetapi/en/unit` | JSON array | 1226 |
| weapon | `/ggetapi/en/weapon` | JSON object | 4785 weapons, 1342 units |
| stage | `/ggetapi/en/stage` | JSON array | 2104 |
| formula | `/gget/formula` | HTML page | 17 formula lines, 3 notes |

The formula address is a rendered page, not an API. The page also
embeds prefetched API payloads, and the server writes those in the
order in which they complete. Two fetches of the page therefore give
different bytes. The formula tab of the page is static markup, and
the crawler stores that tab alone.

The three API addresses give the same bytes for two fetches at the
same stamp. This was measured on 2026-08-22 for `unit` and `stage`.

The unit table and the weapon table do not hold the same set of
units. The weapon table names 1342 owners. The unit table holds
1226 rows, and every one of them owns weapons. 116 owners of the
weapon table are absent from the unit table. The sidecar object
`units` of the weapon endpoint holds one row for each of the 1342
owners.

## The unit row

| Group | Fields |
|---|---|
| Identity | `id`, `main_unit`, `name`, `short_name`, `models`, `desc`, `icon` |
| Catalogue | `rarity`, `role`, `series`, `series_set`, `tags`, `area`, `body_type`, `tr`, `acquisition`, `schedule_id`, `ult`, `mechanism_set`, `base_skill` |
| Stance | `defend`, `evade` |
| Values | `stats` |
| Terrain adaptability | `terrain` |
| Free text | `abilities`, `skills`, `mechanism` |
| Super mode | `ssp_config` |
| Always null here | `weapons`, `get`, `gacha`, `transform_from`, `transform_to`, `schedule`, `link`, `ssp_weapon` |

`defend` and `evade` are true on all 1226 rows.

The object `stats` holds 25 fields. Six values repeat in four
groups: `hp`, `en`, `attack`, `defense`, `mobility` and `movement`.
The four groups are the plain group, the `max_` group, the `sp_`
group and the `sp_max_` group. The prefix `max_` is the value at
full development. The prefix `sp_` is the value in the super mode.
Which group the game shows on the panel of a deployed unit is not
verified.

The object `terrain` holds one value for each of the five terrain
kinds: `space`, `atmospheric`, `ground`, `surface` and
`underwater`. Each value is 1, 2 or 3. The map from these three
numbers to the symbols ○, △ and － is a hypothesis
(`docs/reference/combat-formulas.md`). It is not verified.

`abilities` and `mechanism` hold rows of free English text: a name
and a description. `skills` is empty on 1222 of the 1226 rows.

The unit row holds no pilot. It holds no reaction value.

## The weapon row

| Field | Content |
|---|---|
| `id`, `name` | The identity of the weapon |
| `unit_id` | The owner of the weapon |
| `weapon_status_id`, `is_ssp` | The value set and the super mode flag |
| `power` | The weapon power, 0 to 8600 |
| `en` | The energy cost, 12 to 86 |
| `ammo` | 1 on 4668 rows, 2 to 9 on the rest |
| `range_min`, `range_max` | The band, `range_max` 0 to 7 |
| `hit_rate` | 100 on 3301 rows, 105 on 1226, 95 on 133, 90 on 125 |
| `critical_rate` | 0 on 3111 rows, then 5, 10, 15, 20, 25, 30 and 40 |
| `type`, `work_type`, `attack_attr`, `weapon_attr` | Four integer enums |
| `ssp_range_max_add` | 0 on all 4785 rows |
| `growth` | The scaling by weapon level |

The meaning of the four integer enums is not verified. `type` takes
three values, `work_type` five, `attack_attr` seven and
`weapon_attr` six.

`growth` holds the list `wsc`. Each row of the list holds `level`,
`power`, `en`, `hit_rate` and `crit_rate`. The four values are
percentages of the base value at that weapon level.

The weapon list endpoint holds no terrain restriction. The address
`/ggetapi/en/unit/{id}` gives a second form of the same weapon, and
that form holds the field `weapon_capability`. The three rows of the
capability table are the source of the terrain divisor of formula
eight (`docs/reference/combat-formulas.md`). The crawler does not
fetch the capability table: no public address for it was found on
2026-08-22.

The same second form holds `map_weapon_can_use_after_move`,
`map_weapon_shooting_range` and `map_weapon_effect_range`.

## The stage row

| Group | Fields |
|---|---|
| Identity | `id`, `name`, `icon`, `stage_type`, `stage_category` |
| Terrain | `is_space`, `is_atmospheric`, `is_ground`, `is_surface`, `is_underwater`, `sortie_terrain`, `stage_terrain` |
| Cost | `cp`, `ap`, `secret_cp` |
| Rewards | `drop_set`, `drop_reward`, `first_reward`, `first_pickup_reward`, `secret_clear_reward`, `secret_clear_pickup`, `secret_clear_drop` |
| Other | `stage_condition_set`, `has_guest` |
| Always null here | `drop`, `reward`, `first_reward_set`, `first_pickup`, `capturable`, `condition`, `map` |

`name` is empty on 1617 of the 2104 rows.

The five terrain flags are booleans. 1790 rows light no flag. 114
rows light one flag. 200 rows light two or more, and 128 of those
200 light all five. `sortie_terrain` and `stage_terrain` are
integer enums, and each one takes the values 0 to 5. The meaning of
the flags and of the two enums is not verified.

The stage row holds no map. It gives no width, no height, no
terrain of a cell, no deployment slot, no enemy list and no victory
condition.

## The formula chain

The formula tab of `/gget/formula` holds the damage chain in the
multiplier form of the datamine:

```
characterStatRatio = Max(0, attackerCharacterAtk - defenderCharacterDef) / 5000
unitStatRatio = Max(0, RoundUp((attackerUnitAtk / 10.0) - (defenderUnitDef / 10.0))) / 5000
characterSigmoidAdjustment = 1.0 / (Exp((250 * (defenderCharacterDef - attackerCharacterAtk)) / 100000.0) + 1.0)
unitSigmoidAdjustment = 1.0 / (Exp((25 * (defenderUnitDef - attackerUnitAtk)) / 100000.0) + 1.0)
baseDamage = RoundUp((characterStatRatio + unitStatRatio + characterSigmoidAdjustment + unitSigmoidAdjustment) * weaponPower)
attackerCombinedStat = RoundUp((attackerUnitAtk + 2 * attackerCharacterAtk) / 10.0)
targetCombinedStat = RoundUp((defenderUnitDef + 2 * defenderCharacterDef) / 10.0)
offenseCorrectionExponent = ((5000 - attackerCombinedStat) * 30) / 100000.0
defenseCorrectionExponent = ((5000 - targetCombinedStat) * 3) / 100000.0
offenseDamageComponent = (10000 / 100.0) / (Exp(offenseCorrectionExponent) + 1.0)
defenseMitigationComponent = (-4000 / 100.0) / (Exp(defenseCorrectionExponent) + 1.0)
damageCorrection = (offenseDamageComponent + defenseMitigationComponent) * baseDamage
battleDamage = RoundUp((baseDamage + damageCorrection) * terrainCorrection)
totalDamageMultiplierPercent = sumAttackerDamageDealtPercent + sumAttackerCritDamageDealtPercent + attackerVigorDamageBonus - sumDefenderDamageTakenPercent
scaledDamage = RoundUp((totalDamageMultiplierPercent * battleDamage) / 100.0)
combinedDamage = (battleDamage + scaledDamage ) * defensiveCorrection
finalDamage = Max(0, RoundUp(combinedDamage * ((criticalCorrectionPercent + 100.0) / 100.0)))
```

The three notes of the tab:

- For weapon with multiple types, the formula uses the best
  corresponding stat.
- `attackerVigorDamageBonus`: high vigor 10%, max 20%, supercharged
  30%.
- `criticalCorrectionPercent`: mid vigor 10%, high and max 20%,
  supercharged 30%.

The chain agrees with `docs/reference/combat-formulas.md` at the
constants. `offenseDamageComponent` divides 10000 by 100 and gives
the 100 of formula six. `defenseMitigationComponent` divides -4000
by 100 and gives the -40 of formula seven.

Two statements differ from that document:

- This page multiplies `battleDamage` by `terrainCorrection`.
  Formula eight of that document divides by the terrain correction.
  Whether the two names hold the same value is not verified.
- This page rounds up at seven steps. That document writes no
  rounding.

## What the crawler stores

One run writes five files into `data/datamine/<stamp>/`:

| File | Content |
|---|---|
| `unit.json` | The unit payload, written again |
| `weapon.json` | The weapon payload, written again |
| `stage.json` | The stage payload, written again |
| `formula.json` | The formula lines and the notes, read from the page |
| `manifest.json` | The stamp, the crawled address, the address of each file, the row counts, the byte count and the SHA-256 |

"Written again" means this: the crawler decodes the payload and
writes it a second time. It changes no value. It sorts every object
key, it writes two-space indent, and it keeps the row order of the
source. The stored bytes are therefore not the received bytes. A
comparison against a raw fetch must decode first.

The crawler writes no timestamp into the store. Two runs at one
stamp therefore give the same bytes, and a byte compare answers the
drift question. The crawler prints the start time to stdout
instead.

The crawler reads the stamp a second time, after the four payloads.
A new stamp at that moment stops the run, because the four payloads
can then hold two versions.

A run at a stamp that already has a directory overwrites the five
files. It removes no other file of that directory. Give `--out` a
second root to keep both dumps for a comparison.

`data/` is in `.gitignore`. The store is not in the repository.

## Field review

This section answers the fourth acceptance criterion of issue #74.
It compares the three data sources with the section "Types" of
`docs/spec/battle-engine-protocol.md` and with
`docs/spec/intel-data-spec.md`.

### The unit row against the engine unit

The engine keeps two levels apart: the final panel (`battle.Unit`)
and the base data (`battle.Mech` and `battle.Pilot`).

Agreements:

| Datamine | Engine | Note |
|---|---|---|
| `stats.hp` | `mech_hp` | Base data |
| `stats.en` | `mech_en` | Base data |
| `stats.movement` | `mech_move_range` | Base data |
| `stats.attack` | `unit_attack` | |
| `stats.defense` | `unit_defense` | |
| `stats.mobility` | `mobility` | |
| `defend`, `evade` | The stance set of the reaction | Both true everywhere, so they gate nothing today |
| `mechanism` row "Shield Defense" | `has_shield` | Free text on one side, a boolean on the other |

Divergences:

- The datamine holds four value groups for one mech. The engine
  holds one number for each field. Which group feeds the final
  panel is an open question.
- The datamine unit row holds no pilot. `pilot_attack`,
  `pilot_defense` and `reaction` have no field here. The address
  `/ggetapi/en/character` holds the pilots, and issue #74 does not
  crawl it. This split agrees with issue #72, which separates the
  mech, the pilot and the unit.
- The datamine holds `terrain`, a per-terrain adaptability value.
  The engine holds no adaptability field. The engine models terrain
  in the state (`terrain`, `terrain_cells`) and in the weapon
  (`terrain_damage`, `unusable_in`) alone. Issue #76 covers the
  gap.
- The engine fields `size`, `chance_steps_max`,
  `support_defend_charges_max`, `support_attack_charges_max`,
  `attack_shield` and `interception_reduction` have no numeric
  column in the datamine. The ability rows and the mechanism rows
  carry the same facts as English text.
- The datamine fields `rarity`, `role`, `series`, `tags` and
  `acquisition` have no engine field. They belong to team
  development, not to the board.

### The weapon row against the engine weapon

Agreements:

| Datamine | Engine |
|---|---|
| `name` | `name` |
| `power` | `power` |
| `range_min` | `range_min` |
| `range_max` | `range_max` |
| `en` | `en_cost` |
| `hit_rate` | `accuracy` |

The binding of `hit_rate` to `accuracy` is already in
`docs/reference/terminology-map.md`.

Divergences:

- `critical_rate` has no engine field. The engine holds the
  critical multiplier, not the rate at which a critical happens.
  `docs/spec/intel-data-spec.md` already marks the panel column
  "爆擊%" as outside the specification.
- The engine field `map_weapon` has no boolean here. The list
  endpoint gives `type` and `work_type`, and their meaning is not
  verified. The unit detail form gives three `map_weapon_` fields.
- The engine field `usable_after_move` matches
  `map_weapon_can_use_after_move` of the unit detail form. The
  datamine therefore carries the permission for each weapon, and
  not for a kind of weapon. This agrees with the user ruling of
  2026-08-20.
- The engine field `blast` has no numeric column. The unit detail
  form gives `map_weapon_effect_range` as a string.
- The engine field `can_counter` has no field in the datamine.
- The engine fields `debuff_kind` and `debuff_magnitude` have no
  column. The unit detail form gives the id `weapon_effect`, and
  the address `/ggetapi/en/weapon/effect` holds 388 rows of effect
  text.
- The engine fields `terrain_damage` and `unusable_in` map to
  `weapon_capability` of the unit detail form. That table is not in
  the four crawled sources.
- The datamine `ammo` is 1 on 4668 of the 4785 rows.
  `docs/reference/combat-formulas.md` records a user recollection
  that only map weapons carry an ammunition count, and the Go
  engine reads energy alone. The two statements do not agree. The
  meaning of `ammo` is not verified.
- The datamine `growth` scales the power, the energy, the hit rate
  and the critical rate by weapon level. The engine holds no weapon
  level.

### The stage row against the specs

The engine carries no stage type. It carries the board, the terrain
of the map, and the event table.

Agreements:

- The five terrain kinds of the datamine (`space`, `atmospheric`,
  `ground`, `surface`, `underwater`) are the five kinds of the
  section "Terrain" of the engine contract, in the same order.
- More than one kind on one stage is possible in both. 200 rows of
  the datamine light two or more flags, and the engine holds
  `terrain` plus `terrain_cells`.

Divergences:

- The datamine gives no map. It cannot fill the engine field
  `board`, and it cannot fill `terrain_cells`.
- The datamine gives no victory condition. `condition` and
  `capturable` are null on all 2104 rows. The stage information
  screen stays the only channel for the victory condition.
- The datamine gives no reinforcement event. The engine field
  `StageEvent` has no source here.
- `docs/spec/intel-data-spec.md` asks for one terrain correction
  for each stage. The datamine gives `stage_terrain`, one enum for
  each stage, next to the five flags. The two do not answer the
  same question: the terrain correction of formula eight reads the
  cell of the target, and the datamine gives no cell.

### The three sources against the intel data spec

| Group of the intel spec | Datamine cover |
|---|---|
| Values panel | Full. `stats` holds every field of the group |
| Pilot | None. The pilots are at `/ggetapi/en/character` |
| Weapon, for each weapon | Most. Name, power, band, energy and hit rate agree. The category, the ammunition and the debuff text need a second address |
| Ability text | Full, as English text in `abilities` and `mechanism` |
| Charge counts | None as a number. The text of an ability row states them |
| Board state | None, and it must stay none. Position, current HP and the acted flag come from the screen |
| Support crew | None. The crew is at `/ggetapi/en/supporter` |

The intel spec records a sampling result of 2026-07-30: the mech
panel of the game has no reaction column. The datamine agrees. The
unit row holds no reaction value.

## Not verified

- The licence of the site and its rate limit.
- The map from the values 1, 2 and 3 of `terrain` to the symbols ○,
  △ and －.
- The meaning of the weapon enums `type`, `work_type`,
  `attack_attr` and `weapon_attr`.
- The meaning of `ammo` on a weapon that is not a map weapon.
- The meaning of the five terrain flags of a stage, and of the
  enums `sortie_terrain` and `stage_terrain`.
- Which of the four value groups of `stats` the game shows on the
  panel.
- Whether any value of the datamine agrees with the device for the
  same unit. No comparison was made.
- How a game patch invalidates a dump under an older stamp.
