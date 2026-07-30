"""實機驗證輪駕駛 script 的組裝：分段停點、每段解鎖、失敗停在原地。

裝置整支換成假件（螢幕是預錄的實幀 PNG 位元組），所以這一組完全不碰 adb。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np
import pytest

from ggge_ai.runtime import entry
from ggge_ai.runtime.device import LiveExecutor
from ggge_ai.runtime.journal import Journal
from ggge_ai.runtime.perceive import LivePerceiver
from ggge_ai.stage.survey import survey_drivers
from scripts.dry_run_entry import JOURNAL_NAME, Camera, DryRun, Halt, point
from tests.fixtures.frames import load

STAGE_LIST = "popups/stage_list_dim_20260719"
PREP = "stage_panels/prep_screen"


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

    def screenshot(self) -> bytes:
        return cv2.imencode(".png", self.frame)[1].tobytes()

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


def test_stopping_after_select_never_taps_anything(tmp_path):
    """關卡列表段不花資源也不動任何按鈕——第一次上機就跑這一段。"""
    run, device = dry_run(tmp_path, load(STAGE_LIST), stop_after="select")

    run.run()

    assert device.taps == []
    assert stages(run.journal) == ["select"]
    assert "gate" in kinds(run.journal)


def test_stopping_after_prep_taps_only_the_prep_button(tmp_path):
    run, device = dry_run(tmp_path, load(STAGE_LIST), to_prep(), stop_after="prep")

    run.run()

    assert [(x, y) for x, y, _ in device.taps] == [entry.STAGE_LIST_PREP_TAP]
    assert stages(run.journal) == ["select", "prep"]
    # 出擊鈕永遠不在這一段裡：出擊才開始花 EN 與挑戰次數。
    assert entry.SORTIE_TAP not in [(x, y) for x, y, _ in device.taps]


def test_every_stage_re_arms_the_keyguard(tmp_path):
    """兩種鎖都會無聲吞 tap，所以每段開頭一定要問一次。"""
    run, device = dry_run(tmp_path, load(STAGE_LIST), to_prep(), stop_after="prep")

    run.run()

    assert device.unlocks == len(stages(run.journal)) == 2


def test_a_failed_gate_halts_in_place_without_tapping(tmp_path):
    run, device = dry_run(tmp_path, np.zeros((1080, 2340, 3), np.uint8), stop_after="select")

    with pytest.raises(Halt):
        run.run()

    assert device.taps == []


def test_every_stage_boundary_keeps_a_native_frame(tmp_path):
    run, _ = dry_run(tmp_path, load(STAGE_LIST), stop_after="select")

    run.run()

    saved = [line for line in run.journal.entries() if line["kind"] == "frame"]
    assert [line["label"] for line in saved] == ["select:start", "select:end"]
    for line in saved:
        assert (tmp_path / line["frame"]).exists()


def test_the_node_argument_is_parsed_as_a_point():
    assert point("544,667") == (544, 667)
    assert point(None) is None
