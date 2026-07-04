"""Run the manual battle controller on the battle currently on screen."""

from __future__ import annotations

import logging

from ggge_ai.app import connect
from ggge_ai.battle.controller import ManualBattleController

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S"
)

perception, actuator = connect()
controller = ManualBattleController(perception=perception, actuator=actuator)
result = controller.run()
print(f"controller finished: {result}")
