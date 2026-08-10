"""名冊採集：戰鬥選單「部隊資訊」逐格點開詳情，把每一頁存成幀。

這一層只走位與存幀，不解析數值——把幀讀成數字是離線的事（panels／panel_text）。
所以「拍到的是不是那一頁」比「拍了幾張」重要：每一拍先等幀差收斂、再驗面板種類、
再過一道哨兵讀值，三道都過才算數。

採集是加值步驟：`run()` 頂層吞掉所有例外。後面還有棄戰鏈要走，名冊沒拿到下一輪
再拿，卡在半開的面板上卻會讓整輪報廢。

座標分兩級：`BATTLE_MENU_TROOP_INFO_TAP` 以下到 `cell_taps` 為止是 0806 實幀量測
過的；`DETAIL_TAB_TAPS`／`BASIC_VIEW_TAP`／`WEAPON_SCROLL` 是 0810 在 UC HARD 1
戰場內逐點實機標定的。
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

# 詳情頁三個分頁的切換點，由 panels.TAB_BANDS 的帶心推得，0810 實機逐點驗過：
# (985,173)／(1415,173)／(1835,173) 切出的分頁 panels.classify 全數命中。
DETAIL_TAB_TAPS: tuple[Point, ...] = tuple(
    (x + w // 2, y + h // 2) for x, y, w, h in panels.TAB_BANDS
)

# 右上角的視圖切換鈕：基本資訊視圖顯示「詳情」、詳情視圖顯示「基本資訊」，同一點來回切。
BASIC_VIEW_TAP: Point = (1936, 96)
# 武裝分頁往下捲（武裝卡下面接技能區塊）。0.8s 是坑：0.4s 快滑帶慣性會整張武裝卡
# 掠過去，第 4 把武裝的數值列落在首幀與捲後幀之間都拍不到；0.8s 慢滑實測完整入幀。
WEAPON_SCROLL: tuple[Point, Point, float] = ((1400, 700), (1400, 400), 0.8)

PAGE_BASIC = "basic"
PAGE_WEAPONS = "weapons"
PAGE_WEAPONS_MORE = "weapons_more"
PAGE_ABILITIES = "abilities"
DETAIL_TAB_PAGES = ("stats0", PAGE_WEAPONS, PAGE_ABILITIES)

# 面板等待一律壁鐘：attempts×sleep 的計數窗在串流取幀下會塌縮成幾十毫秒（0808 實機）。
PANEL_WAIT_S = 6.0
PANEL_POLL_S = 0.3
SHOT_RETRIES = 2
# 哨兵重拍的間隔要另計：詳情左欄有加成的欄位會輪替顯示絕對值與藍字 +delta，週期約
# 兩秒（0810 實機），而 read_stat_column 讀到 delta 會標旗拒收。用 PANEL_POLL_S 的
# 0.3s 重拍等於連拍同一個相位，跨得過半個輪替才有機會拍到絕對值那一相。
SHOT_RETRY_SLEEP_S = 1.2
# 開詳情動畫實測 2.5-3s：點格後畫面停在 TROOP_INFO 這段時間才轉出詳情，留足餘裕取
# 3.5s。這是坑——判列表盡頭不能用輪數（串流下 0.3s×N 的計數窗會塌縮），只能熬滿這段
# 壁鐘：正常格 ~2.5s 就開出詳情提前收工，唯有末列空格（點下去畫面永不變）才吃滿。
DETAIL_OPEN_WAIT_S = 3.5

# 逐層關閉的座標圖。認得出畫面就照畫面挑關閉鈕；認不出來（可能在開啟動畫中）先等一
# 小段再重判，不盲點——地圖裸露時這些關閉座標打中的是格子。
CLOSE_TAPS: dict[str, Point] = {
    screens.UNIT_DETAIL: DETAIL_CLOSE_TAP,
    screens.TROOP_INFO: TROOP_INFO_CLOSE_TAP,
    screens.BATTLE_MENU: BATTLE_MENU_CLOSE_TAP,
}
# 詳情→部隊資訊→戰鬥選單→地圖最多三關；多給兩步容錯開啟動畫的殘留起點。
CLOSE_MAX_STEPS = 5


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
                ally_ok=sum(1 for shot in shots if shot.faction == ALLY and shot.ok),
                ally_failed=sum(1 for shot in shots if shot.faction == ALLY and not shot.ok),
                enemy_ok=sum(1 for shot in shots if shot.faction == ENEMY and shot.ok),
                enemy_failed=sum(1 for shot in shots if shot.faction == ENEMY and not shot.ok),
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
        screen_before = self.screen_of(self.grab())
        frame_before = self.keep(f"roster:tab:{faction}:before")
        t0 = self.clock()
        self.tap(*TAB_TAPS[faction])
        landed = self._await_screen(screens.TROOP_INFO)
        elapsed = round(self.clock() - t0, 3)
        screen_after = self.screen_of(self.grab())
        frame_after = self.keep(f"roster:tab:{faction}:after")
        self.journal.record(
            "roster_tab",
            faction=faction,
            ok=landed,
            elapsed_s=elapsed,
            screen_before=screen_before,
            screen_after=screen_after,
            frame_before=frame_before,
            frame_after=frame_after,
        )
        return landed

    def capture_unit(self, faction: str, index: int) -> list[CaptureShot]:
        """一格單位的所有頁。回空 list ＝詳情打不開＝列表盡頭。

        視圖是全域記憶（0810 實機）：詳情面板記住上一次看的是基本資訊還是詳情、詳情
        又停在哪個分頁，而且跨單位跨陣營共享。所以開場落在哪一頁不能假設——先讀一張
        判當前視圖，落在詳情就先切回基本資訊，拍完再切回詳情走分頁。
        """
        if not self.open_detail(faction, index):
            return []
        shots: list[CaptureShot] = []
        landing_kind = self.panel_of(self.grab())
        basic_view_tapped = landing_kind not in panels.BASIC_KINDS
        if basic_view_tapped:
            self.tap(*BASIC_VIEW_TAP)
        shots.append(self._shot(faction, index, PAGE_BASIC, panels.BASIC_KINDS, _basic_ok))
        t_toggle = self.clock()
        self.tap(*BASIC_VIEW_TAP)
        for tab, page in enumerate(DETAIL_TAB_PAGES):
            gap = self.clock() - t_toggle if tab == 0 else None
            self.tap(*DETAIL_TAB_TAPS[tab])
            if gap is not None:
                self.journal.record(
                    "roster_view_state",
                    faction=faction,
                    index=index,
                    landing_panel=str(landing_kind),
                    basic_view_tapped=basic_view_tapped,
                    toggle_tab0_gap_s=round(gap, 3),
                )
            shots.append(
                self._shot(faction, index, page, DETAIL_TAB_KINDS[tab], DETAIL_TAB_SENTINELS[tab])
            )
            if page == PAGE_WEAPONS and self.swipe is not None:
                (x1, y1), (x2, y2), duration = WEAPON_SCROLL
                self.swipe(x1, y1, x2, y2, duration)
                shots.append(
                    self._shot(
                        faction, index, PAGE_WEAPONS_MORE, panels.WEAPON_KINDS, _weapons_ok
                    )
                )
        self.tap(*DETAIL_CLOSE_TAP)
        self._await_screen(screens.TROOP_INFO)
        return shots

    def open_detail(self, faction: str, index: int) -> bool:
        """點開一格的詳情。

        點之前必須確認畫面真的是部隊資訊：名冊格 (1564,267)/(1843,267)/(729,847)
        與設定頁 AUTO戰鬥 三選一、戰鬥選單的放棄鈕同座標，面板沒開的時候同一下打
        中的是那些東西（所以裝置層也只放行帶 roster_cell intent 的點）。
        """
        landing = self.screen_of(self.grab())
        if landing != screens.TROOP_INFO:
            self.journal.record(
                "roster_cell_blocked",
                faction=faction,
                index=index,
                screen=landing,
                frame=self.keep(f"roster:cell_blocked:{faction}:{index}"),
            )
            return False
        point = cell_taps(faction)[index]
        self.tap(*point, intent=ROSTER_CELL_INTENT)
        start = self.clock()
        detail_deadline = start + DETAIL_OPEN_WAIT_S
        hard_deadline = start + max(PANEL_WAIT_S, DETAIL_OPEN_WAIT_S + PANEL_POLL_S)
        never_left = True
        samples: list[list[Any]] = []
        frame_first: str | None = None
        while True:
            frame = self.grab()
            name = self.screen_of(frame)
            kind = self.panel_of(frame)
            samples.append([round(self.clock() - start, 2), name, str(kind)])
            if len(samples) == 1:
                frame_first = self.keep(f"roster:detail:{faction}:{index}:first")
            if kind is not PanelKind.UNKNOWN or name == screens.UNIT_DETAIL:
                self.journal.record(
                    "roster_open_detail",
                    faction=faction,
                    index=index,
                    tap_point=list(point),
                    elapsed_s=round(self.clock() - start, 2),
                    outcome="opened",
                    never_left=never_left,
                    samples=samples,
                    frame_first=frame_first,
                    frame_last=None,
                )
                return True
            if name != screens.TROOP_INFO:
                never_left = False
            now = self.clock()
            if now >= detail_deadline or now >= hard_deadline:
                elapsed = round(now - start, 2)
                frame_last = self.keep(f"roster:detail:{faction}:{index}:last")
                if never_left:
                    self.journal.record(
                        "roster_list_edge",
                        faction=faction,
                        index=index,
                        elapsed_s=elapsed,
                        frame=frame_last,
                    )
                self.journal.record(
                    "roster_open_detail",
                    faction=faction,
                    index=index,
                    tap_point=list(point),
                    elapsed_s=elapsed,
                    outcome="edge" if never_left else "timeout",
                    never_left=never_left,
                    samples=samples,
                    frame_first=frame_first,
                    frame_last=frame_last,
                )
                return False
            self.sleep(PANEL_POLL_S)

    def close_to_map(self) -> bool:
        """從任一起點逐層關回地圖，不假設起點。

        open_detail 誤判盡頭時那一格的 tap 已經觸發詳情開啟，收尾要能從詳情頁／半開
        詳情／部隊資訊／戰鬥選單任一殘留畫面收回地圖。每步先看畫面：已經在地圖上就
        不再點——地圖裸露時這些關閉座標打中的是格子；認不出畫面（可能在開啟動畫中）
        先等一小段再重判，不盲點。
        """
        self.closed = True
        for _ in range(CLOSE_MAX_STEPS):
            name = self.screen_of(self.grab())
            if name in screens.MAP_SCREENS:
                self.journal.record("roster_closed", screen=name, ok=True)
                return True
            point = CLOSE_TAPS.get(name)
            if point is None:
                self.sleep(PANEL_POLL_S)
                continue
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
        attempts: list[dict[str, Any]] = []
        weapons_page = PanelKind.STAGE_WEAPONS in expect_kinds
        for attempt in range(SHOT_RETRIES + 1):
            settle_start = self.clock()
            frame = self._settled()
            settle_s = round(self.clock() - settle_start, 2)
            kind = self.panel_of(frame)
            sentinel_ok: bool | None = None
            if kind not in expect_kinds:
                reason = f"panel={kind}"
            elif not (sentinel_ok := sentinel(frame, kind)):
                reason = "sentinel"
            else:
                reason = None
            record: dict[str, Any] = {
                "kind": str(kind),
                "settle_s": settle_s,
                "sentinel_ok": sentinel_ok,
            }
            if weapons_page:
                record["header_strips"] = len(panels.header_strips(frame))
            attempts.append(record)
            if reason is None:
                break
            if attempt < SHOT_RETRIES:
                self.keep(f"roster:{faction}:{index}:{page}:a{attempt}")
                self.sleep(SHOT_RETRY_SLEEP_S)
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
            attempts=attempts,
        )
        return shot

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
