# Branch roadmap: issue #74, crawl the soshage datamine

> Type: working—deleted at merge

Issue: #74. Branch: issue-74-datamine-crawl. Status: awaiting-review.

## Change summary

Six commits.

| Commit | Files | What |
|---|---|---|
| 5b15665 | `docs/roadmaps/branch-issue-74.md` | This file |
| b8d37b8 | `scripts/crawl_datamine.py`, `tests/test_crawl_datamine.py`, `tests/fixtures/datamine/` | The crawler, the offline fixture and the tests |
| c4ed67c | `docs/reference/datamine-source.md`, `docs/reference/terminology-map.md`, `docs/reference/combat-formulas.md` | The reference document, three term bindings, one cross-reference |
| 426705a | `scripts/crawl_datamine.py`, `tests/test_crawl_datamine.py`, `docs/reference/datamine-source.md` | The fixes that the branch code review found |
| 43e4434 | `docs/reference/datamine-source.md`, `docs/reference/datamine-samples/`, `docs/reference/terminology-map.md` | The per-id forms, the verified enums, and a sample of ten UR units, ten pilots and one support crew, read on 2026-08-28 |
| (next) | `docs/reference/datamine-source.md`, `docs/reference/datamine-samples/` | The stage detail form: placed enemies with cells and a reinforcement flag, and the condition text |

`scripts/crawl_datamine.py` writes `data/datamine/<stamp>/` with five
files: `unit.json`, `weapon.json`, `stage.json`, `formula.json` and
`manifest.json`. It uses `urllib` from the standard library, so it
adds no dependency.

`docs/reference/datamine-source.md` names the four sources, the row
counts of 2026-08-22, the fields of each row, and the field review
against `docs/spec/battle-engine-protocol.md` and
`docs/spec/intel-data-spec.md`. The field review is a section of that
same document.

`.gitignore` needs no change. Line 16 already holds `data/`.

## Call chain

```
scripts/crawl_datamine.py main()
  HttpFetch(base_url, timeout)          one urllib GET for each path
  crawl(fetch, out_root, source)
    _stamp(fetch)                       GET /ggetapi/version, checked as a name
    fetch(/ggetapi/en/unit)             -> json.loads
    fetch(/ggetapi/en/weapon)           -> json.loads
    fetch(/ggetapi/en/stage)            -> json.loads
    fetch(/gget/formula)                -> formula_chain
      _tab_panel(page, "formula")       div-depth walk over the page
      _CODE / _text                     the 17 lines and the 3 notes
    _stamp(fetch)                       read again, stop on a new stamp
    _dump(payload)                      sort_keys, indent 2, no timestamp
    manifest.json                       stamp, source, path, rows, bytes, sha256
```

`tests/test_crawl_datamine.py` calls `crawl` with a fetch that reads
`tests/fixtures/datamine/`. The suite touches no network.

## Verification

- `uv run pytest -q`: 1003 passed, 4 skipped.
- `uv run ruff check src tests scripts`: all checks passed.
- Live crawl, three runs on 2026-08-22 at stamp `202608161248`.
  `diff -r` between two runs reports no difference. Row counts:
  unit 1226, weapon 4785 plus 1342 sidecar units, stage 2104,
  formula 17 lines and 3 notes. Every count matches the issue.
- The branch code review raised seven findings. Six are fixed in
  426705a and in this file. One is not fixed: see the contention
  points.

## Contention points

1. **The issue names four endpoints. There are five.** The stamp
   `202608161248` is not in any of the four. It comes from
   `GET /ggetapi/version`. The crawler reads that fifth address.

2. **One of the four is not an endpoint.** `/gget/formula` is a
   rendered page. It also embeds prefetched API payloads, and the
   server writes those in completion order, so two fetches of the
   page give different bytes. The crawler stores the formula tab of
   the page and drops the rest. The stored file is therefore read
   from markup, not received as JSON. The manifest marks it
   `"kind": "extracted"`.

3. **The weapon capability table is not in the four sources.** The
   issue states that `/ggetapi/en/weapon` carries "a weapon
   capability table of exactly three rows". It does not. The list
   endpoint has no such field. The id `weapon_capability` appears
   only in `/ggetapi/en/unit/{id}`, a per-unit address. No public
   address for the table itself was found on 2026-08-22. The
   reference document records this. It does not re-derive the three
   rows: `docs/reference/combat-formulas.md` keeps them from the
   2026-08-21 review.

4. **Two other field names of the issue differ from the source.**
   The issue writes `en_cost` and `attributes` for the weapon row.
   The source writes `en`, and it writes four separate enums:
   `type`, `work_type`, `attack_attr` and `weapon_attr`.

5. **The dump keeps the row order of the source; it does not sort
   rows.** Two fetches of `unit` and of `stage` gave the same bytes
   on 2026-08-22, so upstream order is stable at one stamp. Sorting
   the rows by `id` would also work and would survive an upstream
   reorder, but it would hide that reorder. Ruling 2026-08-28: keep
   the order of the source ("保留原順序").

6. **A re-run at one stamp overwrites the five files in place.** It
   removes no other file of that directory. Review finding 4 asked
   for a temp directory and a swap, or for a clear of the
   directory. Neither is done: deleting files that the crawler did
   not write is a destructive act for a small gain. The behaviour
   is now in the reference document instead. Ruling 2026-08-28:
   overwrite in place ("原地覆寫").

7. **The store is not in the repository.** `data/` is gitignored, so
   the 114 MB dump does not travel with the merge. The reviewer's
   copy is in this worktree at `data/datamine/202608161248/`. The
   user must run the crawler once after the merge.

8. **Nothing reads the store yet.** No code path consumes
   `data/datamine/`. That is the issue's own boundary: no crawled
   value is trusted for a live decision until the intel store
   checks it against the device.

## Open questions of the issue

The issue carries three open questions. This branch answers none of
them, and the reference document records all three under "Not
verified":

- Whether the datamine agrees with the device for one unit. No
  comparison was made.
- The licence and the rate limit of the site. Neither is stated on
  the site.
- How a game patch invalidates a dump under an older stamp.

## Added on 2026-08-28

The user asked for the shapes of the mech, the pilot and the support
crew, and for a sample in the repository. The review read the
per-id addresses over curl and the rendered pages in Chrome. The
Chrome extension blocked in-page script fetches, so the JSON came
over curl; the pages gave the labels the JSON encodes as integers.

Verified against the rendered pages: `rarity` 5 is UR, `role` 1, 2, 3
is 攻擊型, 耐久型, 支援型, and `terrain` 3, 2, 1 is ○, △, －.

The sample store is in `docs/`, not in `data/`, because it must
travel with the repository. 832 KB. Ruling 2026-08-28: it stays in
`docs/` ("留在 docs").

Ruling 2026-08-28: the crawler does not fetch the pilot, the support
crew or the per-id forms ("不用"). Issue #84 owns the pilot crawl.

## Deferred

- The weapon capability table: contention point 3. The per-id unit
  form carries it as `capability`; the sample store holds rows 1, 2
  and 4.
- Crawling `/ggetapi/en/character` (pilots) and
  `/ggetapi/en/supporter` (support crew) is outside the scope of the
  issue. The reference document now records both rows, and the
  sample store holds ten pilots and one support crew.
