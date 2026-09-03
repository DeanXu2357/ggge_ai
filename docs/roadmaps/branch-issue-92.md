# Branch roadmap: issue 92, the game data in PostgreSQL

> Type: working—deleted at merge

Issue: #92. Branch: issue-92-game-data-db. Status: awaiting-review.

## Review artifact

Branch off 'dev' at 4eb94b0. Eleven commits, eab33c9 to HEAD: eight
build steps, one document pass, the review fixes, this artifact.
Gates at 8ad3308: ruff clean; pytest 1089 passed, 12 skipped; the
store tests 8 passed against the container; the migration cycle
'down -all', 'up', 'down 1', 'up' clean at version 7; 'go vet' and
'go test' pass.

### Change summary

The deliverable is the store and the data model (user, 2026-09-03):
a later crawl adds data through the ingest alone; the loader, the
payload shape and the engine contract do not change.

- compose.yaml: one service, postgres:16, db/user/password 'ggge',
  port 5432, volume 'ggge_ai_postgres-data'.
- db/migrations/0001 to 0007: plain SQL for golang-migrate. Raw
  rows, the constants (level_curve, limit_break_rate,
  rarity_level_cap), unit (with stats, terrain, abilities, SSP
  stats, cores, releases), weapon (with growth and traits), pilot
  (with stats, abilities, skills), supporter (with limit break
  skills and the growth table), holding (a stub). Every normalized
  table carries 'stamp' in its key; the three constant tables of
  growth.py do not.
- scripts/crawl_datamine.py: the endpoints 'supporter' and
  'supporter/growth'; nine requests per crawl.
- src/ggge_ai/gamedata/growth.py: the 100-entry level curve, the
  caps, the star rates, the integer formulas.
- src/ggge_ai/gamedata/normalize.py: the dump to rows, pure.
  records.py: the frozen record types and 'Catalog', the one record
  assembler. store.py: psycopg 3, delete-then-insert per stamp,
  'read_rows' gives the rows of one stamp back in the shape that
  normalize() produces; 'Catalog.from_rows' assembles them.
- src/ggge_ai/gamedata/holding.py: 'Holding' to the engine payload
  per docs/reference/growth-model.md.
- scripts/ingest_datamine.py and scripts/load_holding.py: the two
  entry points; the loader reads the store or a dump ('--from-dump').
- engine/battle/state/payload_test.go: every golden decodes into
  'battle.Mech' and 'battle.Pilot' with 'DisallowUnknownFields'.
  engine/boundary_test.go: no import outside the standard library
  and the module. No non-test file under engine/ changed.
- Docs: docs/how-to/game-data-db.md (new), growth-model.md (new),
  datamine-source.md (the two endpoints, the weapon 'type' enum),
  terminology-map.md (mech_sp, mech_ssp, holding, level curve,
  catalog, Ex weapon), decisions.md (0902, 0903).
- Tests: 54 new Python test functions (growth 9, normalize 16,
  holding 20, crawler 1; store 8 gated on 'GGGE_DATABASE_URL');
  three goldens in tests/fixtures/gamedata/.

### Call chain

    crawl_datamine.py  ->  data/datamine/<stamp>/*.json + manifest.json
    ingest_datamine.py ->  normalize.normalize(stamp, Dump.read(dir)) -> Rows
                           normalize.raw_rows(...)                    -> raw
                           Store.write_constants(); Store.write_stamp(rows, raw)
    load_holding.py    ->  Holding(...)
                           rows = Store.read_rows(stamp) | normalize(stamp, Dump.read(dir))
                           catalog = Catalog.from_rows(rows)
                           holding.assemble(holding, catalog.unit(id), catalog.pilot(id),
                                            catalog.supporter(id), catalog.supporter_rate(l, lb))
                           holding.payload(assembled) -> {"mech", "pilot", "crew"}
    engine (unchanged) <-  the mech and the pilot of the payload, in the wire form
                           of protocol 2.0 ('load' request; issue #72 wires the call)

'assemble': level group (sp when mech_sp and rarity below 5), level
curve at the cap, SSP addition (ssp_max plus status_up sums) when
mech_ssp, star rate on five stats, releases in core order
(weapon_change, weapon_enhance), direct weapons alone, pilot on the
plain group at the rarity cap, crew bonus beside the payload.

### Contention points

1. 'mech_ssp' is one stage and the loader adds 'ssp_max' (user
   ruling 2026-09-03). The site shows the half point; no device
   check of the full value yet.
2. Ex weapons ('type' 2) and map weapons ('type' 3) are stored and
   not emitted; 'map_weapons' is an empty list. The engine has no
   affect-area mapping from the datamine; issue #72 takes it.
3. The crew bonus travels beside the payload ('crew' key), not in
   it. The Go test drops the key on purpose; a key inside 'mech' or
   'pilot' that the engine does not know fails the test.
4. 'weapon_effect', 'ability_change' and 'terrain' releases are
   stored, not applied. 'critical_rate' and the weapon traits have
   no engine field.
5. The 'holding' table is a stub: the loader takes its inputs from
   the command line. Issue #72 decides who writes the table.
6. The datamine fixture slice has no manifest, so it is not a dump.
   The store tests build the rows from it with 'Dump.read'. The
   end-to-end check of the store path (ingest, load, compare with
   the golden) ran by hand at 94aebf2 and is not a test; since the
   review fixes the round-trip test 'Catalog.from_rows(read_rows)'
   equals 'Catalog.from_rows(rows)' covers the same path.
7. Deviations from the plan of 2026-09-03: the fixtures stay in
   tests/fixtures/datamine (the sample store holds UR units alone,
   no SSP); the stamp moved to 202609010310; the schema gained
   'tag', 'pilot_series', 'weapon_trait'; the Zeong HP literals of
   the first growth-model.md example were wrong and are corrected
   (plain 8032 to 57831, sp 8936 to 64337).
8. No full dump exists on this machine ('data/datamine/' is empty).
   'read_rows' reads every table of a stamp into memory; its cost at
   the full size (about 95 MB of JSON) is unmeasured.
9. The other NOT NULL jsonb columns ('unit_ability.payload',
   'weapon_trait.payload', 'unit_ssp_release.payload',
   'supporter_limit_break.leader_skill' and 'active_skill') are
   unchanged. The fixture holds no null there. A null in a later
   crawl fails the ingest with a NOT NULL violation, not silently.

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

### Review fixes

The code review ('/code-review' on dev..94aebf2) gave ten findings.
Each one and its resolution, in commit 8ad3308:

1. 'Store._delete' never cleared 'holding'; a stamp with a holding
   row failed the second ingest on the foreign key. 'DELETE_ORDER'
   now leads with 'holding'; a store test inserts a holding row,
   writes the stamp again and deletes it.
2. 'Jsonb(None)' stored the JSON literal null, not SQL NULL.
   '_wrapped' wraps a value only when it is not None. The fixture
   holds 2 null skills and 3 null abilities (Kai Shiden 1001000200,
   sorts 2 to 4); 'pilot_ability.payload' was NOT NULL in 0005 and
   is now nullable. A store test pins the two counts.
3. The 'ult' rules of the loader (cap 100, stars forced to 0) were
   in the code and not in growth-model.md. The document states them
   with the plan approval date.
4. 'supporter_growth' carried no stamp against the user ruling. The
   table moved from 0002 to 0006 with 'stamp' in its key;
   normalize() writes the stamp; the store treats it like the rest.
5. 'attack_attr' 5 and 6 were untested. One holding test names the
   hypothesis and pins ranged+awaken and melee+awaken.
6. 'raw_rows' let two rows of one source share a key, so the second
   overwrote the first in 'datamine_raw'. It raises ValueError with
   the source and the key.
7. '--supporter' without its level and limit break silently used
   level 1, zero stars. The two flags default to None; 'parser.error'
   stops a half-given crew. 'Holding' keeps its defaults for direct
   callers.
8. The weapon 'type' enum was promoted to a fact in the documents.
   Reverted to a hypothesis with two sources (the name pattern of the
   82 rows, and the mutual exclusion with 'is_ssp'); the Not
   verified list of datamine-source.md names it.
9. The 'holding' terminology entry omitted the support crew. Fixed.
10. 'Store.read_unit', 'read_pilot', 'read_supporter' and
    'supporter_rate' duplicated 'Catalog'. Replaced with
    'Store.read_rows(stamp) -> Rows'; 'Catalog.from_rows' is the one
    record assembler for the store path and the dump path.
    'StampedStore' in scripts/load_holding.py is gone.

The migrations 0002, 0005 and 0006 were edited in place: the branch
is unmerged and only the local container had applied them. The
container was cycled 'down -all', 'up', 'down 1', 'up' (version 7).


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
- 2026-09-03: step 8 done. Type 2 of the weapon 'type' enum is the
  existing term 'Ex weapon' (all 82 rows end with "EX"); the
  datamine reference records the three type values with counts and
  the 'attack_attr' 5 and 6 hypotheses. End-to-end check against
  the container: a dump built from the fixture slice ingested (431
  raw rows), the Zeong loaded through 'Store', the output equal to
  the golden 'zeong_sp_ssp_lb3.json', the stamp deleted.
- 2026-09-04: finish. Gates at 94aebf2 green; '/code-review' gave
  ten findings, all fixed (the 'Review fixes' section); the reference
  documents corrected; this file reworked into the review artifact.
  Gates after the fixes: ruff clean, pytest 1089 passed 12 skipped,
  store 8 passed, migrate cycle clean, go vet and go test pass.
