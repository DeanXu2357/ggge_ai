# Branch roadmap: issue-36-dead-review-refs

> Type: working—deleted at merge

## Goal

Issue #36: seven source comments name paths under `docs/reviews/`, the
directory the user deleted on 2026-08-11. Remove the dead pointers.

## Rule this branch follows

The change is a reference cleanup, not a comment rewrite. The first attempt
(`c6e4fcb`, discarded; the branch restarted from `dev`) recovered the deleted
reports from git history and moved their derivations into the comments. The
user rejected it: issue #36 changes the references to deleted material, not
the content of the comments.

- Remove the dead pointer only. In most sites the pointer is a parenthetical
  naming `docs/reviews/...`, and deleting it leaves a sentence that still
  reads correctly. That is the whole edit.
- Add nothing. No number that the comment does not already hold.
- Delete surrounding text only when that text fails the CLAUDE.md existence
  check on its own: it narrates the flow, or it records history.
- Keep every comment in the language it already uses. No translation.
- A why-comment is legitimate under CLAUDE.md. A comment is not deleted
  because it explains why.

## Change summary

Commits, branch `issue-36-dead-review-refs`, off `dev` at `5dd8953`:

| Commit | Content |
|---|---|
| `4c4659f` | This roadmap. |
| `b503444` | Six comments in `src/` lose the dead path and nothing else. |
| `ce5fb94` | The replay script writes its detail file under `data/`. |

`grep -rn "docs/reviews" src/ scripts/` now returns no match. `README.md:32`
is untouched.

## Site table

Line numbers are the ones the issue gives, on `dev` before the change.

| Site | Pointer removed | Other text deleted | Test it failed |
|---|---|---|---|
| `src/ggge_ai/runtime/projection.py:3`, module docstring | "`docs/reviews/perspective-measurement.md` §1／§2.3" inside the parenthetical | none; the parenthetical keeps its evidence, "758 幀兩 run" | — |
| `src/ggge_ai/runtime/projection.py:69`, `Projection` docstring | the path in "預設值出自 <path>：" | none | — |
| `src/ggge_ai/runtime/sweep.py:84`, `SCREEN_CENTRE` | the whole trailing parenthetical "（<path> §SCREEN_CENTRE）" | none | — |
| `src/ggge_ai/runtime/sweep.py:1091`, `aim_drift` docstring | "，見 <path>" inside the parenthetical | none; "差 p95 0.156 格" stays | — |
| `src/ggge_ai/runtime/board.py:664`, `find_lattice_band` docstring | the whole parenthetical "（<path> §3.3）" | none | — |
| `src/ggge_ai/runtime/board.py:151`, `UNIT_DENSITY_HUD_HOLES` | "，見 docs/reviews/scan-v2_7-review.md 第二節" inside the parenthetical | none; "（0801 第 6 輪逐幀量測）" stays | — |
| `scripts/validate_projection.py:35`, module docstring | the output path, repointed to `data/analysis/projection-shadow/replay-residuals.json` | none | — |

No surrounding text was deleted at any site, so the last column is empty
everywhere. Three sites needed a line rewrap after the pointer came out;
the wording did not change.

`projection.py:69` is the only site where deleting the pointer alone would
break the sentence: "預設值出自 <path>：§2.2 的縱線斜率 ..." needs a subject
after "出自". It now reads "預設值出自量測報告：", with no path. See
contention point 1.

## Call chain

None. Six edits are comment text only. The seventh changes one constant,
`DEFAULT_OUT` in `scripts/validate_projection.py`, which feeds only the
`--out` argparse default; the script already calls
`args.out.parent.mkdir(parents=True, exist_ok=True)`, and no module imports
the script.

## Gates

- `uv run pytest -q`: 1023 passed, 4 skipped.
- `uv run ruff check src tests scripts`: All checks passed.
- No device evidence needed: `battle/vision.py` and `scripts/sweep_scan.py`
  are untouched.

## Contention points

1. **A path-less pointer to the deleted report stays in
   `projection.py:69`.** The sentence needs a subject after "出自", so the
   path became "量測報告". The same file already says "報告 §3.3" and
   "報告 §5" in four other comments, and `scripts/sweep_scan.py:927` says
   "量測報告 §3.4", so the form is the file's own. It satisfies the issue
   grep, but it still points at material the reader cannot open. Rule
   otherwise if you want the whole clause gone.
2. **One sentence is a candidate for deletion and was left in place.**
   `sweep.py:80-82` records the old `SCREEN_CENTRE` value and the damage it
   did ("舊值拿 MAP_REGION 中點 (950,540) 冒充螢幕中點 ... 也帶著同樣的毒").
   That reads as history, which the existence check sends to the commit
   message. It is also readable as the why-comment for a constant that is
   not the obvious centre. The call is not forced by this ticket, and the
   ticket is a reference cleanup, so the sentence stays. Rule on it here or
   in a separate issue.
3. **Nine path-less mentions of the deleted material survive.** They carry
   no path, so they are outside the issue grep and outside its seven sites:
   `projection.py:7, 16, 53, 71, 73, 229`, `validate_projection.py:61, 74`,
   and `sweep_scan.py:927`. The last one is out of scope by instruction, and
   `sweep_scan.py` also asks for device evidence on any change.
4. **`DEFAULT_OUT` is a behaviour change, not a comment change.** The old
   default rebuilt `docs/reviews/projection-shadow/` on the next run of the
   script. `data/analysis/` is a new directory name inside the ignored
   `data/` tree. Reject it if the replay output belongs somewhere else.
