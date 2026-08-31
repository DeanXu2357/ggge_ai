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
  the crawler makes six requests and downloads about 71 MB.

## The data version stamp

`GET /ggetapi/version` gives the stamp:

```
{"version":"202608161248"}
```

The same value is in the payload of every rendered page, in the
field `remoteVersion`. The four data addresses carry no stamp of
their own.

The crawler names the dump directory with the stamp. A game patch
changes the stamp, so a new dump lands beside the old one.

## The five sources

The row counts come from a crawl on 2026-08-22, at the stamp
`202608161248`.

| Name | Address | Form | Rows |
|---|---|---|---|
| unit | `/ggetapi/en/unit` | JSON array | 1226 |
| weapon | `/ggetapi/en/weapon` | JSON object | 4785 weapons, 1342 units |
| stage | `/ggetapi/en/stage` | JSON array | 2104 |
| character | `/ggetapi/en/character` | JSON array | 583 |
| formula | `/gget/formula` | HTML page | 17 formula lines, 3 notes |

The formula address is a rendered page, not an API. The page also
embeds prefetched API payloads, and the server writes those in the
order in which they complete. Two fetches of the page therefore give
different bytes. The formula tab of the page is static markup, and
the crawler stores that tab alone.

The four API addresses give the same bytes for two fetches at the
same stamp. This was measured on 2026-08-22 for `unit` and `stage`,
and on 2026-08-28 for `character`.

The unit table and the weapon table do not hold the same set of
units. The weapon table names 1342 owners. The unit table holds
1226 rows, and every one of them owns weapons. 116 owners of the
weapon table are absent from the unit table. The sidecar object
`units` of the weapon endpoint holds one row for each of the 1342
owners.

## The per-id addresses

Each list address has a per-id form. A review on 2026-08-28, at the
same stamp, read these addresses. The crawler does not fetch them.

| Address | Form | Rows |
|---|---|---|
| `/ggetapi/en/unit/{id}` | JSON object | One unit, with its weapons in full |
| `/ggetapi/en/character/{id}` | JSON object | One pilot |
| `/ggetapi/en/supporter` | JSON array | 86 support crews |
| `/ggetapi/en/supporter/{id}` | JSON object | One support crew |

The datamine names a pilot "character" and a support crew
"supporter". This document uses the project terms.

The per-id unit form holds every field of the list row, and it
fills the fields that the list row leaves null: `weapons`, `get`,
`gacha`, `transform_to` and `mechanism`. Section "The unit detail
form" records the filled fields.

The per-id pilot form holds every field of the list row. It fills
`get`, `gc` and `series_set[].series`. The skills and the abilities
are complete in the list row already.

The per-id support crew form holds the same fields as the list row.

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
`underwater`. Each value is 1, 2 or 3. The map to the symbols of
the game is:

| Value | Symbol |
|---|---|
| 3 | ○ |
| 2 | △ |
| 1 | － |

Verified on 2026-08-28 on two units. The rendered page of the site
shows the symbols under "地形適性". Gundam (EX), id 1001000150,
shows ○ － ○ － △ for space, atmospheric, ground, surface and
underwater, and its row holds 3, 1, 3, 1, 2. Zeong (EX), id
1001003050, shows ○ △ － － －, and its row holds 3, 2, 1, 1, 1.

`rarity` is 1 to 5. The map to the rarity names of the game:

| Value | Name | Units | Pilots |
|---|---|---|---|
| 1 | N | 101 | 0 |
| 2 | R | 309 | 51 |
| 3 | SR | 359 | 320 |
| 4 | SSR | 345 | 128 |
| 5 | UR | 112 | 84 |

Verified on 2026-08-28. The rarity filter of the pilot list page
shows the five names with the counts 51, 320, 128 and 84, and the
counts of the values 2 to 5 in the pilot rows are the same four
numbers. The unit counts are the counts of the values in the unit
rows.

`role` is 1 to 3. The map to the unit role names of the game:

| Value | Name | Units | Pilots |
|---|---|---|---|
| 1 | 攻擊型 | 488 | 227 |
| 2 | 耐久型 | 328 | 163 |
| 3 | 支援型 | 410 | 193 |

Verified on 2026-08-28. The type filter of the unit list page shows
the three names with the counts 488, 328 and 410, and the counts of
the values in the unit rows are the same three numbers. The same
enum is on the pilot row. The pilot ability text also names the
role: the ability "Support Defense LV 4" of Amuro Ray, id
1001000100, carries the condition `unit_role: "2"`, and the page
renders it as "耐久型".

Among the 112 UR units, 43 are 攻擊型, 26 are 耐久型 and 43 are
支援型.

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

`type` takes three values. On the 15 unit detail forms read on
2026-08-28, every map weapon has `type` 3, and no other weapon has
it. The Ex weapon of Gundam (EX), "Beam Saber EX", has `type` 2.
`type` 1 is the rest. The map 1 normal, 2 Ex, 3 map weapon is a
hypothesis from that sample.

`weapon_attr` is the damage attribute that the site writes in angle
brackets after the weapon name. Verified on 2026-08-28 on the
rendered pages of Gundam (EX) and Zeong (EX):

| Value | Text | Example |
|---|---|---|
| 1 | 物理 | Hyper Bazooka |
| 2 | 光束 | Beam Rifle |
| 3 | 特殊 | All-Range Attack |
| 4 | 光束、物理 | Beam Saber EX |
| 6 | 光束、特殊 | All-Range Attack EX |

Value 5 was not seen on a page. Its weapons in the sample, "Shotgun
EX" and "Heat Saber EX", make 物理、特殊 the hypothesis.

`attack_attr` is the weapon category: which pilot value the damage
reads. The user ruled on 2026-08-28 that the three categories are
格鬥, 射擊 and 覺醒, and that a weapon with more than one reads the
highest of those pilot values. The site draws the categories as
badges before the attribute text. Seen on the Zeong (EX) page: a
yellow badge on "5-Barrel Arm Mega Particle Cannon" (value 1), a
purple badge on "All-Range Attack" (value 3), and yellow, red and
purple on "All-Range Attack EX" (value 7). With Beam Saber at value
2 and Beam Rifle at value 1, the map is:

| Value | Categories | Pilot value |
|---|---|---|
| 1 | 射擊 | `ranged` |
| 2 | 格鬥 | `melee` |
| 3 | 覺醒 | `awaken` |
| 4 | 射擊、格鬥 | the higher of `ranged` and `melee` |
| 7 | 射擊、格鬥、覺醒 | the highest of the three |

Value 4 was seen on the Blue Destiny Unit-1 (EX) page: yellow and
red badges on "EXAM System". Value 5 ("Wired Claw Arm") is a pair
with 覺醒 by this reading; which pair is not verified. The engine
field is `categories` of the weapon payload. `work_type`
(five values) is not verified.

`ammo` is the ammunition count. The user ruled on 2026-08-28 that a
map weapon needs both the energy and one round: "必須有足夠的 en 並且
還有剩餘彈數才能使用". Of the 226 map weapons (`type` 3), 131 hold
`ammo` 1, 65 hold 2, 27 hold 3, 2 hold 4 and 1 holds 9. Whether
`ammo` 1 on the 4459 normal weapons means one round or no limit is
not verified.

`growth` holds the list `wsc`. Each row of the list holds `level`,
`power`, `en`, `hit_rate` and `crit_rate`. The four values are
percentages of the base value at that weapon level.

The weapon list endpoint holds no terrain restriction. The unit
detail form gives a second form of the same weapon, and that form
holds the id `weapon_capability` and the row `capability` it names.
Section "The unit detail form" records the row. The crawler does
not fetch the capability table: no public address for the table
itself was found on 2026-08-22.

## The unit detail form

The address `/ggetapi/en/unit/{id}` gives one unit with these
fields filled. The facts come from 15 UR units read on 2026-08-28.

`weapons` holds one row for each weapon of the unit. Each row holds
`weapon`, and `weapon` holds `weapon_status` and `capability`.

| Object | Fields |
|---|---|
| `weapon` | `id`, `name`, `type`, `work_type`, `attack_attr`, `weapon_attr`, `tension`, `main_weapon`, `weapon_capability`, `weapon_effect`, `ex_short_weapon`, `map_weapon_desc`, `map_weapon_range`, `map_weapon_trait` |
| `weapon_status` | `range_min`, `range_max`, `power`, `en`, `hit_rate`, `critical_rate`, `map_weapon_shooting_range`, `map_weapon_effect_range`, `map_weapon_can_use_after_move`, `weapon_level_growth`, `growth` |
| `capability` | `in_space`, `in_ground`, `in_atmospheric`, `in_underwater`, `in_surface`, `desc`, `damage_space`, `damage_ground`, `damage_atmospheric`, `damage_underwater`, `damage_surface`, `damage_desc` |

The capability rows seen in the sample:

| `weapon_capability` | `in_underwater` | `damage_underwater` | Text |
|---|---|---|---|
| 1 | true | 100 | None |
| 2 | true | 50 | "Damage to underwater enemies is halved" |
| 4 | false | 50 | "Cannot be used underwater" and "Damage to underwater enemies is halved" |

Every other `in_` flag is true and every other `damage_` value is
100 on all three rows. Row 3 was not seen in the sample.

A map weapon carries two cell lists, each one a string of `(x,y)`
pairs. `map_weapon_effect_range` is the set of cells the weapon
strikes. `map_weapon_shooting_range` is empty on six of the ten map
weapons of the sample, and it holds 4 to 48 cells on the other
four. `map_weapon_range` is 1 to 4.

The user ruled on 2026-08-28 that a map weapon fires in one of two
modes: a fixed shape turned to one of four directions, or an aim
cell chosen inside the allowed range with the area applied around
it. The sample fits that ruling as a hypothesis: a weapon with an
empty shooting list is the directional mode, and its effect list is
the shape drawn facing +y; a weapon with a shooting list is the aimed
mode, its shooting list is the set of aim cells relative to the
unit, and its effect list is the area relative to the aim cell. On
that reading `map_weapon_range` 1 is an area around the unit, 2 is
the aimed mode, 3 is the directional mode, and 4 is a line
("Detonation Cord": four aim cells in one line, twelve effect
cells). `map_weapon_trait` 2 is the supply kind, which the user
confirmed heals allies in the area. None of this is verified on the
device. The sample:

| Unit | Weapon | `map_weapon_range` | `map_weapon_trait` | Effect cells | Shooting cells |
|---|---|---|---|---|---|
| Big-Rang (EX) | Supply Function | 1 | 2 | 40 | 0 |
| Atlas Gundam (EX) | Medusa's Arrow | 2 | 1 | 1 | 40 |
| Gundam GP02A (EX) | Atomic Bazooka | 2 | 1 | 25 | 16 |
| Nightingale (EX) | Funnels | 2 | 1 | 13 | 48 |
| Kampfer (EX) | Barrage | 3 | 1 | 16 | 0 |
| Neue Ziel (EX) | Deflection Type Mega Particle Cannon | 3 | 1 | 16 | 0 |
| Full Armor ZZ Gundam (EX) | High Mega Cannon | 3 | 1 | 18 | 0 |
| Nightingale (EX) | Large Mega Beam Rifle (Focused) | 3 | 1 | 18 | 0 |
| Gundam GP03 (EX) | Detonation Cord | 4 | 1 | 12 | 4 |

"Supply Function" has `power` 0 and `map_weapon_trait` 2. Every
other map weapon of the sample has `map_weapon_trait` 1.
`map_weapon_can_use_after_move` is false on all ten.

`abilities` holds one row for each mech ability. Each row holds
`ability`, and `ability` holds `detail` (`name`, `desc`, `rarity`,
`is_stackable`, `stack_limit`) and `traits`. Each trait holds
`trait_type`, `trait_value`, `desc`, `action_timing`, `tlimit`, an
`active_condition` and a `target_condition`. A condition holds
`target` (`Owner`, `AttackTarget`, `ActiveAttacker`, `SameGroup`
seen), `unit_role`, `unit_tags`, `unit_series`, `map_battle_action`
(`SupportDefense` seen), HP and EN thresholds, a distance band, a
turn number and two flags, `is_in_chance_step` and
`is_in_one_on_one`. The ability text of the list row is the `desc`
of these traits.

`gacha.bonus.character` holds the pilot that the game gives with
the unit. On every one of the 15 UR units, that pilot is UR and has
the role of the unit. This is the only link from a unit to a pilot
in the datamine: the pilot row holds no unit id, and the per-id
pilot form holds the reverse link in `gc.gacha.unit`.

`transform_to` holds the transformation targets. Gundam GP03 (EX)
holds one; the other 14 units hold none. `get` holds the
acquisition list, 80 gacha rows for Gundam (EX).

## The pilot row

The address `/ggetapi/en/character` gives 583 rows.

| Group | Fields |
|---|---|
| Identity | `id`, `main_character_id`, `name`, `sort_name`, `abbreviation`, `desc`, `icon`, `is_playable` |
| Catalogue | `rarity`, `role`, `series_set_id`, `series_set`, `tags`, `acquisition`, `schedule_id` |
| Values | `stats` |
| Skills | `skills` |
| Abilities | `abilities` |
| Voice | `acquisition_voice`, `killed_quote`, `voice_resource_id` |
| Null in the list | `get`, `gc`, `schedule`, `link` |

`rarity` and `role` take the same enums as the unit row. `is_playable`
is true on 582 rows. One name has many rows: "Amuro Ray" has eight,
with rarity 3 to 5 and every role.

The object `stats` holds 20 fields. Five values repeat in four
groups: `ranged`, `melee`, `defense`, `reaction` and `awaken`. The
four groups are the plain group, the `max_` group, the `sp_` group
and the `sp_max_` group, as on the unit row. The pilot holds two
attack values, ranged and melee, and no single attack value. The
formula page states that a weapon with more than one type reads the
best stat.

`skills` holds two rows on 498 pilots and three rows on 84. Each
row holds `sort`, `level` (the pilot level that unlocks the skill),
`character_skill_id`, `sp_character_skill_id` and `skill`. `skill`
is null on 370 rows of the 583 pilots. A filled `skill` holds
`name`, `desc`, `sp` (the cost, 3, 5, 7 or 10), `duration` (1 on
all 878 filled rows), `is_auto_usage`, `auto_usage_threshold`,
`auto_usage_priority` and `trait_set`. `trait_set` holds one trait
on 850 rows and two on 28. A trait holds `trait_type`,
`trait_value`, `name`, `desc`, `target_tag_id` and
`target_unit_role`.

The `trait_type` values of the 878 filled pilot skills, with the
skill names they carry:

| `trait_type` | Rows | Names | Text of one row |
|---|---|---|---|
| 1 | 32 | HP Repair Lite, HP Repair, HP Repair (Range) | Restore HP by 10%. |
| 2 | 24 | EN Charge, EN Charge Lite | Restore EN by 40%. |
| 3 | 108 | Boost Range | During the next fight after activating the effect, increase max range of own weapons by 1. |
| 4 | 55 | MP Up, MP Up (Range) | Increase MP by 5. |
| 5 | 25 | Increased ACC | Increases Accuracy by 15% [1 turn]. |
| 6 | 25 | Increased EVA | Increase Evasion by 15% [1 turn]. |
| 7 | 139 | High Speed | During the next movement after activating the effect, increase MOV by 1. |
| 8 | 129 | Attack Burst, Attack Burst (Range) | Increase damage dealt to enemies by 10% [1 turn(s)]. |
| 9 | 43 | Ranged Boost | Increase Ranged by 15% [1 turn]. |
| 10 | 37 | Melee Boost | Increase Melee by 15% [1 turn]. |
| 11 | 12 | Awaken Boost | Increase Awaken by 20% [1 turn]. |
| 12 | 47 | Boost Critical | Increase Critical Rate by 20% [1 turn]. |
| 13 | 62 | Lock On | During the next fight after activating the effect, increase Accuracy by 100%. |
| 14 | 46 | Sway | During the next fight after activating the effect, increase Evasion by 100%. |
| 15 | 48 | Save EN | Reduce weapons EN consumption by 5% [1 turn(s)]. |
| 17 | 66 | Force Guard, Force Guard (Range) | Reduce damage taken by 20% [1 turn(s)]. |
| 25 | 2 | Chance Step Count Increase | Chance Step +1 time. |
| 26 | 2 | Support Attack Count Increase | Support Attack / Counter Support +1 time(s). |
| 29 | 2 | Zero Ammo | Can be used once without consuming MAP Weapon's remaining ammo. |
| 30 | 2 | Zero EN | Can be used once without consuming EN from own weapon. |

`duration` does not separate "1 turn", "the next fight" and "the
next movement". The text separates them. The `trait_type` enum of a
pilot skill and the `trait_type` enum of an ability are two
different enums: `trait_type` 17 is "reduce damage taken" in both,
but `trait_type` 9 is "Ranged Boost" on a skill and "DEF up on
Support Defense" on an ability.

`abilities` holds four rows on the UR pilots seen. Each row holds
`sort`, `level`, `ability_id`, `sp_ability_id` and `ability`, in
the same form as the mech ability of the unit detail form. The
conditions carry the pairing rule of the game: an ability of a
pilot can require a unit role (`unit_role`), a unit tag
(`unit_tags`) or a series (`unit_series`) of the mech the pilot
rides, and it can require a tag of the enemy (`target`
`AttackTarget`).

## The support crew row

The address `/ggetapi/en/supporter` gives 86 rows: 47 UR, 31 SSR
and 8 SR.

| Group | Fields |
|---|---|
| Identity | `id`, `name`, `sort_name`, `desc`, `icon` |
| Catalogue | `rarity`, `acquisition_route`, `obtained_word`, `limit_break_item_id`, `schedule_id` |
| Values | `max_hp_addition_value`, `max_attack_addition_value` |
| Skills | `lb_skills` |

`lb_skills` holds one row for each limit-break step, 0 to 3. Each
row holds `leader_skill` and `active_skill`.

`leader_skill` is a passive. Its `skills[].trait_condition` names
the units it covers, with `target` `SameGroup` and, for example,
`unit_series` 10 (Mobile Suit Gundam). Its `trait_content.trait_value`
holds `trait_type` and `value`; the value grows with the step (25,
30, 33, 36 for "Bright Noa & White Base", id 1001000150).

`active_skill` is the support crew skill of the terminology map. It
holds `name`, `desc`, `range_type`, `effect_range` (a string of
`(x,y)` pairs, 41 cells for the sample), `is_auto_usage`,
`auto_usage_passed_turn`, `auto_usage_threshold`,
`auto_usage_target_threshold`, `auto_usage_priority` and
`effect_scale_rate_percent`. The sample's skill is "EN Restoration":
"Allies in range: Restore EN by 50%". The four steps hold the same
active skill.

## The sample store

The directory `docs/reference/datamine-samples/<stamp>/` holds a
sample of the per-id forms, read on 2026-08-28 at the stamp
`202608161248`. It is in the repository, unlike the datamine store.

The sample holds ten UR units with the pilot of each, and one
support crew. The file `index.json` lists them. The ten units cover
the three unit roles, ten map weapons, two weapons that cannot fire
underwater, and one transformation.

| Role | Units |
|---|---|
| 攻擊型 | Zeong (EX), Kampfer (EX), Atlas Gundam (EX), Neue Ziel (EX) |
| 耐久型 | Gundam (EX), Gouf Custom (EX), Gundam GP03 (EX) |
| 支援型 | Big-Rang (EX), Nu Gundam (EX), Nightingale (EX) |

The support crew is "Bright Noa & White Base", id 1001000150.

Each file is the per-id payload, sorted by key, with the field `get`
(the acquisition list) removed. No other value is changed.

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

## The stage detail form

The address `/ggetapi/en/stage/{id}` gives one stage with two fields
filled that the list row leaves null: `condition` and `map`. The
facts come from one stage read on 2026-08-28: id 900103, "The
Serpent That Vanished at Loum", `stage_type` 5.

`condition` holds one row for each condition text of the stage
information screen: `category`, `sort`, `text` and `unit_id`. The
sample holds a `category` 1 row, "Defeat all enemy units.", and a
`category` 3 row, "All of your units defeated. Guest force
Aleksandro Hemme defeated.". The map from `category` to win and loss
is a hypothesis from these two rows.

`map` holds `map_id`, `stage_difficulty` and `npcs`. It holds no
width, no height, no cell, no terrain of a cell and no deploy slot.
`map_id` names a map that no address of this review expands.

`npcs` holds one row for each unit the stage places that is not the
player's. The sample holds 14. Each row holds the cell (`x`, `y`),
`battle_side`, `direction`, `step_order`, `is_initially_placed`,
`is_initially_on_warship`, `unit_standby`, `npc_unique_name`,
`is_story_event_boss`, `cannot_capture` and `npc`. `npc` holds
`unit_id`, `level`, `hp`, `en`, `attack`, `defense`, `mobility`,
`movement`, the ability set, the weapon set and the unit row.

In the sample, 13 rows have `is_initially_placed` true and one has
it false: a Magellan named "magellan" at (17, 8), `step_order` 10.
That row is the shape of a reinforcement. The row with
`battle_side` 1 is the guest unit that the loss condition names;
the other 13 rows have `battle_side` 2. The values of
`battle_side`, `direction` and `step_order` are not verified beyond
this reading.

The sample store holds this stage under `stage/`.

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

One run writes six files into `data/datamine/<stamp>/`:

| File | Content |
|---|---|
| `unit.json` | The unit payload, written again |
| `weapon.json` | The weapon payload, written again |
| `stage.json` | The stage payload, written again |
| `character.json` | The pilot payload, written again |
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

The crawler reads the stamp a second time, after the five payloads.
A new stamp at that moment stops the run, because the five payloads
can then hold two versions.

A run at a stamp that already has a directory overwrites the six
files. It removes no other file of that directory. Give `--out` a
second root to keep both dumps for a comparison.

`data/` is in `.gitignore`. The store is not in the repository.

## Field review

This section answers the fourth acceptance criterion of issue #74.
It compares the three data sources with the section "Types" of
`docs/spec/battle-engine-protocol.md` and with
`docs/spec/intel-data-spec.md`.

### The unit row against the engine unit

The engine keeps two levels apart: the final panel (`board.Unit`)
and the base data (`board.Mech` and `board.Pilot`).

Agreements:

| Datamine | Engine | Note |
|---|---|---|
| `stats.hp` | `mech_hp` | Base data |
| `stats.en` | `mech_en` | Base data |
| `stats.movement` | `mech_move_range` | Base data |
| `stats.attack` | `unit_attack` | |
| `stats.defense` | `unit_defense` | |
| `stats.mobility` | `mobility` | |
| `defend`, `evade` | The stance set of the response attack | Both true everywhere, so they gate nothing today |
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
- The engine field `can_counter` had no field in the datamine.
  The engine retired the field on 2026-08-30 (issue #88): a
  counter fires under the rule of an attack.
- The engine fields `debuff_kind` and `debuff_magnitude` have no
  column. The unit detail form gives the id `weapon_effect`, and
  the address `/ggetapi/en/weapon/effect` holds 388 rows of effect
  text.
- The datamine `capability` row of the unit detail form carries the
  two weapon abilities of issue #80: `damage_underwater` 50 is the
  halved damage, and `in_underwater` false is the fire restriction.
  That table is not in the four crawled sources.
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
- The stage list row gives no reinforcement event. The stage
  detail form gives the placed units with `is_initially_placed`
  and `step_order`, and the condition text. Section "The stage
  detail form" records it. Which of them fills the engine field
  `StageEvent` is not decided.
- `docs/spec/intel-data-spec.md` asks for one terrain correction
  for each stage. The datamine gives `stage_terrain`, one enum for
  each stage, next to the five flags. The two do not answer the
  same question: the terrain correction of formula eight reads the
  cell of the target, and the datamine gives no cell.

### The UR selection

A UR unit is a unit row with `rarity` 5: 112 rows at the stamp
`202608161248`. A UR pilot is a pilot row with `rarity` 5: 84
rows. The two selections are independent. The user ruled on
2026-08-28 that a pilot and a mech pair freely, and that
`gacha.bonus.character` of the unit detail form is the pilot
bundled with a pull, not a link. No stored selection exists; a
reader applies the one filter to each table.

### The UR values against the engine contract

The contract of issue #84 (`docs/spec/battle-engine-protocol.md`,
section "The unit, the pilot and the mech") holds the pilot and
the mech as data on the unit. This table maps every value of a UR
mech row and of a UR pilot row to that contract.

Mech, from the unit row and the unit detail form:

| Datamine | Engine | Note |
|---|---|---|
| `stats.hp` | `mech.hp` | Which of the four value groups feeds it: issue #77 |
| `stats.en` | `mech.en` | Same |
| `stats.attack` | `mech.attack` | Same |
| `stats.defense` | `mech.defense` | Same |
| `stats.mobility` | `mech.mobility` | Same |
| `stats.movement` | `mech.move_range` | Same |
| `weapons[].weapon` | `mech.weapons[]` | The weapon table below |
| `terrain` | none | Issue #76 owns the adaptability field |
| `abilities`, `mechanism` | none | Text; the derivation of the maxima is issue #77, the shield is `has_shield` |
| `defend`, `evade` | none | True on every row |
| `rarity`, `role`, `series`, `series_set`, `tags`, `area`, `body_type`, `tr`, `acquisition`, `schedule_id`, `ult`, `mechanism_set`, `base_skill`, `ssp_config`, `transform_from`, `transform_to`, `get`, `gacha` | none | Team development, not the board |

Pilot, from the pilot row:

| Datamine | Engine | Note |
|---|---|---|
| `stats.ranged` | `pilot.ranged` | Value group: issue #77 |
| `stats.melee` | `pilot.melee` | Same |
| `stats.awaken` | `pilot.awaken` | Same |
| `stats.defense` | `pilot.defense` | Same |
| `stats.reaction` | `pilot.reaction` | Same |
| — | `pilot.sp` | No column. The device is the source |
| `skills` | none | Issue #81 owns the skill shape |
| `abilities` | none | Issue #72 owns the pairing conditions; issue #77 the value effects |
| `rarity`, `role`, `series_set`, `tags`, `acquisition`, the voice fields | none | Team development |

Weapon, from the unit detail form:

| Datamine | Engine |
|---|---|
| `attack_attr` | `categories`, by the table in section "The weapon row" |
| `capability` | Issue #80 |
| `map_weapon_*` | Issue #79 |
| the rest | Section "The weapon row against the engine weapon" |

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
- The meaning of the weapon enums `work_type`, `attack_attr` and
  `weapon_attr`, and the values 1 and 2 of `type`.
- The cell the offsets of `map_weapon_effect_range` and of
  `map_weapon_shooting_range` are relative to, and the meaning of
  `map_weapon_range` and `map_weapon_trait`.
- The rule that the rendered page of the site uses to show a panel
  value that is higher than `max_hp` of the row. Gundam (EX) shows
  HP 151599 at level 100 with three stars, and its row holds
  `max_hp` 94162.
- The meaning of `ammo` on a weapon that is not a map weapon.
- The meaning of the five terrain flags of a stage, and of the
  enums `sortie_terrain` and `stage_terrain`.
- Which of the four value groups of `stats` the game shows on the
  panel.
- Whether any value of the datamine agrees with the device for the
  same unit. No comparison was made.
- How a game patch invalidates a dump under an older stamp.
