# Branch roadmap: issue 92, the game data in PostgreSQL

> Type: working—deleted at merge

Issue: #92. Branch: issue-92-game-data-db. Status: in-progress.

## Resume point

Session start 2026-09-03. Worktree added off 'dev' at 4eb94b0. The
user approved the plan on 2026-09-03 with three rulings (ledger
0903). Next: step 2, the crawler.

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
- unit(stamp, id, name, short_name, rarity, role, area, body_type,
  series, ult, acquisition, main_unit, defend, evade);
  unit_tag(stamp, unit_id, tag_id); unit_series(stamp, unit_id,
  series_id); unit_stat(stamp, unit_id, stat, base, max, sp_base,
  sp_max) with stat in hp, en, attack, defense, mobility, movement;
  unit_terrain(stamp, unit_id, terrain, grade);
  unit_ability(stamp, unit_id, sort, ability_id, payload jsonb).
- unit_ssp_stat(stamp, unit_id, stat, base, max);
  unit_ssp_core(stamp, unit_id, core_id, level, release_point); the
  'initial_release' is core level 0.
  unit_ssp_release(stamp, core_id, sort_order, kind, payload jsonb)
  with kind from 'release_function_type_index': 1 weapon_enhance,
  3 status_up, 4 terrain, 5 weapon_change, 6 ability_change,
  7 weapon_effect (counted over the 1107 units of the scratch list:
  2152, 564, 250, 1141, 1 per unit, 1743).
- weapon(stamp, id, unit_id, name, type, work_type, attack_attr,
  weapon_attr, power, en, hit_rate, critical_rate, range_min,
  range_max, ammo, is_ssp); weapon_growth(stamp, weapon_id, level,
  power_rate, en_rate, hit_rate_rate, crit_rate).
- pilot(stamp, id, name, rarity, role); pilot_stat(stamp, pilot_id,
  stat, base, max, sp_base, sp_max); pilot_tag; pilot_ability(stamp,
  pilot_id, sort, ability_id, payload jsonb); pilot_skill(stamp,
  pilot_id, sort, payload jsonb).
- supporter(stamp, id, name, rarity, max_hp_addition,
  max_attack_addition); supporter_limit_break(stamp, supporter_id,
  step, leader_skill jsonb, active_skill jsonb).
- stage: raw only. Scope item 3 names no stage table.
- holding(id, stamp, unit_id, level, limit_break, mech_sp,
  mech_ssp, pilot_id, pilot_level, weapon_level). A stub: the
  loader reads its inputs from the command line, not from this table.

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
- 'attack_attr' 5 = ranged and awaken.
- The star rate applies to EN, ATK, DEF and MOB as to HP (the site
  does this; the device panel of 0829 confirmed HP only).

## Progress log

- 2026-09-03: worktree, this file, the state block on the issue,
  recon, the plan, the user's three rulings. Step 1 done: the ledger
  entries 0902 and 0903, six terminology rows.
