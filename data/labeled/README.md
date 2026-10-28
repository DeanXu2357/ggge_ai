# Labeled frames

This directory is the dataset of screen labels that the user ruled. The
OpenCV interpreter tests read these cases.

This directory is the authoritative copy. No script makes it again. To
change the dataset, edit the files here: add or remove a frame in
`frames/` and its row in `cases.jsonl`.

## Contents

- Only cases that the user ruled are in the dataset.
- The dataset keeps no duplicate cases. A second case of the same screen
  stays only when it is different from the first case.
- A case with `transition` true is on an animation screen (kind
  `animation` or `loading` in `assets/ui_stages/stages.json`).

## Source

The first version (2026-10-26) comes from the frames of the recording
`data/ui_recordings/20261014-234132` that the user reviewed. Later cases
come from device runs in `data/runs/` and from device screenshots in
`data/map_samples/`. The sources are not in git.
`source`, `index` and `sha256` in each row point back to the source frame.

## Files

- `frames/`: the full frames, 2340x1080. Recording frames are JPG with the
  recording file name. Run frames are PNG, named `run<run>_<index>.png`. Screenshots are PNG,
  named `map<day>_<index>.png`.
- `cases.jsonl`: one row for each frame, sorted by `source`, then `index`.

## Fields of `cases.jsonl`

- `id`: the case ID, `rec20261014-<index>` or `run<run>-<index>`.
- `source`: the recording directory or the run directory.
- `index`: the frame index in the recording, or the frame sequence number
  of the run.
- `file`: the frame file name.
- `t`: the frame time in seconds from the start of the recording. `null`
  for a run frame.
- `sha256`: the SHA-256 of the frame file.
- `screen`: the screen name, as in `assets/ui_stages/stages.json`.
- `transition`: `true` when the frame shows a transition.
- `auto`: the AUTO mode: `full` (blue), `semi` (red) or `manual` (white).
  `null` when the screen has no AUTO button.
- `power_save`: `lock` (the power-save lock icon) or `dim` (the dimmed
  screen). `null` when the frame is not in power save. `screen` is the
  screen under the power-save overlay.
- `phase`: the faction of the phase, from the color of the title band at the
  top left: `player` (blue) or `non_player` (red or purple). `null` on a
  screen without that band.
- `map`: what the frame shows of the battle map. `null` when the user has
  not ruled the frame. A map cell counts when the frame shows the whole
  cell and the HUD does not cover it. A cell is (column, row); (0, 0) is
  the top-left corner of the box around the counted cells. Fields:
  - `cells`: the counted cells.
  - `borders`: the map edges that show in the frame (`top`, `bottom`,
    `left`, `right`).
  - `units`: one entry for each unit: `pos`, the cell of its footprint with the
    least column and the least row, and `size`, its width and height in cells.
    `pos` and `size` give the cells that the unit covers in the frame. A unit
    whose cells are not a rectangle lists the cells outside the rectangle in
    `extra`. The cells that select a unit are not in the dataset: one frame
    does not show them.
  - `controllable`: the `pos` of the units that show the chevron (the
    units the player can still move).
  - `selected`: the `pos` of the unit with the blue selection circle, or
    `null`.
  - `markers`: the cells of each marker: `move_range` (the double-line
    cells of the move range), `threat` (the exclamation mark) and
    `weapon_range` (the red cells of the weapon range).

## Later work

Cases with cropped images of the recognition target come in a later
version.
