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

from ggge_ai.runtime import board
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


def test_an_unchanged_frame_after_a_pan_means_the_edge():
    frame = dict(series())["01_pt1_first_anchor.png"]

    assert board.at_edge(frame, frame) is True


def test_a_frame_that_moved_is_not_the_edge():
    base = dict(series())["03_pt3_pan_up.png"]
    moved = np.roll(base, 250, axis=1)

    assert board.at_edge(base, moved) is False


def test_the_pan_origin_dodges_every_detected_unit():
    """起手落在單位精靈上會被遊戲吃掉（看起來像到邊但鏡頭沒動）。"""
    crowded = tuple(
        board.Sighting((float(x), 470.0)) for x in (760, 940, 1170, 1400, 1580)
    )

    origin = board.pick_pan_origin(crowded)

    assert origin in board.PAN_ORIGIN_GRID
    assert origin[1] != 470.0


def test_the_pan_origin_falls_back_to_the_middle_when_nothing_is_seen():
    assert board.pick_pan_origin(()) in board.PAN_ORIGIN_GRID


def test_the_pan_gesture_drags_the_content_the_other_way():
    """往東看＝手指把內容往西拉。"""
    x1, y1, x2, y2 = board.pan_gesture("east", (1170.0, 500.0))

    assert (x1, y1) == (1170, 500)
    assert x2 < x1 and y2 == y1

    _, _, _, south_y = board.pan_gesture("south", (1170.0, 500.0))
    assert south_y < 500


def test_the_cursor_accumulates_offsets_and_merges_repeat_sightings():
    base = dict(series())["03_pt3_pan_up.png"]
    moved = np.roll(base, -250, axis=1)
    cursor = board.ScanCursor()

    cursor.feed(base)
    first = len(cursor.scan.sightings)
    offset = cursor.feed(moved)

    assert offset[0] == pytest.approx(250, abs=3)
    assert cursor.scan.frames == 2
    assert cursor.scan.unlocalised == 0
    # 同一批單位換了個鏡頭位置：世界座標對上就不該長出第二份
    assert len(cursor.scan.sightings) <= first + 3


def test_the_cursor_flags_frames_it_could_not_localise():
    flat = np.zeros((1080, 2340, 3), np.uint8)
    cursor = board.ScanCursor()

    cursor.feed(flat)
    cursor.feed(flat)

    assert cursor.scan.unlocalised == 1


def test_the_walk_stops_a_direction_at_its_edge_and_records_it():
    frames = [
        dict(series())["03_pt3_pan_up.png"],
        np.roll(dict(series())["03_pt3_pan_up.png"], -250, axis=1),
    ]
    served: list[np.ndarray] = []
    pans: list[tuple[str, tuple[int, int, int, int]]] = []

    def capture():
        frame = frames[min(len(served), len(frames) - 1)]
        served.append(frame)
        return frame

    def pan(direction, origin):
        pans.append((direction, board.pan_gesture(direction, origin)))

    scan = board.walk(capture, pan, itinerary=("west", "north"), legs_per_direction=3)

    # 第二腿之後畫面不再變（腳本卡在最後一幀）＝到邊，兩個方向各記一次
    assert scan.edges == {"west", "north"}
    assert scan.frames >= 2
    assert [direction for direction, _ in pans].count("west") <= 3


def test_the_scan_reports_bounds_from_what_it_actually_saw():
    cursor = board.ScanCursor()
    cursor.feed(dict(series())["03_pt3_pan_up.png"])

    bounds = cursor.scan.bounds

    assert bounds is not None
    assert bounds[0] < bounds[2] and bounds[1] < bounds[3]


def test_an_empty_scan_has_no_bounds_and_no_cells():
    scan = board.BoardScan()

    assert scan.bounds is None
    assert scan.cells == []
