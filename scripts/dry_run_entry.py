"""實機驗證輪駕駛：關卡列表 → 進場閘門 → 開格線／收卡條 → 盤面掃描 → 棄戰。

全程走批 2d 的新通道（LiveDevice／LivePerceiver／LiveExecutor／runtime.entry／
stage.survey），危險帶白名單不繞過，每一段開頭掛一次 Keyguard。判斷全在 runtime／
stage 模組（都有離線測試），這支只負責組裝、迴圈與落證據。

usage:
  # 只驗到關卡列表／出擊準備頁——**不花任何資源**，第一次跑先跑這兩段
  uv run python scripts/dry_run_entry.py --serial R5CRC37JBYJ --stage-node 544,667 \
      --stop-after select
  uv run python scripts/dry_run_entry.py --serial R5CRC37JBYJ --stage-node 544,667 \
      --stop-after prep

  # 分段停點：select / prep / stage_info / map / grid / survey
  # stage_info 起開始花 EN 與挑戰次數
  uv run python scripts/dry_run_entry.py … --stop-after grid
  uv run python scripts/dry_run_entry.py … --survey-ticks 20   # 預設 80
  uv run python scripts/dry_run_entry.py … --no-zoom           # 不 pinch，掃當前縮放
  uv run python scripts/dry_run_entry.py … --dump-survey-frames  # 每次 observe 的幀都留

  # 全程（預設進到地圖之後會棄戰收尾；棄戰不耗 AP／挑戰次數／EN，0730 實證）
  uv run python scripts/dry_run_entry.py --serial R5CRC37JBYJ --stage-node 544,667
  uv run python scripts/dry_run_entry.py … --no-abandon

前提：手機已經停在目標系列的關卡列表（選擇關卡頁）。

**--stage-node X,Y 是必填的**：棄戰回來的關卡列表游標會飄（見 docs/ui-navigation-
map.md），沿用「現在選著的那一關」會打到別關去，所以每次都要明示要打哪個節點。
選中的是哪一關畫面上讀不出來（右欄標題還沒接文字讀取），所以選完會多存一張右欄
截圖（frames 的 select:right_panel）供事後比對。0730 的 UC HARD 1 節點平台約在
(544,872)，**那個點撞上戰鬥選單「放棄」的危險帶會被拒點**——要點就點編號／星列
那一列（y 較高，例如 544,667）。

證據：data/runs/<時間戳>/dry_run.jsonl＋frames/（每段界線、每次觀測與每次失敗各存
一張原生幀）。截圖只有 Camera 一個來源——感知器也吃它，所以存下來的幀就是當下判定
用的那張。掃描每 tick 另出兩筆 survey_tick（前置複核幀與 leg 幀各一），帶位移量、
閘門裁決與靜止閘輪數；斷鏈那幾次另存 frames/broken/ 的前後幀對（上限 20 對），
`--dump-survey-frames` 則把每次 observe 的幀全留在 frames/survey/ 供離線重放量測。
任何 expect 失敗就停在原地不再點，印出畫面名與當下截圖路徑。
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np

from ggge_ai.runtime import coverage, entry, screens, zoom
from ggge_ai.runtime.device import Adb, LiveDevice, LiveExecutor
from ggge_ai.runtime.journal import FRAMES_DIRNAME, Journal, rotate_runs
from ggge_ai.runtime.keyguard import Keyguard
from ggge_ai.runtime.perceive import LivePerceiver, Observation, decode
from ggge_ai.stage.actions import CollapseRoster, ShowGrid, SurveyBoard
from ggge_ai.stage.survey import BoardDriver, survey_drivers

log = logging.getLogger("dry_run_entry")

RUNS_ROOT = Path("data/runs")
JOURNAL_NAME = "dry_run.jsonl"
STAGES = ("select", "prep", "stage_info", "map", "grid", "survey")
# 逐 observe 的量測遙測（A5 儀器化）：微步驟名答不了「那一把平移到底移了多少」，
# 位移量、閘門裁決與靜止閘輪數只有這一種紀錄看得到。
SURVEY_TICK = "survey_tick"
# 斷鏈存證：0801 複驗第 2 輪兩輪共 37 次 BROKEN(phase) 幾乎全在東西向，候選假說
# （量測系統性欠讀 vs 相位參考漂移）在幀存下來之前定不了讞。上限擋的是 80 tick
# 全斷鏈時把 run 目錄塞爆——超過只記流水帳。
SURVEY_BROKEN = "survey_broken"
BROKEN_DIRNAME = "broken"
BROKEN_PAIRS = 20
SURVEY_DIRNAME = "survey"
SURVEY_DONE = "survey_done"
# 步數帳（0801 複驗實測）：南 11＋北 2＋東 18＋西 ~10 已 41 把平移，40 tick 連一輪
# 都走不完。80 給殘餘與西側補掃留裕度；真正的上限仍是 coverage.LEG_BUDGET。
# 這是**上限**不是目標——掃完就停（DryRun.sweep）。
SURVEY_TICKS = 80
# 只有真的進到地圖才有戰鬥可棄；停在更早的段落就交給人自己收。
IN_BATTLE_STAGES = (None, "map", "grid", "survey")


class Halt(RuntimeError):
    """停在原地：印出原因與當下截圖，不再點任何東西。"""


@dataclass
class Camera:
    """**唯一幀源**：這支所有的截圖都經過這裡，最後一張原生幀留著給段界與失敗點。

    感知器也吃這個通道（`LivePerceiver(device=camera)`），因為它自己抓幀時存檔存
    到的是別張——0730 實機發現②：段界存的是陳舊幀，只有 journal 的結構化欄位
    才對得上。共用同一張之後，同一個停點的判定與存檔必然是同一張幀。
    """

    device: LiveDevice
    journal: Journal
    raw: bytes | None = field(default=None, init=False)
    shots: int = field(default=0, init=False)

    def screenshot(self) -> bytes:
        self.raw = self.device.screenshot()
        self.shots += 1
        return self.raw

    def grab(self) -> np.ndarray:
        return decode(self.screenshot())

    def keep(self, label: str) -> str | None:
        path = self.journal.save_frame(self.raw, self.shots)
        self.journal.record("frame", label=label, frame=path)
        return path


@dataclass
class SurveyFrames:
    """掃描的幀存證水槽：斷鏈的前後幀對，外加可選的全幀傾印。

    存的是 `cv2.imencode` 重編的 PNG——PNG 無失真，像素與裝置那張逐點相同，只有
    檔案位元組不同（幀在 driver 那一層已經是解碼過的陣列，拿不到原始位元組）。
    離線重放量測要的是像素，這個代價可以接受。

    純觀察者：寫檔失敗只記一次警告，掃描照跑（driver 那一層也包了一層 try）。
    """

    journal: Journal
    dump: bool = False
    pairs: int = 0

    @property
    def run_dir(self) -> Path:
        return self.journal.path.parent

    def __call__(
        self, record: dict[str, object], previous: np.ndarray | None, current: np.ndarray
    ) -> None:
        if record.get("verdict") == coverage.BROKEN:
            self._pair(record, previous, current)
        if self.dump:
            self._dump(record, current)

    def _pair(
        self, record: dict[str, object], previous: np.ndarray | None, current: np.ndarray
    ) -> None:
        stem = f"t{record['tick']}-{record['probe']}-{_slug(str(record['reason']))}"
        saved = self.pairs < BROKEN_PAIRS
        frames: dict[str, str | None] = {"prev": None, "curr": None}
        if saved:
            self.pairs += 1
            frames["prev"] = self._write(BROKEN_DIRNAME, f"{stem}-prev.png", previous)
            frames["curr"] = self._write(BROKEN_DIRNAME, f"{stem}-curr.png", current)
        self.journal.record(
            SURVEY_BROKEN,
            tick=record["tick"],
            probe=record["probe"],
            direction=record["direction"],
            reason=record["reason"],
            saved=saved,
            **frames,
        )

    def _dump(self, record: dict[str, object], current: np.ndarray) -> None:
        self._write(SURVEY_DIRNAME, f"t{record['tick']}-{record['probe']}.png", current)

    def _write(self, folder: str, name: str, frame: np.ndarray | None) -> str | None:
        if frame is None:
            return None
        directory = self.run_dir / FRAMES_DIRNAME / folder
        try:
            directory.mkdir(parents=True, exist_ok=True)
            ok, buffer = cv2.imencode(".png", frame)
            if not ok:
                raise ValueError("cv2.imencode refused the frame")
            (directory / name).write_bytes(buffer.tobytes())
        except Exception:
            log.warning("could not keep survey frame %s/%s", folder, name, exc_info=True)
            return None
        return f"{FRAMES_DIRNAME}/{folder}/{name}"


def _slug(text: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_") or "unknown"


@dataclass
class DryRun:
    device: LiveDevice
    camera: Camera
    journal: Journal
    executor: LiveExecutor
    driver: BoardDriver
    perceiver: LivePerceiver
    stop_after: str | None = None
    survey_ticks: int = SURVEY_TICKS
    node: tuple[int, int] | None = None
    sleep: Callable[[float], None] = time.sleep

    def run(self) -> None:
        capture, tap, nap = self.camera.grab, self.device.tap, self.sleep

        self.begin("select")
        self.gate("select", entry.select_stage(capture, tap, node=self.node, sleep=nap))
        # 選中哪一關畫面上讀不出來，所以留一張右欄的圖給人事後核對——棄戰回來
        # 游標會飄，盲選會打到別關。
        self.camera.grab()
        self.camera.keep("select:right_panel")
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
        self.sweep()
        self.observe("after_survey")
        self.summarize_survey()
        self.end("survey")

    def sweep(self) -> int:
        """掃到 synced 就停，回傳花掉幾個 tick。

        完成判準是建構性的（四旗全定 ∧ 界內無缺口），達成之後每多跑一 tick 都是
        白燒截圖——0801 複驗第 2 輪 29 把平移就 synced，剩下的 50 tick 各燒兩張。
        """
        for index in range(self.survey_ticks):
            self.perform(SurveyBoard(), f"survey_board#{index + 1}")
            if self.driver.ledger.synced:
                self.journal.record(SURVEY_DONE, tick=index + 1, budget=self.survey_ticks)
                log.info("survey synced after %d of %d ticks", index + 1, self.survey_ticks)
                return index + 1
        return self.survey_ticks

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
        # 存的就是這次判定用的那張幀（感知器與存檔共用 Camera），事後才對得起來。
        self.journal.record(
            "observed",
            label=label,
            screen=seen.screen,
            frame=self.journal.save_frame(seen.frame, self.camera.shots),
            **seen.evidence,
        )
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
        summary = ledger.summary()
        # unlocalised＝那一幀的位移量不出來、觀測被隔離進島嶼。>0 就代表這一輪
        # 斷過鏈，要跟結果放在同一筆紀錄裡，不是只留在 log。
        self.journal.record(
            "survey_summary",
            steps=list(self.driver.steps),
            synced=ledger.synced,
            unlocalised=summary["unlocalised"],
            survey=summary,
            cells=[[list(cell), hint] for cell, hint in cells],
        )
        log.info("survey steps: %s", self.driver.steps)
        log.info(
            "synced=%s coverage=%s bounded=%s cells=%d unlocalised=%s islands=%s",
            ledger.synced,
            summary["coverage"],
            summary["bounded"],
            len(cells),
            summary["unlocalised"],
            summary["islands"],
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", default=None)
    parser.add_argument("--stop-after", choices=STAGES, default=None)
    parser.add_argument("--survey-ticks", type=int, default=SURVEY_TICKS)
    parser.add_argument(
        "--stage-node",
        required=True,
        help="X,Y：要打的關卡節點。必填——棄戰回來游標會飄，沿用現選會打到別關",
    )
    parser.add_argument("--abandon", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--zoom",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="掃描前先 pinch 到最小縮放（需要 uiautomator2 連得上）",
    )
    parser.add_argument(
        "--dump-survey-frames",
        action="store_true",
        help="每次 observe 的 settled 幀都存進 frames/survey/（離線重放量測用）",
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
    平移次數與截圖次數變多，所以這裡不讓它擋任何事。"""
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
    driver, _ = survey_drivers(
        camera.grab,
        device,
        zoom_out=zoom_driver(args, camera, journal),
        telemetry=lambda record: journal.record(SURVEY_TICK, **record),
        evidence=SurveyFrames(journal=journal, dump=args.dump_survey_frames),
        dump_frames=args.dump_survey_frames,
    )
    return DryRun(
        device=device,
        camera=camera,
        journal=journal,
        executor=LiveExecutor(device=device, drivers=driver.drivers(), journal=journal),
        driver=driver,
        perceiver=LivePerceiver(device=camera),
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
    journal.record(
        "dry_run_start",
        stop_after=args.stop_after,
        survey_ticks=args.survey_ticks,
        stage_node=args.stage_node,
    )
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
