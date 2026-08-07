from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

import cv2

log = logging.getLogger(__name__)

# Two distinct locks interrupt long runs, both dismissed by the same upward
# drag from the lock icon:
# - the system keyguard (screen-off wake), visible to dumpsys
# - the game's own battery-saver touch lock after ~3 min without input; it
#   dims the frame and draws a lock icon at screen center, is invisible to
#   dumpsys (the game window stays focused), and swallows all taps while
#   screen templates still partially match through the dim overlay. After a
#   few more idle seconds the overlay FADES: the icon disappears and only
#   the dimming remains, still eating every tap (2026-07-19 live -- two
#   probe rounds died tapping through it while ensure_unlocked saw no icon
#   and reported unlocked). A tap anywhere wakes the icon back up, so the
#   detector pokes the neutral spot and re-checks before trusting a dim
#   iconless frame.
LOCK_DRAG = "input swipe 1164 430 1164 60 350"
# (500,75) 落在回合橫幅／各頁標題帶：0807 實測 battle_map 點了毫無反應，單位移動
# 模式也是標題死區。舊點 (1170,90) 是地圖頂帶格子——鎖在點下前一刻自行解除時，
# 這一戳會直接選中頂帶單位（0807 run 20260807-012336 就這樣把 GQuuuuuuX 戳進
# 行動模式）；在單位移動模式下更可能戳成真的移動。
LOCK_POKE = "input tap 500 75"
LOCK_POKE_SETTLE_S = 0.8

GAME_LOCK_TEMPLATE = (
    Path(__file__).resolve().parents[3]
    / "assets"
    / "templates"
    / "elements"
    / "game_lock_icon.png"
)
GAME_LOCK_REGION = (1040, 320, 260, 230)
GAME_LOCK_THRESHOLD = 0.75
# second signal to gate the lock-icon match: TM_CCOEFF_NORMED false-matches the
# icon on a dark uniform patch of a stalled-but-live battle map (the 20260706
# HARD-2 stall, where a spurious "lock" drag opened a unit modal on a map unit).
# the real battery-saver lock dims the *whole* frame (measured grey mean ~12-17
# on 20260706-231320.png) while an active map -- even a dark one -- stays far
# brighter (stage_info 47, hub ~73, bright menu 114). require whole-frame mean
# brightness below this gate before trusting the icon, so a local dark patch on
# a live map no longer triggers a drag.
GAME_LOCK_MAX_MEAN = 40.0


class Keyguard:
    def __init__(self, device, capture: Callable | None = None) -> None:
        self.device = device
        self.capture = capture
        self._template = cv2.imread(str(GAME_LOCK_TEMPLATE))

    def is_locked(self) -> bool:
        out = self.device.shell("dumpsys window policy | grep mIsShowing").output
        return "mIsShowing=true" in out

    def _icon_visible(self, frame) -> bool:
        x, y, w, h = GAME_LOCK_REGION
        crop = frame[y : y + h, x : x + w]
        result = cv2.matchTemplate(crop, self._template, cv2.TM_CCOEFF_NORMED)
        _, score, _, _ = cv2.minMaxLoc(result)
        return score >= GAME_LOCK_THRESHOLD

    def is_game_locked(self) -> bool:
        if self.capture is None or self._template is None:
            return False
        frame = self.capture()
        # a live battle map is never dim enough to be the battery-saver lock,
        # so skip the icon match entirely when the frame is bright: it can only
        # false-match there, never truly lock
        if float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean()) > GAME_LOCK_MAX_MEAN:
            return False
        if self._icon_visible(frame):
            return True
        # dim but iconless: either the faded lock overlay or a transition /
        # loading black frame. The poke tells them apart -- the overlay wakes
        # its icon back up, a transition ignores an inert neutral tap.
        self.device.shell(LOCK_POKE)
        time.sleep(LOCK_POKE_SETTLE_S)
        return self._icon_visible(self.capture())

    def _drag_lock_icon(self) -> None:
        self.device.shell(LOCK_DRAG)
        time.sleep(1.5)

    def unlock(self, attempts: int = 3) -> bool:
        for _ in range(attempts):
            self.device.shell("input keyevent KEYCODE_WAKEUP")
            time.sleep(1.0)
            self.device.shell("wm dismiss-keyguard")
            time.sleep(0.5)
            self._drag_lock_icon()
            if not self.is_locked():
                return True
        return False

    def dismiss_game_lock(self, attempts: int = 3) -> bool:
        for _ in range(attempts):
            self._drag_lock_icon()
            if not self.is_game_locked():
                return True
        return False

    def ensure_unlocked(self) -> bool:
        """No-op when nothing is locked; safe to call at any loop cadence."""
        ok = True
        if self.is_locked():
            log.warning("system keyguard engaged mid-run, unlocking")
            ok = self.unlock()
            log.info("keyguard %s", "dismissed" if ok else "STILL LOCKED")
        if self.is_game_locked():
            log.warning("game battery-saver lock engaged mid-run, dismissing")
            got = self.dismiss_game_lock()
            log.info("game lock %s", "dismissed" if got else "STILL LOCKED")
            ok = ok and got
        return ok
