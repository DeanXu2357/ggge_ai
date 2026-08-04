"""每格點擊清算掃描的實機駕駛：進場閘門 → 西北角歸零 → 逐格點擊裁決 → 棄戰。

與 `dry_run_entry.py` 同一套組裝模式（Camera 唯一幀源、Journal 落證據、危險帶白
名單不繞過、進場閘門鏈照走），但掃描走的是 `runtime/sweep.py` 的點擊裁決路徑：
弧色（find_sightings／arc_hint）**不參與任何佔位裁決**，只在挑平移起手點時用來
避開精靈（那是手勢安全，不是帳本事實）。

usage:
  # 分段停點：select / prep / stage_info / map / grid / zero / sweep
  uv run python scripts/sweep_scan.py --serial R5CRC37JBYJ --stage-node 544,667 \
      --stop-after zero
  uv run python scripts/sweep_scan.py … --max-taps 200 --tap-interval 0.5
  uv run python scripts/sweep_scan.py … --no-abandon

前提：手機已經停在目標系列的關卡列表。--stage-node X,Y 必填（棄戰回來游標會飄）。

證據：data/runs/<時間戳>/sweep.jsonl＋frames/。出卡與置中事件的幀必存，空格裁決
每 --empty-frame-every 筆存一張。
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from ggge_ai.battle import faction as faction_mod
from ggge_ai.battle import map_view, vision
from ggge_ai.battle.state import Faction
from ggge_ai.runtime import board, entry, screens, sweep, zoom
from ggge_ai.runtime.device import Adb, LiveDevice, LiveExecutor
from ggge_ai.runtime.journal import Journal, rotate_runs
from ggge_ai.runtime.keyguard import Keyguard
from ggge_ai.runtime.perceive import LivePerceiver, Observation, decode
from ggge_ai.stage.actions import CollapseRoster, ShowGrid
from ggge_ai.stage.survey import BoardDriver
from ggge_ai.vision.manifest import TemplateManifest
from ggge_ai.vision.pipeline import RecognizerPipeline, Stage

log = logging.getLogger("sweep_scan")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = PROJECT_ROOT / "assets" / "templates"
RUNS_ROOT = Path("data/runs")
JOURNAL_NAME = "sweep.jsonl"
STAGES = ("select", "prep", "stage_info", "map", "grid", "zero", "sweep")
IN_BATTLE_STAGES = (None, "map", "grid", "zero", "sweep")

MAX_TAPS = 600
TAP_INTERVAL_S = 0.4
EMPTY_FRAME_EVERY = 20
# 歸零往西北推的上限。一把約 570px 內容位移，地圖再大也用不到這麼多把。
ZERO_LEGS = 24
SETTLE_POLL_S = 0.25
SETTLE_ROUNDS = 4
CARD_SETTLE_S = 1.0


class Halt(RuntimeError):
    """停在原地：印出原因與當下截圖，不再點任何東西。"""


@dataclass
class Camera:
    """唯一幀源——感知器與存檔共用，段界存下的幀就是當下判定用的那一張。"""

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
class ViewGate:
    """`battle.map_view` 要的那一面：capture()＋probe()。

    分類器與 escape 鏈住 battle/，runtime 不得 import 它（新包自足），所以接線
    落在這支腳本上。
    """

    camera: Camera
    pipeline: RecognizerPipeline

    def capture(self) -> np.ndarray:
        return self.camera.grab()

    def probe(self, element_ids: Sequence[str], frame: np.ndarray | None = None) -> dict:
        image = self.capture() if frame is None else frame
        return {found.id: found for found in self.pipeline.detect_elements(image, element_ids)}


@dataclass
class SweepRun:
    device: LiveDevice
    camera: Camera
    journal: Journal
    executor: LiveExecutor
    driver: BoardDriver
    perceiver: LivePerceiver
    gate: ViewGate
    identifier: faction_mod.FactionIdentifier
    stop_after: str | None = None
    node: tuple[int, int] | None = None
    max_taps: int = MAX_TAPS
    tap_interval: float = TAP_INTERVAL_S
    empty_frame_every: int = EMPTY_FRAME_EVERY
    sleep: Callable[[float], None] = time.sleep
    zoom_out: Callable[[], None] | None = None

    ledger: sweep.SweepLedger | None = field(default=None, init=False)
    offset: sweep.Point = field(default=(0.0, 0.0), init=False)
    heading: str = field(default="east", init=False)
    landmarks: dict[str, float] = field(default_factory=dict, init=False)
    signature: board.MarkerSignature | None = field(default=None, init=False)
    marker_cell: sweep.Cell | None = field(default=None, init=False)
    empties: int = field(default=0, init=False)
    started: float = field(default_factory=time.monotonic, init=False)

    def run(self) -> None:
        capture, tap, nap = self.camera.grab, self.device.tap, self.sleep

        self.begin("select")
        self.gate_report("select", entry.select_stage(capture, tap, node=self.node, sleep=nap))
        self.camera.grab()
        self.camera.keep("select:right_panel")
        if self.end("select"):
            return

        self.begin("prep")
        self.gate_report(
            "prep", entry.open_sortie_prep(capture, tap, entry.GateReport(), sleep=nap)
        )
        if self.end("prep"):
            return

        self.begin("stage_info")
        report = entry.sortie(capture, tap, sleep=nap)
        self.gate_report("sortie", report)
        if self.end("stage_info"):
            return

        self.begin("map")
        self.gate_report("advance", entry.advance_to_map(capture, tap, report, sleep=nap))
        if self.end("map"):
            return

        self.begin("grid")
        self.perform(ShowGrid(), "show_grid")
        self.perform(CollapseRoster(), "collapse_roster")
        seen = self.observe("after_grid_and_roster")
        if not seen.evidence.get("grid_on"):
            raise Halt("格網讀不出來：ShowGrid 沒生效，掃描的前置條件不成立")
        if seen.evidence.get("roster_strip") != screens.ROSTER_COLLAPSED:
            raise Halt(f"卡條不是收合態（{seen.evidence.get('roster_strip')}），不掃")
        if self.zoom_out is not None:
            self.zoom_out()
        if self.end("grid"):
            return

        self.begin("zero")
        self.zero()
        if self.end("zero"):
            return

        self.begin("sweep")
        self.tour()
        self.summarize()
        self.end("sweep")

    def zero(self) -> None:
        """往西北推到同一幀看得到北界＋西界，世界座標由那一幀**定義**。"""
        frame = self.settled()
        borders = sweep.read_borders(frame)
        for _ in range(ZERO_LEGS):
            if "west" in borders and "north" in borders:
                break
            direction = "west" if "west" not in borders else "north"
            self.pan(direction, frame)
            frame = self.settled()
            borders = sweep.read_borders(frame)
        self.journal.record("zero_borders", borders={k: round(v, 1) for k, v in borders.items()})
        if "west" not in borders or "north" not in borders:
            raise Halt(f"推不到西北角：同一幀只看到 {sorted(borders)}")
        if self.ledger is None:
            lattice = board.find_lattice(frame)
            if lattice is None:
                raise Halt("角落幀讀不出格網，世界座標無從定義")
            anchored = sweep.anchor_northwest(lattice, borders)
            if anchored is None:
                raise Halt("角落幀的格距不合理，世界座標無從定義")
            grid, self.offset = anchored
            self.ledger = sweep.SweepLedger(grid=grid)
            self.landmarks = {"west": 0.0, "north": 0.0}
            self.ledger.see_border("west", 0.0)
            self.ledger.see_border("north", 0.0)
            self.journal.record(
                "world_anchored",
                phase=[round(value, 1) for value in grid.phase],
                pitch=[round(grid.col_pitch, 1), round(grid.row_pitch, 1)],
                offset=[round(value, 1) for value in self.offset],
            )
            return
        self.offset = (
            self.landmarks["west"] - borders["west"],
            self.landmarks["north"] - borders["north"],
        )
        self.journal.record("rezeroed", offset=[round(value, 1) for value in self.offset])

    def tour(self) -> None:
        ledger = self._ledger()
        while not ledger.complete and ledger.taps < self.max_taps:
            frame = self.settled()
            self.witness(frame)
            plan = sweep.plan_window(ledger, self.offset, heading=self.heading)
            for cell in plan.blocked:
                ledger.defer(cell)
            self.journal.record(
                "window",
                offset=[round(value, 1) for value in self.offset],
                heading=self.heading,
                taps=len(plan.taps),
                blocked=[list(cell) for cell in plan.blocked],
                window=None if plan.window is None else [list(plan.window[0]), list(plan.window[1])],
            )
            if plan.taps and self.work(plan, frame):
                continue
            direction, self.heading = sweep.plan_pan(ledger, self.offset, self.heading)
            self.journal.record("pan_plan", direction=direction, heading=self.heading)
            if direction is None:
                break
            self.pan(direction, frame)
            self.relocate()
        self.retire_deferred()

    def work(self, plan: sweep.WindowPlan, frame: np.ndarray) -> bool:
        """本窗逐格點擊。回傳「被中斷了」——出卡或置中之後幾何要重讀才算數。"""
        ledger = self._ledger()
        before = frame
        for target in plan.taps:
            if ledger.taps >= self.max_taps:
                return False
            outcome = self.decide(target, before)
            if outcome in (sweep.TAP_CARD, sweep.TAP_SHIFTED):
                return True
            before = self.camera.grab()
        return False

    def decide(self, target: sweep.TapTarget, before: np.ndarray) -> str:
        """一格的一次裁決。分不出結果就重試一次，還是分不出就 UNSURE 留白。"""
        ledger = self._ledger()
        outcome = self.tap_cell(target, before)
        if outcome.verdict == sweep.TAP_NONE:
            # 分不出結果的那一下可能把畫面帶進了選擇狀態，而選擇狀態下的下一次
            # 格點擊會變成移動指令——重試之前先確認人在 hub。
            if not self.on_hub():
                self.escape()
            outcome = self.tap_cell(target, self.camera.grab())
        if outcome.verdict == sweep.TAP_EMPTY:
            if outcome.learned is not None:
                self.signature = outcome.learned
            self.marker_cell = target.cell
            self.empties += 1
            keep = self.empties % max(1, self.empty_frame_every) == 0
            ledger.record(target.cell, sweep.EMPTY, frame=self.camera.keep("empty") if keep else None)
            self.journal.record("verdict", cell=list(target.cell), verdict=sweep.EMPTY)
            return outcome.verdict
        if outcome.verdict == sweep.TAP_CARD:
            self.sentence_card(target)
            return outcome.verdict
        if outcome.verdict == sweep.TAP_SHIFTED:
            self.sentence_shift(target, outcome)
            return outcome.verdict
        ledger.record(target.cell, sweep.UNSURE, reason="no_feedback")
        self.journal.record("verdict", cell=list(target.cell), verdict=sweep.UNSURE,
                            reason="no_feedback")
        return outcome.verdict

    def tap_cell(self, target: sweep.TapTarget, before: np.ndarray) -> sweep.TapOutcome:
        ledger = self._ledger()
        self.device.tap(int(target.point[0]), int(target.point[1]))
        ledger.taps += 1
        self.sleep(self.tap_interval)
        after = self.camera.grab()
        return sweep.classify_tap(
            before,
            after,
            target.point,
            signature=self.signature,
            card=_card_present,
            pitch=(ledger.grid.col_pitch, ledger.grid.row_pitch),
        )

    def sentence_card(self, target: sweep.TapTarget) -> None:
        """出卡：橫幅停靠側判陣營（定案 5），讀完 escape。名字讀不到仍記 ENEMY。"""
        ledger = self._ledger()
        self.sleep(CARD_SETTLE_S)
        frame = self.camera.grab()
        path = self.camera.keep("card")
        verdict = self.identifier.identify(frame)
        summary = vision.read_enemy_summary(frame)
        side = None if verdict is None else verdict.side
        if verdict is not None and verdict.faction is Faction.ALLY:
            ledger.record(target.cell, sweep.ALLY, frame=path, reason=side)
        elif verdict is not None:
            ledger.record(
                target.cell,
                sweep.ENEMY,
                name=None if summary is None else summary.name_sig,
                frame=path,
                reason=side,
            )
        else:
            # 卡在畫面上但停靠側讀不出來＝有東西、陣營不明；不猜。
            ledger.record(target.cell, sweep.UNSURE, frame=path, reason="card_without_dock")
        self.journal.record(
            "verdict",
            cell=list(target.cell),
            verdict=ledger.verdict(target.cell),
            side=side,
            sig=None if summary is None else summary.name_sig,
            hp=None if summary is None else summary.hp,
            en=None if summary is None else summary.en,
            frame=path,
        )
        self.escape()

    def sentence_shift(self, target: sweep.TapTarget, outcome: sweep.TapOutcome) -> None:
        """置中＝點到我方（只有未行動的我方單位吃得下這一下）。escape 後重錨。"""
        ledger = self._ledger()
        path = self.camera.keep("shift")
        ledger.record(target.cell, sweep.ALLY, frame=path, reason="recentred")
        self.journal.record(
            "verdict",
            cell=list(target.cell),
            verdict=sweep.ALLY,
            reason="recentred",
            delta=None if outcome.delta is None else [round(v, 1) for v in outcome.delta],
            frame=path,
        )
        self.escape()
        candidate = sweep.recentre_offset(ledger.grid, target.cell)
        self.relocate(candidate=candidate)

    def on_hub(self) -> bool:
        return map_view.classify_view(self.gate) == map_view.HUB

    def escape(self) -> None:
        """選擇狀態下任何非「返回」的點擊都可能誤下移動指令，所以 escape 走
        strict（不做中性輕點）。"""
        ok = map_view.return_to_top(
            self.gate, self.device, allow_neutral_nudge=False, sleep=self.sleep
        )
        self.journal.record("escape", ok=ok)
        if not ok:
            raise Halt("escape 回不到 hub，選擇狀態下不再點任何東西")

    def witness(self, frame: np.ndarray) -> None:
        """這一幀目視到的終止邊 → 地標與界線。界線第一次記下就不再改。"""
        ledger = self._ledger()
        for side, screen_position in sweep.read_borders(frame).items():
            axis = 0 if side in ("west", "east") else 1
            world = screen_position + self.offset[axis]
            if side not in self.landmarks:
                self.landmarks[side] = world
                self.journal.record("landmark", side=side, world=round(world, 1))
            ledger.see_border(side, self.landmarks[side])

    def relocate(self, candidate: sweep.Point | None = None) -> None:
        """推鏡／置中之後重定鏡位：地標優先，標記填色補位，都沒有才回角落歸零。"""
        ledger = self._ledger()
        frame = self.settled()
        borders = sweep.read_borders(frame)
        marker = self.marker_offset(frame)
        offset, source = sweep.reanchor(
            ledger.grid,
            landmarks=self.landmarks,
            borders=borders,
            candidate=candidate if candidate is not None else marker,
        )
        self.journal.record(
            "relocate",
            source=source,
            offset=None if offset is None else [round(value, 1) for value in offset],
            borders=sorted(borders),
            marker=marker is not None,
        )
        if offset is None:
            self.zero()
            return
        self.offset = offset
        self.witness(frame)

    def marker_offset(self, frame: np.ndarray) -> sweep.Point | None:
        """填色是我們自己放的絕對地標：找得到就一次解出兩軸。"""
        if self.signature is None or self.marker_cell is None:
            return None
        found = board.find_marker(
            frame, self.signature, holes=board.UNIT_DENSITY_HUD_HOLES
        )
        if found is None:
            return None
        world = self._ledger().grid.centre_of(self.marker_cell)
        return (world[0] - found[0], world[1] - found[1])

    def retire_deferred(self) -> None:
        """任何到得了的鏡位都沒把它輪進安全窗的格：UNSURE 收場，理由明寫。"""
        ledger = self._ledger()
        for cell in sorted(ledger.blocked):
            if ledger.decided(cell):
                continue
            ledger.record(cell, sweep.UNSURE, reason="never_tappable")
            self.journal.record(
                "verdict", cell=list(cell), verdict=sweep.UNSURE, reason="never_tappable"
            )

    def pan(self, direction: str, frame: np.ndarray) -> None:
        origin = board.pick_pan_origin(board.find_sightings(frame))
        x1, y1, x2, y2 = board.pan_gesture(direction, origin)
        self.device.swipe(x1, y1, x2, y2, board.PAN_DURATION_S)
        self.sleep(board.PAN_SETTLE_S)
        self.journal.record("pan", direction=direction, origin=[round(v, 1) for v in origin])

    def settled(self) -> np.ndarray:
        frame = self.camera.grab()
        for _ in range(SETTLE_ROUNDS):
            self.sleep(SETTLE_POLL_S)
            frame = self.camera.grab()
        return frame

    def abandon(self) -> None:
        self.begin("abandon")
        report = entry.abandon_battle(self.camera.grab, self.device.tap, sleep=self.sleep)
        self.gate_report("abandon", report)
        self.end("abandon")

    def begin(self, name: str) -> None:
        self.device.ensure_unlocked(force=True)
        self.journal.record("stage", name=name)
        self.camera.grab()
        self.camera.keep(f"{name}:start")

    def end(self, name: str) -> bool:
        log.info("stage %s done (frame %s)", name, self.camera.keep(f"{name}:end"))
        return self.stop_after == name

    def gate_report(self, name: str, report: entry.GateReport) -> None:
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
        self.journal.record(
            "observed",
            label=label,
            screen=seen.screen,
            frame=self.journal.save_frame(seen.frame, self.camera.shots),
            **seen.evidence,
        )
        return seen

    def summarize(self) -> None:
        ledger = self._ledger()
        summary = ledger.summary()
        self.journal.record(
            "sweep_summary",
            elapsed_s=round(time.monotonic() - self.started, 1),
            shots=self.camera.shots,
            **summary,
        )
        log.info(
            "complete=%s bounded=%s taps=%d counts=%s pending=%d",
            summary["complete"],
            summary["bounded"],
            summary["taps"],
            summary["counts"],
            summary["pending"],
        )

    def _ledger(self) -> sweep.SweepLedger:
        if self.ledger is None:
            raise Halt("世界座標還沒定義（zero 沒跑或沒過）")
        return self.ledger


def _card_present(frame: np.ndarray) -> bool:
    return vision.read_enemy_summary(frame) is not None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", default=None)
    parser.add_argument("--stop-after", choices=STAGES, default=None)
    parser.add_argument(
        "--stage-node",
        required=True,
        help="X,Y：要打的關卡節點。必填——棄戰回來游標會飄，沿用現選會打到別關",
    )
    parser.add_argument("--max-taps", type=int, default=MAX_TAPS)
    parser.add_argument("--tap-interval", type=float, default=TAP_INTERVAL_S)
    parser.add_argument("--empty-frame-every", type=int, default=EMPTY_FRAME_EVERY)
    parser.add_argument("--abandon", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--zoom", action=argparse.BooleanOptionalAction, default=True)
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
    if not args.zoom:
        journal.record("zoom_backend", available=False, reason="disabled")
        return None
    try:
        import uiautomator2 as u2

        pincher = zoom.gesture_pincher_for(u2.connect(args.serial))
    except Exception as boom:
        log.warning("no zoom backend; sweeping at the current zoom", exc_info=True)
        journal.record("zoom_backend", available=False, reason=repr(boom))
        return None
    journal.record("zoom_backend", available=True)
    return zoom.ZoomOut(
        capture=camera.grab,
        pincher=pincher,
        on_step=lambda step: journal.record("zoom_step", **asdict(step)),
    )


def build(args: argparse.Namespace, journal: Journal) -> SweepRun:
    adb = Adb(serial=args.serial)
    device = LiveDevice(adb=adb)
    camera = Camera(device=device, journal=journal)
    device.keyguard = Keyguard(shell=adb.shell, capture=soft_capture(camera))
    recognizer = TemplateManifest.load(TEMPLATE_ROOT).build_recognizer()
    pipeline = RecognizerPipeline(
        screen_stages=[Stage(recognizer, accept_above=0.90)],
        element_stages=[Stage(recognizer, accept_above=0.80)],
    )
    driver = BoardDriver(capture=camera.grab, actuator=device)
    return SweepRun(
        device=device,
        camera=camera,
        journal=journal,
        executor=LiveExecutor(device=device, drivers=driver.drivers(), journal=journal),
        driver=driver,
        perceiver=LivePerceiver(device=camera),
        gate=ViewGate(camera=camera, pipeline=pipeline),
        identifier=faction_mod.DockBannerIdentifier(),
        stop_after=args.stop_after,
        node=point(args.stage_node),
        max_taps=args.max_taps,
        tap_interval=args.tap_interval,
        empty_frame_every=args.empty_frame_every,
        zoom_out=zoom_driver(args, camera, journal),
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args()
    journal = open_run(args.run_dir)
    run_dir = journal.path.parent
    print(f"run dir: {run_dir}")
    run = build(args, journal)
    journal.record(
        "sweep_start",
        stop_after=args.stop_after,
        stage_node=args.stage_node,
        max_taps=args.max_taps,
        tap_interval=args.tap_interval,
    )
    try:
        run.run()
        if args.abandon and args.stop_after in IN_BATTLE_STAGES:
            run.abandon()
    except Halt as stop:
        frame = run.camera.keep("halt")
        journal.record("halt", reason=str(stop), frame=frame)
        print(f"HALT: {stop}")
        print(f"當下截圖: {run_dir / frame if frame else '(無)'}")
        return 1
    except Exception as boom:
        frame = run.camera.keep("crash")
        journal.record("crash", reason=repr(boom), frame=frame)
        print(f"CRASH: {boom!r}")
        raise
    journal.record("sweep_end")
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
