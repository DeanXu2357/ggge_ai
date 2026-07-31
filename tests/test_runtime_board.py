"""盤面全覽掃描：格網、密度峰單位偵測、平移量測、邊界、走訪控制流。

單位偵測的召回率對著 map_scan/ex2if_20260719 的逐幀人工轉錄量（ground_truth.json，
四分塊窮舉抄寫）——只算 status=full 的，被螢幕邊切與被 HUD 蓋住的不列入。
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from ggge_ai.runtime import board, coverage
from tests.fixtures.frames import load

SERIES = Path(__file__).resolve().parent / "fixtures" / "vision" / "map_scan" / "ex2if_20260719"
MATCH_RADIUS = 60


@functools.cache
def series() -> tuple[tuple[str, np.ndarray], ...]:
    manifest = json.loads((SERIES / "manifest.json").read_text(encoding="utf-8"))
    out = []
    for entry in sorted(manifest["frames"], key=lambda frame: frame["seq"]):
        image = cv2.imread(str(SERIES / entry["image"]))
        assert image is not None, entry["image"]
        out.append((entry["image"], image))
    return tuple(out)


@functools.cache
def ground_truth() -> dict[str, list[dict]]:
    return json.loads((SERIES / "ground_truth.json").read_text(encoding="utf-8"))["frames"]


def test_the_lattice_matches_the_curated_line_positions():
    expected = json.loads(
        (Path(__file__).resolve().parent / "fixtures" / "vision" / "grid" / "grid_on_lattice.json")
        .read_text(encoding="utf-8")
    )["expect"]

    lattice = board.read_lattice(load("grid/hub_grid_on_20260719"))

    assert lattice is not None
    assert list(lattice.cols) == expected["cols"]
    assert list(lattice.rows) == expected["rows"]


def test_a_gridless_map_yields_no_lattice():
    assert board.read_lattice(load("grid/hub_gridless_20260719")) is None


def test_the_lattice_reports_line_positions_not_one_cell_size():
    """橫線間距隨 y 遞增（縱向透視），所以格網不能概括成單一 cell size。"""
    lattice = board.read_lattice(load("grid/hub_grid_on_20260719"))
    gaps = [b - a for a, b in zip(lattice.rows, lattice.rows[1:], strict=False)]

    assert len(set(gaps)) > 1
    assert 90 <= lattice.col_pitch <= 160
    assert 90 <= lattice.row_pitch <= 160


def test_snapping_moves_a_point_to_its_cell_centre():
    lattice = board.Lattice(cols=(100, 200, 300), rows=(50, 150))

    assert lattice.snap((110, 60)) == (150.0, 100.0)
    assert lattice.snap((290, 140)) == (250.0, 100.0)
    # 線 span 之外的軸原值通過，不硬拉進格內
    assert lattice.snap((10, 60)) == (10, 100.0)
    assert lattice.cell_of((110, 60)) == (0, 0)
    assert lattice.cell_of((290, 60)) == (1, 0)
    assert lattice.cell_of((10, 60)) is None


@pytest.mark.parametrize("image", [entry[0] for entry in series()])
def test_the_density_peaks_find_every_fully_visible_unit(image):
    frame = dict(series())[image]
    expected = [unit["pos"] for unit in ground_truth()[image] if unit["status"] == "full"]

    found = board.find_units(frame)
    missed = [
        pos
        for pos in expected
        if not any(
            (pos[0] - x) ** 2 + (pos[1] - y) ** 2 <= MATCH_RADIUS**2 for x, y in found
        )
    ]

    assert len(missed) <= 1, f"missed {missed} of {len(expected)}"


def test_the_series_recall_stays_at_the_measured_level():
    total = hits = 0
    for image, frame in series():
        found = board.find_units(frame)
        for unit in ground_truth()[image]:
            if unit["status"] != "full":
                continue
            total += 1
            pos = unit["pos"]
            if any((pos[0] - x) ** 2 + (pos[1] - y) ** 2 <= MATCH_RADIUS**2 for x, y in found):
                hits += 1

    assert total >= 100
    assert hits / total >= 0.95, f"recall {hits}/{total}"


def test_flat_arc_shape_gates_would_have_gone_blind_here():
    """最小縮放下 HP 弧與隊徽環併成一個環：這就是密度峰取代形狀閘門的理由。"""
    frame = dict(series())["03_pt3_pan_up.png"]
    expected = [unit for unit in ground_truth()["03_pt3_pan_up.png"] if unit["status"] == "full"]

    assert len(board.find_units(frame)) >= len(expected)


def test_the_arc_hint_is_reported_but_never_a_faction():
    frame = dict(series())["03_pt3_pan_up.png"]

    sightings = board.find_sightings(frame)

    assert sightings
    assert {sighting.hint for sighting in sightings} <= {
        board.RED_HINT,
        board.BLUE_HINT,
        board.TEAL_HINT,
        None,
    }
    assert not hasattr(sightings[0], "faction")


@pytest.mark.parametrize(("dx", "dy"), [(250, 0), (-250, 0), (0, 170), (0, -170)])
def test_phase_correlation_recovers_a_nudge_sized_pan(dx, dy):
    base = dict(series())["03_pt3_pan_up.png"]
    moved = np.roll(np.roll(base, dy, axis=0), dx, axis=1)

    shift = board.measure_shift(base, moved)

    assert shift.source == "phase"
    assert shift.dx == pytest.approx(dx, abs=2)
    assert shift.dy == pytest.approx(dy, abs=2)


def test_the_constellation_vote_measures_a_pan_without_any_texture():
    """星空上相位相關會瞎掉，單位星座還在。"""
    before = ((100.0, 100.0), (400.0, 300.0), (700.0, 500.0))
    after = tuple((x + 250, y + 10) for x, y in before)

    vote = board._constellation_shift(before, after)

    assert vote is not None
    assert (round(vote[0]), round(vote[1])) == (250, 10)


def test_a_tied_constellation_refuses_to_guess():
    before = ((0.0, 0.0), (100.0, 0.0))
    after = ((500.0, 0.0), (600.0, 0.0), (0.0, 0.0), (100.0, 0.0))

    assert board._constellation_shift(before, after) is None


def test_too_few_units_is_no_constellation_at_all():
    assert board._constellation_shift(((0.0, 0.0),), ((10.0, 0.0),)) is None


def test_an_unmeasurable_shift_says_so_instead_of_returning_zero():
    flat = np.zeros((1080, 2340, 3), np.uint8)

    shift = board.measure_shift(flat, flat)

    assert shift.source == "none"
    assert not shift.known


def test_the_pan_gesture_drags_the_content_the_other_way():
    """往東看＝手指把內容往西拉。"""
    x1, y1, x2, y2 = board.pan_gesture("east", (1170.0, 500.0))

    assert (x1, y1) == (1170, 500)
    assert x2 < x1 and y2 == y1

    _, _, _, south_y = board.pan_gesture("south", (1170.0, 500.0))
    assert south_y < 500


def test_the_pan_gesture_takes_the_reach_the_caller_worked_out():
    """腿長由掃描端依無歧義量測範圍算，不是固定的 PAN_HALF。"""
    x1, _, x2, _ = board.pan_gesture("west", (1170.0, 500.0), 140.0)

    assert x2 - x1 == 140


def test_the_lattice_reader_still_reads_the_minimum_zoom_grid():
    """0731 pinch 煙測：縮到最小之後欄距 91.5／列距 86，舊的單一間距帶讀不到，
    整段 grid_on 因此翻 False（掃描的符號前置條件會憑空失效）。"""
    expect = json.loads((SERIES.parent / "min_zoom_grid_20260731.json").read_text(encoding="utf-8"))
    crop = cv2.imread(str(SERIES.parent / "min_zoom_grid_20260731.png"))
    x, y, w, h = expect["box"]
    canvas = np.zeros((1080, 2340, 3), np.uint8)
    canvas[y : y + h, x : x + w] = crop

    lattice = board.read_lattice(canvas)

    assert lattice is not None
    assert list(lattice.cols) == expect["expect"]["cols"]
    assert list(lattice.rows) == expect["expect"]["rows"]
    assert 60 <= lattice.col_pitch <= 105


def test_the_coarse_band_alone_would_have_gone_blind_on_the_zoomed_out_grid():
    """細帶先試是防混疊的關鍵：粗帶的最小間距套在細格網上會隔行取線，湊出翻倍的
    「均勻」格距——那是自信錯值，不是讀不到。"""
    expect = json.loads((SERIES.parent / "min_zoom_grid_20260731.json").read_text(encoding="utf-8"))
    crop = cv2.imread(str(SERIES.parent / "min_zoom_grid_20260731.png"))
    x, y, w, h = expect["box"]
    canvas = np.zeros((1080, 2340, 3), np.uint8)
    canvas[y : y + h, x : x + w] = crop

    assert board.read_lattice(canvas, bands=((90, 160),)) is None


def test_the_default_zoom_lattice_is_untouched_by_the_extra_band():
    """既有標定不因為多一條細帶而改讀數。"""
    expected = json.loads(
        (Path(__file__).resolve().parent / "fixtures" / "vision" / "grid" / "grid_on_lattice.json")
        .read_text(encoding="utf-8")
    )["expect"]

    lattice = board.read_lattice(load("grid/hub_grid_on_20260719"), bands=((90, 160),))

    assert list(lattice.cols) == expected["cols"]
    assert list(lattice.rows) == expected["rows"]


def test_replaying_the_real_series_keeps_the_bookkeeping_honest():
    """半真實案例：0719 的九幀是用舊腿長拍的（一腿約 600px，量測窗 620 高），
    所以縱向那幾腿本來就量不準——重點不是它掃得完，而是**量不到的時候不會亂寫**：
    斷鏈一律進島嶼，重錨不成就丟掉，出來的每一格都有實際覆蓋過的幀撐著。
    """
    survey = coverage.Survey()
    for name, frame in series():
        direction = (
            "north" if "up" in name else "south" if "down" in name else "east" if "right" in name else None
        )
        leg = None
        if direction is not None:
            dx, dy = board.DIRECTIONS[direction]
            leg = coverage.Leg(direction, 250.0, (-dx * 575.0, -dy * 575.0))
        survey.observe(frame, leg)

    summary = survey.summary()
    islands = summary["islands"]

    assert survey.anchored
    assert summary["units"] > 10
    assert summary["unlocalised"] > 0
    assert islands["isolated"] == islands["merged"] + islands["discarded"] + bool(islands["open"])
    # STALE 是換代才有的狀態，一輪掃描裡不該冒出來
    assert summary["cells"]["stale"] == 0
