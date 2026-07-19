"""Offline stitch regression on the 20260719 ex2if manual-pan series:
9 real hub frames + subagent-transcribed ground truth. Guards the
min-zoom density detector's recall and the stitcher's placement chain
(vote + hint + support + ICP + weak-frame relocate)."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import pytest

from ggge_ai.battle import map_stitch, vision

SERIES = Path(__file__).parent / "fixtures" / "vision" / "map_scan" / "ex2if_20260719"
# units the transcription itself flags as HUD-covered or banner-hidden;
# the detector is not expected to see them in that frame
GT_HUD_COVERED = {
    ("07_pt7_pan_down.png", (435, 300)),
    ("07_pt7_pan_down.png", (420, 205)),
    ("09_pt9_pan_down_end.png", (455, 125)),
}
GT_MATCH_RADIUS = 75.0

HINTS = [None, "up", "up", "up", "up", "right", "down", "down", "down"]


@pytest.fixture(scope="module")
def series():
    manifest = json.loads((SERIES / "manifest.json").read_text(encoding="utf-8"))
    entries = sorted(manifest["frames"], key=lambda f: f["seq"])
    frames = [cv2.imread(str(SERIES / e["image"])) for e in entries]
    assert all(f is not None for f in frames)
    return entries, frames


@pytest.fixture(scope="module")
def result(series):
    _, frames = series
    return map_stitch.stitch(frames, hints=HINTS)


def test_density_detector_recall(series):
    entries, frames = series
    gt = json.loads((SERIES / "ground_truth.json").read_text(encoding="utf-8"))["frames"]
    total = hit = 0
    r2 = GT_MATCH_RADIUS * GT_MATCH_RADIUS
    for entry, frame in zip(entries, frames):
        peaks = vision.find_unit_density_peaks(frame)
        for unit in gt[entry["image"]]:
            if (entry["image"], tuple(unit)) in GT_HUD_COVERED:
                continue
            total += 1
            if any((unit[0] - x) ** 2 + (unit[1] - y) ** 2 < r2 for x, y in peaks):
                hit += 1
    assert total >= 100
    assert hit / total >= 0.85


def test_placement_directions_follow_pans(result):
    cameras = [p.camera for p in result.placements]
    assert cameras[0] == (0.0, 0.0)
    for i, hint in enumerate(HINTS):
        if hint is None or i == 0:
            continue
        dx = cameras[i][0] - cameras[i - 1][0]
        dy = cameras[i][1] - cameras[i - 1][1]
        primary, cross = {
            "up": (-dy, abs(dx)),
            "down": (dy, abs(dx)),
            "left": (-dx, abs(dy)),
            "right": (dx, abs(dy)),
        }[hint]
        assert primary > 100, f"frame {i} moved {dx:+.0f},{dy:+.0f} against hint {hint}"
        assert cross < primary


def test_static_filter_finds_hud_buttons(result):
    def near(p, q):
        return (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 < 40**2

    for button in ((199, 273), (391, 273), (2012, 90)):
        assert any(near(s, button) for s in result.static_screen)
    assert len(result.static_screen) <= 5


def test_pool_size_and_consistency(result):
    assert 28 <= len(result.units) <= 38
    multi = [u for u in result.units if u.support >= 2]
    assert len(multi) >= 24
    assert all(u.spread < 70 for u in multi)


def test_grid_pitch_measured(result):
    assert result.col_pitch is not None and 90 <= result.col_pitch <= 105
    assert result.row_pitch is not None and 88 <= result.row_pitch <= 100


def test_missing_hints_still_stitches(series):
    _, frames = series
    result = map_stitch.stitch(frames)
    assert len(result.placements) == len(frames)
    assert 28 <= len(result.units) <= 40
