from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

# Samsung idle relock swallows all taps while screen templates still match
# through the dimmed overlay, so long runs silently stall. The keyguard state
# is read from dumpsys; unlocking needs a drag that starts on the lock icon
# (raw device coordinates, not scaled - the lock screen ignores game rotation).
LOCK_ICON_DRAG = "input swipe 1164 430 1164 60 350"


class Keyguard:
    def __init__(self, device) -> None:
        self.device = device

    def is_locked(self) -> bool:
        out = self.device.shell("dumpsys window policy | grep mIsShowing").output
        return "mIsShowing=true" in out

    def unlock(self, attempts: int = 3) -> bool:
        for _ in range(attempts):
            self.device.shell("input keyevent KEYCODE_WAKEUP")
            time.sleep(1.0)
            self.device.shell("wm dismiss-keyguard")
            time.sleep(0.5)
            self.device.shell(LOCK_ICON_DRAG)
            time.sleep(1.5)
            if not self.is_locked():
                return True
        return False

    def ensure_unlocked(self) -> bool:
        """No-op when already unlocked; safe to call at any loop cadence."""
        if not self.is_locked():
            return True
        log.warning("keyguard engaged mid-run, unlocking")
        ok = self.unlock()
        if ok:
            log.info("keyguard dismissed, resuming")
        else:
            log.error("could not dismiss keyguard")
        return ok
