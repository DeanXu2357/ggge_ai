"""四態知識圖、前緣補掃與五層量測防禦。

單元層對著手寫的圖與座標，整段行為對著合成世界（tests/fixtures/synthetic_map）：
單位擺在哪一格、鏡頭移了多少都是我們定的，所以「四態逐格正確」「跳過的帶被回補」
這種斷言才有地面真相可對。實幀系列另有半真實回放（test_runtime_board）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pytest

from ggge_ai.runtime import board, coverage
from ggge_ai.runtime.coverage import (
    ACCEPTED,
    BROKEN,
    STALLED,
    FrameView,
    Island,
    Knowledge,
    KnowledgeMap,
    Leg,
    Odometer,
    Reading,
    Survey,
    WorldGrid,
)
from ggge_ai.runtime.perceive import Observation
from ggge_ai.stage.actions import SurveyBoard
from ggge_ai.stage.survey import survey_drivers
from tests.fixtures.synthetic_map import World

GRID = WorldGrid(phase=(0.0, 0.0), col_pitch=100.0, row_pitch=100.0)
# 一格 100px 的小視窗：手算得出來哪幾格「整格看得清楚」。
WINDOW = (0, 0, 400, 300)
UNITS = ((3, 2), (5, 4), (9, 6), (14, 3), (18, 9))


def view(offset=(0.0, 0.0), units=(), region=WINDOW, holes=()):
    return FrameView(offset=offset, units=tuple(units), region=region, holes=tuple(holes))


def chart(**kwargs) -> KnowledgeMap:
    return KnowledgeMap(grid=GRID, **kwargs)


def test_the_world_grid_maps_pixels_to_cells_in_both_directions():
    assert GRID.cell_of((0.0, 0.0)) == (0, 0)
    assert GRID.cell_of((99.0, 250.0)) == (0, 2)
    # 負座標是常態：世界原點是 turn-1 首幀，地圖往西往北都可能繼續
    assert GRID.cell_of((-1.0, -1.0)) == (-1, -1)
    assert GRID.centre_of((1, 1)) == (150.0, 150.0)


def test_only_whole_cells_inside_the_band_count_as_scanned():
    """被螢幕邊切一半的格不算掃過——那裡漏看一台單位是沉默的錯。"""
    seen = coverage.covered(GRID, view(region=(0, 0, 350, 250)))

    assert seen == ((0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1))


def test_cells_under_a_hud_hole_are_never_called_empty():
    """回合橫幅蓋住的那一角讀不到單位，所以它不是空的，是沒掃。"""
    seen = coverage.covered(GRID, view(holes=[(0, 0, 150, 150)]))

    assert (0, 0) not in seen
    assert (1, 1) not in seen
    assert (2, 2) in seen


def test_absorbing_a_frame_marks_empty_then_stamps_the_sightings():
    world = chart()

    world.absorb(view(units=[board.Sighting((250.0, 150.0), board.RED_HINT)]))

    assert world.knowledge((2, 1)) is Knowledge.UNIT
    assert world.knowledge((0, 0)) is Knowledge.EMPTY
    assert world.units() == (((2, 1), board.RED_HINT),)


def test_a_seen_unit_survives_a_later_frame_that_simply_missed_it():
    """掃描在我方回合，敵單位不會移動：同一代裡「看得清楚卻沒目擊」＝偵測漏，
    不是離開。無條件鋪 EMPTY 的話一次漏檢就抹掉整格知識（0801 複驗：23 個目擊
    最後只記得 10 台）。"""
    world = chart()
    world.absorb(view(units=[board.Sighting((250.0, 150.0), board.RED_HINT)]))

    world.absorb(view())

    assert world.knowledge((2, 1)) is Knowledge.UNIT
    assert world.units() == (((2, 1), board.RED_HINT),)
    assert world.knowledge((0, 0)) is Knowledge.EMPTY


def test_a_fresh_sighting_on_the_same_cell_still_updates_the_mark():
    """滯後保的是「有單位」這件事，不是舊座標：本幀量到的世界像素照樣蓋上去，
    不然重定位器比對的是過期的星座。"""
    world = chart()
    world.absorb(view(units=[board.Sighting((250.0, 150.0), board.RED_HINT)]))

    world.absorb(view(units=[board.Sighting((262.0, 158.0), board.BLUE_HINT)]))

    assert world.marks[(2, 1)] == board.Sighting((262.0, 158.0), board.BLUE_HINT)
    assert world.units() == (((2, 1), board.BLUE_HINT),)


def test_a_stale_cell_is_downgraded_by_an_empty_view_because_the_enemy_did_move():
    """跨代才是單位離開的合法證據：expire() 之後同款的 view 照常蓋成 EMPTY。"""
    world = chart()
    world.absorb(view(units=[board.Sighting((250.0, 150.0), board.RED_HINT)]))
    world.expire()
    assert world.knowledge((2, 1)) is Knowledge.STALE

    world.absorb(view())

    assert world.knowledge((2, 1)) is Knowledge.EMPTY
    assert world.marks == {}


def test_a_sighting_outside_the_readable_band_is_not_written_at_all():
    """半個機體露在畫面外時峰的位置不可信：寧可留 UNKNOWN 等前緣回補。"""
    world = chart()

    world.absorb(view(region=(0, 0, 250, 250), units=[board.Sighting((350.0, 150.0))]))

    assert world.knowledge((3, 1)) is Knowledge.UNKNOWN
    assert world.units() == ()


def test_scanned_empty_and_never_scanned_are_different_facts():
    world = chart()
    world.absorb(view())

    assert world.knowledge((0, 0)) is Knowledge.EMPTY
    assert world.knowledge((9, 9)) is Knowledge.UNKNOWN
    assert (9, 9) not in world.charted


def test_the_frontier_hugs_the_charted_edge_instead_of_the_whole_plane():
    """界內在四旗全定之前是無限大，所以前緣只認測繪區周邊——不然缺口清單無限長。"""
    world = chart()
    world.absorb(view())

    front = set(world.frontier())

    assert (4, 0) in front
    assert (0, 3) in front
    assert (9, 9) not in front


def test_a_fixed_boundary_takes_the_cells_beyond_it_out_of_bounds():
    world = chart()
    world.absorb(view())
    world.fix_boundary("west", view())

    assert world.boundary["west"] == 0
    assert not world.in_bounds((-1, 0))
    assert (-1, 0) not in world.frontier()


def test_the_boundary_lands_on_the_outermost_cell_we_can_actually_read():
    """界線取「看得清楚的最外一格」而不是地圖美術的邊：看不全的半格永遠補不完，
    畫進界內會讓前緣永遠不空。"""
    world = chart()

    line = world.fix_boundary("east", view(region=(0, 0, 350, 300)))

    assert line == 2


def test_completion_needs_all_four_flags_and_an_empty_interior():
    world = chart()
    world.absorb(view())
    for direction, line in (("west", 0), ("east", 4), ("north", 0), ("south", 2)):
        world.boundary[direction] = line

    assert world.gaps() == ((4, 0), (4, 1), (4, 2))
    assert not world.complete

    world.absorb(view(offset=(100.0, 0.0)))

    assert world.gaps() == ()
    assert world.complete


def test_expiry_downgrades_the_units_and_keeps_the_geometry():
    world = chart()
    world.absorb(view(units=[board.Sighting((250.0, 150.0))]))
    world.boundary["west"] = 0

    world.expire()

    assert world.knowledge((2, 1)) is Knowledge.STALE
    assert world.knowledge((0, 0)) is Knowledge.UNKNOWN
    assert world.boundary == {"west": 0}
    assert (0, 0) in world.charted
    # 前代的站位永遠不能當現況，但它仍然是缺口——整張圖都要重掃
    assert world.units() == ()
    assert (2, 1) in world.frontier()
    assert (0, 0) in world.frontier()


def test_clusters_are_four_connected_components():
    pockets = coverage.clusters([(0, 0), (1, 0), (0, 1), (5, 5), (5, 6)])

    assert pockets == (((0, 0), (0, 1), (1, 0)), ((5, 5), (5, 6)))


def test_a_stale_cluster_outranks_a_slightly_nearer_unknown_one():
    """含 STALE ＝ 單位大概率在附近，威脅評估最需要，所以距離打折。是加權不是絕對
    優先：夠遠的 STALE 仍然排在眼前的缺口後面。"""
    world = chart()
    world.charted.update({(0, 0), (5, 0)})
    world.state[(0, 0)] = Knowledge.STALE
    world.state[(5, 0)] = Knowledge.EMPTY

    # 視口在 x=300：STALE 那團的質心 250px 遠打折成 125，最近的未知團 150——折扣
    # 翻轉了選擇。視口拉到 x=700 之後 STALE 團 650px 打折仍有 325，眼前 50px 的
    # 未知團贏回來。
    assert (0, 0) in world.choose((300.0, 50.0))
    assert (0, 0) not in world.choose((700.0, 50.0))


def test_the_envelope_gate_accepts_the_commanded_leg():
    assert board.envelope(board.Shift(-330.0, 2.0, 0.9, "phase"), (-350.0, 0.0)) == (
        board.ENVELOPE_OK
    )


def test_the_envelope_gate_flags_a_double_execution_but_still_takes_it():
    """腿長規則保證 2× 仍落在無歧義範圍內，所以照量入帳——被跳過的帶留 UNKNOWN
    由前緣回補，不構成錯誤。"""
    assert board.envelope(board.Shift(-700.0, 0.0, 0.9, "phase"), (-350.0, 0.0)) == (
        board.ENVELOPE_REPEAT
    )


@pytest.mark.parametrize(
    "shift",
    [
        board.Shift(1250.0, 0.0, 0.9, "phase"),  # 繞回混疊：差一個窗寬、反號
        board.Shift(-1950.0, 0.0, 0.9, "phase"),  # 繞回混疊：另一側
        board.Shift(-330.0, 400.0, 0.9, "phase"),  # 同軸閘：垂直分量爆掉
    ],
)
def test_the_envelope_gate_refuses_the_confident_wrong_values(shift):
    assert board.envelope(shift, (-350.0, 0.0)) == board.ENVELOPE_REFUSED


def test_an_uncommanded_frame_may_only_have_stood_still():
    assert board.envelope(board.Shift(3.0, 1.0, 0.9, "phase"), None) == board.ENVELOPE_OK
    assert board.envelope(board.Shift(600.0, 0.0, 0.9, "phase"), None) == board.ENVELOPE_REFUSED


def test_the_phase_residual_is_the_signed_distance_to_the_nearest_line():
    assert board.phase_residual(384.0, 128.0, 0.0) == 0.0
    assert board.phase_residual(388.0, 128.0, 0.0) == pytest.approx(4.0)
    assert board.phase_residual(380.0, 128.0, 0.0) == pytest.approx(-4.0)


def test_the_relocaliser_solves_the_offset_from_the_recorded_sightings():
    known = ((100.0, 100.0), (400.0, 300.0), (700.0, 500.0))
    seen = tuple((x + 256.0, y) for x, y in known)

    drift = board.relocalise(known, seen)

    assert drift is not None
    assert (round(drift[0]), round(drift[1])) == (256, 0)


def test_the_relocaliser_refuses_to_guess_without_a_unique_mode():
    assert board.relocalise(((0.0, 0.0),), ((10.0, 0.0),)) is None


def _synthetic() -> World:
    return World(cols=22, rows=12, units=UNITS)


def test_the_odometer_holds_everything_back_when_the_measurement_is_unusable():
    world = _synthetic()
    odometer = Odometer(previous=world.frame())
    before = odometer.offset

    reading = odometer.feed(np.zeros((1080, 2340, 3), np.uint8))

    assert reading.verdict == BROKEN
    assert reading.reason == "unmeasurable"
    assert odometer.offset == before


def test_the_odometer_calls_an_unmoved_view_a_stall_not_a_measurement():
    world = _synthetic()
    frame = world.frame()
    odometer = Odometer(previous=frame)

    reading = odometer.feed(world.frame(), (-350.0, 0.0))

    assert reading.verdict == STALLED
    # 相位相關對零位移有半像素的系統偏差；停滯必須量成準確的 0，不然累成整格漂移
    assert odometer.offset == (0.0, 0.0)


def test_the_odometer_tracks_a_real_leg_and_snaps_it_to_the_grid_phase():
    world = _synthetic()
    frame = world.frame()
    grid = WorldGrid.anchor(board.read_lattice(frame))
    odometer = Odometer(grid=grid, previous=frame)
    world.move(300.0, 0.0)

    reading = odometer.feed(world.frame(), (-300.0, 0.0))

    assert reading.verdict == ACCEPTED
    assert odometer.offset[0] == pytest.approx(300.0, abs=2.0)


def test_the_odometer_refuses_a_jump_the_command_cannot_explain():
    world = _synthetic()
    frame = world.frame()
    grid = WorldGrid.anchor(board.read_lattice(frame))
    odometer = Odometer(grid=grid, previous=frame)
    world.move(476.0, 0.0)

    reading = odometer.feed(world.frame(), (-150.0, 0.0))

    assert reading.verdict == BROKEN
    assert odometer.offset == (0.0, 0.0)


@dataclass
class Rig:
    """腳本化鏡頭：手指行程乘上增益推鏡頭，畫布邊界就是地圖邊界。

    blank 數的是**截圖次數**，而取幀靜止閘讓每一次 observe 花掉兩張圖（f1、f2 各
    一），所以第 k 次 observe 拿到的是第 2k 張——合成世界瞬時靜止，第一輪就過閘。

    blind ＝ 那幾張截圖的單位沒畫出來（偵測漏的合成版）：背景與格線逐像素相同，
    只有機體環不見了，所以量測照舊、目擊憑空少一批。
    """

    world: World
    gain: float = 2.0
    swipes: int = 0
    shots: int = 0
    eaten: tuple[int, ...] = ()
    doubled: tuple[int, ...] = ()
    blank: tuple[int, ...] = ()
    blind: tuple[int, ...] = ()
    jumps: dict[int, tuple[float, float]] = field(default_factory=dict)
    bare: World | None = None

    def capture(self) -> np.ndarray:
        self.shots += 1
        if self.shots in self.blank:
            return np.zeros((1080, 2340, 3), np.uint8)
        if self.shots in self.blind:
            return self._bare_frame()
        return self.world.frame()

    def _bare_frame(self) -> np.ndarray:
        if self.bare is None:
            self.bare = World(cols=self.world.cols, rows=self.world.rows, units=())
        self.bare.camera = self.world.camera
        return self.bare.frame()

    def tap(self, x: int, y: int, intent: str = "") -> None:
        raise AssertionError("掃描不點任何東西")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_s: float) -> None:
        self.swipes += 1
        if self.swipes in self.eaten:
            return
        jump = self.jumps.get(self.swipes)
        if jump is not None:
            self.world.move(*jump)
            return
        scale = 2.0 if self.swipes in self.doubled else 1.0
        self.world.move((x1 - x2) * self.gain * scale, (y1 - y2) * self.gain * scale)


def sweep(rig: Rig, ticks: int = 40):
    driver, ledger = survey_drivers(rig.capture, rig, sleep=lambda _: None)
    ledger.zoomed = True
    for _ in range(ticks):
        driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))
        if ledger.synced:
            break
    return driver, ledger


def unit_cells(ledger, world: World) -> tuple[list, list]:
    grid = ledger.survey.chart.grid
    want = sorted(grid.cell_of(world.centre(cell)) for cell in world.units)
    return want, sorted(cell for cell, _ in ledger.cells())


def test_the_survey_converges_on_a_known_world_and_places_every_unit():
    world = _synthetic()

    _, ledger = sweep(Rig(world))

    assert ledger.synced
    want, got = unit_cells(ledger, world)
    assert got == want
    census = ledger.summary()["cells"]
    assert census["unit"] == len(world.units)
    assert census["empty"] > 100
    assert census["stale"] == 0


def test_a_scan_that_misses_units_on_some_frames_still_ends_with_all_of_them():
    """A6 的簽名：偵測漏一幀就抹掉那一格，整輪掃完記得的遠少於世界真值（0801
    複驗：單幀 23 個目擊，整輪只記 10 台）。同一代內單位數只准增加。"""
    world = _synthetic()
    # 第 3、6、9… 次 observe 的那一幀看不到任何單位（截圖序號 ＝ observe 序號 ×2）
    rig = Rig(world, blind=tuple(range(6, 200, 6)))
    driver, ledger = survey_drivers(rig.capture, rig, sleep=lambda _: None)
    ledger.zoomed = True

    tally: list[int] = []
    for _ in range(40):
        driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))
        tally.append(len(ledger.cells()))
        if ledger.synced:
            break

    assert ledger.synced
    assert tally == sorted(tally)
    want, got = unit_cells(ledger, world)
    assert got == want


def test_the_corner_cells_the_camera_can_never_expose_are_retired_out_loud():
    """回合橫幅壓在地圖角落的那幾格：鏡頭夾在兩條邊上就是看不到它們。退休是明寫
    的事實（逐 tick 進流水帳），不是把缺口悄悄抹掉。"""
    world = _synthetic()

    _, ledger = sweep(Rig(world))

    summary = ledger.summary()
    assert summary["unreachable"] > 0
    assert summary["cells"]["unknown"] == summary["unreachable"]
    assert summary["coverage"] > 0.95


def test_an_eaten_command_costs_a_leg_and_nothing_else():
    """起手點被單位精靈吃掉的手勢跟撞邊長得一模一樣：一次停滯不准釘邊界旗。"""
    world = _synthetic()

    _, ledger = sweep(Rig(world, eaten=(2, 3, 7)))

    assert ledger.synced
    want, got = unit_cells(ledger, world)
    assert got == want


def test_a_doubled_command_is_measured_and_the_skipped_band_gets_filled_in():
    world = _synthetic()

    _, ledger = sweep(Rig(world, doubled=(2, 5, 8)))

    assert ledger.synced
    want, got = unit_cells(ledger, world)
    assert got == want
    assert ledger.summary()["islands"]["isolated"] == 0


def test_an_unlocalisable_frame_is_isolated_and_never_written_blind():
    world = _synthetic()

    # 第 9、10、11 次 observe 收到空白幀（截圖序號 ＝ observe 序號 ×2，見 Rig）
    _, ledger = sweep(Rig(world, blank=(18, 20, 22)))

    summary = ledger.summary()
    assert summary["unlocalised"] >= 1
    assert summary["islands"]["isolated"] >= 1
    assert ledger.synced
    want, got = unit_cells(ledger, world)
    assert got == want


def test_a_camera_jump_is_refused_then_re_anchored_by_the_constellation():
    """鏡頭莫名跳走＝繞回混疊的實機版本：包絡閘先擋下來，島嶼再靠已記目擊重錨。"""
    world = _synthetic()

    _, ledger = sweep(Rig(world, jumps={4: (900.0, 0.0)}))

    summary = ledger.summary()
    assert summary["islands"]["isolated"] == 1
    assert summary["islands"]["merged"] == 1
    assert ledger.synced
    want, got = unit_cells(ledger, world)
    assert got == want


def test_an_island_that_never_re_anchors_is_dropped_and_the_world_restarts():
    """重錨失敗就整批丟棄（那一區留 UNKNOWN）、誠實重開世界——寧可重掃一次，
    也不要把不知道位置的觀測寫進權威圖。"""
    world = World(cols=22, rows=12, units=())
    rig = Rig(world, blank=(6,))
    driver, ledger = survey_drivers(rig.capture, rig, sleep=lambda _: None)
    ledger.zoomed = True
    survey = ledger.survey
    for _ in range(3):
        driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))
    assert survey.island is not None
    charted = len(survey.chart.charted)

    for _ in range(coverage.ISLAND_BUDGET + 1):
        if survey.island is None:
            break
        driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))

    summary = ledger.summary()
    assert summary["islands"]["discarded"] >= 1
    assert summary["islands"]["reset"] >= 1
    assert survey.island is None
    assert len(survey.chart.charted) <= charted


def test_a_turn_boundary_downgrades_the_board_and_the_next_turn_re_anchors():
    world = _synthetic()
    driver, ledger = sweep(Rig(world))
    assert ledger.synced

    ledger.expire()
    decayed = ledger.summary()

    assert decayed["cells"]["stale"] == len(world.units)
    assert decayed["cells"]["unit"] == 0
    assert ledger.cells() == ()
    assert not ledger.synced
    # 地圖幾何不衰效：邊界旗跨代保留
    assert decayed["bounded"] == ["east", "north", "south", "west"]

    for _ in range(30):
        driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))
        if ledger.synced:
            break

    assert ledger.synced
    want, got = unit_cells(ledger, world)
    assert got == want
    assert ledger.summary()["islands"]["merged"] >= 1


def test_the_summary_carries_the_numbers_the_journal_needs_every_tick():
    world = _synthetic()
    _, ledger = sweep(Rig(world), ticks=3)

    summary = ledger.summary()

    assert set(summary) >= {
        "coverage",
        "clusters",
        "frontier",
        "unlocalised",
        "islands",
        "generation",
        "unreachable",
        "bounded",
    }
    assert set(summary["islands"]) == {"isolated", "merged", "discarded", "reset", "open"}


def test_a_leg_never_commands_more_than_half_the_unambiguous_range():
    """腿長規則：單腿指令 ≤ 該軸無歧義量測範圍的一半，不然繞回混疊會量出自信錯值。"""
    world = _synthetic()
    rig = Rig(world)
    survey = Survey()
    survey.observe(world.frame())

    checked = 0
    for _ in range(10):
        leg = survey.plan_leg()
        if leg is None:
            break
        axis = 0 if leg.direction in ("east", "west") else 1
        assert abs(leg.expected[axis]) <= coverage.LEG_LIMIT["x" if axis == 0 else "y"] + 1e-6
        assert board.PAN_MIN_REACH <= leg.reach <= board.PAN_MAX_REACH
        rig.swipe(*board.pan_gesture(leg.direction, (1170.0, 500.0), leg.reach), 0.7)
        survey.observe(world.frame(), leg)
        checked += 1

    assert checked >= 5


def test_an_unanchored_survey_still_moves_so_it_can_find_a_readable_frame():
    """地圖邊緣的半幅虛空會讓格網讀不出來；待在原地只會永遠讀不到。"""
    survey = Survey()
    survey.observe(np.zeros((1080, 2340, 3), np.uint8))

    assert not survey.anchored
    assert survey.plan_leg() is not None


def test_the_fuse_stops_the_survey_instead_of_burning_the_whole_tick_budget():
    world = _synthetic()
    survey = Survey(budget=2)
    survey.observe(world.frame())

    assert survey.plan_leg() is not None
    assert survey.plan_leg() is not None
    assert survey.fused
    assert survey.plan_leg() is None
    assert not survey.complete


# ---- v2.1 缺陷修正的迴歸線（0731 重審定讞的六缺陷，復現腳本見流水帳存檔） ----


def test_the_leg_fuse_is_a_per_turn_ceiling_not_a_whole_battle_quota():
    """保險絲只防單一回合內的失控。跨回合累積的話十幾回合就燒斷，之後 fused 恆真、
    board_synced 永遠達不成——整關從那一刻起卡死。"""
    world = _synthetic()
    rig = Rig(world)
    driver, ledger = survey_drivers(rig.capture, rig, sleep=lambda _: None)
    ledger.zoomed = True

    spent = []
    for _ in range(3):
        for _ in range(60):
            driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))
            if ledger.synced:
                break
        assert ledger.synced
        assert not ledger.survey.fused
        spent.append(ledger.survey.legs)
        ledger.expire()
        assert ledger.survey.legs == 0

    assert max(spent) < coverage.LEG_BUDGET
    # 每回合各自從零起算，所以後面的回合不會比第一回合貴
    assert max(spent[1:]) <= spent[0] * 2


def test_a_half_row_island_offset_is_merged_as_measured_not_rounded_to_a_row():
    """島與世界的**列**偏移可以是任意值：橫軸沒有相位閘（橫線間距隨 y 遞增），敵
    回合演出常把鏡頭拉走半列。硬吸附整列＝把誤差當成 0 寫進整批合併。"""
    truth = (0.0, 60.0)
    marks = ((350.0, 290.0), (550.0, 490.0), (950.0, 690.0))
    survey = _islanded(marks, truth)

    delta = survey._solve()

    assert delta == pytest.approx(truth)
    merged = survey.island.views[0].shifted(delta)
    assert [merged.world(unit.point) for unit in merged.units] == [
        pytest.approx(point) for point in marks
    ]
    assert [GRID.cell_of(merged.world(unit.point)) for unit in merged.units] == [
        GRID.cell_of(point) for point in marks
    ]


def test_one_stall_never_pins_an_island_axis():
    """島嶼釘軸比照主圖釘邊界旗：起手點被單位精靈吃掉的手勢，畫面同樣不動，一次
    停滯分不出是哪一種。釘錯一軸＝整批島嶼寫進錯的世界座標。"""
    survey = _stalling_island()
    leg = Leg("west", 100.0, (350.0, 0.0))
    seen = view(offset=(640.0, 0.0), region=(0, 0, 1280, 1080))

    survey._pin(leg, _reading(STALLED), seen)

    assert survey.island.pins == {}

    survey._pin(leg, _reading(STALLED), seen)

    assert survey.island.pins == {"x": pytest.approx(-700.0)}


def test_a_leg_that_actually_moved_starts_the_island_stall_count_over():
    survey = _stalling_island()
    leg = Leg("west", 100.0, (350.0, 0.0))
    seen = view(offset=(640.0, 0.0), region=(0, 0, 1280, 1080))

    survey._pin(leg, _reading(STALLED), seen)
    survey._pin(leg, _reading(ACCEPTED), seen)
    survey._pin(leg, _reading(STALLED), seen)

    assert survey.island.pins == {}


def test_a_pinned_offset_still_has_to_agree_with_the_recorded_sightings():
    """兩軸都釘住不代表釘對——邊界旗或邊緣格任一量錯就是「量錯寫入」，而那條路徑
    這個模型不准存在。對不上就當沒釘過，退回星座重定位。"""
    truth = (0.0, 60.0)
    marks = ((350.0, 290.0), (550.0, 490.0), (950.0, 690.0))
    survey = _islanded(marks, truth)
    survey.island.pins = {"x": 0.0, "y": 0.0}

    delta = survey._solve()

    assert delta == pytest.approx(truth)


def test_pins_stand_on_their_own_when_the_island_saw_nothing_to_contradict_them():
    """島上零目擊時沒有可矛盾之物：撞邊釘軸是絕對參考，不需要星座背書。"""
    survey = Survey()
    survey.chart = chart()
    survey.island = Island(reason="test", odometer=Odometer(grid=GRID))
    survey.island.views = [view()]
    survey.island.pins = {"x": -700.0, "y": 300.0}

    assert survey._solve() == (-700.0, 300.0)


def test_one_unit_seen_in_three_overlapping_views_only_votes_once():
    """支持數門檻要的是「這麼多台**實體**真的對上位置」。同一台在重疊 view 出現
    N 次就自己湊滿門檻的話，重錨的星座複驗形同虛設。"""
    marks = ((350.0, 290.0), (550.0, 490.0), (950.0, 690.0))
    survey = Survey()
    survey.chart = chart()
    for point in marks:
        survey.chart.state[GRID.cell_of(point)] = Knowledge.STALE
        survey.chart.marks[GRID.cell_of(point)] = board.Sighting(point)
    # 島上只有兩台實體，其中一台被三個重疊 view 各看到一次
    wide = (0, 0, 2340, 1080)
    survey.island = Island(reason="test", odometer=Odometer(grid=GRID))
    survey.island.views = [
        view(region=wide, units=[board.Sighting((550.0, 430.0))]),
        view(region=wide, units=[board.Sighting((551.0, 431.0))]),
        view(
            region=wide,
            units=[board.Sighting((549.0, 429.0)), board.Sighting((950.0, 630.0))],
        ),
    ]

    assert survey.island.sightings == ((549.0, 429.0), (950.0, 630.0))
    assert survey._solve() is None


def test_a_retired_target_is_always_a_cell_of_the_pocket_itself():
    """L 形聚類的質心不在聚類裡。退休質心既不會讓目標清單變短（每 tick 重挑同一團
    ＝活鎖、腿數不前進、保險絲永遠不燒），又把一格 EMPTY 跨代排除掉＝無聲丟失。"""
    survey = _boxed()
    survey.clamps.update({"north": -50.0, "south": -50.0})

    leg = survey.plan_leg()

    assert survey.chart.unreachable <= set(_POCKET)
    assert (1, 1) not in survey.chart.unreachable
    assert survey.chart.knowledge((1, 1)) is Knowledge.EMPTY
    # 退休讓目標清單真的變短，同一次 plan_leg 就挑得到別團——沒有活鎖
    assert leg is not None
    assert survey.legs == 1


def test_a_pocket_no_camera_position_can_expose_retires_cell_by_cell_and_stops():
    survey = _boxed()
    for direction in coverage.COMPASS:
        survey.clamps[direction] = -50.0

    assert survey.plan_leg() is None
    assert survey.chart.unreachable == set(_POCKET)
    assert survey.complete
    # 每輪嚴格縮小目標清單，所以停下來靠的是缺口清空，不是燒斷保險絲
    assert not survey.fused


def test_a_clamp_line_from_the_old_world_never_survives_into_the_new_one():
    """撞邊線記的是世界座標。縮放之後原點換了一幀，同一個數字不代表頂在邊上——
    帶過去會讓新世界裡地圖中央的方向被當成推不動。"""
    survey = Survey()
    survey.clamps["east"] = 3200.0
    survey.legs = 30

    survey.reset()
    survey.odometer = Odometer(grid=GRID, offset=(3210.0, 0.0))

    assert survey.clamps == {}
    assert not survey._clamped("east")
    assert survey.legs == 0


def test_abandoning_an_island_drops_the_clamps_but_keeps_the_leg_fuse():
    survey = Survey()
    survey.chart = chart()
    survey.clamps["east"] = 3200.0
    survey.legs = 7
    island = Island(reason="test", odometer=Odometer(grid=GRID))
    survey.island = island

    survey._abandon(island)

    assert survey.clamps == {}
    # 同一回合內島嶼反覆丟棄重開仍受同一條保險絲約束，不然回合內就沒有上界
    assert survey.legs == 7


# ---- v2.3：增益學習死鎖（0801 複驗第 2 輪遙測 measured/expected 恆 0.33） ----


def test_a_three_fold_overestimated_gain_is_learned_down_within_a_few_legs():
    """舊條件「量到的不足預期一半就不入帳」在增益高估三倍時恆真：0801 遙測南向
    9 腿 measured/expected 全是 0.33（51.5 對 155），增益一次都沒學到。"""
    world = World(cols=40, rows=24, units=())
    rig = Rig(world, gain=0.76)
    survey = Survey()
    survey.observe(world.frame())

    ratios: dict[str, list[float]] = {"x": [], "y": []}
    for _ in range(24):
        leg = survey.plan_leg()
        assert leg is not None
        before = world.camera
        rig.swipe(*board.pan_gesture(leg.direction, (1170.0, 500.0), leg.reach), 0.7)
        moved = math.hypot(world.camera[0] - before[0], world.camera[1] - before[1])
        survey.observe(world.frame(), leg)
        if moved >= board.EDGE_SHIFT_PX:
            ratios["x" if leg.direction in ("east", "west") else "y"].append(
                moved / math.hypot(*leg.expected)
            )

    for axis, seen in ratios.items():
        assert len(seen) >= 6, axis
        # 起手三倍超推（未修碼的 measured/expected 就永遠停在這裡）
        assert seen[0] < 0.4, axis
        # 第 5、6 腿已經收斂：指令要的行程就是實際走到的行程
        assert min(seen[4:6]) > 0.85, axis
        assert survey.gain[axis] < 1.0, axis


def test_a_leg_that_hit_the_map_edge_never_teaches_the_gain():
    """真撞邊的位移 < EDGE_SHIFT_PX 已經被判 STALLED，而 STALLED 進不了增益帳
    ——撞邊污染靠的是這條，不是「不到半個預期就不學」。"""
    survey = Survey()
    before = dict(survey.gain)
    leg = Leg("east", 200.0, (-350.0, 0.0))

    survey._learn_gain(leg, Reading(STALLED, board.Shift(-2.0, 0.0, 1.0, "still"), (0.0, 0.0)))

    assert survey.gain == before

    survey._learn_gain(leg, Reading(ACCEPTED, board.Shift(-150.0, 0.0, 0.9, "phase"), (0.0, 0.0)))

    blended = (1 - coverage.GAIN_BLEND) * coverage.GAIN_DEFAULT + coverage.GAIN_BLEND * 0.75
    assert survey.gain["x"] == pytest.approx(blended)
    assert survey.gain["y"] == coverage.GAIN_DEFAULT


def test_a_broken_leg_never_reaches_the_gain_ledger():
    """observe 判 BROKEN 就直接隔離進島嶼，_learn_gain 根本沒被叫到——量不出來的
    位移不准當成增益證據。"""
    world = _synthetic()
    survey = Survey()
    survey.observe(world.frame())
    before = dict(survey.gain)

    reading = survey.observe(np.zeros((1080, 2340, 3), np.uint8), Leg("east", 200.0, (-350.0, 0.0)))

    assert reading.verdict == BROKEN
    assert survey.gain == before


_POCKET = ((0, 0), (1, 0), (2, 0), (2, 1), (2, 2))


def _boxed() -> Survey:
    """四旗全定的 5x5 小世界，缺口是一個 L 形聚類（質心 (1,1) 落在聚類外）。"""
    survey = Survey(region=WINDOW)
    survey.chart = chart()
    survey.odometer = Odometer(grid=GRID, offset=(-50.0, -50.0))
    for direction, line in (("west", 0), ("east", 4), ("north", 0), ("south", 4)):
        survey.chart.boundary[direction] = line
    for col in range(5):
        for row in range(5):
            survey.chart.charted.add((col, row))
            survey.chart.state[(col, row)] = Knowledge.EMPTY
    for cell in _POCKET:
        survey.chart.state[cell] = Knowledge.UNKNOWN
    return survey


def _islanded(marks: tuple[tuple[float, float], ...], truth: tuple[float, float]) -> Survey:
    """權威圖記著 marks，島嶼在同一批單位上差了 truth 這個偏移。"""
    survey = Survey()
    survey.chart = chart()
    for point in marks:
        survey.chart.state[GRID.cell_of(point)] = Knowledge.STALE
        survey.chart.marks[GRID.cell_of(point)] = board.Sighting(point)
    survey.island = Island(reason="test", odometer=Odometer(grid=GRID))
    survey.island.views = [
        view(
            region=(0, 0, 2340, 1080),
            units=[board.Sighting((x - truth[0], y - truth[1])) for x, y in marks],
        )
    ]
    return survey


def _stalling_island() -> Survey:
    survey = Survey()
    survey.chart = chart(boundary={"west": 0})
    survey.island = Island(reason="test", odometer=Odometer(grid=GRID))
    return survey


def _reading(verdict: str) -> Reading:
    return Reading(verdict, board.Shift(0.0, 0.0, 1.0, "still"), (640.0, 0.0))
