# Branch roadmap: feat/stream-input

> Type: working—deleted at merge

- Issue: https://github.com/DeanXu2357/ggge_ai/issues/30
- Base commit: `3513126` (dev, "Label docs by type and sort into directories")
- Branch: `feat/stream-input` (named before the `issue-N-slug` rule)
- Last code commit: `1a5c5b5` "Delete review guides restored by rebase"
- Status: approved by the user 2026-08-13; merge pending

The branch started before the branch-roadmap convention. It recorded its
progress in `docs/record/roadmap.md` with the retired pause-snapshot
format. This document replaces that file. The snapshots stay in the git
history of the branch.

## Change summary

The branch replaces the screenshot-per-frame scan loop with a live
stream, adds evidence-driven pacing, moves the position chain to one
projection model, and adds the roster stage that writes the first
complete intel of a stage.

43 commits. 29 files, +6749/-119.

| Batch | Effect | Key commits |
|---|---|---|
| Stream frame source | `scrcpy --v4l2-sink` replaces the `adb screencap` round trip. Opt-in with `--stream`. | `162a9ad` |
| Evidence-driven pacing | Tap feedback polling and frame-difference settle replace blind sleeps. Settle cost enters the journal. | `b60128f`, `c3d6e76`, `68e1eeb` |
| Attribution fixes | `--filter-mode` returns to `full` by default. A barren-pan fuse stops the pan-pan livelock. | `ab89e02`, `b1c7f46` |
| Projection switch | The aim gate judges position-space residuals against one homography. `SCREEN_CENTRE` moves to the measured centre (1170, 553). | `1e1e777`, `a5f32f6`, `a66938c`, `ddd1c01`, `dd454f2`, `2cccd34` |
| Roster stage | A new stage reads every unit detail page, then assembles `scenario.json` and `intel_report.json` offline. | `4be4688`, `3b4c3f5`, `93a941c`, `8c61e59`, and the four fixes `9ca5059`, `1384064`, `4dae84b`, `c0ce8b6` |
| Border-first scan | A veil gate rejects cells outside the provisional bounds of the current frame. Border definition beats pending cells in `plan_pan`. | `cdff205` |

No dependency changed. `pyproject.toml` and `uv.lock` are untouched.

## Call chain

Live path, from the command line to the two output files:

```
scripts/sweep_scan.py build()
  --stream -> ggge_ai.stream.StreamSource.start() -> StreamCamera
  default -> runtime.device.Camera            (adb screencap, unchanged)

SweepRun.run()
  select -> prep -> stage_info -> map -> grid -> zero -> sweep -> roster

  sweep stage: SweepRun.tour()
    sweep.read_borders(frame)
      -> sweep.provisional_bounds(grid, offset, borders, boundary)  = veil
      -> sweep.plan_window(..., veil=veil)   rejects cells outside the veil
      -> SweepRun.aimed(frame)
           -> projection.shadow_drift(lattice, band, grid, offset)
           -> SweepRun.aim_overruled(frame)  border-backed release
      -> SweepRun.tap_cell() -> settle.await_still(ctx="feedback")
      -> sweep.plan_pan()    border definition first when not bounded
    SweepRun.summarize() -> journal "sweep_summary"

  roster stage: SweepRun.collect_roster()
    -> runtime.roster_capture.RosterCapture.run()
         open_troop_info -> select_tab(faction) -> capture_unit(index)
         -> open_detail -> _select_detail_tab(page, tab) -> _shot()
         every wait goes through _settled() -> settle.await_still()

  after the abandon chain:
    -> stage.roster_offline.run_offline(run_dir, reader=OllamaPanelTextReader)
         read_entries -> collect_captures -> parse_unit
         -> sweep_facts -> reconcile -> build_scenario / build_report
         -> scenario.json + intel_report.json
```

`runtime/settle.py` holds the settle primitive. `runtime/entry.py`,
`scripts/sweep_scan.py`, and `runtime/roster_capture.py` are its three
callers. `runtime/panel_text.py` holds the free-text transcription
contract that `roster_offline` calls.

`scripts/validate_projection.py` is offline only. It replays run
journals and compares the old phase model against
`projection.shadow_drift`.

## Verification

Gates on `1a5c5b5`, worktree clean:

- `uv run pytest -q`: 1023 passed, 4 skipped. Dev is at 865 passed, 1
  skipped.
- `uv run ruff check src tests scripts`: all checks passed.

`scripts/sweep_scan.py` changed, so the rule in CLAUDE.md asks for a run
log. Run `20260811-110638` is the sealed run. Its journal is at
`data/runs/20260811-110638/sweep.jsonl`. The directory is not tracked by
git. These readings come from the journal itself, not from the prose of
the old snapshots:

| Reading | Value | Agreement |
|---|---|---|
| Verdicts | 472 empty, 18 enemy, 10 ally, 0 unsure, 0 inferred | 500 cells = 25 x 20 |
| Boundary | east 24, north 0, south 19, west 0 | equal to `assets/stage_truth/uc_hard_1.json` |
| Ally cells | the ten cells of the truth file | equal, cell for cell |
| Enemy at [9,4] | signature `4aea8a4aafa92bea` | equal to the user-verified entry |
| Taps, wall clock | 552 taps, 1906.8 s | 31.8 min, `complete` true, `bounded` true |
| Veil | all 91 window events carry the field | the gate was live for the whole scan |
| Roster | 124 shots, 122 ok, 2 enemy failures | `roster_capture_summary` |
| Outputs | `intel_offline` exit 0, `sweep_end` present | `scenario.json` and `intel_report.json` written |

The other cited runs (`035940`, `092754`, `230716`, `133305`, `011740`,
`031256`) are on this machine as tar archives under `data/runs/`.

## Contention points

1. **`docs/record/roadmap.md` is deleted in this commit.** Dev deleted
   the file at the base commit `3513126`, and the branch added 245 lines
   to it. That is the only merge conflict between the branch and dev.
   The alternative was to keep the file and make dev carry a retired
   convention again. Issue #33 removed the last README pointers to it,
   so keeping it would undo that fix. The snapshots stay in the git
   history of the branch.

2. **Six new source comments name a deleted document.**
   `runtime/projection.py` (two places), `runtime/board.py`,
   `runtime/sweep.py` (two places), and `scripts/validate_projection.py`
   point at `docs/reviews/perspective-measurement.md` or at
   `docs/reviews/projection-shadow/replay-residuals.json`. The user
   ruling of 0811 deleted `docs/reviews/`. The measurement report is the
   source of the default values in `projection.py`, so the comments
   still carry information, but the paths resolve to nothing. This is
   the defect class of issue #33. It is not fixed here.

3. **The branch subsumes `feat/projection-switch`.** The 21 commits that
   `feat/projection-switch` holds and this branch does not are rebase
   duplicates of the same patches. The content difference between the
   two branches is the roster batch only, and
   `runtime/projection.py`, `runtime/coverage.py`, `runtime/entry.py`,
   and `runtime/settle.py` are identical on both. Issue #31 therefore
   asks about a branch that this merge makes empty.

4. **The stream path is opt-in and the default path is untested live.**
   `--stream` is a `store_true` flag. All live evidence on this branch
   comes from stream runs. The `adb screencap` path keeps its unit tests
   but has no run log on this branch.

5. **The veil reading of the 0811 ruling is still marked for user
   review.** The ruling says "finish the four borders first, then clear
   the board". The code lets a window that the camera passes during
   border definition clear its cells as usual. The decision ledger
   carries this reading with a pending mark.

6. **Commit style.** 40 of the 43 commits use Chinese titles with
   conventional-commit prefixes. The English, prefix-free rule and the
   commit-msg hook came after these commits. On 2026-08-13 the user
   ruled to leave them as they are for now, and to correct the writing
   when a later task touches it.

7. **The branch name is `feat/stream-input`.** The `issue-N-slug` rule
   came later. The branch keeps its name.

## Open items after the merge

None of these blocks the merge. Each one needs its own issue.

1. **East-edge `expand_lost` to `reroot` loop.** Issue #28 is closed,
   but the closing comment says it was closed for missing a `type:`
   label, not because it was fixed. Run `20260811-110638` still shows 16
   `reroot` events. The `expand()` overshoot path does not call
   `witness()`, so the east border votes fill only by chance.
2. **`no_feedback` early-close tuning.** Pending user ruling. Named in
   the decision ledger and in the last snapshot.
3. **`date_changed` midnight dialog.** The classifier knows the screen.
   The entry chain does not recover from it. Every crossing needed
   manual navigation.
4. **`abandon:unconfirmed` false halt.** A long black transition is
   classified `unknown` and reports a halt after the device is already
   back at the stage list. Seen in run `002819`.
5. **Intel completeness.** Two enemy roster captures failed, and
   `intel_report.json` carries 21 pairing issues from the offline step.
6. **Terminology entries are missing.** The branch introduces `veil`,
   the stream frame source, the roster stage, `settle`, and the
   projection model. `docs/reference/terminology-map.md` has an entry
   for none of them. CLAUDE.md asks for the binding in the change that
   introduces the term.
