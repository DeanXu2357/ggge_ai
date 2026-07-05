"""Run the manual battle controller on the battle currently on screen."""

from __future__ import annotations

import logging

from ggge_ai.actuation.keyguard import Keyguard
from ggge_ai.agent.blackboard import RunBlackboard
from ggge_ai.app import connect
from ggge_ai.battle.controller import ManualBattleController

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S"
)

perception, actuator = connect()
keyguard = Keyguard(actuator.device, capture=perception.capture)
keyguard.ensure_unlocked()
blackboard = RunBlackboard(goal="manual_battle")
ledger = blackboard.new_ledger()
controller = ManualBattleController(
    perception=perception, actuator=actuator, keyguard=keyguard, ledger=ledger
)
result = controller.run()
blackboard.archive(ledger)
print(f"controller finished: {result}")
