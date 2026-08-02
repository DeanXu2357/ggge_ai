"""四態知識圖、待掃格補掃，以及 v3 的定位骨架（角落歸零＋地標＋對回已知地圖）。

單元層對著手寫的圖與座標，整段行為對著合成世界（tests/fixtures/synthetic_map）：
單位擺在哪一格、鏡頭移了多少都是我們定的，所以「四態逐格正確」「跳過的帶被回補」
這種斷言才有地面真相可對。實幀系列另有半真實回放（test_runtime_board）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pytest

from ggge_ai.runtime import board, coverage
from ggge_ai.runtime.coverage import (
    ACCEPTED,
    BROKEN,
    STALLED,
    ZEROING,
    FrameView,
    Knowledge,
    KnowledgeMap,
    Leg,
    Survey,
    WorldGrid,
)
from ggge_ai.runtime.perceive import Observation
from ggge_ai.stage.actions import SurveyBoard
from ggge_ai.stage.survey import survey_drivers
from tests.fixtures.synthetic_map import COL_PITCH, ROW_PITCH, World, animated, void_outside

GRID = WorldGrid(phase=(0.0, 0.0), col_pitch=100.0, row_pitch=100.0)
# 一格 100px 的小視窗：手算得出來哪幾格「整格看得清楚」。
WINDOW = (0, 0, 400, 300)
UNITS = ((3, 5), (5, 4), (9, 6), (14, 3), (18, 9))
# 大世界的擺位：欄距固定但**列位刻意不成等差**。等差擺位會讓好幾對單位共用同一個
# 平移量，配對投票湊出並列眾數就直接棄權。
SPREAD = ((2, 5), (5, 7), (8, 12), (11, 4), (14, 9), (17, 13), (20, 3), (23, 8), (26, 11))

SCREEN = (0, 0, 2340, 1080)


def view(offset=(0.0, 0.0), units=(), region=WINDOW, holes=(), lattice=SCREEN, edges=()):
    """預設「整幀都有格線、四側都沒看到終止邊」＝格線遮罩不裁任何格。"""
    return FrameView(
        offset=offset,
        units=tuple(units),
        region=region,
        holes=tuple(holes),
        lattice=lattice,
        edges=frozenset(edges),
    )


def chart(**kwargs) -> KnowledgeMap:
    return KnowledgeMap(grid=GRID, **kwargs)


def test_the_world_grid_maps_pixels_to_cells_in_both_directions():
    assert GRID.cell_of((0.0, 0.0)) == (0, 0)
    assert GRID.cell_of((99.0, 250.0)) == (0, 2)
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
    不是離開。無條件鋪 EMPTY 的話一次漏檢就抹掉整格知識。"""
    world = chart()
    world.absorb(view(units=[board.Sighting((250.0, 150.0), board.RED_HINT)]))

    world.absorb(view())

    assert world.knowledge((2, 1)) is Knowledge.UNIT
    assert world.units() == (((2, 1), board.RED_HINT),)
    assert world.knowledge((0, 0)) is Knowledge.EMPTY


def test_a_fresh_sighting_on_the_same_cell_still_updates_the_mark():
    """滯後保的是「有單位」這件事，不是舊座標：本幀的世界像素照樣蓋上去，不然對回
    已知地圖時比對的是過期的星圖。"""
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
    """半個機體露在畫面外時峰的位置不可信：寧可留 UNKNOWN 等待掃格回補。"""
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
    """界內在四面界線都定之前是無限大，所以待掃格只認測繪區周邊。"""
    world = chart()
    world.absorb(view())

    front = set(world.frontier())

    assert (4, 0) in front
    assert (0, 3) in front
    assert (9, 9) not in front


def test_a_fixed_boundary_takes_the_cells_beyond_it_out_of_bounds():
    world = chart()
    world.absorb(view())
    world.set_boundary("west", 0)

    assert world.boundary["west"] == 0
    assert not world.in_bounds((-1, 0))
    assert (-1, 0) not in world.frontier()


def test_fixing_a_boundary_deletes_every_record_that_fell_outside_it():
    """線外沒有地圖：界線一定案，線外的 state／marks／charted／unreachable 全部作廢。"""
    world = chart()
    world.absorb(view(units=[board.Sighting((250.0, 150.0), board.RED_HINT)]))
    world.absorb(
        view(offset=(1500.0, 0.0), units=[board.Sighting((150.0, 150.0), board.BLUE_HINT)])
    )
    world.unreachable.add((17, 2))
    assert world.knowledge((16, 1)) is Knowledge.UNIT

    assert world.set_boundary("east", 13) == 13

    assert world.knowledge((16, 1)) is Knowledge.UNKNOWN
    assert (16, 1) not in world.marks
    assert not any(cell[0] > 13 for cell in world.charted)
    assert world.unreachable == set()
    assert world.knowledge((2, 1)) is Knowledge.UNIT
    assert world.knowledge((0, 0)) is Knowledge.EMPTY
    assert world.units() == (((2, 1), board.RED_HINT),)


def test_a_reversed_boundary_trims_the_strip_it_just_gave_up():
    """改判走同一條裁剪：舊界那一欄的紀錄留著就成了永遠對不上的鬼影。"""
    world = chart()
    world.boundary["west"] = -10
    for col in (-10, -9):
        world.charted.add((col, 0))
        world.state[(col, 0)] = Knowledge.UNIT
        world.marks[(col, 0)] = board.Sighting((col * 100.0 + 50.0, 50.0), board.RED_HINT)

    assert world.set_boundary("west", -9) == -9

    assert world.knowledge((-10, 0)) is Knowledge.UNKNOWN
    assert (-10, 0) not in world.marks and (-10, 0) not in world.charted
    assert world.units() == (((-9, 0), board.RED_HINT),)


def test_the_border_pixel_maps_to_the_outermost_cell_inside_the_map():
    """界線＝目視終止邊往界內半格的那一格。線是看到的，不是從推不動推論的。"""
    assert coverage._border_cell(GRID, "west", 300.0) == 3
    assert coverage._border_cell(GRID, "east", 300.0) == 2
    assert coverage._border_cell(GRID, "north", 500.0) == 5
    assert coverage._border_cell(GRID, "south", 500.0) == 4


def test_the_unit_roll_and_the_census_count_the_same_cells():
    """流水帳的 cells 與 census 必須同一個口徑。absorb 不看界線（界線可能還沒定），
    所以界外的 mark 照樣寫得進來——讀值側才是對齊的地方。"""
    world = chart()
    for direction, line in (("west", 0), ("east", 3), ("north", 0), ("south", 2)):
        world.boundary[direction] = line
    world.absorb(view(units=[board.Sighting((250.0, 150.0), board.RED_HINT)]))
    world.absorb(
        view(offset=(1500.0, 0.0), units=[board.Sighting((150.0, 150.0), board.BLUE_HINT)])
    )

    assert world.knowledge((16, 1)) is Knowledge.UNIT
    assert world.units() == (((2, 1), board.RED_HINT),)
    assert world.census()["unit"] == len(world.units())
    assert world.sightings() == ((250.0, 150.0),)


def test_the_comparison_star_chart_never_offers_a_previous_generation_position():
    """`sightings()` 是把新幀對回已知地圖的比對標的。STALE 是敵方回合之前的站位，
    那些機體早就動過了——拿它定位等於用過期的星圖。"""
    world = chart()
    world.absorb(view(units=[board.Sighting((250.0, 150.0), board.RED_HINT)]))
    assert world.sightings() == ((250.0, 150.0),)

    world.expire()

    assert world.knowledge((2, 1)) is Knowledge.STALE
    assert world.sightings() == ()


def test_an_unbounded_chart_still_reports_every_mark_it_has():
    """界線沒定滿之前界內無限大：這時候濾界內等於憑半套界線丟掉真的觀測。"""
    world = chart(boundary={"east": 3})
    world.absorb(view(offset=(1500.0, 0.0), units=[board.Sighting((150.0, 150.0), board.RED_HINT)]))

    assert world.units() == (((16, 1), board.RED_HINT),)
    assert world.sightings() == ((1650.0, 150.0),)


def test_completion_needs_all_four_boundaries_and_an_empty_interior():
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
    assert world.units() == ()
    assert (2, 1) in world.frontier()
    assert (0, 0) in world.frontier()


def test_clusters_are_four_connected_components():
    pockets = coverage.clusters([(0, 0), (1, 0), (0, 1), (5, 5), (5, 6)])

    assert pockets == (((0, 0), (0, 1), (1, 0)), ((5, 5), (5, 6)))


def test_a_stale_cluster_outranks_a_slightly_nearer_unknown_one():
    """含 STALE ＝ 單位大概率在附近，威脅評估最需要，所以距離打折。"""
    world = chart()
    world.charted.update({(0, 0), (5, 0)})
    world.state[(0, 0)] = Knowledge.STALE
    world.state[(5, 0)] = Knowledge.EMPTY

    assert (0, 0) in world.choose((300.0, 50.0))
    assert (0, 0) not in world.choose((700.0, 50.0))


def test_the_relocaliser_solves_the_offset_from_the_recorded_sightings():
    known = ((100.0, 100.0), (400.0, 300.0), (700.0, 500.0))
    seen = tuple((x + 256.0, y) for x, y in known)

    drift = board.relocalise(known, seen)

    assert drift is not None
    assert (round(drift[0]), round(drift[1])) == (256, 0)


def test_the_relocaliser_refuses_to_guess_without_a_unique_mode():
    assert board.relocalise(((0.0, 0.0),), ((10.0, 0.0),)) is None


# ---- 合成世界的整段行為 ----


def _synthetic() -> World:
    return World(cols=22, rows=12, units=UNITS)


@dataclass
class Rig:
    """腳本化鏡頭：手指行程乘上比例推鏡頭，虛空外緣就是鏡頭推得到的界。

    blank 數的是**截圖次數**，而取幀靜止閘讓每一次 observe 花掉兩張圖（f1、f2 各
    一），所以第 k 次 observe 拿到的是第 2k 張——合成世界瞬時靜止，第一輪就過閘。

    blind ＝ 那幾張截圖的單位沒畫出來（偵測漏的合成版）：背景與格線逐像素相同，
    只有機體環不見了。
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


def sweep(rig: Rig, ticks: int = 45, telemetry=None):
    driver, ledger = survey_drivers(rig.capture, rig, sleep=lambda _: None, telemetry=telemetry)
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


def zeroed(world: World) -> Survey:
    """把一個世界推到西北角錨定好，回傳已經進入繞邊階段的世界模型。"""
    survey = Survey()
    world.corner("west", "north")
    frame = world.frame()
    survey.observe(frame)
    for direction in coverage.ZERO_CORNER:
        leg = Leg(direction, 260.0, (0.0, 0.0))
        for _ in range(coverage.STALL_CONFIRM):
            survey.observe(world.frame(), leg)
    assert survey.stance == coverage.TOUR
    return survey


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


def test_a_taller_world_needs_the_middle_band_filled_and_still_lands_every_unit():
    """地圖高過一個螢幕時繞完一圈中央帶還是空的——那一段沒有地圖邊可讀，定位全靠
    對回已知地圖。整輪掃完仍要逐格對得上真值。"""
    world = World(cols=30, rows=16, units=SPREAD)

    _, ledger = sweep(Rig(world), ticks=90)

    assert ledger.synced
    want, got = unit_cells(ledger, world)
    assert got == want
    assert ledger.summary()["unlocalised"] == 0


def test_a_scan_that_misses_units_on_some_frames_still_ends_with_all_of_them():
    """偵測漏一幀就抹掉那一格的話，整輪掃完記得的遠少於世界真值。同一代內單位數
    只准增加。"""
    world = _synthetic()
    rig = Rig(world, blind=tuple(range(6, 200, 6)))
    driver, ledger = survey_drivers(rig.capture, rig, sleep=lambda _: None)
    ledger.zoomed = True

    tally: list[int] = []
    for _ in range(45):
        driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))
        tally.append(len(ledger.cells()))
        if ledger.synced:
            break

    assert ledger.synced
    assert tally == sorted(tally)
    want, got = unit_cells(ledger, world)
    assert got == want


def test_an_eaten_command_costs_a_gesture_and_nothing_else():
    """起手點被單位精靈吃掉的手勢跟推到底長得一模一樣：一次不動不准當成到邊。"""
    world = _synthetic()

    _, ledger = sweep(Rig(world, eaten=(6, 7, 11)))

    assert ledger.synced
    want, got = unit_cells(ledger, world)
    assert got == want


def test_a_doubled_command_lands_where_the_picture_says_it_landed():
    world = _synthetic()

    _, ledger = sweep(Rig(world, doubled=(6, 9, 12)))

    assert ledger.synced
    want, got = unit_cells(ledger, world)
    assert got == want


# ---- v3 的四條骨架迴歸 ----


def test_the_world_is_anchored_by_pushing_into_the_corner_not_by_the_first_frame():
    """歸零：推到西北角、連續兩次畫面不變、而且角落至少一側看得到地圖終止邊，才
    敢說「這裡就是原點」。半路的幀一格都不寫。"""
    world = World(cols=22, rows=12, units=UNITS)
    world.camera = (900.0, 400.0)
    survey = Survey()

    first = survey.observe(world.frame())

    assert first.verdict == ZEROING
    assert survey.chart is None and not survey.anchored

    leg = Leg("west", 260.0, (598.0, 0.0))
    while survey.stance == coverage.ZERO and survey.legs < 20:
        direction = survey.plan_leg().direction
        moved = board.DIRECTIONS[direction]
        world.move(moved[0] * 598.0, moved[1] * 598.0)
        survey.observe(world.frame(), Leg(direction, 260.0, leg.expected))

    assert world.camera == (0.0, 0.0)
    assert survey.stance == coverage.TOUR
    assert survey.offset == (0.0, 0.0)
    assert set(survey.landmarks) == {"west", "north"}
    assert survey.chart.boundary["west"] == 0
    assert survey.chart.boundary["north"] == 0


def test_a_frame_that_can_see_a_landmark_reads_its_position_straight_off_the_picture():
    """定位不是累加出來的：地標的世界像素減掉它在這一幀螢幕上的位置就是座標。
    中間跳過幾張幀完全不影響——這正是 v3 換骨架的理由。"""
    world = _synthetic()
    survey = zeroed(world)

    for camera in ((200.0, 0.0), (420.0, 0.0), (100.0, 0.0)):
        world.camera = camera
        reading = survey.observe(world.frame())

        assert reading.verdict == ACCEPTED
        assert reading.reason == coverage.SOURCE_EDGE
        assert reading.offset[0] == pytest.approx(camera[0], abs=2.0)


def test_the_two_landmarks_of_one_axis_have_to_agree_or_the_frame_is_dropped():
    """兩側都看得到而彼此差超過半格＝至少一側不是地圖邊。挑一個信就是量錯寫入。"""
    world = World(cols=22, rows=4, units=((3, 1), (9, 2)))
    survey = zeroed(world)
    assert {"north", "south"} <= set(survey.landmarks)
    survey.landmarks["south"] = survey.landmarks["north"] + 9.0 * ROW_PITCH

    reading = survey.observe(world.frame())

    assert reading.verdict == BROKEN
    assert reading.reason == coverage.EDGE_MISMATCH


def test_a_frame_nobody_can_place_is_dropped_whole_and_never_accumulates():
    """定位不出來的幀整張丟掉：不進緩衝、不重錨、不累積。知識圖與「最近一張定位
    成功的幀」都不准被它動到。"""
    world = _synthetic()
    survey = zeroed(world)
    world.camera = (400.0, 0.0)
    survey.observe(world.frame())
    charted = set(survey.chart.charted)
    marks = dict(survey.chart.marks)
    located = survey.located

    reading = survey.observe(np.zeros((1080, 2340, 3), np.uint8), Leg("east", 200.0, (-400.0, 0.0)))

    assert reading.verdict == BROKEN
    assert survey.chart.charted == charted
    assert survey.chart.marks == marks
    assert survey.located is located
    assert survey.unlocalised == 1


def test_three_unplaceable_frames_in_a_row_send_the_camera_back_to_the_corner():
    """帶著不知道位置的鏡頭繼續走沒有上界，所以連丟三張就推回角落重新歸零。"""
    world = _synthetic()
    survey = zeroed(world)
    blank = np.zeros((1080, 2340, 3), np.uint8)

    for _ in range(coverage.LOST_PATIENCE):
        survey.observe(blank, Leg("east", 200.0, (-400.0, 0.0)))

    assert survey.stance == coverage.ZERO
    assert not survey.anchored
    # 地圖幾何不因為鏡頭迷路就作廢
    assert survey.chart is not None
    assert survey.landmarks


def test_an_enemy_phase_sends_the_scan_back_to_the_corner_instead_of_re_anchoring():
    """敵方回合鏡頭被遊戲拉走，兩個回合之間的位移量不出來——v3 不再嘗試接回去，
    直接推回西北角。角落可重現，所以界線與地標一格都不必重學。"""
    world = _synthetic()
    driver, ledger = sweep(Rig(world))
    assert ledger.synced
    survey = ledger.survey
    landmarks = dict(survey.landmarks)
    boundary = dict(survey.chart.boundary)

    ledger.expire()

    assert survey.stance == coverage.ZERO
    assert not survey.anchored
    assert survey.landmarks == landmarks
    assert survey.chart.boundary == boundary
    assert ledger.summary()["cells"]["stale"] == len(world.units)
    assert not ledger.synced

    # 敵方回合把鏡頭丟在地圖中央，下一輪照樣掃得完，而且回到同一套世界座標
    world.camera = (900.0, 400.0)
    for _ in range(60):
        driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))
        if ledger.synced:
            break

    assert ledger.synced
    assert survey.zeroings == 2
    assert survey.landmarks == landmarks
    want, got = unit_cells(ledger, world)
    assert got == want


# ---- 感知與遮罩（v2 資產，v3 原樣保留） ----


# 鏡頭停在地圖中央（四側都讀不到終止邊）時，把這個框以外挖成虛空造一條西側邊：
# 框的左緣壓在格線上（螢幕 x468＝畫布 600+6×COL_PITCH 減鏡頭 900）。
VOID_WEST = (468, 250, 726, 530)


def test_a_frame_whose_grid_stops_partway_stamps_only_up_to_the_edge():
    """地圖以外那片無特徵的深色背景（下稱星空）不是 EMPTY：四態知識全是單位知識，每一態都預設「這裡有一格」，
    而說得出那句話的畫面證據只有格線。"""
    world = _synthetic()
    survey = zeroed(world)
    grid = survey.chart.grid
    edge = survey._view(world.frame(), (0.0, 0.0))

    seen = coverage.covered(grid, edge)
    band = coverage.readable(grid, edge)

    assert {"west", "north"} <= edge.edges
    assert seen and set(seen) < set(band)
    assert any(grid.box_of(cell)[0] < edge.lattice[0] for cell in band)


def test_the_lattice_mask_only_cuts_the_sides_that_were_seen_to_end():
    """取樣帶的邊緣不是證言：`GRID_REGION` 讀不到那裡的線不代表那裡沒格子。"""
    box = (150, 150, 200, 150)
    corner = view(lattice=box, edges=("west", "north"))

    seen = set(coverage.covered(GRID, corner))

    assert (0, 0) not in seen
    assert (2, 2) in seen
    assert set(coverage.covered(GRID, view(lattice=box))) == set(coverage.readable(GRID, view()))


def test_the_outermost_row_survives_a_few_pixels_of_coordinate_error():
    """最外那一排格子的外緣**就是**終止邊，座標差幾個像素就會把它整排切掉。半格
    以內的超出仍是界內那一格，真正在線外的由界線定案後的裁剪收拾。"""
    box = (0, 0, 400, 296)
    grazing = view(region=(0, 0, 400, 300), lattice=box, edges=("south",))

    assert (0, 2) in coverage.covered(GRID, grazing)
    assert (0, 2) not in coverage.covered(GRID, view(region=(0, 0, 400, 300),
                                                     lattice=(0, 0, 400, 240),
                                                     edges=("south",)))


def test_a_frame_without_any_lattice_stamps_no_empty_but_keeps_the_sighting():
    """整幀讀不出格線＝零遮罩。單位偵測不依賴格線，所以目擊照收。"""
    world = chart()

    world.absorb(view(lattice=None, units=[board.Sighting((250.0, 150.0), board.RED_HINT)]))

    assert world.knowledge((2, 1)) is Knowledge.UNIT
    assert world.units() == (((2, 1), board.RED_HINT),)
    assert world.knowledge((0, 0)) is Knowledge.UNKNOWN
    assert world.charted == set()


def test_a_corner_that_contradicts_the_kept_landmarks_starts_the_world_over():
    """歸零那一幀的座標是被定義成原點的，不是從地標算回來的——所以上一代留下的
    地標對不對得上是獨立的問題。對不上就整張圖作廢重來：寧可重掃一次，也不要拿
    跨代永久保留的地標去湊。"""
    world = _synthetic()
    survey = zeroed(world)
    charted = len(survey.chart.charted)
    assert charted

    survey.landmarks["west"] = survey.landmarks["west"] + 4.0 * COL_PITCH
    survey._rezero("test")
    survey.observe(world.frame())
    for direction in coverage.ZERO_CORNER:
        for _ in range(coverage.STALL_CONFIRM):
            survey.observe(world.frame(), Leg(direction, 260.0, (0.0, 0.0)))

    assert survey.stance == coverage.TOUR
    assert survey.offset == (0.0, 0.0)
    # 舊圖作廢，地標從這一幀重記
    assert survey.landmarks["west"] == pytest.approx(600.0, abs=2.0)


def test_a_bright_strip_beyond_the_last_line_is_no_edge_at_all():
    """只看「線到這裡為止」會把「這一帶剛好沒讀到線」當成地圖邊。外側要同時安靜、
    暗、而且比內側安靜得多。"""
    world = _synthetic()
    world.camera = (900.0, 400.0)
    assert board.read_span(world.frame()).edges == frozenset()

    dark = board.read_span(void_outside(world.frame(), VOID_WEST))
    lit = board.read_span(void_outside(world.frame(), VOID_WEST, level=(60, 90)))

    assert "west" in dark.edges
    assert lit is not None and lit.edges == frozenset()


def test_an_idle_animation_never_makes_a_still_picture_look_like_a_moving_one():
    """待機動畫讓幀差恆高於門檻（實機 5.8-12.5 對 2.5），原地幀因此走不進「逐像素
    幾乎相同」那一支——證言要靠相位相關與影像複驗。"""
    world = _synthetic()
    survey = zeroed(world)
    frame = world.frame()
    survey.observe(frame)

    assert board.frame_difference(frame, animated(frame)) > board.EDGE_FRAME_DIFF

    reading = survey.observe(animated(frame), Leg("south", 70.0, (0.0, -155.0)))

    assert reading.verdict == STALLED


def test_an_unmeasurable_frame_is_never_called_still():
    """「沒動」要有人指著畫面說沒動。量不出來就算沒動的話，空白幀會被判靜止，而
    靜止的處置是沿用上一張的座標——下一張真的動過的幀就以舊座標寫進圖。"""
    world = _synthetic()
    survey = zeroed(world)
    blank = np.zeros((1080, 2340, 3), np.uint8)
    survey.observe(world.frame())

    assert not survey._unchanged(world.frame(), blank, None)
    assert not survey._unchanged(world.frame(), blank, Leg("east", 200.0, (-400.0, 0.0)))


# ---- 規劃：繞邊、補中央與退休 ----


def test_the_tour_walks_east_then_south_then_west_before_it_fills_the_middle():
    world = World(cols=30, rows=16, units=SPREAD)
    survey = zeroed(world)

    order: list[str] = []
    for _ in range(60):
        leg = survey.plan_leg()
        if leg is None or survey.stance == coverage.FILL:
            break
        if not order or order[-1] != leg.direction:
            order.append(leg.direction)
        moved = board.DIRECTIONS[leg.direction]
        world.move(moved[0] * 300.0, moved[1] * 300.0)
        survey.observe(world.frame(), leg)

    assert order == ["east", "south", "west"]


def test_a_gesture_never_commands_more_than_a_quarter_of_the_measuring_window():
    """一把推移的內容位移上限：前後幀要留得下八成以上的重疊，補位量測也不能超出
    自己的無歧義範圍。"""
    world = _synthetic()
    survey = zeroed(world)

    checked = 0
    for _ in range(10):
        leg = survey.plan_leg()
        if leg is None:
            break
        axis = 0 if leg.direction in ("east", "west") else 1
        assert abs(leg.expected[axis]) <= coverage.LEG_LIMIT["x" if axis == 0 else "y"] + 1e-6
        assert board.PAN_MIN_REACH <= leg.reach <= board.PAN_MAX_REACH
        moved = board.DIRECTIONS[leg.direction]
        world.move(moved[0] * 200.0, moved[1] * 200.0)
        survey.observe(world.frame(), leg)
        checked += 1

    assert checked >= 5


def test_the_zeroing_gesture_pushes_as_hard_as_the_actuator_allows():
    """歸零那幾把不必留重疊——那一段本來就不談座標，推得快才划算。"""
    survey = Survey()

    leg = survey.plan_leg()

    assert leg.direction == coverage.ZERO_CORNER[0]
    assert leg.reach == board.PAN_MAX_REACH


def test_aiming_brings_the_cell_into_the_band_instead_of_centring_the_view():
    """目標已經在帶內的那一軸推它只是把它推出去，而另一軸夾在邊上推不動——兩者一湊
    就是來回空推的活鎖。"""
    survey = _boxed()

    needs = dict(survey._needs((4, 1)))

    assert needs["y"] == 0.0
    assert needs["x"] > 0.0


def test_a_cell_stuck_under_a_hud_hole_is_aimed_out_of_it_not_retired_on_the_spot():
    """洞在螢幕座標固定不動，鏡頭一動格子就從洞底下移出來——「洞蓋著」是這個鏡頭
    位置的事實，不是永久事實，而退休是跨代生效的。"""
    survey = Survey(region=(0, 0, 800, 600), holes=((0, 0, 300, 200),))
    survey.chart = chart()
    survey.located = (np.zeros((1, 1, 3), np.uint8), (0.0, 0.0))

    escapes = survey._needs((1, 1))

    assert escapes
    axis, wanted = escapes[0]
    assert coverage._bearing(axis, wanted) == "north"
    assert survey._exposes(coverage._screen_box(GRID, (1, 1), (0.0, 0.0)), escapes[0])


def test_a_retired_target_is_always_a_cell_of_the_pocket_itself():
    """L 形聚類的質心不在聚類裡。退休質心既不會讓目標清單變短（每次重挑同一團
    ＝活鎖），又把一格 EMPTY 跨代排除掉＝無聲丟失。"""
    survey = _boxed()
    survey.sighted = frozenset(coverage.COMPASS)

    leg = survey.plan_leg()

    assert leg is None
    assert survey.chart.unreachable <= set(_POCKET)
    assert (1, 1) not in survey.chart.unreachable


def test_a_pocket_no_camera_position_can_expose_retires_cell_by_cell_and_stops():
    survey = _boxed()
    survey.sighted = frozenset(coverage.COMPASS)

    for _ in range(len(_POCKET) + 2):
        if survey.complete:
            break
        survey.plan_leg()

    assert survey.chart.unreachable == set(_POCKET)
    assert survey.complete
    assert not survey.fused


def test_the_sighted_clamp_lifts_as_soon_as_the_camera_leaves_the_edge():
    """目視邊是逐幀的證言不是旗子：讀不到終止邊的下一幀就解除，不然鏡頭離開之後
    那個方向會被永久封死。"""
    world = _synthetic()
    survey = zeroed(world)

    assert survey.sighted == frozenset({"west", "north"})
    assert survey._clamped("west")

    world.camera = (900.0, 400.0)
    survey.observe(world.frame())

    assert "west" not in survey.sighted
    assert not survey._clamped("west")


def test_the_hud_button_hole_costs_the_west_band_everything_above_the_button():
    """挖洞的代價要看得見，不能只寫在導覽裡。回合橫幅（y0-170）與「變更初期配置」
    鈕（y242-326）之間只剩 72px，最小縮放的格距塞不進一整格。"""
    grid = WorldGrid(phase=(150.0, 170.0), col_pitch=89.0, row_pitch=89.0)
    band = FrameView(
        offset=(0.0, 0.0),
        region=board.UNIT_DENSITY_REGION,
        holes=board.UNIT_DENSITY_HUD_HOLES,
    )

    seen = set(coverage.readable(grid, band))

    assert (0, 0) not in seen and (0, 1) not in seen
    assert (0, 2) in seen
    assert (4, 0) in seen


def test_a_zoom_step_throws_the_whole_world_away_including_the_landmarks():
    """縮放改的是比例：舊世界的像素座標與地標全部作廢。"""
    world = _synthetic()
    survey = zeroed(world)
    assert survey.landmarks

    survey.reset()

    assert survey.chart is None
    assert survey.landmarks == {}
    assert survey.stance == coverage.ZERO
    assert survey.legs == 0
    assert survey.sighted == frozenset()


def test_the_summary_carries_the_numbers_the_journal_needs_every_tick():
    world = _synthetic()
    _, ledger = sweep(Rig(world), ticks=3)

    summary = ledger.summary()

    assert set(summary) >= {
        "coverage",
        "clusters",
        "frontier",
        "unlocalised",
        "stance",
        "zeroings",
        "landmarks",
        "generation",
        "unreachable",
        "bounded",
    }


def test_the_fuse_stops_the_survey_instead_of_burning_the_whole_tick_budget():
    world = _synthetic()
    survey = Survey(budget=2)
    survey.observe(world.frame())

    assert survey.plan_leg() is not None
    assert survey.plan_leg() is not None
    assert survey.fused
    assert survey.plan_leg() is None
    assert not survey.complete


def test_the_fuse_is_a_per_turn_ceiling_not_a_whole_battle_quota():
    """保險絲只防單一回合內的失控。跨回合累積的話十幾回合就燒斷，之後 fused 恆真、
    board_synced 永遠達不成——整關從那一刻起卡死。"""
    world = _synthetic()
    rig = Rig(world)
    driver, ledger = survey_drivers(rig.capture, rig, sleep=lambda _: None)
    ledger.zoomed = True

    spent = []
    for _ in range(3):
        for _ in range(70):
            driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))
            if ledger.synced:
                break
        assert ledger.synced
        assert not ledger.survey.fused
        spent.append(ledger.survey.legs)
        ledger.expire()
        assert ledger.survey.legs == 0

    assert max(spent) < coverage.LEG_BUDGET


_POCKET = ((0, 0), (1, 0), (2, 0), (2, 1), (2, 2))


def _boxed() -> Survey:
    """四面界線都定的 5x5 小世界，缺口是一個 L 形聚類（質心 (1,1) 落在聚類外）。"""
    survey = Survey(region=WINDOW, holes=())
    survey.chart = chart()
    survey.stance = coverage.FILL
    survey.located = (np.zeros((1, 1, 3), np.uint8), (-50.0, -50.0))
    for direction, line in (("west", 0), ("east", 4), ("north", 0), ("south", 4)):
        survey.chart.boundary[direction] = line
    for col in range(5):
        for row in range(5):
            survey.chart.charted.add((col, row))
            survey.chart.state[(col, row)] = Knowledge.EMPTY
    for cell in _POCKET:
        survey.chart.state[cell] = Knowledge.UNKNOWN
    return survey
