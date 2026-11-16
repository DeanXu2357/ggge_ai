# Review a stage run

> Type: how-to—must match the current workflow

The script `scripts/analyze_run.py` writes review pages for one run of
`scripts/run_loop_v2.py`. The stage run does not start the analysis. You
start it yourself, after the run or at the end of a pipeline.

## Before the run

The analysis needs the plan trace. Start the run with `--trace-plans`.
Add `--keep-frames` when you want the full frames on the pages; without
it, the pages show the small frames of `frames/`.

## Analyze while the run goes on

Send the output of the run into the analysis:

```sh
uv run --python 3.12 python scripts/run_loop_v2.py --stage uc-hard-1 \
    --trace-plans --keep-frames 2>&1 \
  | uv run --python 3.12 python scripts/analyze_run.py
```

The analysis prints each line of the run. When the run prints
`run directory: ...`, the analysis starts on that directory. Ctrl-C
stops the run only; the analysis then reads the run directory and
writes the pages.

## Analyze a finished run

```sh
uv run --python 3.12 python scripts/analyze_run.py data/runs/<timestamp>
```

## Output

The analysis writes these files in the run directory:

- `analysis.html`: one row for each cycle. The row shows the frame with
  the gesture, the units and the tap mark; the screen and the
  expectation; the step; the map judgment; and the flags. A check box
  hides the rows without flags.
- `analysis.json`: the same rows as data.
- `analysis/`: the frames of the rows.

The analysis flags these events:

- `unexpected screen`: the screen after the step is not one that the
  step expected.
- `outside candidates`: the interpreter found a screen outside the
  candidates.
- `same step N times`: the same step and gesture, N cycles in a row.
- `swipe reversed N times`: N survey swipes in a row, each against the
  direction of the swipe before it.
- `view joins nothing`: the newest view joins no other view.
- `tap on (x, y) read mark ...`: the reading after a tap on an empty cell
  does not show the mark on that cell.
- `replay differs`: the replayed survey step is not the logged step.

## Determinism

The analysis reads only the run directory. It replays the map sync
planner on the traced map readings, with the seed of the run log. The
same run directory and the same code give the same files. The page
shows the code version of the run and the code version of the
analysis. When the two differ, a `replay differs` flag can come from the
code change and not from the run.

An older run log has pickled readings and no seed in its stage line.
The analysis does not read such a run.

The analysis replays every survey step and joins all views again at each
step. A run of 100 survey steps takes about four minutes.

## Draw the saved stage map

When a survey saves stage data, draw the saved map over the frames that
the survey saw:

```sh
uv run --python 3.12 python scripts/render_stage_map.py data/runs/<timestamp>
```

The run needs `--trace-plans` and `--keep-frames`, and the stage store
must run. The script writes these files in the run directory:

- `stage_map.html`: the saved map size and fields, the map image, and a
  table of the saved units with their name masks.
- `stage_map.png`: a mosaic of the top view of each cell, from the
  newest view that showed the cell. Red boxes are the saved units, green
  boxes are the units that the player controls, and orange diagonals are
  uncertain cells. A black cell is a cell that no view showed.
- `stage_map_plain.png`: the same mosaic without marks.

The page tells whether the replayed survey gives the same map size and
units as the store. The survey ends on a reading that the plan trace
does not hold, so the script reads that last frame again from
`stream/`. Add `--views` to print the shift and the units of each view
on the map.
