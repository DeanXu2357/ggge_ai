"""盤面全覽的符號建模：前置條件、規劃排序、恢復式微步驟、覆蓋簿記與衰效。"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pytest

from ggge_ai.contracts import Ending, HiddenPolicy, Objective, StageOrder
from ggge_ai.runtime import board, coverage
from ggge_ai.runtime.device import LiveExecutor
from ggge_ai.runtime.journal import Journal
from ggge_ai.runtime.perceive import Observation
from ggge_ai.sandbox.advise import Guarantee, Pricing
from ggge_ai.runtime import screens
from ggge_ai.stage.actions import Attack, CollapseRoster, ShowGrid, SurveyBoard, candidates
from ggge_ai.stage.goals import Annihilation
from ggge_ai.stage.loop import StageLoop, TickOutcome
from ggge_ai.stage.planner import PlannerConfig, plan
from ggge_ai.stage.run import JOURNAL_NAME
from ggge_ai.stage.state import Phase, StageState, next_player_phase
from ggge_ai.stage.survey import (
    DONE_STEP,
    FILL_STEP,
    FUSE_STEP,
    LEG_PROBE,
    MARK_INTENT,
    MARK_MISS_STEP,
    MARK_STEP,
    PRECHECK_PROBE,
    ROSTER_ALREADY,
    ROSTER_TAPPED,
    ROSTER_UNREADABLE,
    SETTLE_POLL_S,
    SETTLE_ROUNDS,
    STANCE_STEPS,
    STUCK_STEP,
    TOUR_STEP,
    ZERO_STEP,
    ZOOM_STEP,
    BoardDriver,
    CoverageLedger,
    SettledFrame,
    SurveyPerceiver,
    survey_drivers,
)
from tests.fixtures.frames import load
from tests.fixtures.stage_offline import MockAdvisor, ScriptedPerceiver, battle, frame
from tests.fixtures.synthetic_map import CORNER, World

SERIES = Path(__file__).resolve().parent / "fixtures" / "vision" / "map_scan" / "ex2if_20260719"
FREE = Pricing(1.0)
ROSTER_EXPANDED_FRAME = "forecast/our_turn_unit_list_20260719"
ROSTER_COLLAPSED_FRAME = "forecast/our_turn_list_collapsed_20260719"
ROSTER_COVERED_FRAME = "forecast/unit_detail_combined_20260719"


@functools.cache
def map_frame() -> np.ndarray:
    image = cv2.imread(str(SERIES / "03_pt3_pan_up.png"))
    assert image is not None
    return image


@dataclass
class Rig:
    """腳本化鏡頭：手指行程乘上比例推鏡頭，虛空外緣就是鏡頭推得到的界。

    blank 數的是截圖次數（靜止閘讓每次 observe 花掉兩張，見 test_runtime_coverage
    的同名替身）：空白幀定位不出來，那一幀整張丟掉。
    """

    world: World
    gain: float = 2.0
    swipes: int = 0
    taps: int = 0
    shots: int = 0
    blank: tuple[int, ...] = ()

    def capture(self) -> np.ndarray:
        self.shots += 1
        if self.shots in self.blank:
            return np.zeros((1080, 2340, 3), np.uint8)
        return self.world.frame()

    def tap(self, x: int, y: int, intent: str = "") -> None:
        """掃描只點一種東西：空格（放標記格）。點到別的地方就是這一批的錯。"""
        assert intent == MARK_INTENT
        self.taps += 1
        self.world.tap(x, y)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_s: float) -> None:
        self.swipes += 1
        self.world.move((x1 - x2) * self.gain, (y1 - y2) * self.gain)


@dataclass
class Glide:
    """慣性滑行的鏡頭：每次取幀前先滑一段，drifts 用完就停住（＝滑行結束）。"""

    world: World
    drifts: list[float] = field(default_factory=list)
    shots: int = 0

    def capture(self) -> np.ndarray:
        self.shots += 1
        if self.drifts:
            self.world.move(self.drifts.pop(0), 0.0)
        return self.world.frame()


@dataclass
class FakeActuator:
    taps: list[tuple[int, int, str]] = field(default_factory=list)
    swipes: list[tuple[int, int, int, int, float]] = field(default_factory=list)

    def tap(self, x: int, y: int, intent: str = "") -> None:
        self.taps.append((x, y, intent))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_s: float) -> None:
        self.swipes.append((x1, y1, x2, y2, duration_s))

    def key(self, keycode: str) -> None:
        raise AssertionError("掃描不用按鍵")


@dataclass
class Camera:
    """腳本化鏡頭：每次平移把畫面捲一段，或（到邊時）原地不動。"""

    frames: list[np.ndarray]
    index: int = 0

    def capture(self) -> np.ndarray:
        return self.frames[min(self.index, len(self.frames) - 1)]

    def advance(self) -> None:
        self.index += 1


def rolled(steps: int) -> np.ndarray:
    return np.roll(map_frame(), -250 * steps, axis=1)


def _survey_then_kill(current: StageState, action) -> Pricing | None:
    """情報不全＝行為：盤面沒同步就不替戰鬥背書，計畫自己長出掃描。"""
    if isinstance(action, Attack):
        return Pricing(1.0, Guarantee.KILL) if current.board_synced else None
    if isinstance(action, ShowGrid | CollapseRoster | SurveyBoard):
        return Pricing(1.0)
    return None


def test_the_survey_needs_the_grid_first():
    """grid_on 是符號前置條件：沒格線就不可掃，也沒有降級版可以掃。"""
    dark = battle(allies=["a1"], enemies=["e1"], grid_on=False, board_synced=False)

    assert not SurveyBoard().applicable(dark)
    assert ShowGrid().applicable(dark)


def test_the_survey_needs_the_roster_strip_collapsed_too():
    """展開的卡條蓋住掃描帶下緣（一路到 y1020）：同 grid_on，前置條件是符號的。"""
    open_strip = battle(allies=["a1"], enemies=["e1"], roster_collapsed=False, board_synced=False)

    assert not SurveyBoard().applicable(open_strip)
    assert CollapseRoster().applicable(open_strip)

    collapsed = CollapseRoster().apply(open_strip, FREE)

    assert collapsed.roster_collapsed
    assert SurveyBoard().applicable(collapsed)
    assert CollapseRoster().progressed(collapsed, FREE)
    assert not CollapseRoster().applicable(collapsed)


def test_collapsing_the_roster_is_a_candidate_only_while_the_strip_is_open():
    open_strip = battle(allies=["a1"], enemies=["e1"], roster_collapsed=False, board_synced=False)
    collapsed = battle(allies=["a1"], enemies=["e1"], board_synced=False)

    assert "collapse_roster" in [action.label for action in candidates(open_strip)]
    assert "collapse_roster" not in [action.label for action in candidates(collapsed)]


def test_the_planner_collapses_the_roster_before_the_survey():
    state = battle(
        allies=["a1"],
        enemies=["e1"],
        grid_on=False,
        roster_collapsed=False,
        board_synced=False,
        known=["a1", "e1"],
    )

    labels = [
        step.action.label
        for step in plan(
            state, Annihilation(), MockAdvisor(_survey_then_kill), PlannerConfig()
        ).steps
    ]

    assert labels.index("collapse_roster") < labels.index("survey_board")
    assert labels.index("show_grid") < labels.index("survey_board")


def test_a_turn_boundary_makes_the_collapse_stale_again():
    """換回合重算可行動單位、卡條重繪：搜尋側取保守的那一邊（還要再收一次）。"""
    collapsed = battle(allies=["a1"], enemies=["e1"], actionable=[])

    assert not next_player_phase(collapsed).roster_collapsed


def test_the_driver_reads_the_strip_before_touching_the_toggle():
    actuator = FakeActuator()
    driver, _ = survey_drivers(
        lambda: load(ROSTER_COLLAPSED_FRAME), actuator, sleep=lambda _: None
    )

    step = driver.collapse_roster(CollapseRoster(), Observation(screen="battle_map"))

    assert step == ROSTER_ALREADY
    assert actuator.taps == []


def test_the_driver_taps_the_toggle_when_the_strip_is_open():
    actuator = FakeActuator()
    driver, _ = survey_drivers(lambda: load(ROSTER_EXPANDED_FRAME), actuator, sleep=lambda _: None)

    step = driver.collapse_roster(CollapseRoster(), Observation(screen="battle_map"))

    assert step == ROSTER_TAPPED
    assert [(x, y) for x, y, _ in actuator.taps] == [screens.ROSTER_TOGGLE_TAP]


def test_an_unreadable_strip_is_never_tapped_blind():
    """彈窗蓋住條帶＝讀不出來，不是收好了。盲點一下會把收好的卡條又展開。"""
    actuator = FakeActuator()
    driver, _ = survey_drivers(lambda: load(ROSTER_COVERED_FRAME), actuator, sleep=lambda _: None)

    step = driver.collapse_roster(CollapseRoster(), Observation(screen="battle_map"))

    assert step == ROSTER_UNREADABLE
    assert actuator.taps == []


def test_the_journal_records_which_micro_step_the_driver_did(tmp_path):
    """驅動型行動的自述要進流水帳：不然事後只看得到「做過一次掃描」，看不出那一 tick
    是縮放、平移還是合併，也看不出收卡條是點了還是本來就收好。"""
    journal = Journal(tmp_path / JOURNAL_NAME)
    driver, ledger = survey_drivers(
        lambda: load(ROSTER_COLLAPSED_FRAME), FakeActuator(), sleep=lambda _: None
    )
    executor = LiveExecutor(
        device=FakeActuator(), drivers=driver.drivers(), journal=journal, sleep=lambda _: None
    )
    ledger.zoomed = True

    executor.perform(CollapseRoster(), Observation(screen="battle_map"))

    recorded = [line for line in journal.entries() if line["kind"] == "perform"]
    assert [(line["label"], line["step"]) for line in recorded] == [
        ("collapse_roster", ROSTER_ALREADY)
    ]


def test_the_perceiver_takes_the_strip_state_from_the_frame_evidence():
    """感知權威：逐幀觀測覆寫符號狀態，讀不出來一律折成「沒收起」。"""
    seen = Observation(
        screen="battle_map",
        state=battle(allies=["a1"], enemies=["e1"], roster_collapsed=False),
        evidence={"roster_strip": screens.ROSTER_COLLAPSED},
    )
    covered = Observation(
        screen="battle_map",
        state=battle(allies=["a1"], enemies=["e1"]),
        evidence={"roster_strip": None},
    )

    assert SurveyPerceiver(ScriptedPerceiver([seen]), CoverageLedger()).look().state.roster_collapsed
    assert (
        not SurveyPerceiver(ScriptedPerceiver([covered]), CoverageLedger())
        .look()
        .state.roster_collapsed
    )


def test_showing_the_grid_supplies_the_precondition():
    dark = battle(allies=["a1"], enemies=["e1"], grid_on=False, board_synced=False)

    lit = ShowGrid().apply(dark, FREE)

    assert lit.grid_on
    assert SurveyBoard().applicable(lit)
    assert ShowGrid().progressed(lit, FREE)
    assert not ShowGrid().applicable(lit)


def test_the_survey_is_done_when_the_board_is_synced():
    lit = battle(allies=["a1"], enemies=["e1"], board_synced=False)

    after = SurveyBoard().apply(lit, FREE)

    assert after.board_synced
    assert SurveyBoard().progressed(after, FREE)
    assert not SurveyBoard().applicable(after)


def test_partial_coverage_is_not_completion():
    """完成判準是建構性的（四旗全定 ∧ 界內無缺口）：掃了一半仍然沒完成，而
    符號層看得到的就只有這一個位元。"""
    ledger = CoverageLedger()
    ledger.survey.observe(map_frame())
    halfway = battle(allies=["a1"], enemies=["e1"], board_synced=ledger.synced)

    assert not ledger.synced
    assert not SurveyBoard().progressed(halfway, FREE)
    assert SurveyBoard().applicable(halfway)


def test_both_board_actions_show_up_as_candidates_only_when_applicable():
    dark = battle(allies=["a1"], enemies=["e1"], grid_on=False, board_synced=False)
    lit = battle(allies=["a1"], enemies=["e1"], board_synced=False)
    done = battle(allies=["a1"], enemies=["e1"])

    assert "show_grid" in [action.label for action in candidates(dark)]
    assert "survey_board" not in [action.label for action in candidates(dark)]
    assert "survey_board" in [action.label for action in candidates(lit)]
    assert "show_grid" not in [action.label for action in candidates(lit)]
    assert not {"show_grid", "survey_board"} & {action.label for action in candidates(done)}


def test_the_planner_orders_show_grid_before_the_survey():
    """規劃器自然排序：Advisor 不替沒同步盤面的攻擊背書，計畫就自己長出
    開格線→掃描→攻擊。"""
    state = battle(
        allies=["a1"], enemies=["e1"], grid_on=False, board_synced=False, known=["a1", "e1"]
    )

    result = plan(state, Annihilation(), MockAdvisor(_survey_then_kill), PlannerConfig())

    assert [step.action.label for step in result.steps] == [
        "show_grid",
        "survey_board",
        "attack:a1->e1",
    ]


def test_a_turn_boundary_expires_the_board_sync():
    """敵方回合過完，敵人都動過，站位全部作廢。格線不受影響。"""
    synced = battle(allies=["a1"], enemies=["e1"], actionable=[])

    after = next_player_phase(synced)

    assert after.grid_on
    assert not after.board_synced


def test_the_ledger_zooms_first_and_only_once():
    """縮放是最佳化不是前提，但它改的是比例——所以它排在最前面，掃描的世界錨點
    才不會在半路作廢。"""
    world = World(cols=22, rows=12, units=CORNER + ((3, 5), (9, 6)))
    rig = Rig(world)
    zooms: list[int] = []
    driver, ledger = survey_drivers(
        rig.capture, rig, zoom_out=lambda: zooms.append(1), sleep=lambda _: None
    )

    assert driver.survey_board(SurveyBoard(), Observation(screen="battle_map")) == ZOOM_STEP
    assert ledger.zoomed
    assert zooms == [1]
    assert rig.swipes == 0

    # 縮放之後第一件事是放標記格（一 tick 一個微步驟），第二件才是往角落推。
    assert driver.survey_board(SurveyBoard(), Observation(screen="battle_map")) == MARK_STEP
    step = driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))

    assert step.startswith(ZERO_STEP)
    assert zooms == [1]
    assert rig.swipes == 1


def test_the_survey_carries_on_without_a_zoom_backend():
    """成功不依賴縮小：接不上後端照樣掃得完，只是截圖與平移次數變多。"""
    world = World(cols=22, rows=12, units=CORNER + ((3, 5), (9, 6)))
    rig = Rig(world)
    driver, ledger = survey_drivers(rig.capture, rig, sleep=lambda _: None)

    assert driver.survey_board(SurveyBoard(), Observation(screen="battle_map")) == ZOOM_STEP
    assert ledger.zoomed

    for _ in range(45):
        driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))
        if ledger.synced:
            break

    assert ledger.synced
    assert ledger.cells()


def test_the_driver_does_exactly_one_micro_step_per_call():
    """一 tick 一個微步驟：反射才插得進來。微步驟是點一下或推一把，永遠不是兩件事。"""
    world = World(cols=22, rows=12, units=CORNER + ((3, 5),))
    rig = Rig(world)
    driver, ledger = survey_drivers(rig.capture, rig, sleep=lambda _: None)
    ledger.zoomed = True

    for count in (1, 2, 3):
        driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))

        assert rig.swipes + rig.taps == count
        assert len(driver.steps) == count


def test_the_micro_step_says_which_way_it_went():
    """流水帳要看得出這一 tick 往哪推——不然事後只知道「做過一次掃描」。"""
    world = World(cols=22, rows=12, units=())
    rig = Rig(world)
    driver, ledger = survey_drivers(rig.capture, rig, sleep=lambda _: None)
    ledger.zoomed = True

    driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))
    step = driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))

    assert driver.steps[0] == MARK_STEP
    assert step.split(":")[0] in STANCE_STEPS
    assert step.split(":")[1] in board.DIRECTIONS


@dataclass
class DeafRig(Rig):
    """點下去什麼都沒發生的裝置：點到單位、點擊被吃掉都長這樣。"""

    def tap(self, x: int, y: int, intent: str = "") -> None:
        assert intent == MARK_INTENT
        self.taps += 1


def test_the_mark_step_taps_one_empty_cell_and_pans_nothing():
    """一 tick 至多一次操作：放標記那一 tick 點一下就結束，推移留給下一 tick。"""
    world = World(cols=22, rows=12, units=CORNER + ((3, 5),))
    rig = Rig(world)
    driver, ledger = survey_drivers(rig.capture, rig, sleep=lambda _: None)
    ledger.zoomed = True

    step = driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))

    assert step == MARK_STEP
    assert (rig.taps, rig.swipes) == (1, 0)
    assert ledger.survey.marker_signature is not None
    assert world.marker is not None


def test_three_taps_that_filled_nothing_stop_the_marking_for_this_turn():
    """點下去卻沒出現填色＝點擊本身失敗（點到單位、指令被吃掉）。連三次就這一代
    不再嘗試，照舊掃——標記是增強不是硬依賴。"""
    world = World(cols=22, rows=12, units=CORNER + ((3, 5),))
    rig = DeafRig(world)
    driver, ledger = survey_drivers(rig.capture, rig, sleep=lambda _: None)
    ledger.zoomed = True

    for _ in range(5):
        driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))

    assert driver.steps[: coverage.MARKER_TRIES] == [MARK_MISS_STEP] * coverage.MARKER_TRIES
    assert rig.taps == coverage.MARKER_TRIES
    assert ledger.survey.marker_declined
    assert [step.split(":")[0] for step in driver.steps[coverage.MARKER_TRIES :]] == [ZERO_STEP] * 2
    assert rig.swipes == 2


def test_losing_the_marker_to_a_pan_costs_nothing_but_a_fresh_tap():
    """**推移之後標記消失是常態不是異常**：補放不記罰、不計入放棄門檻。"""
    world = World(cols=22, rows=12, units=CORNER + ((3, 5),))
    rig = Rig(world)
    driver, ledger = survey_drivers(rig.capture, rig, sleep=lambda _: None)
    ledger.zoomed = True
    for _ in range(6):
        driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))
    world.marker = None

    step = driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))

    assert step == MARK_STEP
    assert ledger.survey.marker_misses == 0
    assert not ledger.survey.marker_declined
    assert ledger.summary()["marker"]["placed"] >= 2


def test_an_unreadable_world_keeps_pushing_towards_the_corner_and_writes_nothing():
    """讀不出格網的畫面（地圖邊緣的半幅虛空）待在原地只會永遠讀不到，所以照樣推。
    但那幾幀還在歸零段——微步驟名說得出來，而且一格都沒寫進知識圖。"""
    blank = np.zeros((1080, 2340, 3), np.uint8)
    actuator = FakeActuator()
    driver, ledger = survey_drivers(lambda: blank, actuator, sleep=lambda _: None)
    ledger.zoomed = True

    step = driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))

    assert step.startswith(ZERO_STEP)
    assert len(actuator.swipes) == 1
    assert not ledger.survey.anchored
    assert ledger.survey.chart is None




def _glider(drifts: list[float]) -> Glide:
    return Glide(World(cols=22, rows=12, units=CORNER + ((3, 5), (9, 6))), drifts=drifts)


def test_the_scan_waits_out_the_glide_before_it_takes_the_frame():
    """pan 的慣性滑行拖過 PAN_SETTLE_S，所以取幀前多等幾輪，收下的是最後那一幀
    ——滑行已經停了的那一張。"""
    glide = _glider([0.0, 40.0, 15.0])
    naps: list[float] = []
    driver, _ = survey_drivers(glide.capture, FakeActuator(), sleep=naps.append)

    settled = driver._settled_capture()

    assert settled.waits == SETTLE_ROUNDS
    assert glide.shots == SETTLE_ROUNDS + 1
    assert naps == [SETTLE_POLL_S] * SETTLE_ROUNDS
    assert glide.drifts == []
    assert np.array_equal(settled.frame, glide.world.frame())


def test_a_frame_that_is_still_moving_is_observed_anyway():
    """多等只降污染率，不保證零污染：停在原地不收幀會把整個 tick 空轉掉。"""
    glide = _glider([30.0] * 12)
    driver, _ = survey_drivers(glide.capture, FakeActuator(), sleep=lambda _: None)

    settled = driver._settled_capture()

    assert settled.waits == SETTLE_ROUNDS
    assert glide.shots == SETTLE_ROUNDS + 1
    assert settled.frame.any()


def test_the_frame_grab_never_asks_the_background_whether_the_screen_stopped():
    """0803 第 10 輪定讞：整區灰階量測讀到的是不隨鏡頭動的星空層，拿它問「畫面停了
    沒」是背景在答話。取幀這一步於是沒有判準，也不准長回來——連同手勢的量早就退出
    座標計算（`board.envelope` 與 `measure_pan` 隨骨架退場）。"""
    for gone in ("envelope", "measure_pan", "measure_shift", "_phase_shift"):
        assert not hasattr(board, gone), gone

    assert not hasattr(SettledFrame(np.zeros((1, 1, 3), np.uint8), 1), "quiet")


def _traced(ticks: int, **kwargs) -> tuple[BoardDriver, Rig]:
    rig = Rig(World(cols=22, rows=12, units=CORNER + ((3, 5), (9, 6))))
    driver, ledger = survey_drivers(rig.capture, rig, sleep=lambda _: None, **kwargs)
    ledger.zoomed = True
    for _ in range(ticks):
        driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))
    return driver, rig


def _expected_probes(driver: BoardDriver) -> list[tuple[int, str]]:
    """每一個微步驟該留下哪幾筆 observe：放標記那一 tick 只收前置複核幀（確認幀是
    「剛剛那一下填出顏色沒有」，不是位置證據），推移那一 tick 前後各收一張。"""
    return [
        (tick, probe)
        for tick, step in enumerate(driver.steps, start=1)
        for probe in (
            (PRECHECK_PROBE,) if step.startswith(MARK_STEP) else (PRECHECK_PROBE, LEG_PROBE)
        )
    ]


def test_the_telemetry_files_one_row_per_observe_with_the_measurement():
    """A5 儀器化：微步驟名答不了「那一把到底移了多少」，位移量與閘門裁決只有這一種
    紀錄看得到。"""
    rows: list[dict] = []
    driver, _ = _traced(3, telemetry=rows.append)

    assert [(row["tick"], row["probe"]) for row in rows] == _expected_probes(driver)
    for row in rows:
        assert set(row) == {
            "tick",
            "probe",
            "sequence",
            "stance",
            "direction",
            "reach",
            "expected",
            "verdict",
            "reason",
            "shift",
            "offset",
            "span",
            "locate",
            "settle",
            "marker",
        }
        assert set(row["shift"]) == {"dx", "dy", "magnitude", "confidence", "source"}
        assert set(row["span"]) == {"sequence", "box", "edges"}
        assert set(row["settle"]) == {"waits"}
        assert set(row["marker"]) == {"cell", "screen", "seen", "placed", "survived", "lost"}
        assert len(row["offset"]) == 2
        assert row["sequence"] == row["span"]["sequence"]
        assert row["stance"] in STANCE_STEPS

    prechecks = [row for row in rows if row["probe"] == PRECHECK_PROBE]
    legs = [row for row in rows if row["probe"] == LEG_PROBE]
    # 前置複核幀沒有推移指令，所以那三欄全空
    assert all(row["direction"] is None and row["expected"] is None for row in prechecks)
    assert all(row["reach"] is None for row in prechecks)
    assert all(row["direction"] in board.DIRECTIONS for row in legs)
    assert all(len(row["expected"]) == 2 for row in legs)
    # 開頭這幾把是往西北角推的歸零段：那裡本來就不談座標
    assert legs[0]["verdict"] == coverage.ZEROING


def test_the_telemetry_reports_how_many_polls_the_frame_grab_spent():
    """節奏是固定的，所以這個數字現在只記「等了幾輪」，不再宣稱畫面停了沒。"""
    rows: list[dict] = []
    _traced(2, telemetry=rows.append)

    assert {row["settle"]["waits"] for row in rows} == {SETTLE_ROUNDS}


def test_the_telemetry_lands_in_the_journal_as_numbers_not_strings(tmp_path):
    """Journal 的 default=str 是安全網不是預期路徑——numpy 純量會被悄悄寫成字串，
    事後就沒得算了。"""
    journal = Journal(tmp_path / JOURNAL_NAME)
    driver, _ = _traced(3, telemetry=lambda record: journal.record("survey_tick", **record))

    rows = [line for line in journal.entries() if line["kind"] == "survey_tick"]

    assert len(rows) == len(_expected_probes(driver))
    for row in rows:
        assert isinstance(row["shift"]["magnitude"], float)
        assert isinstance(row["shift"]["dx"], float)
        assert all(isinstance(value, float) for value in row["offset"])
        assert isinstance(row["settle"]["waits"], int)


def test_a_failing_telemetry_sink_never_stops_the_scan():
    """遙測是純觀察者：水槽炸了只記一次警告，掃描照跑。"""

    def boom(record: dict) -> None:
        raise RuntimeError("journal is on fire")

    driver, rig = _traced(3, telemetry=boom)

    assert [step.split(":")[0] for step in driver.steps] == [MARK_STEP, ZERO_STEP, ZERO_STEP]
    assert rig.swipes == 2




def _witnessed(
    *, dump_frames: bool = False, **kwargs
) -> tuple[BoardDriver, list[tuple[dict, np.ndarray | None, np.ndarray]]]:
    rig = Rig(World(cols=22, rows=12, units=CORNER + ((3, 5), (9, 6))), **kwargs)
    kept: list[tuple[dict, np.ndarray | None, np.ndarray]] = []
    driver, ledger = survey_drivers(
        rig.capture,
        rig,
        sleep=lambda _: None,
        evidence=lambda record, prev, curr: kept.append((record, prev, curr)),
        dump_frames=dump_frames,
    )
    ledger.zoomed = True
    return driver, kept


# 錨定之後的第一張前置複核幀（第 6 tick 的第 55 張截圖，取幀節奏一次五張、收最後
# 那一張）。那時才談得上定位——之前的幀還在歸零段，本來就不解座標。
FIRST_PLACED_SHOT = 55


def test_a_discarded_frame_hands_both_frames_to_the_evidence_sink():
    """丟棄一幀的根因在幀存下來之前定不了讞——遙測只有數字，離線重放要的是那一對
    幀本身。"""
    driver, kept = _witnessed(blank=(FIRST_PLACED_SHOT,))

    for _ in range(6):
        driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))

    assert len(kept) == 1
    record, previous, current = kept[0]
    assert record["verdict"] == coverage.BROKEN
    assert (record["probe"], record["direction"]) == (PRECHECK_PROBE, None)
    assert not current.any()
    # 前一幀來自執行器自己留的引用：世界模型丟棄一幀時刻意不動它記的定位基準
    assert previous is not None and previous.any()


def test_the_evidence_sink_stays_silent_while_the_chain_holds():
    """存證只在定位中斷時發射：整輪都好好的就不該留下任何一對幀。"""
    driver, kept = _witnessed()

    for _ in range(3):
        driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))

    assert kept == []


def test_dumping_survey_frames_hands_over_every_observe_in_order():
    """離線重放量測要的是整輪的 settled 幀，不只定位中斷那幾張。"""
    driver, kept = _witnessed(dump_frames=True)

    for _ in range(3):
        driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))

    assert [(record["tick"], record["probe"]) for record, _, _ in kept] == _expected_probes(driver)
    assert kept[0][1] is None
    # 上一幀就是上一次 observe 收下的那一張——這條鏈住在執行器，不是量測層
    for (_, previous, _), (_, _, earlier) in zip(kept[1:], kept[:-1], strict=True):
        assert previous is earlier


def test_a_failing_evidence_sink_never_stops_the_scan():
    """存證是純觀察者：水槽炸了只記一次警告，掃描照跑。"""

    def boom(record: dict, previous, current) -> None:
        raise RuntimeError("the disk is on fire")

    rig = Rig(
        World(cols=22, rows=12, units=CORNER + ((3, 5), (9, 6))), blank=(FIRST_PLACED_SHOT,)
    )
    driver, ledger = survey_drivers(rig.capture, rig, sleep=lambda _: None, evidence=boom)
    ledger.zoomed = True

    for _ in range(6):
        step = driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))

    assert step.split(":")[0] in STANCE_STEPS
    assert rig.swipes + rig.taps == 6


def test_the_survey_completes_when_there_is_nothing_left_to_scan():
    world = World(cols=22, rows=12, units=CORNER + ((3, 5), (9, 6), (14, 3)))
    rig = Rig(world)
    driver, ledger = survey_drivers(rig.capture, rig, sleep=lambda _: None)
    ledger.zoomed = True

    for _ in range(45):
        step = driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))
        if ledger.synced:
            break

    assert ledger.synced
    # 三個階段都要走過：推去角落歸零、沿邊繞一圈，中央有缺口才補
    assert any(name.startswith(ZERO_STEP) for name in driver.steps)
    assert any(name.startswith(TOUR_STEP) for name in driver.steps)
    # 收尾那一 tick 可能是掃描平移，也可能是「HUD 挖洞蓋住的角落格退休」——後者同樣
    # 讓待掃格清空，只是回 DONE_STEP。
    assert step.split(":")[0] in STANCE_STEPS or step == DONE_STEP
    assert len(ledger.cells()) == len(world.units)
    # 再叫一次也不會亂動：沒有待掃格了
    assert driver.survey_board(SurveyBoard(), Observation(screen="battle_map")) == DONE_STEP


def test_the_gesture_fuse_stops_instead_of_burning_the_whole_tick_budget():
    """平移次數上限只是防失控的保險絲，不是完成判準——燒斷了就誠實停在沒同步。"""
    world = World(cols=22, rows=12, units=())
    rig = Rig(world)
    ledger = CoverageLedger(survey=coverage.Survey(budget=1))
    ledger.zoomed = True
    driver, _ = survey_drivers(rig.capture, rig, ledger=ledger, sleep=lambda _: None)

    for _ in range(3):
        step = driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))

    assert step == FUSE_STEP
    assert not ledger.synced


def test_the_driver_resumes_from_the_ledger_not_from_its_own_variables():
    """換一個執行器實例也接得下去——恢復點在簿記，不在執行器內部。"""
    world = World(cols=22, rows=12, units=CORNER + ((3, 5),))
    rig = Rig(world)
    ledger = CoverageLedger()
    ledger.zoomed = True
    first, _ = survey_drivers(rig.capture, rig, ledger=ledger, sleep=lambda _: None)
    first.survey_board(SurveyBoard(), Observation(screen="battle_map"))

    second, _ = survey_drivers(rig.capture, rig, ledger=ledger, sleep=lambda _: None)
    second.survey_board(SurveyBoard(), Observation(screen="battle_map"))

    assert second.steps[0].startswith(ZERO_STEP)
    assert ledger.survey.observes > 0


def test_expiry_downgrades_the_board_and_keeps_the_map_geometry():
    """衰效降級不抹除：UNIT→STALE、EMPTY→UNKNOWN，邊界旗與縮放留著。"""
    world = World(cols=22, rows=12, units=CORNER + ((3, 5), (9, 6), (14, 3)))
    rig = Rig(world)
    driver, ledger = survey_drivers(rig.capture, rig, sleep=lambda _: None)
    ledger.zoomed = True
    for _ in range(40):
        driver.survey_board(SurveyBoard(), Observation(screen="battle_map"))
        if ledger.synced:
            break
    bounded = ledger.summary()["bounded"]

    ledger.expire()
    summary = ledger.summary()

    assert not ledger.synced
    assert summary["cells"]["stale"] == len(world.units)
    assert summary["cells"]["unit"] == 0
    assert ledger.cells() == ()
    assert summary["bounded"] == bounded
    assert ledger.zoomed
    assert summary["generation"] == 1


def test_the_perceiver_folds_the_coverage_ledger_into_the_symbolic_state():
    """符號層只看得到 board_synced；逐格的覆蓋進度走 evidence 進流水帳。"""
    ledger = CoverageLedger()
    seen = frame(battle(allies=["a1"], enemies=["e1"], board_synced=False, grid_on=False))
    perceiver = SurveyPerceiver(ScriptedPerceiver([seen]), ledger)

    observed = perceiver.look()

    assert not observed.state.board_synced
    assert observed.evidence["survey"]["coverage"] == 0.0
    assert observed.evidence["survey"]["complete"] is False


def test_the_perceiver_takes_grid_on_from_the_frame_evidence():
    seen = Observation(
        screen="battle_map",
        state=battle(allies=["a1"], enemies=["e1"], grid_on=False),
        evidence={"grid_on": True},
    )
    perceiver = SurveyPerceiver(ScriptedPerceiver([seen]), CoverageLedger())

    assert perceiver.look().state.grid_on is True


def test_an_enemy_phase_expires_the_ledger_so_the_next_turn_rescans():
    ledger = CoverageLedger()
    ledger.survey.observe(map_frame())
    enemy_turn = frame(
        battle(allies=["a1"], enemies=["e1"], actionable=[], phase=Phase.ENEMY)
    )
    perceiver = SurveyPerceiver(ScriptedPerceiver([enemy_turn, enemy_turn]), ledger)

    state = perceiver.look().state

    assert not ledger.synced
    assert ledger.summary()["cells"]["empty"] == 0
    assert not state.board_synced

    perceiver.look()

    # 整個敵方回合只衰效一次：每加一代就換一套世界座標，逐 tick 加會讓掃描
    # 永遠停在重新錨定
    assert ledger.generation == 1


def test_a_screen_with_no_symbolic_reading_passes_straight_through():
    perceiver = SurveyPerceiver(
        ScriptedPerceiver([Observation(screen="cutscene")]), CoverageLedger()
    )

    assert perceiver.look().state is None


def test_the_survey_action_stays_at_the_queue_head_across_ticks(tmp_path):
    """佇列頭跨 tick 重入：畫面還沒說掃完，計畫就不彈。"""
    unsynced = battle(allies=["a1"], enemies=["e1"], board_synced=False)
    order = StageOrder(
        stage="S01",
        objectives=frozenset({Objective.CLEAR}),
        hidden_policy=HiddenPolicy.DECLINE,
        max_ticks=5,
    )

    performed: list[str] = []
    executor = LiveExecutor(
        device=FakeActuator(),
        drivers={SurveyBoard: lambda action, observation: performed.append(action.label)},
        sleep=lambda _: None,
    )
    loop = StageLoop(
        order,
        perceiver=ScriptedPerceiver([frame(unsynced), frame(unsynced), frame(unsynced)]),
        executor=executor,
        advisor=MockAdvisor(_survey_then_kill),
        victory=Annihilation(),
        journal=Journal(tmp_path / JOURNAL_NAME),
    )

    outcomes = [loop.tick().outcome for _ in range(3)]

    assert outcomes == [TickOutcome.ACTED] * 3
    assert performed == ["survey_board"] * 3
    assert [step.action.label for step in loop.queue][0] == "survey_board"


def test_a_reflex_can_interrupt_the_survey_and_it_carries_on(tmp_path):
    from ggge_ai.runtime import screens
    from ggge_ai.runtime.reflexes import UNIT_DETAIL_FIX, PopupReflex

    unsynced = battle(allies=["a1"], enemies=["e1"], board_synced=False)
    order = StageOrder(
        stage="S01",
        objectives=frozenset({Objective.CLEAR}),
        hidden_policy=HiddenPolicy.DECLINE,
        max_ticks=5,
    )
    frames = [
        frame(unsynced),
        Observation(screen=screens.UNIT_DETAIL),
        frame(unsynced),
        Observation(screen="battle_result", terminal=Ending.VICTORY),
    ]
    performed: list[str] = []
    executor = LiveExecutor(
        device=FakeActuator(),
        drivers={SurveyBoard: lambda action, observation: performed.append("survey")},
        sleep=lambda _: None,
    )
    loop = StageLoop(
        order,
        perceiver=ScriptedPerceiver(frames),
        executor=executor,
        advisor=MockAdvisor(_survey_then_kill),
        victory=Annihilation(),
        journal=Journal(tmp_path / JOURNAL_NAME),
        reflexes=(PopupReflex("unit_detail", screens.UNIT_DETAIL, UNIT_DETAIL_FIX),),
    )

    outcomes = [loop.tick().outcome for _ in range(3)]

    assert outcomes == [TickOutcome.ACTED, TickOutcome.REFLEX, TickOutcome.ACTED]
    assert performed == ["survey", "survey"]


def test_the_journal_records_the_board_symbols_every_tick(tmp_path):
    unsynced = battle(allies=["a1"], enemies=["e1"], grid_on=False, board_synced=False)
    order = StageOrder(
        stage="S01",
        objectives=frozenset({Objective.CLEAR}),
        hidden_policy=HiddenPolicy.DECLINE,
        max_ticks=2,
    )
    journal = Journal(tmp_path / JOURNAL_NAME)
    loop = StageLoop(
        order,
        perceiver=ScriptedPerceiver([frame(unsynced)]),
        executor=LiveExecutor(device=FakeActuator(), sleep=lambda _: None),
        advisor=MockAdvisor(lambda current, action: None),
        victory=Annihilation(),
        journal=journal,
    )

    loop.tick()

    seen = journal.entries()[0]["seen"]
    assert seen["grid_on"] is False
    assert seen["board_synced"] is False
    assert "swept" not in seen


def test_the_journal_gets_the_coverage_numbers_every_tick(tmp_path):
    """規格要求逐 tick 記覆蓋率、待掃格聚類數、丟棄幀數與歸零次數。它們壓不成
    搜尋鍵，所以走 evidence——迴圈本來就逐 tick 把 evidence 抄進流水帳。"""
    ledger = CoverageLedger()
    order = StageOrder(
        stage="S01",
        objectives=frozenset({Objective.CLEAR}),
        hidden_policy=HiddenPolicy.DECLINE,
        max_ticks=2,
    )
    journal = Journal(tmp_path / JOURNAL_NAME)
    unsynced = battle(allies=["a1"], enemies=["e1"], board_synced=False)
    loop = StageLoop(
        order,
        perceiver=SurveyPerceiver(ScriptedPerceiver([frame(unsynced)]), ledger),
        executor=LiveExecutor(device=FakeActuator(), sleep=lambda _: None),
        advisor=MockAdvisor(lambda current, action: None),
        victory=Annihilation(),
        journal=journal,
    )

    loop.tick()

    survey = journal.entries()[0]["evidence"]["survey"]
    assert set(survey) >= {"coverage", "clusters", "frontier", "unlocalised", "stance", "zeroings"}
    assert survey["stance"] == coverage.ZERO
    assert survey["zeroings"] == 0
    assert survey["landmarks"] == {}


@pytest.mark.parametrize(
    "step",
    [
        ZOOM_STEP,
        ZERO_STEP,
        TOUR_STEP,
        FILL_STEP,
        DONE_STEP,
        FUSE_STEP,
        STUCK_STEP,
        MARK_STEP,
        MARK_MISS_STEP,
    ],
)
def test_the_micro_step_names_are_stable_for_the_journal(step):
    assert isinstance(step, str) and step
