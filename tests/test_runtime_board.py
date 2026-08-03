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
from tests.fixtures.synthetic_map import (
    COL_PITCH,
    World,
    blind_correlator,
    void_outside,
)

# 這一批對著 board.py 的像素機制，地圖鋪滿畫布最單純：要造地圖終止邊時各案例自己
# 用 void_outside 挖，不靠世界外圍那一圈虛空。
NO_VOID = (0, 0)

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
    """地圖以外那片無特徵的深色背景（下稱星空）上相位相關會瞎掉，單位排列比對還在。"""
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


def test_two_deltas_inside_the_tolerance_land_in_the_same_group():
    """0801 第 7 輪的八把殺手：固定桶 `round(delta/24)` 把差 20px 的兩對切進不同的
    桶（t49 的 (−129,0) 與 (−130,+20)），最高票掉到 1，整條單位排列比對的佐證缺席。"""
    before = ((400.0, 400.0), (900.0, 380.0))
    after = ((271.0, 400.0), (770.0, 400.0))

    vote = board._constellation_shift(before, after)

    assert vote is not None
    assert vote[0] == pytest.approx(-129.5, abs=1.0)
    assert vote[1] == pytest.approx(10.0, abs=1.0)


def test_a_tied_tally_is_broken_by_the_side_that_leaves_no_stragglers():
    """票數只數支持不數矛盾：兩個候選各拿兩票，但「沒動」那一邊要憑空生出兩台
    落在偵測帶正中央的單位，「動了 500」那一邊多出來的兩台是從帶外滑進來的。"""
    before = ((600.0, 400.0), (700.0, 400.0))
    after = ((600.0, 400.0), (700.0, 400.0), (1100.0, 400.0), (1200.0, 400.0))

    vote = board._constellation_shift(before, after)

    assert vote is not None
    assert vote[0] == pytest.approx(500.0, abs=1.0)
    assert board._pairing_score(before, after, (500.0, 0.0)) > board._pairing_score(
        before, after, (0.0, 0.0)
    )


def test_an_unmeasurable_shift_says_so_instead_of_returning_zero():
    flat = np.zeros((1080, 2340, 3), np.uint8)

    shift = board.measure_shift(flat, flat)

    assert shift.source == "none"
    assert not shift.known


# ---- 目視終止邊的位移（v2.10，v3 拿它當獨立於像素量測的佐證來源） ----


def test_a_terminal_edge_seen_in_both_frames_measures_the_pan_on_its_own():
    """地圖的物理邊界不是週期訊號，格線與同型機編隊那種「差整數個週期」的誤配都動不了
    它。這裡整幀沒有半台單位、相關器也只有虛空噪點可看，位移仍然量得出來。"""
    world = World(margin=NO_VOID, cols=22, rows=12, units=())
    # 虛空從最外一條線的右邊開始：地圖到此為止，那條線就是物理邊界
    lit = COL_PITCH * 12 + 8
    step = COL_PITCH * 2
    before = void_outside(world.frame(), (0, 0, lit, 1080))
    world.move(float(step), 0.0)
    after = void_outside(world.frame(), (0, 0, lit - step, 1080))

    spans = (board.read_span(before), board.read_span(after))
    assert all("east" in span.edges for span in spans)

    borders = [{side: span.border(side) for side in span.edges} for span in spans]

    assert board.edge_shift(borders[0], borders[1], "x") == pytest.approx(-step, abs=4.0)


def test_two_terminal_edges_that_disagree_are_both_dropped():
    """兩側各量一次同一個剛體平移，差太多就代表至少一側不是地圖邊——挑一個信
    等於再開一條「量錯寫入」的路。"""
    seen = {"west": 200.0, "east": 1300.0}
    # 西邊挪了 100、東邊一步沒動＝至少一側量的不是同一件事
    drifted = {"west": 100.0, "east": 1300.0}

    assert board.edge_shift(seen, drifted, "x") is None
    assert board.edge_shift(seen, seen, "x") == 0.0
    assert board.edge_shift(seen, {"north": 0.0}, "x") is None


def _formation(cells: tuple[tuple[int, int], ...]) -> World:
    """同一張畫布、只換單位擺位：背景逐像素相同，單位排列比對卻換了一批。"""
    return World(margin=NO_VOID, cols=22, rows=12, units=cells)


ROW = ((3, 3), (4, 3), (5, 3), (6, 3))
ROW_SHIFTED = ((4, 3), (5, 3), (6, 3), (7, 3))


def test_a_formation_alias_vote_is_overruled_by_the_picture(monkeypatch):
    """週期陣列投出的幽靈票（票數十足、位置整批錯開一個週期的票）：偵測到的那一排薩克整批往右錯一個編隊間距，配對投票就投出
    票數十足的 +一格位移——但畫面根本沒動。0801 台數膨脹的第二顆齒輪。"""
    blind_correlator(monkeypatch)
    before = _formation(ROW).frame()
    after = _formation(ROW_SHIFTED).frame()

    vote = board._constellation_shift(board.find_units(before), board.find_units(after))
    assert vote is not None
    assert vote[0] == pytest.approx(COL_PITCH, abs=6.0)

    assert board.null_check(before, after, (vote[0], vote[1])) == board.NULL_STILL

    shift = board.measure_shift(before, after)
    assert shift.source == board.CONSTELLATION_STILL
    assert (shift.dx, shift.dy) == (0.0, 0.0)
    assert shift.known


def test_a_real_pan_still_beats_the_null_hypothesis(monkeypatch):
    """守成：複驗閘只否決對不上畫面的票，真移動照過（不然掃描全程定位中斷）。"""
    blind_correlator(monkeypatch)
    world = _formation(ROW)
    before = world.frame()
    world.move(0.0, 150.0)
    after = world.frame()

    assert board.null_check(before, after, (0.0, -150.0)) == board.NULL_MOVED

    shift = board.measure_shift(before, after)
    assert shift.source == board.WITNESS_CONSTELLATION
    assert shift.dy == pytest.approx(-150.0, abs=6.0)


def test_the_null_check_says_nothing_when_there_is_nothing_to_look_at():
    """鏡頭底下沒幾台＝裁判沒得看。這時要回 blind（呼叫端照舊處置），不是 unclear
    ——把「裁判缺席」當成「兩個假設都不對」會讓空曠地帶整段定位中斷。"""
    world = _formation(((3, 3),))
    before = world.frame()
    world.move(0.0, 150.0)

    assert board.null_check(before, world.frame(), (0.0, -150.0)) == board.NULL_BLIND


def test_the_lattice_falls_back_to_a_sub_window_when_the_band_runs_out_of_lines():
    """地圖走到邊緣只剩右下一角有格線：全幀帶的線數湊不到門檻，相位閘於是整段
    停擺（0801 t7-t13 七幀全 None，兩把各滑了 200px 卻被記成停滯）。"""
    frame = void_outside(_formation(ROW).frame(), board.LATTICE_WINDOWS[3])

    assert board.read_lattice(frame) is None

    lattice = board.find_lattice(frame)

    assert lattice is not None
    assert lattice.col_pitch == pytest.approx(COL_PITCH, abs=4.0)
    x, y, w, h = board.LATTICE_WINDOWS[3]
    assert all(x <= col <= x + w for col in lattice.cols)


def test_the_sub_window_lattice_is_only_a_fallback():
    """全幀帶讀得出來就用全幀帶：子窗的取樣量少，pitch 不該由它決定。"""
    frame = _formation(ROW).frame()

    assert board.find_lattice(frame) == board.read_lattice(frame)


def test_the_median_residual_shrugs_off_one_jittery_line():
    """0801 逐幀實測單線位置抖動 ±10px，而相位閘的容差只有 0.25 pitch。"""
    lines = [110.0, 190.0, 280.0, 370.0, 460.0]

    assert board.median_residual(lines, 90.0, 100.0) == pytest.approx(0.0, abs=0.01)


def test_the_median_residual_does_not_split_a_phase_that_straddles_the_cell_edge():
    """真值卡在 ±pitch/2 時，直接對 wrap 過的值取中位數會分裂到圓的兩端、
    中位數落在離真值最遠的地方。"""
    lines = [163.0, 291.0, 421.0, 549.0]

    assert abs(board.median_residual(lines, 128.0, 100.0)) == pytest.approx(64.0, abs=2.0)


def test_the_pan_gesture_drags_the_content_the_other_way():
    """往東看＝手指把內容往西拉。"""
    x1, y1, x2, y2 = board.pan_gesture("east", (1170.0, 500.0))

    assert (x1, y1) == (1170, 500)
    assert x2 < x1 and y2 == y1

    _, _, _, south_y = board.pan_gesture("south", (1170.0, 500.0))
    assert south_y < 500


def test_the_pan_gesture_takes_the_reach_the_caller_worked_out():
    """平移距離由掃描端依無歧義量測範圍算，不是固定的 PAN_HALF。"""
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
    """細帶先試是防「差整數個週期誤配」的關鍵：粗帶的最小間距套在細格網上會隔行取線，湊出翻倍的
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


# 這一幀在真實截圖上讀得到北側的地圖終止邊（其餘八幀四側都讀不到）。
CORNER_FRAME = "05_pt5_pan_up_small.png"


def test_a_real_frame_can_anchor_the_world_and_hand_over_a_landmark():
    """歸零那一關要的是真畫面：連續兩次推不動，而且角落那一側的地圖終止邊看得見。
    這裡整段都用實機截圖跑，證明目視的邊在真實像素上撐得住定位的起點。"""
    corner = dict(series())[CORNER_FRAME]
    survey = coverage.Survey()

    survey.observe(corner)
    for direction in coverage.ZERO_CORNER:
        for _ in range(coverage.STALL_CONFIRM):
            survey.observe(corner, coverage.Leg(direction, 260.0, (0.0, 0.0)))

    assert survey.anchored
    assert survey.offset == (0.0, 0.0)
    assert "north" in survey.landmarks
    assert survey.chart.boundary["north"] == coverage._border_cell(
        survey.chart.grid, "north", survey.landmarks["north"]
    )


CORNER_DEADLOCK_FIXTURES = (
    Path(__file__).resolve().parent / "fixtures" / "vision" / "map_scan" / "edges_20260803"
)


def test_the_round_9_deadlock_frame_now_anchors_through_the_quadrant_fallback():
    """第 9 輪死因幀（`t21-leg.png`）：`read_lattice` 的全幀取樣帶在這裡讀不到格網
    （格線只填滿取樣帶右下一角），`_anchor` 曾經因此永遠回 False、連三次 ZERO_TRIES
    耗盡卡死。改吃 `find_lattice`（有象限退路）之後這裡要能錨定；北緣是象限窗搆不到
    的那一列，靠邊界目擊補回負格列，不是憑空消失。"""
    corner = cv2.imread(str(CORNER_DEADLOCK_FIXTURES / "t21-leg.png"))
    assert corner is not None
    survey = coverage.Survey()

    survey.observe(corner)
    for direction in coverage.ZERO_CORNER:
        for _ in range(coverage.STALL_CONFIRM):
            survey.observe(corner, coverage.Leg(direction, 260.0, (0.0, 0.0)))

    assert survey.anchored
    assert survey.tries == 0
    assert {"north", "west"} <= set(survey.landmarks)
    north_line = coverage._border_cell(survey.chart.grid, "north", survey.landmarks["north"])
    assert north_line < 0
    assert survey.chart.boundary["north"] == north_line
    assert survey.chart.in_bounds((3, north_line))


def test_replaying_the_real_series_never_writes_a_frame_it_could_not_place():
    """半真實案例：0719 的九幀是用舊的大步幅拍的（一把約 600px），v3 的定位窗根本
    收不下——重點不是它掃得完，而是**收不下的時候不會亂寫**：定位不出來的幀整張
    丟掉，出來的每一格都有實際覆蓋過的幀撐著。
    """
    corner = dict(series())[CORNER_FRAME]
    survey = coverage.Survey()
    survey.observe(corner)
    for direction in coverage.ZERO_CORNER:
        for _ in range(coverage.STALL_CONFIRM):
            survey.observe(corner, coverage.Leg(direction, 260.0, (0.0, 0.0)))
    assert survey.anchored

    placed = 0
    for name, frame in series():
        direction = (
            "north" if "up" in name else "south" if "down" in name else "east" if "right" in name else None
        )
        leg = None
        if direction is not None:
            dx, dy = board.DIRECTIONS[direction]
            leg = coverage.Leg(direction, 250.0, (-dx * 575.0, -dy * 575.0))
        if survey.observe(frame, leg).verdict != coverage.BROKEN:
            placed += 1

    summary = survey.summary()

    assert summary["unlocalised"] > 0
    # 收得下的每一幀都寫得出格子；一格都沒有的話這條斷言就只是在測「什麼都沒做」
    assert placed >= 1
    assert summary["cells"]["unit"] == len(survey.units())
    # STALE 是換代才有的狀態，一輪掃描裡不該冒出來
    assert summary["cells"]["stale"] == 0
