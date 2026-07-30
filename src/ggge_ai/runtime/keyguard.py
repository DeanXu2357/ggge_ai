"""兩種鎖的解除：系統鎖屏與遊戲省電觸控鎖。

兩者都用同一個從鎖頭圖示往上拖的手勢解開，但偵測方式不同——系統鎖 dumpsys
看得到，遊戲省電鎖看不到（遊戲視窗仍是前景），只會把畫面調暗、畫一顆鎖頭、
吞掉每一次 tap。再閒置幾秒鎖頭會淡出、只剩變暗，tap 照樣被吞（0719 兩輪
偵察就死在這裡：ensure_unlocked 看不到圖示回報已解鎖）。所以「暗但沒圖示」
要先戳一下再複驗：淡出的覆蓋層會把圖示叫回來，真正的過場黑幀不理這一戳。

搬自 actuation/keyguard.py，介面換成注入 shell／capture（runtime 不得 import
凍結舊包），亮度閘門與門檻沿用實測值。
"""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

TEMPLATE = (
    Path(__file__).resolve().parents[3] / "assets" / "templates" / "elements" / "game_lock_icon.png"
)
LOCK_DRAG = "input swipe 1164 430 1164 60 350"
# 頂部中央在任何戰鬥畫面上都沒有可互動元素：在淡出的覆蓋層上這一戳只會把鎖頭
# 叫回來，在真的過場黑幀上它什麼也不做。
LOCK_POKE = "input tap 1170 90"
LOCK_POKE_SETTLE_S = 0.8
LOCK_DRAG_SETTLE_S = 1.5
REGION = (1040, 320, 260, 230)
THRESHOLD = 0.75
# 圖示比對的第二道閘：TM_CCOEFF_NORMED 會在還活著的暗地圖的均勻暗塊上假命中
# （0706 HARD-2 事故：假「鎖」的拖曳在地圖單位上開了單位面板）。真的省電鎖會把
# 整幀調暗（實測灰階均值 12-17），活著的地圖再暗也遠亮於此（stage_info 47、
# hub ~73、亮選單 114）。
MAX_MEAN = 40.0


@functools.cache
def _template() -> np.ndarray | None:
    return cv2.imread(str(TEMPLATE))


@dataclass
class Keyguard:
    """shell 回傳指令輸出字串，capture 回傳 BGR 幀。兩個都注入＝離線可測。"""

    shell: Callable[[str], str]
    capture: Callable[[], np.ndarray | None]
    sleep: Callable[[float], None] = field(default=time.sleep)

    def is_locked(self) -> bool:
        return "mIsShowing=true" in self.shell("dumpsys window policy | grep mIsShowing")

    def _icon_visible(self, frame: np.ndarray | None) -> bool:
        template = _template()
        if frame is None or template is None:
            return False
        x, y, w, h = REGION
        patch = frame[y : y + h, x : x + w]
        if patch.shape[0] < template.shape[0] or patch.shape[1] < template.shape[1]:
            return False
        return float(cv2.matchTemplate(patch, template, cv2.TM_CCOEFF_NORMED).max()) >= THRESHOLD

    def is_game_locked(self) -> bool:
        frame = self.capture()
        if frame is None:
            return False
        if float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean()) > MAX_MEAN:
            return False
        if self._icon_visible(frame):
            return True
        self.shell(LOCK_POKE)
        self.sleep(LOCK_POKE_SETTLE_S)
        return self._icon_visible(self.capture())

    def _drag(self) -> None:
        self.shell(LOCK_DRAG)
        self.sleep(LOCK_DRAG_SETTLE_S)

    def unlock(self, attempts: int = 3) -> bool:
        for _ in range(attempts):
            self.shell("input keyevent KEYCODE_WAKEUP")
            self.sleep(1.0)
            self.shell("wm dismiss-keyguard")
            self.sleep(0.5)
            self._drag()
            if not self.is_locked():
                return True
        return False

    def dismiss_game_lock(self, attempts: int = 3) -> bool:
        for _ in range(attempts):
            self._drag()
            if not self.is_game_locked():
                return True
        return False

    def ensure_unlocked(self) -> bool:
        """沒鎖就什麼都不做，任何節奏呼叫都安全。"""
        ok = True
        if self.is_locked():
            log.warning("system keyguard engaged mid-run, unlocking")
            ok = self.unlock()
        if self.is_game_locked():
            log.warning("game battery-saver lock engaged mid-run, dismissing")
            ok = self.dismiss_game_lock() and ok
        return ok
