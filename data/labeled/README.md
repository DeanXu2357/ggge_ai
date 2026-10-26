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
`data/ui_recordings/20261014-234132` that the user reviewed. The recording
is not in git. `source`, `index` and `sha256` in each row point back to the
recording frame.

## Files

- `frames/`: the full frames, 2340x1080 JPG.
- `cases.jsonl`: one row for each frame, sorted by `index`.

## Fields of `cases.jsonl`

- `id`: the case ID, `rec20261014-<index>`.
- `source`: the recording directory.
- `index`: the frame index in the recording.
- `file`: the frame file name.
- `t`: the frame time in seconds from the start of the recording.
- `sha256`: the SHA-256 of the frame file.
- `screen`: the screen name, as in `assets/ui_stages/stages.json`.
- `transition`: `true` when the frame shows a transition.

The dataset does not hold the AUTO mode.

## Later work

Cases with cropped images of the recognition target come in a later
version.
