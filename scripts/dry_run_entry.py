"""實機驗證輪駕駛：關卡列表 → 進場閘門 → 開格線／收卡條 → 盤面掃描 → 棄戰。

全程走批 2d 的新通道（LiveDevice／LivePerceiver／LiveExecutor／runtime.entry／
stage.survey），危險帶白名單不繞過，每一段開頭掛一次 Keyguard。判斷全在 runtime／
stage 模組（都有離線測試），這支只負責組裝、迴圈與落證據。

usage:
  # 只驗到關卡列表／出擊準備頁——**不花任何資源**，第一次跑先跑這兩段
  uv run python scripts/dry_run_entry.py --serial R5CRC37JBYJ --stop-after select
  uv run python scripts/dry_run_entry.py --serial R5CRC37JBYJ --stop-after prep

  # 分段停點：select / prep / stage_info / map / grid / survey
  # stage_info 起開始花 EN 與挑戰次數
  uv run python scripts/dry_run_entry.py --serial R5CRC37JBYJ --stop-after grid
  uv run python scripts/dry_run_entry.py --serial R5CRC37JBYJ --survey-ticks 20

  # 全程（預設進到地圖之後會棄戰收尾；棄戰不耗 AP／挑戰次數／EN，0730 實證）
  uv run python scripts/dry_run_entry.py --serial R5CRC37JBYJ
  uv run python scripts/dry_run_entry.py --serial R5CRC37JBYJ --no-abandon

前提：手機已經停在目標系列的關卡列表（選擇關卡頁），**右欄已經是要打的那一關**。
--stage-node X,Y 可以先點一個關卡節點再進出擊準備，但選中的是哪一關畫面上讀不
出來（右欄標題還沒接文字讀取），所以一律自己看落檔的截圖確認。0730 的 UC HARD 1
節點平台約在 (544,872)，**那個點撞上戰鬥選單「放棄」的危險帶會被拒點**——要點就
點編號／星列那一列（y 較高，例如 544,667），或乾脆手動先選好關卡。

證據：data/runs/<時間戳>/dry_run.jsonl＋frames/（每段界線與每次失敗各存一張原生
幀）。任何 expect 失敗就停在原地不再點，印出畫面名與當下截圖路徑。
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from ggge_ai.runtime import entry, screens, zoom
from ggge_ai.runtime.device import Adb, LiveDevice, LiveExecutor
from ggge_ai.runtime.journal import Journal, rotate_runs
from ggge_ai.runtime.keyguard import Keyguard
from ggge_ai.runtime.perceive import LivePerceiver, Observation, decode
from ggge_ai.stage.actions import CollapseRoster, ShowGrid, SurveyBoard
from ggge_ai.stage.survey import BoardDriver, survey_drivers

log = logging.getLogger("dry_run_entry")

RUNS_ROOT = Path("data/runs")
JOURNAL_NAME = "dry_run.jsonl"
STAGES = ("select", "prep", "stage_info", "map", "grid", "survey")
# 只有真的進到地圖才有戰鬥可棄；停在更早的段落就交給人自己收。
IN_BATTLE_STAGES = (None, "map", "grid", "survey")


class Halt(RuntimeError):
    """停在原地：印出原因與當下截圖，不再點任何東西。"""


@dataclass
class Camera:
    """capture 通道，順手記住最後一張原生幀——段界與失敗點才有圖可指。"""

    device: LiveDevice
    journal: Journal
    raw: bytes | None = field(default=None, init=False)
    shots: int = field(default=0, init=False)

    def grab(self) -> np.ndarray:
        self.raw = self.device.screenshot()
        self.shots += 1
        return decode(self.raw)

    def keep(self, label: str) -> str | None:
        path = self.journal.save_frame(self.raw, self.shots)
        self.journal.record("frame", label=label, frame=path)
        return path


@dataclass
class DryRun:
    device: LiveDevice
    camera: Camera
    journal: Journal
    executor: LiveExecutor
    driver: BoardDriver
    perceiver: LivePerceiver
    stop_after: str | None = None
    survey_ticks: int = 20
    node: tuple[int, int] | None = None
    sleep: Callable[[float], None] = time.sleep

    def run(self) -> None:
        capture, tap, nap = self.camera.grab, self.device.tap, self.sleep

        self.begin("select")
        self.gate("select", entry.select_stage(capture, tap, node=self.node, sleep=nap))
        if self.end("select"):
            return

        self.begin("prep")
        self.gate("prep", entry.open_sortie_prep(capture, tap, entry.GateReport(), sleep=nap))
        if self.end("prep"):
            return

        self.begin("stage_info")
        report = entry.sortie(capture, tap, sleep=nap)
        self.gate("sortie", report)
        if self.end("stage_info"):
            return

        self.begin("map")
        self.gate("advance", entry.advance_to_map(capture, tap, report, sleep=nap))
        if self.end("map"):
            return

        self.begin("grid")
        self.perform(ShowGrid(), "show_grid")
        self.perform(CollapseRoster(), "collapse_roster")
        seen = self.observe("after_grid_and_roster")
        if self.end("grid"):
            return

        # 掃描的兩個符號前置條件，逐幀觀測說了才算。這支不跑規劃器，所以前置條件
        # 要自己在這裡守——沒格線或卡條還開著就掃，量出來的座標是垃圾。
        if not seen.evidence.get("grid_on"):
            raise Halt("格網讀不出來：ShowGrid 沒生效，掃描的前置條件不成立")
        if seen.evidence.get("roster_strip") != screens.ROSTER_COLLAPSED:
            raise Halt(f"卡條不是收合態（{seen.evidence.get('roster_strip')}），不掃")

        self.begin("survey")
        for index in range(self.survey_ticks):
            self.perform(SurveyBoard(), f"survey_board#{index + 1}")
        self.observe("after_survey")
        self.summarize_survey()
        self.end("survey")

    def abandon(self) -> None:
        self.begin("abandon")
        report = entry.abandon_battle(self.camera.grab, self.device.tap, sleep=self.sleep)
        self.gate("abandon", report)
        self.end("abandon")

    def begin(self, name: str) -> None:
        """每段開頭：解鎖一次（兩種鎖都會無聲吞 tap）＋存一張段界幀。"""
        self.device.ensure_unlocked(force=True)
        self.journal.record("stage", name=name)
        self.camera.grab()
        self.camera.keep(f"{name}:start")

    def end(self, name: str) -> bool:
        log.info("stage %s done (frame %s)", name, self.camera.keep(f"{name}:end"))
        return self.stop_after == name

    def gate(self, name: str, report: entry.GateReport) -> None:
        self.journal.record("gate", name=name, trail=list(report.trail))
        if report.ok:
            return
        details = [step.detail for step in report.failures]
        raise Halt(f"{name} 閘門未過：{report.trail} {details}")

    def perform(self, action: object, label: str) -> None:
        observation = self.perceiver.look()
        self.journal.record("perform_start", label=label, screen=observation.screen)
        self.executor.perform(action, observation)

    def observe(self, label: str) -> Observation:
        seen = self.perceiver.look()
        self.journal.record("observed", label=label, screen=seen.screen, **seen.evidence)
        log.info(
            "%s: screen=%s auto=%s grid_on=%s roster=%s",
            label,
            seen.screen,
            seen.evidence.get("auto"),
            seen.evidence.get("grid_on"),
            seen.evidence.get("roster_strip"),
        )
        return seen

    def summarize_survey(self) -> None:
        ledger = self.driver.ledger
        cells = ledger.cells()
        self.journal.record(
            "survey_summary",
            steps=list(self.driver.steps),
            swept=sorted(ledger.swept),
            synced=ledger.synced,
            cells=[[list(cell), hint] for cell, hint in cells],
        )
        log.info("survey steps: %s", self.driver.steps)
        log.info("swept=%s synced=%s cells=%d", sorted(ledger.swept), ledger.synced, len(cells))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", default=None)
    parser.add_argument("--stop-after", choices=STAGES, default=None)
    parser.add_argument("--survey-ticks", type=int, default=20)
    parser.add_argument("--stage-node", default=None, help="X,Y：先點一個關卡節點再進出擊準備")
    parser.add_argument("--abandon", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--zoom",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="掃描前先 pinch 到最小縮放（需要 uiautomator2 連得上）",
    )
    parser.add_argument("--run-dir", type=Path, default=None)
    return parser.parse_args()


def point(text: str | None) -> tuple[int, int] | None:
    if text is None:
        return None
    x, y = (int(value) for value in text.split(","))
    return x, y


def open_run(run_dir: Path | None) -> Journal:
    if run_dir is None:
        rotate_runs(RUNS_ROOT)
        run_dir = RUNS_ROOT / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    return Journal(run_dir / JOURNAL_NAME)


def soft_capture(camera: Camera) -> Callable[[], np.ndarray | None]:
    """Keyguard 只想知道畫面暗不暗；截圖失敗不該炸掉整段流程。"""

    def capture() -> np.ndarray | None:
        try:
            return camera.grab()
        except Exception:
            log.warning("keyguard capture failed", exc_info=True)
            return None

    return capture


def zoom_driver(
    args: argparse.Namespace, camera: Camera, journal: Journal
) -> Callable[[], None] | None:
    """縮放走 uiautomator 注入（本裝置唯一可行的後端，見 runtime/zoom.py），與截圖
    ／點擊的 adb 通道各自獨立。接不上就回 None——掃描在當下縮放照樣跑得完，只是
    腿數與截圖次數變多，所以這裡不讓它擋任何事。"""
    if not args.zoom:
        journal.record("zoom_backend", available=False, reason="disabled")
        return None
    try:
        import uiautomator2 as u2

        pincher = zoom.gesture_pincher_for(u2.connect(args.serial))
    except Exception as boom:
        log.warning("no zoom backend; scanning at the current zoom", exc_info=True)
        journal.record("zoom_backend", available=False, reason=repr(boom))
        return None
    journal.record("zoom_backend", available=True)
    return zoom.ZoomOut(
        capture=camera.grab,
        pincher=pincher,
        on_step=lambda step: journal.record("zoom_step", **asdict(step)),
    )


def build(args: argparse.Namespace, journal: Journal) -> DryRun:
    adb = Adb(serial=args.serial)
    device = LiveDevice(adb=adb)
    camera = Camera(device=device, journal=journal)
    device.keyguard = Keyguard(shell=adb.shell, capture=soft_capture(camera))
    driver, _ = survey_drivers(camera.grab, device, zoom_out=zoom_driver(args, camera, journal))
    return DryRun(
        device=device,
        camera=camera,
        journal=journal,
        executor=LiveExecutor(device=device, drivers=driver.drivers(), journal=journal),
        driver=driver,
        perceiver=LivePerceiver(device=device),
        stop_after=args.stop_after,
        survey_ticks=args.survey_ticks,
        node=point(args.stage_node),
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args()
    journal = open_run(args.run_dir)
    run_dir = journal.path.parent
    print(f"run dir: {run_dir}")
    print(f"screens known: {screens.STAGE_LIST}, {screens.SORTIE_PREP}, {screens.STAGE_INFO}")
    dry = build(args, journal)
    journal.record("dry_run_start", stop_after=args.stop_after, survey_ticks=args.survey_ticks)
    try:
        dry.run()
        if args.abandon and args.stop_after in IN_BATTLE_STAGES:
            dry.abandon()
    except Halt as stop:
        frame = dry.camera.keep("halt")
        journal.record("halt", reason=str(stop), frame=frame)
        print(f"HALT: {stop}")
        print(f"當下截圖: {run_dir / frame if frame else '(無)'}")
        return 1
    except Exception as boom:
        frame = dry.camera.keep("crash")
        journal.record("crash", reason=repr(boom), frame=frame)
        print(f"CRASH: {boom!r}")
        print(f"當下截圖: {run_dir / frame if frame else '(無)'}")
        raise
    journal.record("dry_run_end")
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
