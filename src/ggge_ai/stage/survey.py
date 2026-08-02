"""盤面全覽：覆蓋簿記、感知接縫，以及三個行動的恢復式執行器。

開格線、收卡條與掃描都是**符號行動**（stage/actions.py），不是藏在感知裡的程序：
三者都會改遊戲狀態，照 refire-gate 同一精神由規劃器排序。grid_on 與
roster_collapsed 是掃描的前置條件，所以規劃器自然把 show_grid／collapse_roster
排在 survey_board 之前；掃描程序內部不翻開關、不收卡條，也沒有降級掃。

掃描是**一個**行動，留在計畫佇列頭跨 tick 重入。執行器每次進來先感知複核（等畫面
靜止再收一張新圖交給世界模型定位），再挑下一個微步驟：縮放 → 往角落／邊／缺口推
一把 → 收幀定位。所以反射可以在任何一個 tick 插進來收彈窗，之後接著掃；一個 tick
只做一個微步驟，迴圈「一 tick 至多一次操作」的紀律不變。兩處取幀都走
`_settled_capture`——慣性滑行拖過推移的緩動時，收下的幀定位會歪（見常數區）。

**微步驟名**＝掃描階段加方向（`zero:west`／`tour:east`／`fill:north`），對應世界
模型的三個階段：推去西北角歸零、沿邊繞一圈、補中央的缺口。

**覆蓋進度的落點**：世界模型住 `runtime/coverage.Survey`（四態知識圖＋界線＋地標
＋前緣，覆蓋模型 v3），CoverageLedger 只是簿記側的門面，SurveyPerceiver 把它折進
StageState 的 board_synced——因為完成判定走 progressed(state)，恢復點不能只活在
執行器的內部變數裡（否則換一個執行器實例就看不出掃到哪了）。**分段進度不再進
符號狀態**：進度是逐格的知識圖，壓不成搜尋鍵放得下的東西，也沒有任何
applicable／progressed 讀它；它逐 tick 走 `evidence["survey"]` 進流水帳。

**生命週期**：board_synced 在敵方回合過完就過期——敵人動過，站位全部作廢。
衰效由這裡的接縫執行（它是唯一同時看得到簿記與觀測的地方），與搜尋側
next_player_phase 的同一條規則對齊。衰效只降級單位知識（UNIT→STALE、
EMPTY→UNKNOWN），地圖幾何、界線與地標留著。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from ..runtime import board, coverage, entry, screens
from ..runtime.perceive import Observation, Perceiver
from .actions import CollapseRoster, ShowGrid, SurveyBoard
from .state import Phase, StageState

log = logging.getLogger(__name__)

ZOOM_STEP = "zoom"
# 掃描三階段的微步驟前綴（世界模型的 stance 直接當名字用）。
ZERO_STEP = coverage.ZERO
TOUR_STEP = coverage.TOUR
FILL_STEP = coverage.FILL
STANCE_STEPS: tuple[str, ...] = (ZERO_STEP, TOUR_STEP, FILL_STEP)
# 前緣空＝掃完了；保險絲燒斷或角落讀不出世界都是「這一 tick 沒得推」，但三者的成因
# 完全不同，所以微步驟名分開記——流水帳要看得出來是掃完還是掃不動。
DONE_STEP = "done"
FUSE_STEP = "fuse"
STUCK_STEP = "stuck"
ROSTER_SETTLE_S = 1.2
ROSTER_ALREADY = "already"
ROSTER_TAPPED = "tapped"
ROSTER_UNREADABLE = "unreadable"

# 取幀靜止閘。0801 複驗實證：重手勢的慣性滑行會拖過 PAN_SETTLE_S，殘餘滑行落在
# 格線相位容差（22.5px）到 EDGE_SHIFT_PX（40px）這個窗口時，收下的幀會被格線相位
# 那一關拒收，40 tick 裡斷了 14 次。
# 靜止判準用相位相關的位移量而**不是** frame_difference：單位待機動畫逐幀都在動，
# 幀差永遠安靜不下來；滑行是全域同調位移，相位相關量得到、待機動畫量不到。
SETTLE_POLL_S = 0.25
SETTLE_QUIET_PX = 3.0
SETTLE_ROUNDS = 4
PRECHECK_PROBE = "precheck"
LEG_PROBE = "leg"


@dataclass
class CoverageLedger:
    """一次盤面全覽的覆蓋簿記——掃描行動跨 tick 重入時的恢復點。

    畫面上讀不到「我掃過西邊了」，所以這是程式內記憶，跨執行無狀態（黑板紀律：
    只活在單一 process 內）。內容是世界空間的四態知識圖（runtime/coverage），
    這裡只留符號層要的兩件事：縮放做過沒、盤面同步了沒。
    """

    survey: coverage.Survey = field(default_factory=coverage.Survey)
    zoomed: bool = False

    @property
    def synced(self) -> bool:
        """四面界線都定 ∧ 界內無 UNKNOWN／STALE ——建構性的完成判準，不是推了幾把。"""
        return self.survey.complete

    @property
    def generation(self) -> int:
        return self.survey.generation

    def cells(self) -> tuple[tuple[board.Cell, str | None], ...]:
        """單位格座標清單。陣營不在裡面——弧色只是線索（定案 5）。"""
        return self.survey.units()

    def summary(self) -> dict[str, Any]:
        return {**self.survey.summary(), "zoomed": self.zoomed}

    def expire(self) -> None:
        """回合交界的衰效：單位知識降級，地圖幾何、地標與縮放留著。"""
        self.survey.expire()


@dataclass
class SurveyPerceiver:
    """把 board_synced 與 grid_on／roster_collapsed 併進觀測，覆蓋自述進 evidence。

    第一個來自簿記（同 IntelPerceiver 的理由：符號效果只有我們自己的記憶承接
    得住）；後兩個是畫面事實，感知已經在 evidence 裡讀好了，這裡只搬不重讀。

    卡條走**感知權威**：每個 tick 逐幀觀測，讀不出來（None）一律折成「沒收起」
    ——收一次的成本遠低於在被遮住的掃描帶上量座標。evidence 裡沒有這個鍵時
    （離線假件）保留狀態原值。

    看到敵方回合就讓簿記過期——這個接縫是唯一同時看得到簿記與觀測的地方。整個
    敵方回合只衰效一次：generation 每加一次就換一套世界座標，逐 tick 加會讓掃描
    永遠在重新錨定。
    """

    inner: Perceiver[StageState]
    ledger: CoverageLedger
    decayed: bool = False

    def look(self) -> Observation[StageState]:
        seen = self.inner.look()
        state = seen.state
        if state is None:
            return seen
        if state.phase is Phase.ENEMY:
            if not self.decayed:
                self.ledger.expire()
                self.decayed = True
        else:
            self.decayed = False
        grid_on = bool(seen.evidence.get("grid_on", state.grid_on))
        if "roster_strip" in seen.evidence:
            collapsed = seen.evidence["roster_strip"] == screens.ROSTER_COLLAPSED
        else:
            collapsed = state.roster_collapsed
        return replace(
            seen,
            state=replace(
                state,
                board_synced=self.ledger.synced,
                grid_on=grid_on,
                roster_collapsed=collapsed,
            ),
            evidence={**seen.evidence, "survey": self.ledger.summary()},
        )


@dataclass(frozen=True)
class SettledFrame:
    """等靜止之後收下的那一幀，連同等了幾輪、最後有沒有真的靜下來。"""

    frame: np.ndarray
    waits: int
    quiet: bool


@dataclass
class BoardDriver:
    """兩個閉迴圈行動的執行器：要邊看邊做，不是一串固定手勢。

    zoom_out 是注入的（實作在 runtime/zoom.py，需要 uiautomator 注入通道，與截圖
    ／點擊的 adb 通道分開）：沒給就只記一次警告照樣往下走——**掃描成功不依賴
    縮小**，縮不動只是截圖次數變多（覆蓋模型 v2 的核心目的）。

    telemetry 是逐 observe 的遙測水槽（A5 儀器化）：解出來的座標、這一幀的座標是
    怎麼來的、靜止閘等了幾輪都只在這裡看得到，流水帳的微步驟名答不了「那一把推移
    實際走了多遠」。它是純觀察者——寫失敗只記一次警告，掃描照跑。

    evidence 是丟棄幀的**存證**水槽：observe 判 BROKEN（定位不出來）時把上一張與
    這一張 settled 幀連同那一筆遙測交出去，離線才重放得了定位。`dump_frames` 打開
    時每一次 observe 都發射，供離線把整輪掃描重跑一遍。同樣是純觀察者。

    上一幀由執行器自己留：世界模型丟棄一幀時刻意不動它記的「最近一張定位成功的
    幀」，所以那一側的 previous 未必是時間上的前一張。
    """

    capture: Callable[[], np.ndarray]
    actuator: Any
    ledger: CoverageLedger = field(default_factory=CoverageLedger)
    zoom_out: Callable[[], None] | None = None
    sleep: Callable[[float], None] = field(default=time.sleep)
    steps: list[str] = field(default_factory=list)
    telemetry: Callable[[dict[str, Any]], None] | None = None
    evidence: Callable[[dict[str, Any], np.ndarray | None, np.ndarray], None] | None = None
    dump_frames: bool = False
    previous: np.ndarray | None = None
    ticks: int = 0

    def show_grid(self, action: ShowGrid, observation: Observation[Any]) -> str:
        """翻設定頁的開關。回傳設定頁探針的自述（進流水帳）——它是 advisory，
        grid_on 到底成不成立由感知讀地圖上的格線像素說了算。"""
        return entry.set_battle_grid(self.capture, self._tap, True, sleep=self.sleep).detail

    def collapse_roster(self, action: CollapseRoster, observation: Observation[Any]) -> str:
        """先讀再決定要不要點：卡條的切換鈕是同一顆的兩個位置，讀不出來就別亂點
        （盲點一下會把已經收好的卡條又展開）。回傳這次做了什麼（進流水帳）。"""
        strip = screens.read_roster_strip(self.capture())
        if strip == screens.ROSTER_COLLAPSED:
            return ROSTER_ALREADY
        if strip is None:
            log.warning("roster strip unreadable; not tapping the toggle blind")
            return ROSTER_UNREADABLE
        self._tap(*screens.ROSTER_TOGGLE_TAP)
        self.sleep(ROSTER_SETTLE_S)
        return ROSTER_TAPPED

    def survey_board(self, action: SurveyBoard, observation: Observation[Any]) -> str:
        """一次呼叫＝感知複核＋一個微步驟。回傳這次做了哪一步（進流水帳）。"""
        survey = self.ledger.survey
        if not self.ledger.zoomed:
            self._zoom()
            return self._step(ZOOM_STEP)
        self.ticks += 1
        settled = self._settled_capture()
        self._read(PRECHECK_PROBE, None, settled)
        leg = survey.plan_leg()
        if leg is None:
            if survey.complete:
                return self._step(DONE_STEP)
            return self._step(FUSE_STEP if survey.fused else STUCK_STEP)
        # stance 要在 plan_leg 之後讀：那一步可能剛把繞邊換成補中央。
        stance = survey.stance
        self._pan(leg, board.pick_pan_origin(board.find_sightings(settled.frame)))
        self._read(LEG_PROBE, leg, self._settled_capture())
        return self._step(f"{stance}:{leg.direction}")

    def drivers(self) -> dict[type, Callable[[Any, Observation[Any]], Any]]:
        return {
            ShowGrid: self.show_grid,
            CollapseRoster: self.collapse_roster,
            SurveyBoard: self.survey_board,
        }

    def _step(self, name: str) -> str:
        self.steps.append(name)
        return name

    def _settled_capture(self) -> SettledFrame:
        """等畫面靜止再收幀——掃描的兩處取幀都走這裡。

        重試用盡就收最後一幀照常 observe：這個閘只降污染率，不保證零污染，而停在
        原地不收幀會把整個 tick 空轉掉。量不出位移（known=False，無特徵星空）視為
        靜止：量不出來不是「還在動」的證據，下一步 observe 自己會處置那一幀。
        """
        frame = self.capture()
        for waits in range(1, SETTLE_ROUNDS + 1):
            self.sleep(SETTLE_POLL_S)
            later = self.capture()
            shift = board.measure_shift(frame, later)
            frame = later
            if not shift.known or shift.magnitude < SETTLE_QUIET_PX:
                return SettledFrame(frame, waits, True)
        log.warning("frame never went quiet in %d rounds; observing it anyway", SETTLE_ROUNDS)
        return SettledFrame(frame, SETTLE_ROUNDS, False)

    def _read(
        self, probe: str, leg: coverage.Leg | None, settled: SettledFrame
    ) -> coverage.Reading:
        """一次 observe 連同它的兩個觀察者，然後把這一幀記成「上一幀」。"""
        reading = self.ledger.survey.observe(settled.frame, leg)
        self._trace(probe, leg, reading, settled)
        self._preserve(probe, leg, reading, settled)
        self.previous = settled.frame
        return reading

    def _trace(
        self,
        probe: str,
        leg: coverage.Leg | None,
        reading: coverage.Reading,
        settled: SettledFrame,
    ) -> None:
        if self.telemetry is None:
            return
        try:
            self.telemetry(self._record(probe, leg, reading, settled))
        except Exception:
            log.warning("survey telemetry sink failed; the scan carries on", exc_info=True)

    def _preserve(
        self,
        probe: str,
        leg: coverage.Leg | None,
        reading: coverage.Reading,
        settled: SettledFrame,
    ) -> None:
        """斷鏈的前後幀對交給存證水槽；dump_frames 打開時每一次 observe 都交。

        兩個水槽各包各的 try：遙測炸了不該連帶讓存證失效，反之亦然。
        """
        if self.evidence is None:
            return
        if reading.verdict != coverage.BROKEN and not self.dump_frames:
            return
        try:
            self.evidence(self._record(probe, leg, reading, settled), self.previous, settled.frame)
        except Exception:
            log.warning("survey evidence sink failed; the scan carries on", exc_info=True)

    def _record(
        self,
        probe: str,
        leg: coverage.Leg | None,
        reading: coverage.Reading,
        settled: SettledFrame,
    ) -> dict[str, Any]:
        survey = self.ledger.survey
        shift = reading.shift
        view = survey.last_view
        return {
            "tick": self.ticks,
            "probe": probe,
            "sequence": survey.observes,
            "stance": survey.stance,
            "direction": None if leg is None else leg.direction,
            "reach": None if leg is None else round(leg.reach, 1),
            "expected": None if leg is None else [round(value, 1) for value in leg.expected],
            "verdict": reading.verdict,
            "reason": reading.reason,
            "shift": {
                "dx": round(shift.dx, 2),
                "dy": round(shift.dy, 2),
                "magnitude": round(shift.magnitude, 2),
                "confidence": round(shift.confidence, 3),
                "source": shift.source,
            },
            "offset": [round(value, 1) for value in reading.offset],
            "span": None
            if view is None
            else {
                "sequence": view.sequence,
                "box": None if view.lattice is None else list(view.lattice),
                "edges": sorted(view.edges),
            },
            "locate": reading.detail,
            "settle": {"waits": settled.waits, "quiet": settled.quiet},
        }

    def _zoom(self) -> None:
        if self.zoom_out is None:
            log.warning("no zoom-out driver injected; scanning at the current zoom")
        else:
            self.zoom_out()
        self.ledger.zoomed = True
        # 縮放改的是比例：錨定幀的像素座標與格距全部作廢，世界重開。
        self.ledger.survey.reset()

    def _tap(self, x: int, y: int, *, intent: str = "") -> None:
        self.actuator.tap(x, y, intent=intent)

    def _pan(self, leg: coverage.Leg, origin: board.Point) -> None:
        x1, y1, x2, y2 = board.pan_gesture(leg.direction, origin, leg.reach)
        self.actuator.swipe(x1, y1, x2, y2, board.PAN_DURATION_S)
        self.sleep(board.PAN_SETTLE_S)


def survey_drivers(
    capture: Callable[[], np.ndarray],
    actuator: Any,
    *,
    ledger: CoverageLedger | None = None,
    zoom_out: Callable[[], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    telemetry: Callable[[dict[str, Any]], None] | None = None,
    evidence: Callable[[dict[str, Any], np.ndarray | None, np.ndarray], None] | None = None,
    dump_frames: bool = False,
) -> tuple[BoardDriver, CoverageLedger]:
    """把簿記與執行器一起立起來——感知接縫與執行器必須共用同一本簿記。"""
    book = ledger or CoverageLedger()
    driver = BoardDriver(
        capture=capture,
        actuator=actuator,
        ledger=book,
        zoom_out=zoom_out,
        sleep=sleep,
        telemetry=telemetry,
        evidence=evidence,
        dump_frames=dump_frames,
    )
    return driver, book
