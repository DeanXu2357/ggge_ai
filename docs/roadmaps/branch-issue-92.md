# Branch roadmap: issue 92, the game data in PostgreSQL

> Type: working—deleted at merge

Issue: #92. Branch: issue-92-game-data-db. Status: in-progress.

## Resume point

Session start 2026-09-03. Worktree added off 'dev' at 4eb94b0. The
user approved the plan on 2026-09-03 with three rulings (ledger
0903). Step 1 is eab33c9, step 2 is f9e5357, step 3 is 99c0332, step 4 is
4de5c2f, step 5 is 6f11e74, step 6 is a856b53, step 7 is the next
commit. Next: step 8, the document pass; then step 9, the review
artifact and '/finish-task'.

The fixture slices moved to the stamp 202609010310 in step 2. The
site published that stamp between the plan and the step, and one
slice must come from one stamp. The Zeong 1001003000 core releases
at that stamp: core 1 = weapon_change (adds 100100300090 "All-Range
Attack SSP", is_ssp true in the weapon table) and weapon_enhance
(+175 power on 100100300002); core 5 = terrain; core 10 =
weapon_effect and a second +175 on 100100300002; cores 15 and 20
hold no release. The release rows nest their payload under the key
of the kind ('weapon_change', 'weapon_enhance', 'status_up',
'terrain', 'weapon_effect', 'ability_change').

## Recon facts (2026-09-03)

- The crawler writes one whole-table file per endpoint into
  data/datamine/<stamp>/ (unit, weapon, stage, character, formula,
  manifest). Six requests, about 71 MB. No row files. A list unit row
  carries 'stats', 'abilities', 'ssp_config', 'ult'; 'weapons' is
  null. The weapon endpoint holds every weapon with 'unit_id' and
  'growth.wsc' rows (level, power, en, hit_rate, crit_rate in
  percent).
- The sample store docs/reference/datamine-samples/202608161248 is
  the per-id form (weapons embedded, growth as 'stats_change'). All
  ten units are UR: 'ssp_config' is null in every file. The fixture
  Zeong 1001003000 (rarity 4) is not in the store. The scratch copy
  of the unit list confirms its SSP HP: 229 + floor(5000 × (4577 −
  229) / 10000) = 2403.
- The engine wire form is 'battle.Mech' and 'battle.Pilot' in
  engine/battle/snapshot.go; 'def.Mech' and 'def.Pilot' carry no
  json tags. 'load' and 'init' both reach 'state.FromContract'
  (engine/battle/board/resolver.go:40). engine/go.mod has no require
  block. No Go test guards the import set.
- src/ggge_ai/engine/codec.py holds 'encode_mech' and 'encode_pilot'
  on 'dev'. No Python code sends 'init'; 'EngineSession' sends
  'load' with a scenario state.
- The unmerged branch issue-72-mech-pilot-unit holds
  scripts/build_catalog.py: full level, 'max_' × 14 // 10, weapon
  level 5, pilot 'sp' 0. It depends on 'Ability' types that 'dev'
  lacks. Its enum tables (attack_attr → categories, weapon_attr →
  attributes, value 5 as H) are the reusable part.
- The repository holds no database driver, container file, or
  migration tool. tests/fixtures/datamine holds recorded slices in
  the crawler form (2 units, 3 weapons, 3 pilots, 3 stages).

## Plan

### Layout

    compose.yaml                     postgres:16, db/user/password 'ggge', port 5432
    db/migrations/NNNN_<name>.up.sql / .down.sql   golang-migrate, plain SQL
    docs/how-to/game-data-db.md      start the container, run 'migrate', ingest, load
    docs/reference/growth-model.md   the formulas, the constant tables, the sources
    scripts/crawl_datamine.py        + 'supporter', 'supporter_growth'
    scripts/ingest_datamine.py       data/datamine/<stamp> → raw + normalized + constants
    scripts/load_holding.py          one holding → JSON payload on stdout
    src/ggge_ai/gamedata/growth.py   the constants and the pure formulas
    src/ggge_ai/gamedata/normalize.py  crawler tables → normalized rows (pure)
    src/ggge_ai/gamedata/store.py    psycopg: write rows, read one unit / pilot / crew
    src/ggge_ai/gamedata/holding.py  'Holding' and 'assemble' → state.Mech, state.Pilot
    tests/fixtures/datamine/         + Zeong 1001003050 and 1001003000 rows, their
                                     weapons, supporter.json, supporter_growth.json
    tests/fixtures/gamedata/         the payload goldens the Go test reads
    engine/battle/state/payload_test.go    decode a golden into def.Mech, def.Pilot
    engine/boundary_test.go          no database import under engine/

Connection: the environment variable 'GGGE_DATABASE_URL', default
postgresql://ggge:ggge@localhost:5432/ggge. Python driver:
psycopg 3 ('psycopg[binary]'). Nothing under engine/ changes except
the two test files.

### Schema

Every normalized table carries 'stamp' (the datamine version) in its
key, so two crawls coexist and a holding names the stamp it reads.

- datamine_raw(stamp, source_table, row_key, payload jsonb). The
  row key is the row id; the growth table has none, so its key is
  '<level>-<limit_break>'.
- Constants: level_curve(level, rate), limit_break_rate(step,
  rate_percent), rarity_level_cap(rarity, cap),
  supporter_growth(level, limit_break, correction_rate).
- tag(stamp, id, name): the tag names of the unit and pilot rows.
- unit(stamp, id, name, short_name, rarity, role, area, body_type,
  series, ult, acquisition, main_unit, defend, evade);
  unit_tag(stamp, unit_id, tag_id); unit_series(stamp, unit_id,
  series_id, sort); unit_stat(stamp, unit_id, stat, base, max,
  sp_base, sp_max) with stat in hp, en, attack, defense, mobility,
  movement; unit_terrain(stamp, unit_id, terrain, grade);
  unit_ability(stamp, unit_id, sort, ability_id, payload jsonb).
- unit_ssp_stat(stamp, unit_id, stat, base, max);
  unit_ssp_core(stamp, unit_id, level, core_id, release_point) keyed
  by the level, because the 'initial_release' is core level 0 and
  carries no core id of the same id space.
  unit_ssp_release(stamp, unit_id, core_level, sort_order, kind,
  target_id, payload jsonb)
  with kind from 'release_function_type_index': 1 weapon_enhance,
  3 status_up, 4 terrain, 5 weapon_change, 6 ability_change,
  7 weapon_effect (counted over the 1107 units of the scratch list:
  2152, 564, 250, 1141, 1 per unit, 1743).
- weapon(stamp, id, unit_id, name, type, work_type, attack_attr,
  weapon_attr, power, en, hit_rate, critical_rate, range_min,
  range_max, ammo, is_ssp); weapon_growth(stamp, weapon_id, level,
  power_rate, en_rate, hit_rate_rate, crit_rate_rate);
  weapon_trait(stamp, weapon_id, sort, level, trait_id, payload
  jsonb) from 'growth.wtc', the trait rows by weapon level (#72
  reads them; this issue stores them).
- pilot(stamp, id, name, rarity, role, main_pilot, is_playable);
  pilot_stat(stamp, pilot_id, stat, base, max, sp_base, sp_max);
  pilot_tag; pilot_series; pilot_ability(stamp, pilot_id, sort,
  ability_id, level, payload jsonb); pilot_skill(stamp, pilot_id,
  sort, skill_id, level, payload jsonb, null when the row's 'skill'
  is null).
- supporter(stamp, id, name, rarity, max_hp_addition,
  max_attack_addition); supporter_limit_break(stamp, supporter_id,
  step, leader_skill jsonb, active_skill jsonb).
- stage: raw only. Scope item 3 names no stage table.
- holding(id, stamp, unit_id, level, limit_break, mech_sp,
  mech_ssp, weapon_level, pilot_id, pilot_level, supporter_id,
  supporter_level, supporter_limit_break). A stub: the loader reads
  its inputs from the command line, not from this table.

The constant tables have one source, growth.py. The ingest script
writes them; the migration creates them empty. A test compares the
DB rows against growth.py when 'GGGE_DATABASE_URL' is set.

### Assembly (holding.py)

    group   = sp_ when mech_sp, else plain
    cap     = 100 when mech_sp or ult or rarity 5, else rarity_level_cap
    level   = min(holding.level, cap)
    value   = floor(base + (max − base) × level_curve[level] / 10000)
    value  += ssp_max + Σ status_up(stat)          when mech_ssp (one stage, user ruling
              2026-09-03: "直接計算 MAX"); status_up 'unit_status_type_index' 1 hp,
              2 en, 3 attack, 4 defense, 5 mobility, 6 movement (the site's code)
    value   = floor(value × limit_break_rate[stars])          hp, en, attack, defense, mobility
    stars   = 0 when ult
    move_range = movement of the group + status_up(6), not scaled
    pilot   = plain group, rarity cap, no stars; sp = 0 (the datamine holds no pool)
    weapon  = the unit's weapons with is_ssp false; when mech_ssp, apply every
              release of every core in core order: weapon_change replaces
              'before_weapon_id' with the 'after' weapon row (before 0 adds);
              weapon_enhance 1 adds to power after the growth rate, 2 lowers the EN
              cost, 3 adds ammo, 4 adds to range_max (the site's code)
              level = holding.weapon_level (default 5);
              power = floor(power × power_rate / 100) + ssp_power_add; en_cost =
              floor(en × en_rate / 100) − ssp_en_decrease; accuracy = hit_rate;
              categories from attack_attr (the #72 table, 5 = H);
              debuff_kind null, debuff_magnitude 0; usable_after_move true
    stored, not applied here: weapon_effect (a weapon trait) and ability_change
              (#72), terrain (no engine field)
    map weapons: not emitted in this issue (the affect-area shapes have no
              datamine mapping); 'map_weapons' is an empty list
    crew    = floor(max_addition × supporter_growth[level, step] / 10000); returned
              beside the payload, not in it (no wire field carries it)

The rule of the branch (user, 2026-09-03): the deliverable is the
store and the data model. A later crawl adds data through the ingest
alone; the loader, the payload shape, and the engine contract do not
change. The loader reads tables only; no unit id, weapon id, or
release kind is special-cased in code.

The payload is {"mech": encode_mech(...), "pilot": encode_pilot(...),
"crew": {"hp": n, "attack": n} | null}. The mech and the pilot are
the wire form of protocol 2.0, so 'battle.Mech' and 'battle.Pilot'
decode them without change.

### Steps, one commit each

1. Ledger entries 0902 and 0903 in docs/record/decisions.md; the
   terminology rows 'mech_sp', 'mech_ssp', 'holding', 'level curve';
   this plan in the roadmap.
2. Crawler: the two endpoints, the fixtures, the crawler test, the
   datamine-source.md sections (requests now eight; the support crew
   growth rows).
3. compose.yaml, the migrations, the how-to.
4. growth.py with its tests: the level table endpoints, the caps,
   the rates, the four worked examples.
5. normalize.py, store.py, ingest_datamine.py; the offline tests on
   the recorded slices; the DB round-trip test, skipped without
   'GGGE_DATABASE_URL'.
6. holding.py, load_holding.py, the goldens, the loader tests.
7. The two Go tests.
8. growth-model.md and the datamine-source.md cross-link.
9. Rework this file into the review artifact.

### Hypotheses carried (H)

- The SSP addition is 'ssp_max' plus the status_up sums (one stage,
  user ruling). The site shows the half point (2403 for Zeong HP);
  the full value 4577 replaces it in the acceptance criteria. Not
  checked on the device.
- The weapon level 5 is the full level, and the floored percent is
  the game's rounding (from the #72 branch, unmeasured).
- 'attack_attr' 5 = ranged and awaken; 6 = melee and awaken (the
  counts at the full table: 5 has 74 rows, 6 has 17).
- The pilot level cap follows the rarity table (the pilot row carries
  'rarity'; the site uses one cap table).
- The star rate applies to EN, ATK, DEF and MOB as to HP (the site
  does this; the device panel of 0829 confirmed HP only).

## Progress log

- 2026-09-03: worktree, this file, the state block on the issue,
  recon, the plan, the user's three rulings. Step 1 done: the ledger
  entries 0902 and 0903, six terminology rows.
- 2026-09-03: step 2 done. 'supporter' and 'supporter_growth' in
  'TABLE_PATHS'; the fixture slices re-recorded at 202609010310 with
  the two Zeong rows, their 16 weapons, one support crew and the 400
  growth rows; datamine-source.md counts nine requests, 95 MB, eight
  files, seven sources.
- 2026-09-03: step 3 done. compose.yaml (project name 'ggge_ai'),
  seven migration pairs, applied up, down -all, up against the local
  container with the golang-migrate CLI 4.19.1; the how-to. Schema
  additions over the plan: 'tag', 'pilot_series', 'weapon_trait';
  the SSP core key is (unit_id, level); 'holding' carries the
  support crew columns.
- 2026-09-03: step 4 done. 'gamedata/growth.py' holds the 100-entry
  level curve (equal to the site table), the caps, the limit break
  rates and the integer formulas; nine tests; 'gamedata' joined
  'NEW_MODULES'. 'docs/reference/growth-model.md' written early, from
  the site chunks, so that the module docstring points at a real file.
- 2026-09-03: step 5 done. 'normalize.py' (pure rows in the column
  order of the migrations), 'records.py', 'store.py' (psycopg 3,
  delete-then-insert per stamp, constants upserted),
  'scripts/ingest_datamine.py'; 15 offline tests, 6 store tests gated
  on 'GGGE_DATABASE_URL' (run: 6 passed); an ingest of the fixture
  slice against the container wrote 432 raw rows and the normalized
  tables, read back the Zeong, then the stamp was deleted. Correction:
  the Zeong 1001003000 HP groups are plain 8032 to 57831 and sp 8936
  to 64337 (growth-model.md example fixed; the earlier 53254 was
  wrong).
- 2026-09-03: step 6 done. 'holding.py' assembles a holding into the
  engine payload per growth-model.md; 'Catalog' in 'records.py' reads
  the same records from the rows without a database (a store test
  asserts equality with 'Store'); 'scripts/load_holding.py' with
  '--from-dump'; three goldens in 'tests/fixtures/gamedata/'; 22
  offline tests. Pinned: Zeong sp+ssp LV100 three stars HP 96479,
  Zeong (EX) 100478, '5-Barrel' power 4190, 'All-Range Attack SSP'
  power 5880 EN 54 range 2 to 5 awaken. Decisions: Ex weapons (type
  2) and map weapons (type 3) are stored, not emitted (no engine
  field; issue #72); 'attack_attr' 5 and 6 map to ranged+awaken and
  melee+awaken, and the pilot level cap follows the rarity table
  (hypotheses above).
- 2026-09-03: step 7 done. 'engine/battle/state/payload_test.go'
  decodes every golden with 'DisallowUnknownFields' on the mech and
  the pilot (the crew key is dropped by design), runs the contract
  conversion, and pins the Zeong SSP weapon and the Zeong (EX) HP;
  'engine/boundary_test.go' parses the 73 Go files of the engine and
  rejects every import outside the standard library and the module.
  'go vet ./...' and 'go test ./...' pass.
