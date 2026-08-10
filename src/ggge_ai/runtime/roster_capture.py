"""名冊採集：戰鬥選單「部隊資訊」逐格點開詳情，把每一頁存成幀。

這一層只走位與存幀，不解析數值——把幀讀成數字是離線的事（panels／panel_text）。
所以「拍到的是不是那一頁」比「拍了幾張」重要：每一拍先等幀差收斂、再驗面板種類、
再過一道哨兵讀值，三道都過才算數。

採集是加值步驟：`run()` 頂層吞掉所有例外。後面還有棄戰鏈要走，名冊沒拿到下一輪
再拿，卡在半開的面板上卻會讓整輪報廢。

座標分兩級：`BATTLE_MENU_TROOP_INFO_TAP` 以下到 `cell_taps` 為止是 0806 實幀量測
過的；`DETAIL_TAB_TAPS` 是從 panels 的帶推的，`BASIC_VIEW_TAP`／`PILOT_HALF_OFFSET`
／`WEAPON_SCROLL` 還沒標定（None ＝那一頁這一輪不採，開場記一筆 gap）。
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from . import entry, panels, screens, settle
from .device import ROSTER_CELL_INTENT
from .panels import PanelKind

Point = tuple[int, int]

ALLY = panels.ALLY
ENEMY = panels.ENEMY
FACTIONS = (ALLY, ENEMY)

BATTLE_MENU_TAP: Point = entry.BATTLE_MENU_TAP
BATTLE_MENU_CLOSE_TAP: Point = entry.BATTLE_MENU_CLOSE_TAP
BATTLE_MENU_TROOP_INFO_TAP: Point = (753, 508)
TROOP_INFO_CLOSE_TAP: Point = (1172, 992)
TROOP_INFO_ALLY_TAB_TAP: Point = (460, 440)
TROOP_INFO_ENEMY_TAB_TAP: Point = (460, 600)
DETAIL_CLOSE_TAP: Point = (994, 995)

TAB_TAPS: dict[str, Point] = {ALLY: TROOP_INFO_ALLY_TAB_TAP, ENEMY: TROOP_INFO_ENEMY_TAB_TAP}

# 列表格距（0806 兩張列表幀的圖示中心量測）。我軍是「部隊1／部隊2」兩列，每列多一
# 條 GET SCORE 帶所以列距較大；敵軍四列連排。單位圖示與駕駛圖示成對，點的是單位那半。
CELL_X0 = 729
CELL_X_PITCH = 278.5
CELL_Y0 = 267
CELLS_PER_ROW = 5
ALLY_ROW_PITCH = 245.7
ALLY_ROWS = 2
ENEMY_ROW_PITCH = 193.4
ENEMY_ROWS = 4

# 詳情頁三個分頁的切換點，由 panels.TAB_BANDS 的帶心推得。那些帶量的是「選中分頁的
# 藍底」而不是鈕身，推出來的點只保證落在分頁欄那一列——**未實機驗證**，第一次上機
# 要對著實幀確認三個分頁真的切得動。
DETAIL_TAB_TAPS: tuple[Point, ...] = tuple(
    (x + w // 2, y + h // 2) for x, y, w, h in panels.TAB_BANDS
)

# 以下三個待實機標定。None ＝對應的頁這一輪不採，`run()` 開場落一筆 gap 說明少了什麼。
# 標定完把值填進來，對應的採集步驟自己會開起來。
BASIC_VIEW_TAP: Point | None = None
PILOT_HALF_OFFSET: Point | None = None
WEAPON_SCROLL: tuple[Point, Point, float] | None = None

PAGE_BASIC = "basic"
PAGE_WEAPONS = "weapons"
PAGE_WEAPONS_MORE = "weapons_more"
PAGE_ABILITIES = "abilities"
PAGE_PILOT = "pilot"
DETAIL_TAB_PAGES = ("stats0", PAGE_WEAPONS, PAGE_ABILITIES)

# 面板等待一律壁鐘：attempts×sleep 的計數窗在串流取幀下會塌縮成幾十毫秒（0808 實機）。
PANEL_WAIT_S = 6.0
PANEL_POLL_S = 0.3
SHOT_RETRIES = 2
# 列表盡頭的判準：點了格畫面還停在 TROOP_INFO 這麼多輪＝那一格是空的（敵軍末列不滿格）。
LIST_END_POLLS = 2

# 由內而外的關閉層序。認得出畫面就照畫面挑關閉鈕，認不出來才照層序盲關——三層都
# 走完還沒回到地圖就認賠，繼續亂點只會把面板下面的地圖也點壞。
CLOSE_LAYERS: tuple[Point, ...] = (
    DETAIL_CLOSE_TAP,
    TROOP_INFO_CLOSE_TAP,
    BATTLE_MENU_CLOSE_TAP,
)
CLOSE_TAPS: dict[str, Point] = {
    screens.UNIT_DETAIL: DETAIL_CLOSE_TAP,
    screens.TROOP_INFO: TROOP_INFO_CLOSE_TAP,
    screens.BATTLE_MENU: BATTLE_MENU_CLOSE_TAP,
}


def rows_of(faction: str) -> int:
    return ALLY_ROWS if faction == ALLY else ENEMY_ROWS


def row_pitch_of(faction: str) -> float:
    return ALLY_ROW_PITCH if faction == ALLY else ENEMY_ROW_PITCH


def cell_taps(faction: str) -> tuple[Point, ...]:
    """名冊順序的逐格點擊位置（列優先，左到右）。

    最後一列不見得滿格，而格數在點開之前看不出來——多出來的點交給呼叫端試點：點不
    出詳情頁就是列表盡頭。
    """
    pitch = row_pitch_of(faction)
    return tuple(
        (
            int(round(CELL_X0 + CELL_X_PITCH * column)),
            int(round(CELL_Y0 + pitch * row)),
        )
        for row in range(rows_of(faction))
        for column in range(CELLS_PER_ROW)
    )


Sentinel = Callable[[np.ndarray, PanelKind], bool]


def _basic_ok(frame: np.ndarray, kind: PanelKind) -> bool:
    view = panels.read_basic_view(frame, kind)
    return view is not None and view.max_hp is not None


def _stats_ok(frame: np.ndarray, kind: PanelKind) -> bool:
    column = panels.read_stat_column(frame, kind)
    return column is not None and column.max_hp.value is not None


def _weapons_ok(frame: np.ndarray, kind: PanelKind) -> bool:
    return bool(panels.read_weapon_rows(frame, kind))


def _abilities_ok(frame: np.ndarray, kind: PanelKind) -> bool:
    column = panels.read_stat_column(frame, kind)
    return column is not None and len(column.unread) < len(column.slots())


def _pilot_ok(frame: np.ndarray, kind: PanelKind) -> bool:
    return kind is PanelKind.ROSTER_PILOT


DETAIL_TAB_SENTINELS: tuple[Sentinel, ...] = (_stats_ok, _weapons_ok, _abilities_ok)
DETAIL_TAB_KINDS: tuple[tuple[PanelKind, ...], ...] = (
    (PanelKind.STAGE_COMBO, PanelKind.ROSTER_UNIT_INFO),
    panels.WEAPON_KINDS,
    panels.ABILITY_KINDS,
)


@dataclass(frozen=True)
class CaptureShot:
    faction: str
    index: int
    page: str
    panel_kind: str | None
    frame: str | None
    ok: bool
    reason: str | None = None


@dataclass
class RosterCapture:
    """一輪名冊採集。依賴全注入，離線可全程打樁。"""

    grab: Callable[[], np.ndarray]
    keep: Callable[[str], str | None]
    tap: Callable[..., None]
    journal: Any
    swipe: Callable[..., None] | None = None
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    screen_of: Callable[[np.ndarray], str] = screens.classify
    panel_of: Callable[[np.ndarray], PanelKind] = panels.classify
    closed: bool = field(default=False, init=False)

    def run(self) -> list[CaptureShot]:
        shots: list[CaptureShot] = []
        try:
            self._record_gaps()
            if self.open_troop_info():
                for faction in FACTIONS:
                    self._capture_faction(faction, shots)
        except Exception as error:
            self.journal.record(
                "roster_stage_failed", error=f"{type(error).__name__}: {error}", shots=len(shots)
            )
        finally:
            self.close_to_map()
            self.journal.record(
                "roster_capture_summary",
                shots=len(shots),
                ok=sum(1 for shot in shots if shot.ok),
                failed=sum(1 for shot in shots if not shot.ok),
            )
        return shots

    def open_troop_info(self) -> bool:
        self.tap(*BATTLE_MENU_TAP)
        if not self._await_screen(screens.BATTLE_MENU):
            self.journal.record("roster_open_failed", stage="battle_menu")
            return False
        self.tap(*BATTLE_MENU_TROOP_INFO_TAP)
        if not self._await_screen(screens.TROOP_INFO):
            self.journal.record("roster_open_failed", stage="troop_info")
            return False
        return True

    def select_tab(self, faction: str) -> bool:
        self.tap(*TAB_TAPS[faction])
        landed = self._await_screen(screens.TROOP_INFO)
        self.journal.record("roster_tab", faction=faction, ok=landed)
        return landed

    def capture_unit(self, faction: str, index: int) -> list[CaptureShot]:
        """一格單位的所有頁。回空 list ＝詳情打不開＝列表盡頭。"""
        if not self.open_detail(faction, index):
            return []
        shots: list[CaptureShot] = []
        if BASIC_VIEW_TAP is not None:
            self.tap(*BASIC_VIEW_TAP)
        shots.append(self._shot(faction, index, PAGE_BASIC, panels.BASIC_KINDS, _basic_ok))
        for tab, page in enumerate(DETAIL_TAB_PAGES):
            self.tap(*DETAIL_TAB_TAPS[tab])
            shots.append(
                self._shot(faction, index, page, DETAIL_TAB_KINDS[tab], DETAIL_TAB_SENTINELS[tab])
            )
            if page == PAGE_WEAPONS and WEAPON_SCROLL is not None and self.swipe is not None:
                (x1, y1), (x2, y2), duration = WEAPON_SCROLL
                self.swipe(x1, y1, x2, y2, duration)
                shots.append(
                    self._shot(
                        faction, index, PAGE_WEAPONS_MORE, panels.WEAPON_KINDS, _weapons_ok
                    )
                )
        self.tap(*DETAIL_CLOSE_TAP)
        self._await_screen(screens.TROOP_INFO)
        shots.extend(self._capture_pilot(faction, index))
        return shots

    def open_detail(self, faction: str, index: int) -> bool:
        """點開一格的詳情。

        點之前必須確認畫面真的是部隊資訊：名冊格 (1564,267)/(1843,267)/(729,847)
        與設定頁 AUTO戰鬥 三選一、戰鬥選單的放棄鈕同座標，面板沒開的時候同一下打
        中的是那些東西（所以裝置層也只放行帶 roster_cell intent 的點）。
        """
        if self.screen_of(self.grab()) != screens.TROOP_INFO:
            self.journal.record("roster_cell_blocked", faction=faction, index=index)
            return False
        self.tap(*cell_taps(faction)[index], intent=ROSTER_CELL_INTENT)
        deadline = self.clock() + PANEL_WAIT_S
        stale = 0
        while True:
            frame = self.grab()
            name = self.screen_of(frame)
            if self.panel_of(frame) is not PanelKind.UNKNOWN or name == screens.UNIT_DETAIL:
                return True
            if name == screens.TROOP_INFO:
                stale += 1
                if stale >= LIST_END_POLLS:
                    self.journal.record("roster_list_edge", faction=faction, index=index)
                    return False
            if self.clock() >= deadline:
                return False
            self.sleep(PANEL_POLL_S)

    def close_to_map(self) -> bool:
        """詳情→部隊資訊→戰鬥選單逐層關回地圖。

        每層先看畫面：已經在地圖上就不再點——地圖裸露時這些關閉座標打中的是格子。
        """
        self.closed = True
        for fallback in CLOSE_LAYERS:
            frame = self.grab()
            name = self.screen_of(frame)
            if name in screens.MAP_SCREENS:
                self.journal.record("roster_closed", screen=name)
                return True
            if self.panel_of(frame) is not PanelKind.UNKNOWN:
                point = DETAIL_CLOSE_TAP
            else:
                point = CLOSE_TAPS.get(name, fallback)
            self.tap(*point)
            self._await(lambda frame, was=name: self.screen_of(frame) != was)
        name = self.screen_of(self.grab())
        landed = name in screens.MAP_SCREENS
        self.journal.record("roster_closed", screen=name, ok=landed)
        return landed

    def _capture_faction(self, faction: str, shots: list[CaptureShot]) -> None:
        """收進呼叫端的 list 而不是自己回傳一份：中途爆掉時已經拍到的那幾台要留得住。"""
        if not self.select_tab(faction):
            self.journal.record("roster_list_end", faction=faction, count=0)
            return
        count = 0
        for index in range(len(cell_taps(faction))):
            got = self.capture_unit(faction, index)
            if not got:
                break
            shots.extend(got)
            count += 1
        self.journal.record("roster_list_end", faction=faction, count=count)

    def _capture_pilot(self, faction: str, index: int) -> list[CaptureShot]:
        if PILOT_HALF_OFFSET is None:
            return []
        x, y = cell_taps(faction)[index]
        self.tap(x + PILOT_HALF_OFFSET[0], y + PILOT_HALF_OFFSET[1], intent=ROSTER_CELL_INTENT)
        shot = self._shot(faction, index, PAGE_PILOT, (PanelKind.ROSTER_PILOT,), _pilot_ok)
        self.tap(*DETAIL_CLOSE_TAP)
        self._await_screen(screens.TROOP_INFO)
        return [shot]

    def _shot(
        self,
        faction: str,
        index: int,
        page: str,
        expect_kinds: Sequence[PanelKind],
        sentinel: Sentinel,
    ) -> CaptureShot:
        """收斂→驗面板→過哨兵→存幀。

        哨兵是為了擋淡入的半透明幀：那種幀的標題已經比得中，讀值卻整片是空的，而
        存下去之後離線解析沒有第二次機會。所以哨兵敗了就重拍，最多 SHOT_RETRIES 次。
        """
        kind = PanelKind.UNKNOWN
        reason: str | None = None
        for attempt in range(SHOT_RETRIES + 1):
            frame = self._settled()
            kind = self.panel_of(frame)
            if kind not in expect_kinds:
                reason = f"panel={kind}"
            elif not sentinel(frame, kind):
                reason = "sentinel"
            else:
                reason = None
                break
            if attempt < SHOT_RETRIES:
                self.sleep(PANEL_POLL_S)
        path = self.keep(f"roster:{faction}:{index}:{page}")
        shot = CaptureShot(
            faction=faction,
            index=index,
            page=page,
            panel_kind=str(kind),
            frame=path,
            ok=reason is None,
            reason=reason,
        )
        self.journal.record(
            "roster_capture",
            faction=shot.faction,
            index=shot.index,
            page=shot.page,
            panel_kind=shot.panel_kind,
            frame=shot.frame,
            ok=shot.ok,
            reason=shot.reason,
        )
        return shot

    def _record_gaps(self) -> None:
        missing = [
            name
            for name, value in (
                ("BASIC_VIEW_TAP", BASIC_VIEW_TAP),
                ("PILOT_HALF_OFFSET", PILOT_HALF_OFFSET),
                ("WEAPON_SCROLL", WEAPON_SCROLL),
            )
            if value is None
        ]
        if missing:
            self.journal.record("roster_capture_gap", constants=missing, reason="uncalibrated")

    def _settled(self) -> np.ndarray:
        return settle.await_still(
            self.grab,
            clock=self.clock,
            sleep=self.sleep,
            deadline=self.clock() + settle.SETTLE_WAIT_S,
            poll=settle.SETTLE_POLL_S,
        )

    def _await_screen(self, name: str) -> bool:
        return self._await(lambda frame: self.screen_of(frame) == name)

    def _await(self, ok: Callable[[np.ndarray], bool]) -> bool:
        deadline = self.clock() + PANEL_WAIT_S
        while True:
            if ok(self.grab()):
                return True
            if self.clock() >= deadline:
                return False
            self.sleep(PANEL_POLL_S)
