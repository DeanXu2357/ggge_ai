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

from . import board, screens

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
ACCEPTED_OUTCOMES = ("ok", "skipped")


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
) -> tuple[str, np.ndarray | None]:
    """重截到畫面是 wanted 之一，或放棄。回傳（畫面名, 幀）。

    每次操作前都要重新確認所在頁：解鎖用的 wake-tap 可能誤觸 TAP TO NEXT 直接
    把人推進下一頁（0730 實測發生一次），拿舊畫面推論就會對著錯的頁點下去。
    """
    frame = None
    screen = screens.UNKNOWN
    for index in range(attempts):
        frame = capture()
        screen = screens.classify(frame)
        if screen in wanted:
            return screen, frame
        if index + 1 < attempts:
            sleep(settle_s)
    return screen, frame


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


def set_battle_grid(
    capture: Capture,
    tap: Tapper,
    desired_on: bool,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """從戰鬥選單把顯示方格開到 desired_on，最後把選單關回去。

    每一步都複驗 AUTO戰鬥 三選一還停在 OFF（紅線），不符就從關閉鈕撤退——這一頁
    上絕不亂翻開關。fail-soft：驗不到就回 False 讓呼叫端無格線照掃。
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

    ok = False
    if screens.is_battle_tab_selected(frame) and screens.is_auto_battle_off(frame):
        state = screens.read_grid_setting(frame)
        if state == want:
            ok = True
        elif state is not None:
            tap(*screens.GRID_TOGGLE_TAP)
            sleep(1.0)
            frame = capture()
            ok = screens.read_grid_setting(frame) == want and screens.is_auto_battle_off(frame)
    if not ok:
        log.warning("battle-grid toggle unverified (wanted %s)", want)
    close()
    return ok


def confirm_grid(
    capture: Capture,
    tap: Tapper,
    report: GateReport,
    *,
    desired_on: bool = True,
    attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> Step:
    """顯示方格的地面真相是地圖本身讀不讀得出格網——不是設定頁的滑塊。

    讀得出格網同時也證明我們已經回到地圖上（選單沒被留著開）。
    """
    for _ in range(attempts):
        frame = capture()
        if (board.read_lattice(frame) is not None) == desired_on:
            return report.add("grid", "ok")
        set_battle_grid(capture, tap, desired_on, sleep=sleep)
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


def select_stage(
    capture: Capture,
    tap: Tapper,
    *,
    node: tuple[int, int] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> GateReport:
    """關卡列表上選一關。不花任何資源。

    node 是**呼叫端給的**：哪一關的節點落在哪個像素是關卡內容（而且隨節點軸捲動
    位置變），不進 runtime。不給就什麼都不點，沿用現在選著的那一關。

    點完只複驗「還在關卡列表」——選中的是哪一關畫面上讀不出來（右欄標題還沒接文字
    讀取），所以呼叫端要自己看落檔的截圖確認。
    """
    report = GateReport()
    screen, _ = expect_screen(capture, (screens.STAGE_LIST,), sleep=sleep)
    if screen != screens.STAGE_LIST:
        report.add("stage_list", "not_on_page", screen)
        return report
    report.add("stage_list", "ok")
    if node is None:
        return report

    tap(*node)
    sleep(1.5)
    screen, _ = expect_screen(capture, (screens.STAGE_LIST,), sleep=sleep)
    if screen != screens.STAGE_LIST:
        report.add("stage_node", "left_the_page", screen)
        return report
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

    screen, _ = expect_screen(
        capture, (screens.STAGE_INFO, *screens.MAP_SCREENS), sleep=sleep, attempts=10
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
        capture, (screens.STAGE_INFO, *screens.MAP_SCREENS), sleep=sleep, attempts=10
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


def abandon_battle(
    capture: Capture,
    tap: Tapper,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> GateReport:
    """棄戰：☰ → 放棄 → 確認。放棄鈕落在危險帶內，只有這條流程帶得動
    intent="abandon"；棄戰不耗 AP／挑戰次數／EN（0730 實證）。"""
    report = GateReport()
    screen, _ = expect_screen(capture, screens.MAP_SCREENS, sleep=sleep)
    if screen not in screens.MAP_SCREENS:
        report.add("abandon", "not_on_map", screen)
        return report
    tap(*BATTLE_MENU_TAP)
    sleep(1.5)
    tap(*BATTLE_MENU_ABANDON_TAP, intent="abandon")
    sleep(1.5)
    tap(*ABANDON_CONFIRM_TAP)
    sleep(3.0)
    report.add("abandon", "ok")
    return report
