"""盤面全覽：覆蓋簿記、感知接縫，以及三個行動的恢復式執行器。

開格線、收卡條與掃描都是**符號行動**（stage/actions.py），不是藏在感知裡的程序：
三者都會改遊戲狀態，照 refire-gate 同一精神由規劃器排序。grid_on 與
roster_collapsed 是掃描的前置條件，所以規劃器自然把 show_grid／collapse_roster
排在 survey_board 之前；掃描程序內部不翻開關、不收卡條，也沒有降級掃。

掃描是**一個**行動，留在計畫佇列頭跨 tick 重入。執行器每次進來先感知複核（截
一張新圖、對回上一幀量位移，鏡頭被反射動過也自己修回來），再挑下一個微步驟：
縮放 → 分段平移 → 逐幀量測吸附 → 邊界 → 合併寫回。所以反射可以在任何一個
tick 插進來收彈窗，之後接著掃；一個 tick 只做一個微步驟，迴圈「一 tick 至多
一次操作」的紀律不變。

**覆蓋進度的落點**：CoverageLedger 是簿記側的權威，SurveyPerceiver 把它折進
StageState 的 swept／board_synced——因為完成判定走 progressed(state)，恢復點
不能只活在執行器的內部變數裡（否則換一個執行器實例、或流水帳重建，就看不出
掃到哪了）。反過來，跨幀視口的像素對齊（上一幀、累積位移）純屬執行器內部，
不進符號層。

**生命週期**：board_synced 在敵方回合過完就過期——敵人動過，站位全部作廢。
衰效由這裡的接縫執行（它是唯一同時看得到簿記與觀測的地方），與搜尋側
next_player_phase 的同一條規則對齊。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from ..runtime import board, entry, screens
from ..runtime.perceive import Observation, Perceiver
from .actions import CollapseRoster, ShowGrid, SurveyBoard
from .state import Phase, StageState

log = logging.getLogger(__name__)

ZOOM_STEP = "zoom"
MERGE_STEP = "merge"
DEFAULT_ITINERARY: tuple[str, ...] = ("west", "north", "east", "south")
LEGS_PER_DIRECTION = 8
ROSTER_SETTLE_S = 1.2
ROSTER_ALREADY = "already"
ROSTER_TAPPED = "tapped"
ROSTER_UNREADABLE = "unreadable"


@dataclass
class CoverageLedger:
    """一次盤面全覽的覆蓋簿記——掃描行動跨 tick 重入時的恢復點。

    畫面上讀不到「我掃過西邊了」，所以這是程式內記憶，跨執行無狀態（黑板紀律：
    只活在單一 process 內）。
    """

    itinerary: tuple[str, ...] = DEFAULT_ITINERARY
    legs_per_direction: int = LEGS_PER_DIRECTION
    zoomed: bool = False
    swept: set[str] = field(default_factory=set)
    legs: dict[str, int] = field(default_factory=dict)
    scan: board.BoardScan | None = None
    # 每次衰效加一。執行器拿它認出「上一輪的世界座標系作廢了」並重置游標——
    # 不然下一輪的目擊會疊在上一輪的累積位移上。
    generation: int = 0

    @property
    def synced(self) -> bool:
        return self.scan is not None

    @property
    def frozen_swept(self) -> frozenset[str]:
        return frozenset(self.swept)

    def next_step(self) -> str:
        """下一個微步驟的名字。縮放最前、合併寫回最後，中間是還沒掃完的方向。"""
        if not self.zoomed:
            return ZOOM_STEP
        for direction in self.itinerary:
            if direction not in self.swept:
                return direction
        return MERGE_STEP

    def leg_done(self, direction: str) -> None:
        self.legs[direction] = self.legs.get(direction, 0) + 1
        if self.legs[direction] >= self.legs_per_direction:
            # 走完預算還沒到邊：當作掃過，不無限推下去（誠實停在有限覆蓋，
            # 而不是把整批 tick 燒在一個方向上）。
            log.warning("direction %s hit its leg budget before an edge", direction)
            self.swept.add(direction)

    def edge_reached(self, direction: str) -> None:
        self.swept.add(direction)

    def record(self, scan: board.BoardScan) -> None:
        self.scan = scan

    def cells(self) -> tuple[tuple[board.Cell, str | None], ...]:
        """單位格座標清單。陣營不在裡面——弧色只是線索（定案 5）。"""
        return () if self.scan is None else tuple(self.scan.cells)

    def expire(self) -> None:
        """回合交界的衰效：站位作廢，覆蓋歸零，縮放留著（鏡頭沒被動過）。"""
        self.swept.clear()
        self.legs.clear()
        self.scan = None
        self.generation += 1


@dataclass
class SurveyPerceiver:
    """把 board_synced／swept 與 grid_on／roster_collapsed 併進觀測。

    前兩個來自簿記（同 IntelPerceiver 的理由：符號效果只有我們自己的記憶承接
    得住）；後兩個是畫面事實，感知已經在 evidence 裡讀好了，這裡只搬不重讀。

    卡條走**感知權威**：每個 tick 逐幀觀測，讀不出來（None）一律折成「沒收起」
    ——收一次的成本遠低於在被遮住的掃描帶上量座標。evidence 裡沒有這個鍵時
    （離線假件）保留狀態原值。

    看到敵方回合就讓簿記過期——這個接縫是唯一同時看得到簿記與觀測的地方。
    """

    inner: Perceiver[StageState]
    ledger: CoverageLedger

    def look(self) -> Observation[StageState]:
        seen = self.inner.look()
        state = seen.state
        if state is None:
            return seen
        if state.phase is Phase.ENEMY and self.ledger.synced:
            self.ledger.expire()
        grid_on = bool(seen.evidence.get("grid_on", state.grid_on))
        if "roster_strip" in seen.evidence:
            collapsed = seen.evidence["roster_strip"] == screens.ROSTER_COLLAPSED
        else:
            collapsed = state.roster_collapsed
        folded = (self.ledger.synced, self.ledger.frozen_swept, grid_on, collapsed)
        if (state.board_synced, state.swept, state.grid_on, state.roster_collapsed) == folded:
            return seen
        return replace(
            seen,
            state=replace(
                state,
                board_synced=self.ledger.synced,
                swept=self.ledger.frozen_swept,
                grid_on=grid_on,
                roster_collapsed=collapsed,
            ),
        )


@dataclass
class BoardDriver:
    """兩個閉迴圈行動的執行器：要邊看邊做，不是一串固定手勢。

    zoom_out 是注入的（實作在 runtime/zoom.py，需要 uiautomator 注入通道，與截圖
    ／點擊的 adb 通道分開）：沒給就只記一次警告照樣往下走——覆蓋會比最小縮放時
    差（腿數變多），但不影響流程正確性。
    """

    capture: Callable[[], np.ndarray]
    actuator: Any
    ledger: CoverageLedger = field(default_factory=CoverageLedger)
    zoom_out: Callable[[], None] | None = None
    sleep: Callable[[float], None] = field(default=time.sleep)
    cursor: board.ScanCursor = field(default_factory=board.ScanCursor)
    steps: list[str] = field(default_factory=list)
    generation: int = 0

    def show_grid(self, action: ShowGrid, observation: Observation[Any]) -> bool:
        return entry.set_battle_grid(self.capture, self._tap, True, sleep=self.sleep)

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
        if self.generation != self.ledger.generation:
            # 簿記衰效過：上一輪的累積位移與目擊都作廢，游標整個換掉。
            self.cursor = board.ScanCursor()
            self.generation = self.ledger.generation
        frame = self.capture()
        self.cursor.feed(frame)

        step = self.ledger.next_step()
        if step == ZOOM_STEP:
            self._zoom()
        elif step == MERGE_STEP:
            self.ledger.record(self.cursor.scan)
        else:
            self._sweep_leg(step, frame)
        self.steps.append(step)
        return step

    def drivers(self) -> dict[type, Callable[[Any, Observation[Any]], Any]]:
        return {
            ShowGrid: self.show_grid,
            CollapseRoster: self.collapse_roster,
            SurveyBoard: self.survey_board,
        }

    def _zoom(self) -> None:
        if self.zoom_out is None:
            log.warning("no zoom-out driver injected; scanning at the current zoom")
        else:
            self.zoom_out()
        self.ledger.zoomed = True

    def _sweep_leg(self, direction: str, before: np.ndarray) -> None:
        origin = board.pick_pan_origin(board.find_sightings(before))
        self._pan(direction, origin)
        after = self.capture()
        if board.at_edge(before, after):
            self.ledger.edge_reached(direction)
            return
        self.cursor.feed(after)
        self.ledger.leg_done(direction)

    def _tap(self, x: int, y: int, *, intent: str = "") -> None:
        self.actuator.tap(x, y, intent=intent)

    def _pan(self, direction: str, origin: board.Point) -> None:
        x1, y1, x2, y2 = board.pan_gesture(direction, origin)
        self.actuator.swipe(x1, y1, x2, y2, board.PAN_DURATION_S)
        self.sleep(board.PAN_SETTLE_S)


def survey_drivers(
    capture: Callable[[], np.ndarray],
    actuator: Any,
    *,
    ledger: CoverageLedger | None = None,
    itinerary: Sequence[str] = DEFAULT_ITINERARY,
    zoom_out: Callable[[], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[BoardDriver, CoverageLedger]:
    """把簿記與執行器一起立起來——感知接縫與執行器必須共用同一本簿記。"""
    book = ledger or CoverageLedger(itinerary=tuple(itinerary))
    driver = BoardDriver(
        capture=capture, actuator=actuator, ledger=book, zoom_out=zoom_out, sleep=sleep
    )
    return driver, book
