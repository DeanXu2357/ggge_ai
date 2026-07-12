"""Run the manual battle controller on the battle currently on screen."""

from __future__ import annotations

import logging
import os
import signal
import sys

from ggge_ai.actuation.keyguard import Keyguard
from ggge_ai.agent.blackboard import RunBlackboard
from ggge_ai.app import connect
from ggge_ai.battle.controller import ManualBattleController
from ggge_ai.perception.llm import LlmScreenReader

logging.basicConfig(
    level=logging.DEBUG if os.environ.get("GGGE_DEBUG") else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(143))

perception, actuator = connect()
keyguard = Keyguard(actuator.device, capture=perception.capture)
keyguard.ensure_unlocked()
blackboard = RunBlackboard(goal="manual_battle")
ledger = blackboard.new_ledger()
controller = ManualBattleController(
    perception=perception,
    actuator=actuator,
    keyguard=keyguard,
    ledger=ledger,
    llm=LlmScreenReader.from_env(),
)
try:
    result = controller.run()
finally:
    if ledger.outcome is None:
        ledger.finish("interrupted")
    blackboard.archive(ledger)
print(f"controller finished: {result}")
