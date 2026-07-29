"""Wake and unlock the device screen plus the game battery-saver lock.

usage: uv run python scripts/ensure_unlocked.py

Run before any manual tap sequence: the system relocks 5 s after screen-off
(lock_screen_lock_after_timeout=5000) and both locks silently swallow taps.
Exit code 0 = interactable, 1 = still locked after retries.
"""

from __future__ import annotations

import logging
import sys

from ggge_ai.actuation.keyguard import Keyguard
from ggge_ai.app import connect

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main() -> int:
    perception, actuator = connect()
    keyguard = Keyguard(actuator.device, capture=perception.capture)
    ok = keyguard.ensure_unlocked()
    print("unlocked" if ok else "STILL LOCKED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
