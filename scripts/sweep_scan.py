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
  uv run python scripts/sweep_scan.py … --filter-mode full   # 全格點對照組
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
from collections.abc import Callable, Mapping, Sequence
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
# 歸零往西北推的上限。一把約 240px 內容位移（0804 逐把量測，board.PAN_GAIN），
# 地圖再大也用不到這麼多把。
ZERO_LEGS = 24
# 連續這麼多次「回角落＋接力返航」都沒能推進任何一格裁決就停手：再繞下去只是
# 把同一段路重走。
STRANDINGS_LIMIT = 3
# 推鏡後的緩動等待。輪數是「多等一點降污染率」的保險，不是靜止判準（0803 第 10
# 輪定讞：整區灰階讀到的是不隨鏡頭動的星空層，不准拿它問畫面停了沒）。一張截圖
# 在實機要 ~2.4s，所以保險買一輪就好，改用較長的間隔補回真實靜置時間。
SETTLE_POLL_S = 0.5
SETTLE_ROUNDS = 1
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
    filter_mode: str = sweep.FILTER_FULL
    sleep: Callable[[float], None] = time.sleep
    zoom_out: Callable[[], None] | None = None

    ledger: sweep.SweepLedger | None = field(default=None, init=False)
    offset: sweep.Point = field(default=(0.0, 0.0), init=False)
    heading: str = field(default="east", init=False)
    landmarks: dict[str, float] = field(default_factory=dict, init=False)
    sightings: dict[str, list[float]] = field(default_factory=dict, init=False)
    clashes: dict[str, list[float]] = field(default_factory=dict, init=False)
    grounded: bool = field(default=False, init=False)
    ungrounded: int = field(default=0, init=False)
    signature: board.MarkerSignature | None = field(default=None, init=False)
    marker_cell: sweep.Cell | None = field(default=None, init=False)
    walk: sweep.NodeWalk = field(default_factory=sweep.NodeWalk, init=False)
    fix: sweep.Fix = field(default_factory=sweep.Fix, init=False)
    peaks: tuple[sweep.Point, ...] = field(default=(), init=False)
    pinned: set[str] = field(default_factory=set, init=False)
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
        """往西北推到同一幀看得到北界＋西界，世界座標由那一幀**定義**。

        角落是根節點：走到這裡代表節點鏈已經救不回來，整條鏈作廢重新長。**帳本
        不清**——帳本記的是世界格事實，重錨不是重掃。
        """
        self.walk.rooted()
        frame = self.settled()
        borders = sweep.read_borders(frame)
        for _ in range(ZERO_LEGS):
            if "west" in borders and "north" in borders:
                break
            direction = "west" if "west" not in borders else "north"
            _, frame = self.pan(direction, frame)
            borders = sweep.read_borders(frame)
        self.journal.record("zero_borders", borders={k: round(v, 1) for k, v in borders.items()})
        if "west" not in borders or "north" not in borders:
            raise Halt(f"推不到西北角：同一幀只看到 {sorted(borders)}")
        # 角落是絕對根：看到它就是錨上了，零里程計需求。
        self.fix.regain()
        self.grounded = True
        self.ungrounded = 0
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
        strandings = 0
        progress = ledger.taps
        while not ledger.complete and ledger.taps < self.max_taps:
            if not self.fix.anchored:
                # 失位中一格都不點：先回角落重錨、接力返航，才准回到清算。
                strandings = 0 if ledger.taps > progress else strandings + 1
                progress = ledger.taps
                if strandings > STRANDINGS_LIMIT:
                    raise Halt(f"連續 {strandings} 次回角落返航都接不回鋒面，停手")
                self.zero()
                self.home()
                continue
            if not self.grounded and not self.confirm():
                # 背書不了就當失位——迴圈不留「錨不上又繼續轉」這條空轉路。
                self.fix.lose()
                continue
            frame = self.neutral()
            self.witness(frame)
            candidates = self.candidates(frame)
            plan = sweep.plan_window(
                ledger, self.offset, heading=self.heading, candidates=candidates
            )
            for cell in plan.blocked:
                ledger.defer(cell)
            self.journal.record(
                "window",
                offset=[round(value, 1) for value in self.offset],
                heading=self.heading,
                taps=len(plan.taps),
                blocked=[list(cell) for cell in plan.blocked],
                window=None if plan.window is None else [list(plan.window[0]), list(plan.window[1])],
                frame=self.camera.keep("window"),
            )
            self.infer_empties(plan, candidates)
            if plan.taps and self.work(plan, frame):
                continue
            direction, self.heading = sweep.plan_pan(
                ledger, self.offset, self.heading, pinned=self.pinned
            )
            self.journal.record("pan_plan", direction=direction, heading=self.heading)
            if direction is None:
                break
            self.expand(direction)
        self.retire_deferred()

    def confirm(self) -> bool:
        """非 grounded 鏡位下的復權關卡：強證人背書才恢復裁決，否則當失位處理。

        強證人＝標記填色（我們自己種下去的絕對地標）或與帳本對得上的界線。置中反推
        算得出座標，但那個座標繼承了推斷的錯，而帳本記的是世界格——錯了就是永久的。
        """
        ledger = self._ledger()
        frame = self.settled()
        borders = sweep.read_borders(frame)
        marker = self.marker_offset(frame)
        offset, source = sweep.reanchor(
            ledger.grid, landmarks=self.landmarks, borders=borders, candidate=marker
        )
        backed = offset is not None and (
            source == sweep.SOURCE_EDGE or (marker is not None and source != sweep.SOURCE_LOST)
        )
        if backed and sweep.contradicts(ledger, self.landmarks, borders, offset) is None:
            self.offset = offset
            self.grounded = True
            self.ungrounded = 0
            self.journal.record(
                "anchor_backed",
                source=source,
                offset=[round(value, 1) for value in offset],
                marker=marker is not None,
            )
            self.witness(frame)
            return True
        self.ungrounded += 1
        self.journal.record(
            "anchor_unbacked",
            source=source,
            streak=self.ungrounded,
            marker=marker is not None,
            borders=sorted(borders),
        )
        if self.ungrounded > sweep.UNGROUNDED_ANCHOR_LIMIT:
            self.fix.lose()
        return False

    def neutral(self) -> np.ndarray:
        """窗幀要在中性態拍：單位卡／選取覆蓋還蓋在圖上時，候選檢測會讀出上萬個假峰
        （20260805-075310 的 window 幀有 50/101 張是這樣拍的），線上過濾與離線評分
        一起被騙。"""
        frame = self.settled()
        for _ in range(2):
            hub = self.on_hub(frame)
            if hub and not _card_present(frame):
                return frame
            self.journal.record("window_not_neutral", hub=hub)
            self.escape()
            frame = self.settled()
        self.journal.record("window_dirty", frame=self.camera.keep("dirty"))
        return frame

    def candidates(self, frame: np.ndarray) -> frozenset[sweep.Cell] | None:
        """本窗要點哪些格。full 模式回 None（全格點，舊行為）。

        推斷空格要有格線背書：讀不出格線的幀不准推斷，那一窗退回全格點。
        """
        if self.filter_mode != sweep.FILTER_CANDIDATES:
            return None
        self.peaks = ()
        if board.find_lattice(frame) is None:
            return None
        self.peaks = sweep.candidate_points(frame)
        return sweep.candidate_cells(self._ledger().grid, self.offset, self.peaks)

    def infer_empties(self, plan: sweep.WindowPlan, cells: frozenset[sweep.Cell] | None) -> None:
        """候選以外的窗內格入帳 EMPTY_INFERRED——視覺主張，明白標示沒有點擊背書。"""
        if self.filter_mode != sweep.FILTER_CANDIDATES:
            return
        ledger = self._ledger()
        for cell in plan.inferred:
            ledger.record(cell, sweep.EMPTY_INFERRED, reason="candidate_filter")
        self.journal.record(
            "candidates",
            mode=self.filter_mode,
            reason="no_lattice" if cells is None else None,
            peaks=[[round(value, 1) for value in point] for point in self.peaks],
            cells=None if cells is None else [list(cell) for cell in sorted(cells)],
            inferred=len(plan.inferred),
            inferred_cells=[list(cell) for cell in plan.inferred],
        )

    def expand(self, direction: str) -> None:
        """往 direction 擴張一段：前緣搬標記 → 推鏡 → 找標記重錨；丟了就局部回退。

        沒有標記可用時（第一格空格還沒點出來）退回舊路：推完靠地標重錨，重錨不成
        才回角落歸零。
        """
        frame = self.settled()
        if self.signature is None or self.marker_cell is None:
            self.pan(direction, frame)
            self.relocate()
            return
        self.carry_marker(direction, frame)
        while True:
            reach = self.stride(direction)
            stroke, _ = self.pan(direction, self.camera.grab(), reach)
            node = self.anchor_on_marker()
            if node is not None:
                self.walk.expanded(node)
                return
            self.fix.lose()
            self.journal.record("expand_lost", direction=direction, reach=round(stroke, 1))
            if self.retreat(direction, stroke) == sweep.STEP_ROOT:
                self.zero()
                self.home()
                return

    def retreat(self, direction: str, stroke: float) -> str:
        """反向等幅推回上一個信任節點。回程也丟就沿節點鏈繼續退，到角落為止。

        整條回程都在 LOST 態：只推鏡與全幀重認，一下都不點。
        """
        back = sweep.OPPOSITE[direction]
        step = self.walk.lost()
        while step == sweep.STEP_RETREAT:
            self.pan(back, self.camera.grab(), stroke)
            node = self.anchor_on_marker()
            self.journal.record("retreat", direction=back, found=node is not None)
            if node is not None:
                return self.walk.recovered()
            step = self.walk.lost()
        return step

    def home(self) -> None:
        """歸零後沿已裁決區接力返航回鋒面：每站點一個已知空格搬標記＋一把推鏡＋
        重認。帳本不清，一格都不重掃。"""
        ledger = self._ledger()
        target = sweep.frontier_cell(ledger, self.heading)
        if target is None or self.signature is None or self.marker_cell is None:
            return
        route = sweep.homing_route(ledger.grid, self.offset, target)
        self.journal.record("homing", target=list(target), legs=list(route))
        for direction in route:
            frame = self.settled()
            planted = self.carry_marker(direction, frame)
            if not planted and not sweep.in_window(ledger.grid, self.offset, self.marker_cell):
                # 本窗種不出標記、舊標記又在窗外＝這一把推完沒有證人。與其推出去失位，
                # 不如停在角落讓正規掃描從這裡重新長出鋒面（角落的鏡位是可信的）。
                self.journal.record("homing_blocked", direction=direction)
                return
            self.pan(direction, self.camera.grab(), self.stride(direction))
            if self.anchor_on_marker() is None:
                self.fix.lose()
                self.journal.record("homing_lost", direction=direction)
                return

    def carry_marker(self, direction: str, frame: np.ndarray) -> bool:
        """標記不在推進方向的前緣格就主動搬過去——新窗看不見它就無從重認。

        回傳「標記現在確實落在本窗」。

        點擊生效與手勢生效同一條紀律：發出≠生效。`classify_tap` 只有在填色**確實
        出現在被點的那一格**才回 EMPTY，所以驗收就是它；沒驗過就更新 `marker_cell`
        會讓下一次重錨拿舊填色配新格號，整幀寫進差一格距整數倍的世界位置。
        """
        ledger = self._ledger()
        target = sweep.frontier_tap(
            ledger, self.offset, self.marker_cell, direction, accept=self.carriable
        )
        if target is None:
            return sweep.in_window(ledger.grid, self.offset, self.marker_cell)
        was = ledger.verdict(target.cell)
        outcome = self.tap_cell(target, frame)
        if outcome.verdict == sweep.TAP_NONE:
            self.journal.record("carry_failed", cell=list(target.cell), direction=direction)
            outcome = self.tap_cell(target, self.camera.grab())
        self.journal.record(
            "carry_marker",
            cell=list(target.cell),
            verdict=outcome.verdict,
            direction=direction,
            was=was,
        )
        if outcome.verdict == sweep.TAP_EMPTY:
            ledger.record(target.cell, sweep.EMPTY)
            self.marker_cell = target.cell
            return True
        if outcome.verdict == sweep.TAP_CARD or outcome.verdict in sweep.TAP_SHIFTS:
            # 推斷成空的格點下去卻出卡／置中＝候選過濾漏報了一台，帳本改回點擊事實。
            if was == sweep.EMPTY_INFERRED:
                self.journal.record("inference_broken", cell=list(target.cell))
                if outcome.verdict == sweep.TAP_CARD:
                    self.sentence_card(target)
                    return False
                self.sentence_shift(target, outcome)
                return False
            self.escape()
        return False

    @property
    def carriable(self) -> tuple[str, ...]:
        if self.filter_mode == sweep.FILTER_CANDIDATES:
            return (sweep.EMPTY, sweep.EMPTY_INFERRED)
        return (sweep.EMPTY,)

    def stride(self, direction: str) -> float:
        """這一把推多遠：節點鏈想要的步幅，被「標記仍在新窗視野內」硬上限夾住。"""
        ledger = self._ledger()
        grid = ledger.grid
        pitch = grid.col_pitch if direction in ("east", "west") else grid.row_pitch
        cap = sweep.stride_cap(
            sweep.screen_of(grid, self.marker_cell, self.offset),
            direction,
            margin=sweep.MARKER_KEEP_PITCH * pitch,
        )
        return max(board.PAN_MIN_REACH, min(self.walk.reach, cap))

    def anchor_on_marker(self) -> sweep.TrustNode | None:
        """推鏡後的定位：**找到標記在哪一格**就是鏡位，位移量測不參與。

        錨完還要用當下看得見的終止邊回頭質詢——認錯一塊同色美術就是整幀寫進錯的
        世界位置，而帳本記的是世界格。
        """
        ledger = self._ledger()
        if self.signature is None or self.marker_cell is None:
            return None
        frame = self.settled()
        found = board.find_marker(
            frame, self.signature, holes=board.UNIT_DENSITY_HUD_HOLES
        )
        if found is None:
            self.journal.record("marker_lost")
            return None
        world = ledger.grid.centre_of(self.marker_cell)
        offset = (world[0] - found[0], world[1] - found[1])
        borders = sweep.read_borders(frame)
        clash = sweep.contradicts(ledger, self.landmarks, borders, offset)
        if clash is not None:
            # 撞色簽是唯一沒有幀就診斷不了的失敗（要親看東側是什麼被認成填色），必存。
            self.journal.record(
                "marker_clash",
                side=clash,
                at=[round(value, 1) for value in found],
                offset=[round(value, 1) for value in offset],
                borders={side: round(value, 1) for side, value in borders.items()},
                frame=self.camera.keep("clash"),
            )
            if self.revoke(clash, borders, offset):
                clash = sweep.contradicts(ledger, self.landmarks, borders, offset)
            if clash is not None:
                return None
        for side in borders:
            if side in self.landmarks:
                self.clashes.pop(side, None)
        self.offset = offset
        self.grounded = True
        self.ungrounded = 0
        self.fix.regain()
        self.witness(frame)
        node = sweep.TrustNode(
            cell=self.marker_cell,
            offset=offset,
            borders=tuple(sorted(borders)),
            units=self.units_in_window(offset),
        )
        self.journal.record(
            "node",
            cell=list(node.cell),
            offset=[round(value, 1) for value in offset],
            borders=list(node.borders),
            units=[list(cell) for cell in node.units],
            depth=len(self.walk.nodes) + 1,
        )
        return node

    def units_in_window(self, offset: sweep.Point) -> tuple[sweep.Cell, ...]:
        """本窗內已裁決的單位格＝節點的星座證據（我方回合內單位不動）。"""
        ledger = self._ledger()
        inside = sweep.window_targets(ledger.grid, offset)
        return tuple(
            cell
            for cell in sorted(ledger.cells_of(sweep.ENEMY) + ledger.cells_of(sweep.ALLY))
            if cell in inside
        )

    def work(self, plan: sweep.WindowPlan, frame: np.ndarray) -> bool:
        """本窗逐格點擊。回傳「被中斷了」——出卡或置中之後幾何要重讀才算數。"""
        ledger = self._ledger()
        if not self.grounded:
            self.journal.record("work_blocked", reason="ungrounded")
            return False
        before = frame
        for target in plan.taps:
            if ledger.taps >= self.max_taps:
                return False
            if not self.aimed(before):
                return True
            outcome = self.decide(target, before)
            if outcome == sweep.TAP_CARD or outcome in sweep.TAP_SHIFTS:
                return True
            if outcome == sweep.TAP_ADRIFT:
                return True
            before = self.camera.grab()
        return False

    def aimed(self, frame: np.ndarray) -> bool:
        """這一幀的格線相位對不對得上當前鏡位。對不上就停手重錨，一格都不點。

        讀不出格線回 True：那是「不知道」不是「偏了」，別讓沒有格線的畫面把掃描
        鎖死；那條路上還有標記與界線兩個證人。
        """
        grid = self._ledger().grid
        reading = board.lattice_phase(frame)
        if reading is None:
            return True
        drift = sweep.aim_drift(reading[0], grid, self.offset)
        if sweep.aimed(drift, grid):
            return True
        self.journal.record(
            "aim_drift",
            drift=[round(value, 1) for value in drift],
            offset=[round(value, 1) for value in self.offset],
        )
        self.grounded = False
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
            retry = self.camera.grab()
            # escape 回得了 hub，回不了鏡位：選擇態把鏡頭拉走之後同一個螢幕點已經
            # 是別的世界格，照樣重點就是拿鄰格的回饋替目標格背書（假 EMPTY 的來源）。
            if not self.aimed(retry):
                return sweep.TAP_ADRIFT
            outcome = self.tap_cell(target, retry)
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
        if outcome.verdict in sweep.TAP_SHIFTS:
            self.sentence_shift(target, outcome)
            return outcome.verdict
        ledger.record(target.cell, sweep.UNSURE, reason="no_feedback")
        self.journal.record("verdict", cell=list(target.cell), verdict=sweep.UNSURE,
                            reason="no_feedback")
        return outcome.verdict

    def tap_cell(self, target: sweep.TapTarget, before: np.ndarray) -> sweep.TapOutcome:
        ledger = self._ledger()
        self.fix.allow_tap()
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
            selected=self.in_selection,
            pitch=(ledger.grid.col_pitch, ledger.grid.row_pitch),
        )

    def in_selection(self, frame: np.ndarray) -> bool:
        return map_view.classify_view(self.gate, frame) in map_view.SELECTION_SUBSTATES

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
        """置中＝點到我方（只有未行動的我方單位吃得下這一下）。escape 後重錨。

        幾何對得上但選擇態 UI 沒背書時只重錨鏡頭，陣營記 UNSURE 留白。
        """
        ledger = self._ledger()
        path = self.camera.keep("shift")
        confirmed = outcome.verdict == sweep.TAP_SHIFTED
        verdict = sweep.ALLY if confirmed else sweep.UNSURE
        reason = "recentred" if confirmed else "recentred_unconfirmed"
        ledger.record(target.cell, verdict, frame=path, reason=reason)
        self.journal.record(
            "verdict",
            cell=list(target.cell),
            verdict=verdict,
            reason=reason,
            delta=None if outcome.delta is None else [round(v, 1) for v in outcome.delta],
            frame=path,
        )
        self.escape()
        candidate = sweep.recentre_offset(ledger.grid, target.cell)
        self.relocate(candidate=candidate)

    def on_hub(self, frame: np.ndarray | None = None) -> bool:
        return map_view.classify_view(self.gate, frame) == map_view.HUB

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
        """這一幀目視到的終止邊 → 地標與界線。界線第一次記下就不再改。

        地標是**整幀座標的絕對真值**，所以寫入資格要審，這一點與帳本只收點擊事實
        同一條紅線：推斷出來的鏡位（置中反推）算得出世界座標，但那個座標繼承了
        推斷的錯，沒有資格開新地標——它只能拿既有地標覆核界線。
        """
        ledger = self._ledger()
        for side, screen_position in sweep.read_borders(frame).items():
            axis = 0 if side in ("west", "east") else 1
            world = screen_position + self.offset[axis]
            if side in self.landmarks:
                ledger.see_border(side, self.landmarks[side])
                continue
            if not self.grounded:
                continue
            readings = self.sightings.setdefault(side, [])
            readings.append(world)
            del readings[: -sweep.LANDMARK_VOTES]
            settled = sweep.settled_reading(readings, self.slack(side))
            if settled is None:
                continue
            self.landmarks[side] = settled
            self.journal.record(
                "landmark",
                side=side,
                world=round(settled, 1),
                votes=[round(value, 1) for value in readings],
            )
            self.sightings.pop(side, None)
            ledger.see_border(side, settled)

    def slack(self, side: str) -> float:
        grid = self._ledger().grid
        pitch = grid.col_pitch if side in ("west", "east") else grid.row_pitch
        return sweep.EDGE_AGREEMENT_PITCH * pitch

    def revoke(self, side: str, borders: Mapping[str, float], offset: sweep.Point) -> bool:
        """同一側累積 N 次互相對得上的反證＝錯的是舊地標，撤換。回傳有沒有翻案。

        反證的鏡位是標記錨定解出來的（填色是我們自己種下去的絕對地標），比一次寫死
        的舊地標可信。計數只由「那一側目視到而且對得上」清零——不然回退途中的成功
        重錨（那些鏡位根本看不到這一側）會把計數洗掉，活鎖就永遠等不到第 N 次。
        """
        axis = 0 if side in ("west", "east") else 1
        readings = self.clashes.setdefault(side, [])
        readings.append(borders[side] + offset[axis])
        del readings[: -sweep.LANDMARK_REVOKE_CLASHES]
        settled = sweep.settled_reading(readings, self.slack(side), sweep.LANDMARK_REVOKE_CLASHES)
        if settled is None:
            return False
        was = self.landmarks[side]
        self.landmarks[side] = settled
        self.journal.record(
            "landmark_revoked",
            side=side,
            was=round(was, 1),
            world=round(settled, 1),
            votes=[round(value, 1) for value in readings],
        )
        self.clashes.pop(side, None)
        self._ledger().see_border(side, settled, replace=True)
        return True

    def relocate(self, candidate: sweep.Point | None = None) -> None:
        """推鏡／置中之後重定鏡位：地標優先，標記填色補位，都沒有才回角落歸零。

        置中反推的鏡位照舊寫進 offset（那一步是既有流程），但它是假說：連續這樣錨定
        超過 `UNGROUNDED_ANCHOR_LIMIT` 次就當失位，而在被 `confirm` 背書之前一格都不
        裁決。
        """
        ledger = self._ledger()
        frame = self.settled()
        borders = sweep.read_borders(frame)
        marker = self.marker_offset(frame)
        # 置中反推的鏡位是**假設**（被點的我方格落在螢幕正中心），標記填色解出來的
        # 才是量到的。兩者在 reanchor 的來源標籤裡同叫 centre，這裡自己分得出來。
        from_marker = candidate is None and marker is not None
        offset, source = sweep.reanchor(
            ledger.grid,
            landmarks=self.landmarks,
            borders=borders,
            candidate=candidate if candidate is not None else marker,
        )
        grounded = source == sweep.SOURCE_EDGE or (from_marker and source != sweep.SOURCE_LOST)
        self.journal.record(
            "relocate",
            source=source,
            offset=None if offset is None else [round(value, 1) for value in offset],
            borders=sorted(borders),
            marker=marker is not None,
            grounded=grounded,
        )
        if offset is None:
            self.zero()
            return
        self.offset = offset
        self.grounded = grounded
        if grounded:
            self.ungrounded = 0
            self.fix.regain()
        else:
            self.ungrounded += 1
            if self.ungrounded > sweep.UNGROUNDED_ANCHOR_LIMIT:
                self.fix.lose()
            else:
                self.fix.regain()
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

    def pan(
        self, direction: str, frame: np.ndarray, reach: float | None = None
    ) -> tuple[float, np.ndarray]:
        """一把推鏡，**逐手勢驗收行程**。回傳（實際打出去的行程, 驗收幀）。

        驗收幀交回去給呼叫端接著用：它是 swipe 之後 PAN_SETTLE_S ＋一次 screencap
        往返（實測 ~2.4s）才取的，比再跑一次 settled() 的第一張還晚，重拍只是多付
        截圖錢（0804 那輪 zero 段 24 張裡有 16 張是這樣浪費掉的）。

        發出去的手勢不等於生效的手勢：省電觸控鎖會無聲吞掉整把。沒生效就先做解鎖
        檢查再把同一把原樣重發；連吃就停在原地，不再對著吞點空轉。手勢日誌只是
        導航提示，不在信任鏈裡。

        行程由標記像素位移驗收（未包裝），相位只在標記看不見時撐場——所以行程先
        過 legible_reach，把相位殘量調離 0，免得走了一整把讀起來像沒動。沒走到預期
        行程＝夾停：先問界線（本幀看得見／帳本記過且窗已貼著），是到邊就記行程 0
        收工；界線讀不出來也不 Halt、不寫界線，改記這個方向在本鏡位推盡，讓呼叫端
        轉向——推不動**永遠不等於**有界線。
        """
        wanted = board.PAN_MAX_REACH if reach is None else reach
        origin, stroke = board.pan_stroke(direction, wanted, board.find_sightings(frame))
        seen = board.lattice_phase(frame)
        if seen is not None:
            stroke = board.legible_reach(direction, stroke, seen[1])
        x1, y1, x2, y2 = board.pan_gesture(direction, origin, stroke)
        pinned = 0
        before = seen
        for attempt in range(sweep.GESTURE_EATEN_LIMIT):
            was = self.marker_point(frame)
            self.device.swipe(x1, y1, x2, y2, board.PAN_DURATION_S)
            self.sleep(board.PAN_SETTLE_S)
            frame = self.camera.grab()
            after = board.lattice_phase(frame)
            shift = (
                None
                if before is None or after is None
                else board.phase_shift(before[0], after[0], before[1])
            )
            before = after
            now = self.marker_point(frame)
            moved = None if was is None or now is None else (now[0] - was[0], now[1] - was[1])
            verdict = sweep.gesture_verdict(
                shift, direction, travel=stroke * board.PAN_GAIN, moved=moved
            )
            self.journal.record(
                "pan",
                direction=direction,
                origin=[round(v, 1) for v in origin],
                reach=round(stroke, 1),
                attempt=attempt,
                verdict=verdict,
                phase=None if shift is None else [round(v, 1) for v in shift],
                moved=None if moved is None else [round(v, 1) for v in moved],
            )
            if verdict == sweep.PAN_LANDED:
                self.pinned.clear()
                return stroke, frame
            borders = sweep.read_borders(frame)
            if sweep.at_border(direction, borders, ledger=self.ledger, offset=self.offset):
                self.journal.record(
                    "pan_exhausted",
                    direction=direction,
                    attempt=attempt,
                    borders=sorted(borders),
                )
                if self.ledger is not None:
                    self.witness(frame)
                return 0.0, frame
            if verdict == sweep.PAN_PINNED:
                pinned += 1
                if pinned >= sweep.GESTURE_PINNED_LIMIT:
                    self.pinned.add(direction)
                    self.journal.record(
                        "pan_pinned",
                        direction=direction,
                        attempt=attempt,
                        borders=sorted(borders),
                    )
                    return 0.0, frame
                continue
            self.device.ensure_unlocked(force=True)
        raise Halt(f"推鏡連吃 {sweep.GESTURE_EATEN_LIMIT} 把：手勢沒生效")

    def marker_point(self, frame: np.ndarray) -> sweep.Point | None:
        """填色標記在這一幀的螢幕位置——推鏡前後各問一次就是未包裝的真實位移。"""
        if self.signature is None:
            return None
        return board.find_marker(frame, self.signature, holes=board.UNIT_DENSITY_HUD_HOLES)

    def settled(self) -> np.ndarray:
        frame = self.camera.grab()
        for _ in range(SETTLE_ROUNDS):
            self.sleep(SETTLE_POLL_S)
            frame = self.camera.grab()
        return frame

    def abandon(self) -> None:
        """棄戰鏈逐下存證：確認鈕與戰鬥選單「幫助」同列相距 73px，鏈一旦錯拍就是
        打在幫助上，而流水帳裡看不出來——所以每一下的座標與當下畫面都存。"""
        self.begin("abandon")

        def witness_tap(label: str, point: tuple[int, int]) -> None:
            self.camera.grab()
            self.journal.record(
                "abandon_tap", label=label, point=list(point), frame=self.camera.keep(f"abandon:{label}")
            )

        report = entry.abandon_battle(
            self.camera.grab, self.device.tap, sleep=self.sleep, on_tap=witness_tap
        )
        self.gate_report("abandon", report)
        self.camera.grab()
        self.camera.keep("abandon:landed")
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
    parser.add_argument(
        "--filter-mode",
        choices=(sweep.FILTER_FULL, sweep.FILTER_CANDIDATES),
        default=sweep.FILTER_FULL,
        help=(
            "full＝全格點（預設，真值來源）；candidates＝只點單位候選格、其餘推斷為空"
            "（候選門檻尚無真值背書，等 eval_candidate_recall 報 100%% 召回才翻回預設）"
        ),
    )
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
        filter_mode=args.filter_mode,
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
        filter_mode=args.filter_mode,
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
