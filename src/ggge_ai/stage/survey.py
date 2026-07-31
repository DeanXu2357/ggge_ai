"""盤面全覽：覆蓋簿記、感知接縫，以及三個行動的恢復式執行器。

開格線、收卡條與掃描都是**符號行動**（stage/actions.py），不是藏在感知裡的程序：
三者都會改遊戲狀態，照 refire-gate 同一精神由規劃器排序。grid_on 與
roster_collapsed 是掃描的前置條件，所以規劃器自然把 show_grid／collapse_roster
排在 survey_board 之前；掃描程序內部不翻開關、不收卡條，也沒有降級掃。

掃描是**一個**行動，留在計畫佇列頭跨 tick 重入。執行器每次進來先感知複核（截
一張新圖、對回上一幀量位移），再挑下一個微步驟：縮放 → 往缺口推一步 → 逐幀
量測吸附。所以反射可以在任何一個 tick 插進來收彈窗，之後接著掃；一個 tick 只做
一個微步驟，迴圈「一 tick 至多一次操作」的紀律不變。

**覆蓋進度的落點**：世界模型住 `runtime/coverage.Survey`（四態知識圖＋邊界旗＋
前緣，覆蓋模型 v2），CoverageLedger 只是簿記側的門面，SurveyPerceiver 把它折進
StageState 的 board_synced——因為完成判定走 progressed(state)，恢復點不能只活在
執行器的內部變數裡（否則換一個執行器實例就看不出掃到哪了）。**分段進度不再進
符號狀態**：v2 的進度是逐格的知識圖，壓不成搜尋鍵放得下的東西，也沒有任何
applicable／progressed 讀它；它逐 tick 走 `evidence["survey"]` 進流水帳。

**生命週期**：board_synced 在敵方回合過完就過期——敵人動過，站位全部作廢。
衰效由這裡的接縫執行（它是唯一同時看得到簿記與觀測的地方），與搜尋側
next_player_phase 的同一條規則對齊。衰效只降級單位知識（UNIT→STALE、
EMPTY→UNKNOWN），地圖幾何與邊界旗留著。
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
SWEEP_STEP = "sweep"
# 前緣空＝掃完了；保險絲燒斷或錨不到世界都是「這一 tick 沒得推」，但三者的成因
# 完全不同，所以微步驟名分開記——流水帳要看得出來是掃完還是掃不動。
DONE_STEP = "done"
FUSE_STEP = "fuse"
STUCK_STEP = "stuck"
BLIND_STEP = "blind"
ROSTER_SETTLE_S = 1.2
ROSTER_ALREADY = "already"
ROSTER_TAPPED = "tapped"
ROSTER_UNREADABLE = "unreadable"


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
        """四旗全定 ∧ 界內無 UNKNOWN／STALE ——建構性的完成判準，不是腿數。"""
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
        """回合交界的衰效：單位知識降級，地圖幾何與縮放留著（鏡頭沒被動過）。"""
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


@dataclass
class BoardDriver:
    """兩個閉迴圈行動的執行器：要邊看邊做，不是一串固定手勢。

    zoom_out 是注入的（實作在 runtime/zoom.py，需要 uiautomator 注入通道，與截圖
    ／點擊的 adb 通道分開）：沒給就只記一次警告照樣往下走——**掃描成功不依賴
    縮小**，縮不動只是截圖次數變多（覆蓋模型 v2 的核心目的）。
    """

    capture: Callable[[], np.ndarray]
    actuator: Any
    ledger: CoverageLedger = field(default_factory=CoverageLedger)
    zoom_out: Callable[[], None] | None = None
    sleep: Callable[[float], None] = field(default=time.sleep)
    steps: list[str] = field(default_factory=list)

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
        frame = self.capture()
        survey.observe(frame)
        leg = survey.plan_leg()
        if leg is None:
            if survey.complete:
                return self._step(DONE_STEP)
            return self._step(FUSE_STEP if survey.fused else STUCK_STEP)
        # 錨不到世界（地圖邊緣的半幅虛空讀不出格網）也照樣推一步換視野，但那一腿
        # 是盲推——流水帳要分得出來，不然事後看不出這一段有沒有座標可信。
        prefix = SWEEP_STEP if survey.anchored else BLIND_STEP
        self._pan(leg, board.pick_pan_origin(board.find_sightings(frame)))
        survey.observe(self.capture(), leg)
        return self._step(f"{prefix}:{leg.direction}")

    def drivers(self) -> dict[type, Callable[[Any, Observation[Any]], Any]]:
        return {
            ShowGrid: self.show_grid,
            CollapseRoster: self.collapse_roster,
            SurveyBoard: self.survey_board,
        }

    def _step(self, name: str) -> str:
        self.steps.append(name)
        return name

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
) -> tuple[BoardDriver, CoverageLedger]:
    """把簿記與執行器一起立起來——感知接縫與執行器必須共用同一本簿記。"""
    book = ledger or CoverageLedger()
    driver = BoardDriver(
        capture=capture, actuator=actuator, ledger=book, zoom_out=zoom_out, sleep=sleep
    )
    return driver, book
