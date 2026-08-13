"""adb 截圖與觸控，以及「把一個行動打到裝置上」的接縫。

一次操作＝一串手勢。手勢是資料（Tap／Swipe／Key／Settle），行動要按哪幾下由
上層以 plan 提供——runtime 不認識行動詞彙（型別住 stage），所以這裡只負責重播
手勢、擋危險帶、記流水帳。

危險帶是白名單制而不是黑名單：帶內的點擊必須帶著那一帶指定的 intent 才放行，
沒帶就拋 TapRefused。全都是實機踩過的雷——AUTO 三選一、戰鬥選單的放棄、
自動編制、AUTO 開關本身——寧可整批停下來也不要無聲點下去。
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from .perceive import Observation

log = logging.getLogger(__name__)

SCREEN = (2340, 1080)


class Device(Protocol):
    def screenshot(self) -> Any: ...

    def tap(self, x: int, y: int) -> None: ...

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_s: float) -> None: ...


class Actuator(Protocol):
    """手勢重播需要的那一面：帶 intent 的 tap（危險帶白名單）、swipe、按鍵。"""

    def tap(self, x: int, y: int, intent: str = "") -> None: ...

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_s: float) -> None: ...

    def key(self, keycode: str) -> None: ...


class Executor[ActionT](Protocol):
    """迴圈一個 tick 至多呼叫一次 perform；一次 perform 內部要按幾下由
    實作決定，但成敗一律由下一張畫面的證據裁決，不回報成功與否。"""

    def perform(self, action: ActionT, observation: Observation[Any]) -> None: ...


@dataclass(frozen=True)
class Tap:
    x: int
    y: int
    settle_s: float = 0.6
    intent: str = ""


@dataclass(frozen=True)
class Swipe:
    x1: int
    y1: int
    x2: int
    y2: int
    duration_s: float = 0.3
    settle_s: float = 1.2


@dataclass(frozen=True)
class Key:
    keycode: str
    settle_s: float = 1.0


@dataclass(frozen=True)
class Settle:
    seconds: float


Gesture = Tap | Swipe | Key | Settle


@dataclass(frozen=True)
class DangerBand:
    name: str
    x: tuple[int, int]
    y: tuple[int, int]
    intents: tuple[str, ...] = ()

    def contains(self, x: int, y: int) -> bool:
        return self.x[0] <= x <= self.x[1] and self.y[0] <= y <= self.y[1]


# 名冊（部隊資訊）是全螢幕面板，蓋在地圖與設定列上：面板開著的時候帶內那些鈕
# 實際點不到，點下去命中的是名冊格。這個 intent 只由「面板已開」的流程發出
# （roster_capture 逐格點開詳情前自己驗過畫面是 TROOP_INFO），地圖裸露時發的
# tap 一律不帶。
ROSTER_CELL_INTENT = "roster_cell"

DANGER_BANDS: tuple[DangerBand, ...] = (
    # 設定頁 AUTO戰鬥 三選一的「全軍自動／他軍自動」半邊：踩到就把單位交給
    # 內建 AI（紅線）。只放行名冊格——首列第 4、5 格 (1564,267)/(1843,267) 落在
    # 帶內，但名冊面板蓋著設定列，那兩點打得到的只有名冊格。
    DangerBand("auto_battle_tristate", (1400, SCREEN[0]), (245, 345),
               intents=(ROSTER_CELL_INTENT,)),
    # 戰鬥選單下排左半：放棄 (410,860) 與重試 (752,865)。只有棄戰流程進得去；
    # 敵軍名冊第 4 列第 1 格 (729,847) 也落在帶內，同樣是面板蓋住的假重疊。
    DangerBand("battle_menu_abandon", (0, 900), (825, 905),
               intents=("abandon", ROSTER_CELL_INTENT)),
    # 出擊準備下緣按鈕列最右的「自動編制」——一鍵改隊伍編成（bbox 1369-1624
    # x 973-1047，0731 兩幀像素量測一致）。排好的編成不容許被覆蓋。
    # 左鄰「全部編制」(~1208,1010) 與各對話框通用關閉鈕位
    # (~1170,993) 重疊，設帶會擋掉所有收彈窗的點——已知殘留風險，暫不設防。
    # 帶頂 970：舊武裝選擇槽位列 y=965 貼在帶外 5px；隱藏關「挑戰」(1404,977)
    # 落在鈕面內屬跨畫面固有重疊，該流程搬上 LiveDevice 時再裁。
    DangerBand("auto_deploy", (1360, 1635), (970, 1055)),
    # 右下角大圓鈕槽位跨畫面是不同東西：應戰 stance 選單上是「行動選擇」確認
    # (2037,930)、關卡列表上是「出擊準備」鈕的下半。裝置層看不到畫面名，整帶
    # 只放行刻意的確認——需要按的流程自己帶 intent，手滑一律擋掉。
    DangerBand("bottom_right_confirm", (1960, 2080), (895, 955), intents=("confirm",)),
    # AUTO 開關本身 (1815,52)：暗＝OFF 勿點，只有閘門流程確認過是 ON 才准碰。
    DangerBand("auto_switch", (1770, 1960), (15, 90), intents=("auto_switch",)),
    # 戰鬥地圖左上「變更初期配置」（鈕身 bbox x 153-438 y 250-319，0803 八幀
    # 像素量測一致）。誤點會**無聲**切進部隊配置編輯頁，畫面分類沒有這個名字，
    # 後續腳本仍以為自己在地圖上，接下來每一次點擊都打在別的東西上（0803 實機
    # 連鎖污染兩項量測）。鈕畫在地圖上層，帶內的格子本來就點不到——點下去命中
    # 的是鈕不是格，所以設帶不會多擋掉任何合法的格點擊。
    DangerBand("deploy_change", (145, 447), (242, 328), intents=("deploy_change",)),
    # 「變更初期配置」正上方的「回合結束」（鈕身 bbox x 153-439 y 149-217，
    # 0803 兩張乾淨底幀剖面量測一致）。誤點直接把我方回合讓掉，比切進配置頁
    # 嚴重。量法要留意：一般幀的底是地圖白格線，亮度門檻與不變性疊圖都會跟格
    # 線黏成一片（八幀量出三種 bbox），要挑鏡頭平移到鈕後方是虛空的幀才量得準。
    DangerBand("end_turn", (145, 448), (140, 227), intents=("end_turn",)),
    # 「單位移動」右下的大圓「選擇武裝」鈕（鈕心約 2085,971、半徑約 140，0711 雪原
    # 幀量測）。名冊跳轉到我方單位會落進這個模式，解除要點左鄰的「返回」(1798,971)
    # ——返回鈕右緣量到 1868，整顆落在帶外，所以帶不需要放行任何 intent。
    # 帶頂切在 960 而不是鈕的上緣 831：上面那一段跨畫面是關卡列表「出擊準備」
    # (2035,880) 與應戰「行動選擇」確認 (2042,924)，那兩顆各有自己的閘門。
    DangerBand("weapon_dial", (1945, SCREEN[0]), (960, SCREEN[1]), intents=()),
)


def blocked_for_map_tap(
    point: tuple[float, float], bands: Sequence[DangerBand] = DANGER_BANDS
) -> bool:
    """這一點在「地圖裸露、不帶 intent」的視角下可不可點。

    帶的範圍比可見鈕大（帶要包住鈕在各畫面的所有位置），所以挑地圖格的時候要問的
    是帶而不是鈕的形狀——0806 兩輪實機各撞一次才收斂成這條：先問帶，不要逐一補
    遮罩去追帶的形狀。
    """
    x, y = int(round(point[0])), int(round(point[1]))
    return any(band.contains(x, y) for band in bands)


class TapRefused(RuntimeError):
    pass


class UnsupportedAction(RuntimeError):
    pass


def check_tap(x: int, y: int, intent: str = "", bands: Sequence[DangerBand] = DANGER_BANDS) -> None:
    """越界或誤入危險帶就拋——uiautomator2 對負座標直接 assert crash，而危險帶
    誤點的代價（自動戰鬥、改編成、棄戰）都不是重點一次可以救回來的。"""
    if not (0 <= x < SCREEN[0] and 0 <= y < SCREEN[1]):
        raise TapRefused(f"tap out of screen: ({x},{y})")
    for band in bands:
        if band.contains(x, y) and (not band.intents or intent not in band.intents):
            raise TapRefused(f"tap ({x},{y}) refused by danger band {band.name!r}")


@dataclass
class Adb:
    """adb 子行程通道。

    ADB_LIBUSB=1 是本專案定則（0722）：連線一律走 libusb，不吃 device poll
    執行緒。這裡明寫進環境是為了 tmux／服務等不吃 .claude/settings.json 的
    情境；**若已有一個沒帶這個變數的 server 在跑，先 adb kill-server**，程式
    無法從這裡判斷或修正既有 server 的模式。
    """

    serial: str | None = None
    binary: str = "adb"
    timeout_s: float = 30.0
    env_extra: Mapping[str, str] = field(default_factory=lambda: {"ADB_LIBUSB": "1"})

    def _argv(self, *args: str) -> list[str]:
        head = [self.binary]
        if self.serial:
            head += ["-s", self.serial]
        return head + list(args)

    def _run(self, *args: str) -> bytes:
        completed = subprocess.run(
            self._argv(*args),
            capture_output=True,
            timeout=self.timeout_s,
            env={**os.environ, **self.env_extra},
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"adb {' '.join(args)} failed ({completed.returncode}): "
                f"{completed.stderr.decode(errors='replace').strip()}"
            )
        return completed.stdout

    def shell(self, command: str) -> str:
        return self._run("shell", command).decode(errors="replace")

    def screencap(self) -> bytes:
        """原生幀位元組直通：exec-out 是二進位安全的，PNG 位元組原封不動落到
        流水帳與解碼器，中間不重新編碼也不縮圖。"""
        return self._run("exec-out", "screencap -p")


@dataclass
class LiveDevice:
    """實機通道。截圖回傳 PNG 原生位元組（不是陣列）——解碼是感知層的事，
    流水帳要存的是原始位元組。

    每段操作前掛 Keyguard：兩種鎖都會無聲吞掉 tap，而吞掉的 tap 在下一張畫面
    上看起來就只是「什麼都沒發生」。逐 tap 問一次太貴（dumpsys＋截圖），所以
    節流成每 unlock_every_s 秒至多一次。
    """

    adb: Adb
    keyguard: Any | None = None
    unlock_every_s: float = 30.0
    clock: Callable[[], float] = field(default=time.monotonic)
    _last_unlock_check: float = field(default=float("-inf"), init=False)

    def screenshot(self) -> bytes:
        return self.adb.screencap()

    def ensure_unlocked(self, force: bool = False) -> None:
        if self.keyguard is None:
            return
        now = self.clock()
        if not force and now - self._last_unlock_check < self.unlock_every_s:
            return
        self._last_unlock_check = now
        self.keyguard.ensure_unlocked()

    def tap(self, x: int, y: int, intent: str = "") -> None:
        check_tap(x, y, intent)
        self.ensure_unlocked()
        self.adb.shell(f"input tap {x} {y}")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_s: float = 0.3) -> None:
        for x, y in ((x1, y1), (x2, y2)):
            if not (0 <= x < SCREEN[0] and 0 <= y < SCREEN[1]):
                raise TapRefused(f"swipe endpoint out of screen: ({x},{y})")
        self.ensure_unlocked()
        self.adb.shell(f"input swipe {x1} {y1} {x2} {y2} {round(duration_s * 1000)}")

    def key(self, keycode: str) -> None:
        self.ensure_unlocked()
        self.adb.shell(f"input keyevent {keycode}")


@dataclass
class LiveExecutor:
    """手勢重播器。plans 把一個行動翻成手勢串；自帶 gestures 的操作直接重播。

    drivers 收「要邊看邊做」的行動（翻設定頁開關、收卡條、平移掃描）：它們不是一串
    固定手勢，得自己截圖再決定下一步，所以拿到控制權自己跑完。回傳值只當流水帳的
    自述（這次做了哪一個微步驟），成敗仍不回報——一律由下一張畫面裁決。

    查不到 plan／driver 就拋 UnsupportedAction：無聲空轉是這個專案最貴的失效
    模式。
    """

    device: Actuator
    plans: Mapping[type, Callable[[Any, Observation[Any]], Sequence[Gesture]]] = field(
        default_factory=dict
    )
    drivers: Mapping[type, Callable[[Any, Observation[Any]], None]] = field(default_factory=dict)
    journal: Any | None = None
    sleep: Callable[[float], None] = field(default=time.sleep)

    def perform(self, action: Any, observation: Observation[Any]) -> None:
        driver = self.drivers.get(type(action))
        if driver is not None:
            step = driver(action, observation)
            if self.journal is not None:
                self.journal.record(
                    "perform", label=getattr(action, "label", ""), driven=True, step=step
                )
            return
        self.replay(self.gestures_for(action, observation), label=getattr(action, "label", ""))

    def gestures_for(self, action: Any, observation: Observation[Any]) -> Sequence[Gesture]:
        own = getattr(action, "gestures", None)
        if own is not None:
            return own
        plan = self.plans.get(type(action))
        if plan is None:
            raise UnsupportedAction(f"no gesture plan for {type(action).__name__}")
        return plan(action, observation)

    def replay(self, gestures: Sequence[Gesture], label: str = "") -> None:
        for gesture in gestures:
            self._one(gesture)
        if self.journal is not None:
            self.journal.record("perform", label=label, gestures=[str(g) for g in gestures])

    def _one(self, gesture: Gesture) -> None:
        match gesture:
            case Tap(x=x, y=y, settle_s=settle, intent=intent):
                self.device.tap(x, y, intent=intent)
                self.sleep(settle)
            case Swipe(x1=x1, y1=y1, x2=x2, y2=y2, duration_s=duration, settle_s=settle):
                self.device.swipe(x1, y1, x2, y2, duration)
                self.sleep(settle)
            case Key(keycode=keycode, settle_s=settle):
                self.device.key(keycode)
                self.sleep(settle)
            case Settle(seconds=seconds):
                self.sleep(seconds)
