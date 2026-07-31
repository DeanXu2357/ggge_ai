"""實機驗證輪駕駛 script 的組裝：分段停點、每段解鎖、失敗停在原地。

裝置整支換成假件（螢幕是預錄的實幀 PNG 位元組），所以這一組完全不碰 adb。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from ggge_ai.runtime import coverage, entry
from ggge_ai.runtime.device import LiveExecutor
from ggge_ai.runtime.journal import Journal
from ggge_ai.runtime.perceive import LivePerceiver
from ggge_ai.stage.survey import survey_drivers
from scripts.dry_run_entry import (
    BROKEN_PAIRS,
    JOURNAL_NAME,
    SURVEY_BROKEN,
    SURVEY_DONE,
    SURVEY_TICK,
    SURVEY_TICKS,
    Camera,
    DryRun,
    Halt,
    SurveyFrames,
    build,
    parse_args,
    point,
)
from tests.fixtures.frames import load

STAGE_LIST = "popups/stage_list_dim_20260719"
PREP = "stage_panels/prep_screen"
# 節點平台 (544,872) 落在戰鬥選單「放棄」的危險帶裡會被拒點，改點編號／星列那一列。
NODE = (544, 667)


@dataclass
class FakeDevice:
    """LiveDevice 的替身：截圖回原生 PNG 位元組（同實機通道）。

    畫面只在 transitions 指定的那幾個點被按下時才換頁——所以測試不必去數截圖次數，
    「按了那顆鈕才會到下一頁」這件事本身就是斷言。
    """

    frame: np.ndarray
    transitions: dict[tuple[int, int], np.ndarray] = field(default_factory=dict)
    taps: list[tuple[int, int, str]] = field(default_factory=list)
    unlocks: int = 0
    handed: list[bytes] = field(default_factory=list)

    def screenshot(self) -> bytes:
        raw = cv2.imencode(".png", self.frame)[1].tobytes()
        self.handed.append(raw)
        return raw

    def ensure_unlocked(self, force: bool = False) -> None:
        self.unlocks += 1

    def tap(self, x: int, y: int, intent: str = "") -> None:
        self.taps.append((x, y, intent))
        self.frame = self.transitions.get((x, y), self.frame)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_s: float = 0.3) -> None:
        raise AssertionError("這一組不該平移")

    def key(self, keycode: str) -> None:
        raise AssertionError("這一組不該按鍵")


def dry_run(tmp_path, frame, transitions=None, **kwargs) -> tuple[DryRun, FakeDevice]:
    device = FakeDevice(frame=frame, transitions=transitions or {})
    journal = Journal(tmp_path / JOURNAL_NAME)
    camera = Camera(device=device, journal=journal)
    driver, _ = survey_drivers(camera.grab, device, sleep=lambda _: None)
    run = DryRun(
        device=device,
        camera=camera,
        journal=journal,
        executor=LiveExecutor(device=device, drivers=driver.drivers(), sleep=lambda _: None),
        driver=driver,
        perceiver=LivePerceiver(device=device),
        sleep=lambda _: None,
        **kwargs,
    )
    return run, device


def kinds(journal: Journal) -> list[str]:
    return [entry_["kind"] for entry_ in journal.entries()]


def stages(journal: Journal) -> list[str]:
    return [line["name"] for line in journal.entries() if line["kind"] == "stage"]


def to_prep() -> dict[tuple[int, int], np.ndarray]:
    return {entry.STAGE_LIST_PREP_TAP: load(PREP)}


def test_the_select_stage_taps_the_named_node_and_nothing_else(tmp_path):
    """關卡列表段不花資源，唯一的動作是點明示的那個節點——第一次上機就跑這一段。"""
    run, device = dry_run(tmp_path, load(STAGE_LIST), stop_after="select", node=NODE)

    run.run()

    assert [(x, y) for x, y, _ in device.taps] == [NODE]
    assert stages(run.journal) == ["select"]
    assert "gate" in kinds(run.journal)


def test_stopping_after_prep_taps_only_the_node_and_the_prep_button(tmp_path):
    run, device = dry_run(tmp_path, load(STAGE_LIST), to_prep(), stop_after="prep", node=NODE)

    run.run()

    assert [(x, y) for x, y, _ in device.taps] == [NODE, entry.STAGE_LIST_PREP_TAP]
    assert stages(run.journal) == ["select", "prep"]
    # 出擊鈕永遠不在這一段裡：出擊才開始花 EN 與挑戰次數。
    assert entry.SORTIE_TAP not in [(x, y) for x, y, _ in device.taps]


def test_every_stage_re_arms_the_keyguard(tmp_path):
    """兩種鎖都會無聲吞 tap，所以每段開頭一定要問一次。"""
    run, device = dry_run(tmp_path, load(STAGE_LIST), to_prep(), stop_after="prep", node=NODE)

    run.run()

    assert device.unlocks == len(stages(run.journal)) == 2


def test_a_failed_gate_halts_in_place_without_tapping(tmp_path):
    run, device = dry_run(
        tmp_path, np.zeros((1080, 2340, 3), np.uint8), stop_after="select", node=NODE
    )

    with pytest.raises(Halt):
        run.run()

    assert device.taps == []


def test_the_select_stage_keeps_a_shot_of_the_right_hand_panel(tmp_path):
    """選中哪一關畫面上讀不出來，而棄戰回來游標會飄——所以留圖給人事後核對。"""
    run, _ = dry_run(tmp_path, load(STAGE_LIST), stop_after="select", node=NODE)

    run.run()

    saved = [line for line in run.journal.entries() if line["kind"] == "frame"]
    assert [line["label"] for line in saved] == [
        "select:start",
        "select:right_panel",
        "select:end",
    ]
    for line in saved:
        assert (tmp_path / line["frame"]).exists()


def test_the_command_line_refuses_to_run_without_a_stage_node(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["dry_run_entry", "--stop-after", "select"])

    with pytest.raises(SystemExit):
        parse_args()


def test_the_perceiver_and_the_saved_frame_come_from_one_camera(tmp_path):
    """0730 發現②：Camera 與 LivePerceiver 各抓各的，段界存檔是陳舊幀、只有
    journal 的結構化欄位可信。單一幀源之後，判定用的與存下來的是同一張。"""
    device = FakeDevice(frame=load(STAGE_LIST))
    journal = Journal(tmp_path / JOURNAL_NAME)
    camera = Camera(device=device, journal=journal)

    seen = LivePerceiver(device=camera).look()
    saved = camera.keep("probe")

    assert len(device.handed) == camera.shots == 1
    assert seen.frame == device.handed[-1]
    assert (tmp_path / saved).read_bytes() == seen.frame


def test_the_assembled_run_gives_the_perceiver_the_camera_channel(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["dry_run_entry", "--stage-node", "544,667", "--no-zoom"])

    dry = build(parse_args(), Journal(tmp_path / JOURNAL_NAME))

    assert dry.perceiver.device is dry.camera


def test_the_assembled_run_pipes_the_survey_telemetry_into_the_journal(tmp_path, monkeypatch):
    """逐 observe 的量測（位移量、閘門裁決、靜止閘輪數）要落到流水帳——0801 複驗
    的 A5 量測疑點就是因為 journal 只有微步驟名而答不出來。"""
    monkeypatch.setattr(sys, "argv", ["dry_run_entry", "--stage-node", "544,667", "--no-zoom"])
    journal = Journal(tmp_path / JOURNAL_NAME)

    dry = build(parse_args(), journal)
    dry.driver.telemetry({"tick": 7, "probe": "leg"})

    rows = [line for line in journal.entries() if line["kind"] == SURVEY_TICK]
    assert [(line["tick"], line["probe"]) for line in rows] == [(7, "leg")]


def test_the_survey_summary_carries_the_unlocalised_count(tmp_path):
    """位移量不出來的那一幀會被隔離進島嶼，不進權威圖。次數要跟結果同一筆——
    看到 >0 就代表這一輪斷過鏈，不能只留在 log 裡。"""
    run, _ = dry_run(tmp_path, load(STAGE_LIST), node=NODE)
    run.driver.ledger.survey.unlocalised = 2

    run.summarize_survey()

    summary = [line for line in run.journal.entries() if line["kind"] == "survey_summary"]
    assert [line["unlocalised"] for line in summary] == [2]
    assert summary[0]["survey"]["islands"]["open"] is False
    assert "coverage" in summary[0]["survey"]


# ---- v2.3 斷鏈存證 ----


def broken(tick: int, reason: str = "phase") -> dict[str, object]:
    return {
        "tick": tick,
        "probe": "leg",
        "direction": "east",
        "reason": reason,
        "verdict": coverage.BROKEN,
    }


def test_a_broken_pair_lands_on_disk_as_two_full_frames(tmp_path):
    """斷鏈根因未定讞：離線重放量測要的是那一對幀本身，遙測的數字答不了。"""
    journal = Journal(tmp_path / JOURNAL_NAME)
    sink = SurveyFrames(journal=journal)
    frame = np.zeros((1080, 2340, 3), np.uint8)

    sink(broken(7, "no lattice"), frame, frame)

    row = [line for line in journal.entries() if line["kind"] == SURVEY_BROKEN][0]
    assert row["saved"] is True
    assert (row["tick"], row["probe"], row["reason"]) == (7, "leg", "no lattice")
    assert row["prev"] == "frames/broken/t7-leg-no_lattice-prev.png"
    assert row["curr"] == "frames/broken/t7-leg-no_lattice-curr.png"
    assert cv2.imread(str(tmp_path / row["curr"])).shape == frame.shape


def test_the_very_first_observe_has_no_previous_frame_to_keep(tmp_path):
    journal = Journal(tmp_path / JOURNAL_NAME)
    sink = SurveyFrames(journal=journal)

    sink(broken(1), None, np.zeros((1080, 2340, 3), np.uint8))

    row = [line for line in journal.entries() if line["kind"] == SURVEY_BROKEN][0]
    assert row["prev"] is None
    assert (tmp_path / row["curr"]).exists()


def test_past_the_pair_ceiling_the_break_is_journalled_but_not_photographed(tmp_path):
    """80 tick 全斷鏈時 run 目錄會被幀塞爆；上限之後只記流水帳。"""
    journal = Journal(tmp_path / JOURNAL_NAME)
    sink = SurveyFrames(journal=journal)
    frame = np.zeros((1080, 2340, 3), np.uint8)

    for tick in range(BROKEN_PAIRS + 3):
        sink(broken(tick), frame, frame)

    rows = [line for line in journal.entries() if line["kind"] == SURVEY_BROKEN]
    assert len(rows) == BROKEN_PAIRS + 3
    assert [line["saved"] for line in rows].count(True) == BROKEN_PAIRS
    assert len(list((tmp_path / "frames" / "broken").iterdir())) == BROKEN_PAIRS * 2


def test_an_intact_reading_is_only_photographed_when_dumping_is_on(tmp_path):
    journal = Journal(tmp_path / JOURNAL_NAME)
    frame = np.zeros((1080, 2340, 3), np.uint8)
    quiet = {"tick": 2, "probe": "precheck", "direction": None, "reason": "ok", "verdict": "ok"}

    SurveyFrames(journal=journal)(quiet, frame, frame)

    assert SURVEY_BROKEN not in kinds(journal)
    assert not (tmp_path / "frames" / "survey").exists()

    SurveyFrames(journal=journal, dump=True)(quiet, frame, frame)

    assert (tmp_path / "frames" / "survey" / "t2-precheck.png").exists()


def test_the_assembled_run_wires_the_evidence_sink_and_the_dump_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["dry_run_entry", "--stage-node", "544,667", "--no-zoom"])
    journal = Journal(tmp_path / JOURNAL_NAME)

    dry = build(parse_args(), journal)

    assert isinstance(dry.driver.evidence, SurveyFrames)
    assert dry.driver.dump_frames is False
    assert dry.driver.evidence.dump is False

    monkeypatch.setattr(
        sys,
        "argv",
        ["dry_run_entry", "--stage-node", "544,667", "--no-zoom", "--dump-survey-frames"],
    )
    dumping = build(parse_args(), Journal(tmp_path / "dump" / JOURNAL_NAME))

    assert dumping.driver.dump_frames is True
    assert dumping.driver.evidence.dump is True


# ---- v2.3 synced 提前結束 ----


@dataclass
class CountingLedger:
    """簿記替身：第 stop_at 次 perform 之後就宣告掃完。"""

    stop_at: int
    calls: int = 0

    @property
    def synced(self) -> bool:
        return self.calls >= self.stop_at

    def perform(self, action: object, observation: object) -> None:
        self.calls += 1


def scripted_sweep(tmp_path, stop_at: int, ticks: int) -> DryRun:
    run, _ = dry_run(tmp_path, load(STAGE_LIST), node=NODE, survey_ticks=ticks)
    ledger = CountingLedger(stop_at=stop_at)
    run.driver = SimpleNamespace(ledger=ledger)
    run.executor = ledger
    return run


def test_the_survey_loop_stops_the_moment_the_board_is_synced(tmp_path):
    """0801 複驗第 2 輪 29 腿就 synced，剩下的 50 tick 每 tick 白燒兩張截圖。"""
    run = scripted_sweep(tmp_path, stop_at=3, ticks=20)

    spent = run.sweep()

    assert spent == 3
    done = [line for line in run.journal.entries() if line["kind"] == SURVEY_DONE]
    assert [(line["tick"], line["budget"]) for line in done] == [(3, 20)]


def test_the_survey_loop_still_spends_the_whole_budget_when_it_never_syncs(tmp_path):
    run = scripted_sweep(tmp_path, stop_at=99, ticks=4)

    spent = run.sweep()

    assert spent == 4
    assert SURVEY_DONE not in kinds(run.journal)


def test_the_default_survey_budget_is_the_raised_one(monkeypatch):
    """0801 複驗的步數帳：南 11＋北 2＋東 18＋西 ~10 已 41 腿，40 tick 沒有餘裕。"""
    monkeypatch.setattr(sys, "argv", ["dry_run_entry", "--stage-node", "544,667"])

    assert parse_args().survey_ticks == SURVEY_TICKS == 80
    assert DryRun.survey_ticks == SURVEY_TICKS


def test_the_node_argument_is_parsed_as_a_point():
    assert point("544,667") == (544, 667)
    assert point(None) is None
