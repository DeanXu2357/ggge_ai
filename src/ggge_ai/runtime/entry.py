"""程式版進戰鬥檢查閘門：AUTO=OFF、顯示方格=ON、入圖複核。

三步都是硬閘門，而且都必須**主動確認**——開關狀態沿用上次設定，「不去碰它」
不是安全策略（0730 踩雷：指示寫「不碰」結果放行了一整場自動戰鬥）。

流程一律是「操作 → 純辨識確認」交錯：操作步驟點按鈕，確認步驟只讀傳進來的那
張幀（screens 的 read_*），所以每個確認點都能拿 fixture 離線重演。

AUTO 開關的判定規則寫在 screens.read_auto_switch：暗＝OFF，**勿點**。點錯方向
不是「沒生效」而是親手打開自動戰鬥，所以開關座標另外被裝置層的危險帶擋著，
只有帶 intent="auto_switch" 的點擊進得去。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from . import board, screens, settle

log = logging.getLogger(__name__)

Capture = Callable[[], np.ndarray]


class Tapper(Protocol):
    def __call__(self, x: int, y: int, *, intent: str = "") -> None: ...


# 關卡資訊／條件頁的「TAP TO NEXT」推進點。畫面上大片都可推進，選一個離所有
# 已知按鈕最遠的中下位置；**待實機確認此點無其他元件**。
STAGE_INFO_ADVANCE_TAP = (1170, 780)
# 關卡列表右欄的「出擊準備」鈕（模板 elements/btn_sortie_prep.png 的匹配中心）。
# 鈕的下半壓在 y≈895-955 的危險帶裡（同一帶在應戰 stance 選單上是行動選擇確認
# 鈕），所以這個點刻意落在帶的上緣之上。
STAGE_LIST_PREP_TAP = (2035, 880)
SORTIE_TAP = (1930, 970)
AUTO_DEPLOY_CANCEL_TAP = (971, 1009)
BATTLE_MENU_TAP = (2170, 52)
BATTLE_MENU_SETTINGS_TAP = (1604, 865)
BATTLE_MENU_CLOSE_TAP = (1172, 992)
BATTLE_MENU_ABANDON_TAP = (410, 860)
ABANDON_CONFIRM_TAP = (1400, 865)
SETTINGS_BATTLE_TAB_TAP = (1613, 173)
SETTINGS_CLOSE_TAP = (1180, 992)


#「skipped」＝這一關不需要走（例如已經被推進到下一頁），不是失敗。
#「advisory」＝只留紀錄的觀察值，永遠不裁定（見 set_battle_grid）。
ACCEPTED_OUTCOMES = ("ok", "skipped", "advisory")
ADVISORY = "advisory"


@dataclass(frozen=True)
class Step:
    gate: str
    outcome: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.outcome in ACCEPTED_OUTCOMES


@dataclass
class GateReport:
    steps: list[Step] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.steps) and all(step.ok for step in self.steps)

    @property
    def failures(self) -> tuple[Step, ...]:
        return tuple(step for step in self.steps if not step.ok)

    @property
    def trail(self) -> tuple[str, ...]:
        return tuple(f"{step.gate}:{step.outcome}" for step in self.steps)

    def add(self, gate: str, outcome: str, detail: str = "") -> Step:
        step = Step(gate, outcome, detail)
        self.steps.append(step)
        log.info("gate %s -> %s %s", gate, outcome, detail)
        return step


def expect_screen(
    capture: Capture,
    wanted: tuple[str, ...],
    *,
    attempts: int = 6,
    sleep: Callable[[float], None] = time.sleep,
    settle_s: float = 1.0,
    min_wait_s: float | None = None,
    now: Callable[[], float] = time.monotonic,
) -> tuple[str, np.ndarray | None]:
    """重截到畫面是 wanted 之一，或放棄。回傳（畫面名, 幀）。

    每次操作前都要重新確認所在頁：解鎖用的 wake-tap 可能誤觸 TAP TO NEXT 直接
    把人推進下一頁（0730 實測發生一次），拿舊畫面推論就會對著錯的頁點下去。

    attempts 的時間窗是隱含的：它靠 adb 截圖每張 ~2.4s 撐起來（10 輪 ≈ 34s）。
    串流幀源取幀只要 11ms，同樣輪次會塌縮到 ~10s，0808 實機因此在 19.1s 就耗盡
    重試 Halt（出擊→關卡資訊頁的開場運鏡要 ~15s）。凡是「等遊戲轉場」的呼叫點
    都必須用 min_wait_s 給壁鐘下限，不能只靠輪次。
    """
    frame = None
    screen = screens.UNKNOWN
    started = now()
    index = 0
    while True:
        frame = capture()
        screen = screens.classify(frame)
        if screen in wanted:
            return screen, frame
        index += 1
        if index >= attempts and (min_wait_s is None or now() - started >= min_wait_s):
            return screen, frame
        sleep(settle_s)


def confirm_auto_off(
    capture: Capture,
    tap: Tapper,
    report: GateReport,
    *,
    attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> Step:
    """AUTO 必須讀到 OFF 才過。讀不到開關＝不確認＝閘門不放行（不猜）。"""
    state = None
    for _ in range(attempts):
        state = screens.read_auto_switch(capture())
        if state == screens.AUTO_OFF:
            return report.add("auto_off", "ok")
        if state is None:
            sleep(1.0)
            continue
        tap(*screens.AUTO_SWITCH_TAP, intent="auto_switch")
        sleep(1.2)
    if state is None:
        return report.add("auto_off", "unreadable", "AUTO switch not on screen")
    return report.add("auto_off", "stuck", f"AUTO still {state}")


GRID_PROBE_ALREADY = "already"
GRID_PROBE_TAPPED = "tapped"
GRID_PROBE_UNREADABLE = "unreadable"
GRID_PROBE_GUARDED = "guarded"
GRID_PROBE_AUTO_DRIFT = "auto_drift"


@dataclass(frozen=True)
class GridProbe:
    """設定頁滑塊的讀值——**advisory，不裁定任何事**。

    0730 兩輪都讀成未驗證，而地圖上的格線像素複驗皆過（疑截圖早於 UI 動畫）。
    滑塊是遠端狀態的間接證據，格線是地面真相，所以這裡只回報看到什麼；
    要不要重來由 confirm_grid 讀地圖決定。
    """

    wanted: str
    outcome: str
    before: str | None = None
    after: str | None = None

    @property
    def detail(self) -> str:
        return f"want={self.wanted} {self.outcome} before={self.before} after={self.after}"


def set_battle_grid(
    capture: Capture,
    tap: Tapper,
    desired_on: bool,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> GridProbe:
    """從戰鬥選單把顯示方格翻到 desired_on，最後把選單關回去。

    動作守衛照舊硬性：讀不到「戰鬥分頁選著」＋「AUTO戰鬥 停在 OFF」（紅線）就
    一個開關都不碰，直接從關閉鈕撤退。回傳的 GridProbe 只是紀錄。
    """
    want = "on" if desired_on else "off"

    def close() -> None:
        tap(*SETTINGS_CLOSE_TAP)
        sleep(1.2)
        tap(*BATTLE_MENU_CLOSE_TAP)
        sleep(1.2)

    tap(*BATTLE_MENU_TAP)
    sleep(1.5)
    tap(*BATTLE_MENU_SETTINGS_TAP)
    sleep(1.8)
    tap(*SETTINGS_BATTLE_TAB_TAP)
    sleep(1.2)
    frame = capture()

    before = after = None
    outcome = GRID_PROBE_GUARDED
    if screens.is_battle_tab_selected(frame) and screens.is_auto_battle_off(frame):
        before = screens.read_grid_setting(frame)
        if before == want:
            outcome, after = GRID_PROBE_ALREADY, before
        elif before is None:
            outcome = GRID_PROBE_UNREADABLE
        else:
            tap(*screens.GRID_TOGGLE_TAP)
            sleep(1.0)
            frame = capture()
            after = screens.read_grid_setting(frame)
            outcome = GRID_PROBE_TAPPED
            if not screens.is_auto_battle_off(frame):
                # 我們沒碰那一列（滑塊在 y591，三選一在 y245-345），但真的漂了就
                # 得看得見——AUTO 的硬閘門在 confirm_auto_off／confirm_in_map。
                log.error("AUTO battle row left OFF while toggling the grid")
                outcome = GRID_PROBE_AUTO_DRIFT
    close()
    probe = GridProbe(wanted=want, outcome=outcome, before=before, after=after)
    log.info("grid setting probe (advisory): %s", probe.detail)
    return probe


def confirm_grid(
    capture: Capture,
    tap: Tapper,
    report: GateReport,
    *,
    desired_on: bool = True,
    attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> Step:
    """顯示方格的**唯一判準**是地圖本身讀不讀得出格網——不是設定頁的滑塊。

    讀得出格網同時也證明我們已經回到地圖上（選單沒被留著開）。設定頁探針的結果
    只當 advisory 進報告（0730 兩輪未驗證但地圖複驗皆過），不裁定也不擋流程。
    """
    for _ in range(attempts):
        frame = capture()
        if (board.read_lattice(frame) is not None) == desired_on:
            return report.add("grid", "ok")
        probe = set_battle_grid(capture, tap, desired_on, sleep=sleep)
        report.add("grid_setting", ADVISORY, probe.detail)
    return report.add("grid", "unverified", f"lattice != {desired_on}")


def confirm_in_map(
    capture: Capture,
    tap: Tapper,
    report: GateReport,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> GateReport:
    """入圖複核：人在地圖上、AUTO 仍是 OFF、格網看得見。"""
    screen, frame = expect_screen(capture, screens.MAP_SCREENS, sleep=sleep)
    if frame is None or screen not in screens.MAP_SCREENS:
        report.add("in_map", "not_on_map", screen)
        return report
    report.add("in_map", "ok", screen)
    state = screens.read_auto_switch(frame)
    if state == screens.AUTO_OFF:
        report.add("auto_recheck", "ok")
    else:
        report.add("auto_recheck", "unconfirmed", str(state))
    confirm_grid(capture, tap, report, sleep=sleep)
    return report


DEFAULT_EXPECTED_TITLE = "uc_hard_1"
STAGE_TITLE_ATTEMPTS = 3
STAGE_TITLE_INTERVAL_S = 1.0
# 右欄標題是滑入動畫（實測 ~1s 內到位），位移中的標題模板分數 0.244 對靜止 1.0，
# 讀出來是 None。舊 screencap 每張 ~2.4s 天然跨過動畫窗；串流取幀 11ms 全落在窗內
# （run 20260808-210307/210415 連兩次 stage_title:wrong_stage Halt）。所以每次讀標題
# 之前先等幀差收斂，讀的一律是動畫結束後的那一張。收斂預算按滑入實測取小值，
# screencap 路徑上第一對幀就已經隔了 ~2.4s，等同舊節奏。
STAGE_TITLE_SETTLE_S = 1.5
STAGE_TITLE_POLL_S = 0.25


def _await_stage_title(
    capture: Capture,
    *,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> str | None:
    for index in range(STAGE_TITLE_ATTEMPTS):
        frame = settle.await_still(
            capture,
            clock=now,
            sleep=sleep,
            deadline=now() + STAGE_TITLE_SETTLE_S,
            poll=STAGE_TITLE_POLL_S,
        )
        title = screens.read_stage_title(frame)
        if title is not None:
            return title
        if index + 1 < STAGE_TITLE_ATTEMPTS:
            sleep(STAGE_TITLE_INTERVAL_S)
    return None


def select_stage(
    capture: Capture,
    tap: Tapper,
    *,
    node: tuple[int, int] | None = None,
    expect_title: str | None = DEFAULT_EXPECTED_TITLE,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> GateReport:
    """關卡列表上選一關，並讀右欄標題複驗選中的真的是那一關。不花任何資源。

    node 是**呼叫端給的**：哪一關的節點落在哪個像素是關卡內容（而且隨節點軸捲動
    位置變），不進 runtime。不給就什麼都不點，沿用現在選著的那一關。

    節點座標對不上選中的關卡是實害不是理論風險：0805 第 13 輪 (544,667) 因游標
    飄移實際選中 HARD 2，整輪打錯關。所以點完要讀標題；不合就重點一次，再不合
    就報 wrong_stage 讓呼叫端停手——絕不「先出擊再說」。
    """
    report = GateReport()
    screen, _ = expect_screen(capture, (screens.STAGE_LIST,), sleep=sleep)
    if screen != screens.STAGE_LIST:
        report.add("stage_list", "not_on_page", screen)
        return report
    report.add("stage_list", "ok")
    if node is None:
        return report

    title = None
    for attempt in range(2):
        tap(*node)
        sleep(1.5)
        screen, _ = expect_screen(capture, (screens.STAGE_LIST,), sleep=sleep)
        if screen != screens.STAGE_LIST:
            report.add("stage_node", "left_the_page", screen)
            return report
        if expect_title is None:
            break
        title = _await_stage_title(capture, sleep=sleep, now=now)
        if title == expect_title:
            break
        log.warning("stage title %s != %s (attempt %d)", title, expect_title, attempt + 1)
    if expect_title is not None:
        if title != expect_title:
            report.add("stage_title", "wrong_stage", f"want={expect_title} got={title}")
            return report
        report.add("stage_title", "ok", title)
    report.add("stage_node", "ok", f"{node[0]},{node[1]}")
    return report


def open_sortie_prep(
    capture: Capture,
    tap: Tapper,
    report: GateReport,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> GateReport:
    """關卡列表 →（出擊準備）→ 出擊準備頁。仍然不花任何資源（花的是下一步的出擊）。"""
    screen, _ = expect_screen(capture, (screens.STAGE_LIST,), sleep=sleep)
    if screen != screens.STAGE_LIST:
        report.add("sortie_prep_page", "not_on_list", screen)
        return report
    tap(*STAGE_LIST_PREP_TAP)
    sleep(3.0)
    screen, _ = expect_screen(capture, (screens.SORTIE_PREP,), sleep=sleep, attempts=10)
    if screen != screens.SORTIE_PREP:
        report.add("sortie_prep_page", "not_reached", screen)
        return report
    report.add("sortie_prep_page", "ok")
    return report


DOWNLOAD_WAIT_S = 60.0
DOWNLOAD_POLL_S = 2.0


def clear_download_dialog(
    capture: Capture,
    tap: Tapper,
    report: GateReport,
    *,
    wait_s: float = DOWNLOAD_WAIT_S,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> Step | None:
    """出擊後可能跳出的「下載關卡資料」彈窗：按下載、等它自己消失。

    彈窗不在場就整個跳過（回 None），一下都不點——(1372,848) 在出擊準備頁上是別的
    東西。呼叫順序上這一步永遠排在選關標題複驗之後：確認打的是目標關卡，才有資格
    替它下載資料。
    """
    if not screens.is_download_dialog(capture()):
        return None
    tap(*screens.DOWNLOAD_CONFIRM_TAP)
    deadline = now() + wait_s
    while now() < deadline:
        sleep(DOWNLOAD_POLL_S)
        if not screens.is_download_dialog(capture()):
            return report.add("download", "ok")
    return report.add("download", "stuck", f"dialog still up after {wait_s:.0f}s")


def sortie(
    capture: Capture,
    tap: Tapper,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> GateReport:
    """出擊準備 →（出擊）→ 關卡資訊 → AUTO 硬閘門。**這一步起花 EN 與挑戰次數。**

    同一列的左邊還有「自動編制」(1496,1010)，誤點會覆蓋排好的編成；那一帶由裝置層
    的 auto_deploy 危險帶絕對拒點（無 intent 可放行），這裡只管按出擊那一顆。
    """
    report = GateReport()
    screen, _ = expect_screen(capture, (screens.SORTIE_PREP,), sleep=sleep)
    if screen != screens.SORTIE_PREP:
        report.add("sortie_prep", "not_on_page", screen)
        return report
    report.add("sortie_prep", "ok")
    tap(*SORTIE_TAP)
    sleep(3.0)

    clear_download_dialog(capture, tap, report, sleep=sleep)
    screen, _ = expect_screen(
        capture,
        (screens.STAGE_INFO, *screens.MAP_SCREENS),
        sleep=sleep,
        attempts=10,
        min_wait_s=30.0,
    )
    if screen == screens.STAGE_INFO:
        report.add("stage_info", "ok")
        confirm_auto_off(capture, tap, report, sleep=sleep)
    elif screen in screens.MAP_SCREENS:
        # TAP TO NEXT 被解鎖 wake-tap 誤觸過一次（0730）：已經進圖就不再點推進，
        # 直接進入入圖複核——AUTO 的確認在那裡照樣做。
        report.add("stage_info", "skipped", "already advanced to the map")
    else:
        report.add("stage_info", "not_on_page", screen)
    return report


def advance_to_map(
    capture: Capture,
    tap: Tapper,
    report: GateReport,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> GateReport:
    """關卡資訊 →（TAP TO NEXT）→ 地圖 → 入圖複核。

    推進前重新確認所在頁：解鎖 wake-tap 誤觸 TAP TO NEXT（0730 實測）之後人已經在
    地圖上，再點一下就是對著地圖亂點。
    """
    screen, _ = expect_screen(
        capture,
        (screens.STAGE_INFO, *screens.MAP_SCREENS),
        sleep=sleep,
        attempts=10,
        min_wait_s=30.0,
    )
    if screen == screens.STAGE_INFO:
        tap(*STAGE_INFO_ADVANCE_TAP)
        sleep(2.0)
    elif screen not in screens.MAP_SCREENS:
        report.add("advance", "not_on_page", screen)
        return report
    return confirm_in_map(capture, tap, report, sleep=sleep)


def enter_stage(
    capture: Capture,
    tap: Tapper,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> GateReport:
    """出擊準備 →（出擊）→ 關卡資訊 →（TAP TO NEXT）→ 地圖，逐步硬閘門。"""
    report = sortie(capture, tap, sleep=sleep)
    if not report.ok:
        return report
    return advance_to_map(capture, tap, report, sleep=sleep)


ABANDON_DIALOG_ATTEMPTS = 4
ABANDON_DIALOG_INTERVAL_S = 1.0
ABANDON_SETTLE_ATTEMPTS = 8
ABANDON_SETTLE_INTERVAL_S = 2.0


MAIN_STAGE_TAP = (1030, 800)
SERIES_FOCUSED_TAP = (1230, 590)
SERIES_SELECT_TAP = (1990, 890)
NAV_SETTLE_ATTEMPTS = 5
NAV_SETTLE_INTERVAL_S = 1.5


def _back_to_stage_list(
    capture: Capture,
    tap: Tapper,
    *,
    sleep: Callable[[float], None] = time.sleep,
    on_tap: Callable[[str, tuple[int, int]], None] | None = None,
) -> str:
    """關卡模式選擇頁 → 關卡列表：MAIN STAGE → 系列選擇 → 系列詳情的選擇。

    每一下都要先確認人在該站的畫面才點——這條路固定走「置中的那個系列」，前提是
    進場前就在那個系列的列表；前提破了就停在原地讓呼叫端報 unconfirmed，不瞎點。
    """
    chain = (
        ("main_stage", MAIN_STAGE_TAP, screens.SERIES_SELECT),
        ("series", SERIES_FOCUSED_TAP, screens.SERIES_CONFIRM),
        ("series_select", SERIES_SELECT_TAP, screens.STAGE_LIST),
    )
    screen = screens.STAGE_TYPE_SELECT
    for label, point, wanted in chain:
        if on_tap is not None:
            on_tap(label, point)
        tap(*point)
        sleep(NAV_SETTLE_INTERVAL_S)
        screen, _ = expect_screen(
            capture,
            (wanted,),
            attempts=NAV_SETTLE_ATTEMPTS,
            sleep=sleep,
            settle_s=NAV_SETTLE_INTERVAL_S,
        )
        if screen != wanted:
            return screen
    return screen


def _await_abandon_dialog(
    capture: Capture,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    for index in range(ABANDON_DIALOG_ATTEMPTS):
        if screens.is_abandon_confirm_dialog(capture()):
            return True
        if index + 1 < ABANDON_DIALOG_ATTEMPTS:
            sleep(ABANDON_DIALOG_INTERVAL_S)
    return False


ABANDON_LANDINGS = (screens.STAGE_LIST, screens.STAGE_TYPE_SELECT)


def _leave_battle(
    capture: Capture,
    tap: Tapper,
    report: GateReport,
    screen: str,
    attempt: int,
    *,
    sleep: Callable[[float], None] = time.sleep,
    on_tap: Callable[[str, tuple[int, int]], None] | None = None,
) -> bool:
    """已經離開戰鬥了嗎——關卡模式選擇頁也算數（0805 兩輪實證的合法落點）。

    導不回關卡列表就回 False 讓呼叫端停手：棄戰本身成功了，人只是停在回程半路，
    而戰鬥選單那組座標在這些頁上是別的東西，重跑棄戰鏈只會亂點。
    """
    if screen == screens.STAGE_TYPE_SELECT:
        report.add("abandon", ADVISORY, "landed_on_stage_type_select")
        screen = _back_to_stage_list(capture, tap, sleep=sleep, on_tap=on_tap)
    if screen == screens.STAGE_LIST:
        report.add("abandon", "ok", f"attempt={attempt + 1}")
        return True
    return False


def abandon_battle(
    capture: Capture,
    tap: Tapper,
    *,
    attempts: int = 2,
    sleep: Callable[[float], None] = time.sleep,
    on_tap: Callable[[str, tuple[int, int]], None] | None = None,
) -> GateReport:
    """棄戰：☰ → 放棄 → 確認 → **看到關卡列表才算數**。棄戰不耗 AP／挑戰次數／EN
    （0730 實證）。

    確認鈕 (1400,865) 與戰鬥選單下排的「幫助」(1327,865) 同列、水平相距 73px，而
    「幫助」的鈕格橫跨 1189-1466（同列鈕距 277-283 量出來的）——**確認彈窗沒出來
    的時候，這一下就是打在「幫助」上**。所以確認那一下前面擋一道彈窗探針，彈窗不
    在場就完全不點，直接關面板回頭重走選單那一下；(1400,865) 從此只在彈窗在場時
    按得下去。

    收尾驗收要輪詢：0804 那輪最後一下之後 3.3 秒就判畫面，轉場中讀成 unknown 而
    誤報失敗（事後探針 stage_list 0.992，裝置其實早就回關卡列表了）。

    落點不保證是關卡列表：0805 兩輪都落在關卡模式選擇頁，由 `_back_to_stage_list`
    導航回來。
    """
    report = GateReport()
    screen, _ = expect_screen(capture, screens.MAP_SCREENS, sleep=sleep)
    if screen not in screens.MAP_SCREENS:
        report.add("abandon", "not_on_map", screen)
        return report
    for attempt in range(attempts):
        for label, point, intent in (
            ("menu", BATTLE_MENU_TAP, ""),
            ("abandon", BATTLE_MENU_ABANDON_TAP, "abandon"),
        ):
            if on_tap is not None:
                on_tap(label, point)
            tap(*point, intent=intent)
            sleep(1.5)
        if _await_abandon_dialog(capture, sleep=sleep):
            if on_tap is not None:
                on_tap("confirm", ABANDON_CONFIRM_TAP)
            tap(*ABANDON_CONFIRM_TAP)
            sleep(3.0)
            screen, _ = expect_screen(
                capture,
                ABANDON_LANDINGS,
                attempts=ABANDON_SETTLE_ATTEMPTS,
                sleep=sleep,
                settle_s=ABANDON_SETTLE_INTERVAL_S,
            )
            if screen in ABANDON_LANDINGS:
                if _leave_battle(capture, tap, report, screen, attempt, sleep=sleep, on_tap=on_tap):
                    return report
                break
        else:
            report.add("abandon", ADVISORY, f"no_dialog attempt={attempt + 1}")
        # 鏈沒走完就卡住了：手上停著的可能是戰鬥選單、也可能是誤點開的幫助頁，
        # 兩者的關閉鈕同位。關掉再從頭來，不要對著未知畫面繼續往下點。
        if on_tap is not None:
            on_tap("close", BATTLE_MENU_CLOSE_TAP)
        tap(*BATTLE_MENU_CLOSE_TAP)
        sleep(1.5)
        # 關完還在地圖上才敢重跑：人已經被帶去別的畫面時，整條鏈的座標全部失去
        # 意義，繼續點只會把污染擴大。這裡也可能讀到棄戰其實已經成功——確認之後
        # 的落幀輪詢撞上轉場就會走到這裡（0806 run 20260806-042858 四次全是這條
        # 路徑，每次收尾都讀到 stage_type_select 卻報 unconfirmed）。
        screen, _ = expect_screen(
            capture, (*screens.MAP_SCREENS, *ABANDON_LANDINGS), attempts=2, sleep=sleep
        )
        if screen in ABANDON_LANDINGS:
            if _leave_battle(capture, tap, report, screen, attempt, sleep=sleep, on_tap=on_tap):
                return report
            break
        if screen not in screens.MAP_SCREENS:
            break
    report.add("abandon", "unconfirmed", screen)
    return report
