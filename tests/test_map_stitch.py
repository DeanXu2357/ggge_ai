"""Offline stitch regression on the 20260719 ex2if manual-pan series:
9 real hub frames + per-frame subagent-transcribed ground truth (ring
centers, one dedicated reader per frame). Guards the min-zoom density
detector's recall and the stitcher's placement chain (vote + hint +
support + ICP + weak-frame relocate), and cross-validates the pooled
units against the GT-derived board: every unique GT unit must appear in
the pool; extras are bounded (large sprites shed multiple peaks)."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import pytest

from ggge_ai.battle import map_stitch, vision

SERIES = Path(__file__).parent / "fixtures" / "vision" / "map_scan" / "ex2if_20260719"
GT_MATCH_RADIUS = 70.0
HINTS = [None, "up", "up", "up", "up", "right", "down", "down", "down"]


@pytest.fixture(scope="module")
def series():
    manifest = json.loads((SERIES / "manifest.json").read_text(encoding="utf-8"))
    entries = sorted(manifest["frames"], key=lambda f: f["seq"])
    frames = [cv2.imread(str(SERIES / e["image"])) for e in entries]
    assert all(f is not None for f in frames)
    return entries, frames


@pytest.fixture(scope="module")
def ground_truth():
    return json.loads((SERIES / "ground_truth.json").read_text(encoding="utf-8"))["frames"]


@pytest.fixture(scope="module")
def result(series):
    _, frames = series
    return map_stitch.stitch(frames, hints=HINTS)


def test_density_detector_recall(series, ground_truth):
    entries, frames = series
    total = hit = 0
    r2 = GT_MATCH_RADIUS * GT_MATCH_RADIUS
    for entry, frame in zip(entries, frames):
        peaks = vision.find_unit_density_peaks(frame)
        for unit in ground_truth[entry["image"]]:
            if unit["status"] != "full":
                continue
            ux, uy = unit["pos"]
            total += 1
            if any((ux - x) ** 2 + (uy - y) ** 2 < r2 for x, y in peaks):
                hit += 1
    assert total >= 100
    assert hit / total >= 0.95


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
    assert len(result.static_screen) <= 8


def expected_board(ground_truth, entries, cameras):
    """Unique GT units in world coordinates: full+hud observations of
    every frame carried by the fitted cameras, merged at 60px."""
    merged: list[tuple[float, float]] = []
    for i, entry in enumerate(entries):
        for unit in ground_truth[entry["image"]]:
            if unit["status"] not in ("full", "hud"):
                continue
            w = (unit["pos"][0] + cameras[i][0], unit["pos"][1] + cameras[i][1])
            for j, q in enumerate(merged):
                if (w[0] - q[0]) ** 2 + (w[1] - q[1]) ** 2 < 60**2:
                    merged[j] = ((w[0] + q[0]) / 2, (w[1] + q[1]) / 2)
                    break
            else:
                merged.append(w)
    return merged


def test_pool_covers_every_gt_unit(series, ground_truth, result):
    entries, _ = series
    cameras = [p.camera for p in result.placements]
    board = expected_board(ground_truth, entries, cameras)
    assert 25 <= len(board) <= 30
    missing = [
        b
        for b in board
        if all(
            (b[0] - u.pos[0]) ** 2 + (b[1] - u.pos[1]) ** 2 >= 80**2
            for u in result.units
        )
    ]
    assert not missing, f"GT units absent from pool: {missing}"
    # large sprites (warship, oversized MA) shed extra peaks; bound them
    assert len(result.units) - len(board) <= 14


def test_grid_pitch_measured(result):
    assert result.col_pitch is not None and 90 <= result.col_pitch <= 105
    assert result.row_pitch is not None and 88 <= result.row_pitch <= 100


def test_missing_hints_still_stitches(series):
    _, frames = series
    result = map_stitch.stitch(frames)
    assert len(result.placements) == len(frames)
    assert 27 <= len(result.units) <= 45
