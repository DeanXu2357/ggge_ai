"""候選召回評估工具的離線測試：合成流水帳＋注入的檢測器，不讀任何實機幀。"""

from __future__ import annotations

import json
from dataclasses import replace

from ggge_ai.runtime import sweep
from scripts.eval_candidate_recall import (
    cached,
    detector,
    entries_of,
    evaluate,
    fresh_of,
    grid_of,
    truth_of,
    windows_of,
)

ENTRIES = [
    {"kind": "world_anchored", "phase": [0.0, 0.0], "pitch": [100.0, 100.0]},
    {"kind": "window", "offset": [0.0, 0.0], "window": [[0, 0], [2, 1]],
     "frame": "frames/00001.png"},
    {"kind": "verdict", "cell": [0, 0], "verdict": sweep.EMPTY},
    {"kind": "verdict", "cell": [1, 0], "verdict": sweep.ENEMY},
    {"kind": "verdict", "cell": [2, 1], "verdict": sweep.ALLY},
    {"kind": "window", "offset": [300.0, 0.0], "window": [[3, 0], [5, 1]],
     "frame": "frames/00002.png"},
    {"kind": "verdict", "cell": [4, 0], "verdict": sweep.ENEMY},
]


def test_the_journal_gives_up_the_grid_the_windows_and_the_clicked_truth(tmp_path):
    path = tmp_path / "sweep.jsonl"
    path.write_text("\n".join(json.dumps(entry) for entry in ENTRIES), encoding="utf-8")

    entries = entries_of(tmp_path)
    grid = grid_of(entries)
    windows = windows_of(entries)

    assert grid is not None and grid.col_pitch == 100.0
    assert [window.bounds for window in windows] == [((0, 0), (2, 1)), ((3, 0), (5, 1))]
    assert windows[0].frame == "frames/00001.png"
    assert truth_of(entries)[(1, 0)] == sweep.ENEMY


def test_a_unit_outside_the_candidates_is_reported_as_a_miss_with_its_frame():
    report = evaluate(
        windows_of(ENTRIES),
        truth_of(ENTRIES),
        lambda window: frozenset({(1, 0), (0, 0)}) if window.index == 0 else frozenset(),
    )

    assert report.units == 3
    assert report.missed == 2
    assert report.scores[0].missed == ((2, 1),)
    assert report.scores[0].recall == 0.5
    assert report.scores[0].false_positives == ((0, 0),)  # 點過是空格的候選＝誤報
    assert report.scores[1].missed == ((4, 0),)
    assert report.recall == 1 / 3


def test_full_recall_is_the_go_signal_and_needs_every_window_scored():
    report = evaluate(
        windows_of(ENTRIES),
        truth_of(ENTRIES),
        lambda window: frozenset({(1, 0), (2, 1), (4, 0)}),
    )

    assert report.missed == 0
    assert report.recall == 1.0


def test_a_window_without_a_saved_frame_is_skipped_not_scored_as_a_hit():
    report = evaluate(windows_of(ENTRIES), truth_of(ENTRIES), lambda window: "no_frame")

    assert [score.skipped for score in report.scores] == ["no_frame", "no_frame"]
    assert report.missed == 0
    assert report.units == 3


def test_an_unscored_window_blocks_the_go_signal():
    report = evaluate(
        windows_of(ENTRIES),
        truth_of(ENTRIES),
        lambda window: frozenset({(1, 0), (2, 1)}) if window.index == 0 else "frame_unreadable",
    )

    assert report.missed == 0
    assert not report.go


OVERLAP = [
    {"kind": "world_anchored", "phase": [0.0, 0.0], "pitch": [100.0, 100.0]},
    {"kind": "window", "offset": [0.0, 0.0], "window": [[0, 0], [3, 1]],
     "frame": "frames/00001.png"},
    {"kind": "verdict", "cell": [1, 0], "verdict": sweep.ENEMY},
    {"kind": "window", "offset": [100.0, 0.0], "window": [[1, 0], [4, 1]],
     "frame": "frames/00002.png"},
    {"kind": "verdict", "cell": [4, 0], "verdict": sweep.ENEMY},
]


def test_a_cell_is_attributed_to_the_window_that_sentenced_it():
    assert fresh_of(OVERLAP) == {(1, 0): 0, (4, 0): 1}


def test_the_same_frame_reading_only_scores_the_window_that_sentenced_the_cell():
    windows = windows_of(OVERLAP)
    truth = truth_of(OVERLAP)
    def detect(window):
        return frozenset({(1, 0)} if window.index == 0 else {(4, 0)})

    broad = evaluate(windows, truth, detect)
    fresh = evaluate(windows, truth, detect, fresh_of(OVERLAP))

    assert broad.units == 3 and broad.missed == 1  # (1,0) 被第二窗當成自己的漏報
    assert fresh.units == 2 and fresh.missed == 0
    assert fresh.go


def test_a_window_that_sentenced_nothing_may_be_unscored_without_blocking_the_go():
    windows = windows_of(OVERLAP)
    truth = truth_of(OVERLAP)

    def detect(window):
        return frozenset({(1, 0), (4, 0)}) if window.index == 1 else "frame_unreadable"

    fresh = evaluate(windows, truth, detect, {(1, 0): 1, (4, 0): 1})

    assert fresh.skipped == 1 and fresh.blind == 0
    assert fresh.go


def test_the_detection_of_one_window_is_only_paid_for_once():
    calls: list[int] = []
    detect = cached(lambda window: (calls.append(window.index), frozenset())[1])
    windows = windows_of(OVERLAP)

    for window in windows * 2:
        detect(window)

    assert calls == [0, 1]


def test_the_detector_tells_a_missing_path_apart_from_an_unreadable_file(tmp_path):
    grid = grid_of(ENTRIES)
    assert grid is not None
    detect = detector(tmp_path, grid, halo=1.0, min_count=60, min_dist=8.0)
    recorded, unrecorded = windows_of(ENTRIES)

    assert detect(recorded) == "frame_unreadable"
    assert detect(replace(unrecorded, frame=None)) == "no_frame"
