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
    sleep: Callable[[float], None] = time.sleep
    zoom_out: Callable[[], None] | None = None

    ledger: sweep.SweepLedger | None = field(default=None, init=False)
    offset: sweep.Point = field(default=(0.0, 0.0), init=False)
    heading: str = field(default="east", init=False)
    landmarks: dict[str, float] = field(default_factory=dict, init=False)
    signature: board.MarkerSignature | None = field(default=None, init=False)
    marker_cell: sweep.Cell | None = field(default=None, init=False)
    walk: sweep.NodeWalk = field(default_factory=sweep.NodeWalk, init=False)
    fix: sweep.Fix = field(default_factory=sweep.Fix, init=False)
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
            self.expand(direction)
        self.retire_deferred()

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
            self.carry_marker(direction, frame)
            self.pan(direction, self.camera.grab(), self.stride(direction))
            if self.anchor_on_marker() is None:
                self.fix.lose()
                self.journal.record("homing_lost", direction=direction)
                return

    def carry_marker(self, direction: str, frame: np.ndarray) -> None:
        """標記不在推進方向的前緣格就主動搬過去——新窗看不見它就無從重認。"""
        target = sweep.frontier_tap(self._ledger(), self.offset, self.marker_cell, direction)
        if target is None:
            return
        outcome = self.tap_cell(target, frame)
        self.journal.record(
            "carry_marker", cell=list(target.cell), verdict=outcome.verdict, direction=direction
        )
        if outcome.verdict == sweep.TAP_EMPTY:
            self.marker_cell = target.cell
            return
        if outcome.verdict in (sweep.TAP_CARD, sweep.TAP_SHIFTED):
            self.escape()

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
            self.journal.record("marker_clash", side=clash)
            return None
        self.offset = offset
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
        """一把推鏡，**逐手勢用格線相位驗收**。回傳（實際打出去的行程, 驗收幀）。

        驗收幀交回去給呼叫端接著用：它是 swipe 之後 PAN_SETTLE_S ＋一次 screencap
        往返（實測 ~2.4s）才取的，比再跑一次 settled() 的第一張還晚，重拍只是多付
        截圖錢（0804 那輪 zero 段 24 張裡有 16 張是這樣浪費掉的）。

        發出去的手勢不等於生效的手勢：省電觸控鎖會無聲吞掉整把。相位沒動＝被吃，
        先做解鎖檢查再把同一把原樣重發；連吃就停在原地，不再對著吞點空轉。手勢
        日誌只是導航提示，不在信任鏈裡。
        """
        wanted = board.PAN_MAX_REACH if reach is None else reach
        origin, stroke = board.pan_stroke(direction, wanted, board.find_sightings(frame))
        x1, y1, x2, y2 = board.pan_gesture(direction, origin, stroke)
        for attempt in range(sweep.GESTURE_EATEN_LIMIT):
            before = board.lattice_phase(frame)
            self.device.swipe(x1, y1, x2, y2, board.PAN_DURATION_S)
            self.sleep(board.PAN_SETTLE_S)
            frame = self.camera.grab()
            after = board.lattice_phase(frame)
            shift = (
                None
                if before is None or after is None
                else board.phase_shift(before[0], after[0], before[1])
            )
            landed = sweep.gesture_landed(shift, direction)
            self.journal.record(
                "pan",
                direction=direction,
                origin=[round(v, 1) for v in origin],
                reach=round(stroke, 1),
                attempt=attempt,
                landed=landed,
                phase=None if shift is None else [round(v, 1) for v in shift],
            )
            if landed:
                return stroke, frame
            self.device.ensure_unlocked(force=True)
        raise Halt(f"推鏡連吃 {sweep.GESTURE_EATEN_LIMIT} 把（格線相位不動）：手勢沒生效")

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
