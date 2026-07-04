"""Run the manual battle controller on the battle currently on screen."""

from __future__ import annotations

import logging
import subprocess
import time

from ggge_ai.app import connect
from ggge_ai.battle.controller import ManualBattleController

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S"
)


def wake_and_unlock() -> None:
    """Samsung lock screen wants a drag starting on the lock icon."""
    subprocess.run(["adb", "shell", "input", "keyevent", "KEYCODE_WAKEUP"], check=False)
    time.sleep(1.0)
    subprocess.run(["adb", "shell", "wm", "dismiss-keyguard"], check=False)
    time.sleep(0.5)
    subprocess.run(["adb", "shell", "input", "swipe", "1164", "430", "1164", "60", "350"], check=False)
    time.sleep(1.0)
    subprocess.run(["adb", "shell", "svc", "power", "stayon", "true"], check=False)


wake_and_unlock()
perception, actuator = connect()
controller = ManualBattleController(perception=perception, actuator=actuator)
result = controller.run()
print(f"controller finished: {result}")
