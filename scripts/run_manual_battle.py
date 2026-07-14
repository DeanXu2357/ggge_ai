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

def _flag(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "on", "yes")


perception, actuator = connect()
keyguard = Keyguard(actuator.device, capture=perception.capture)
keyguard.ensure_unlocked()
blackboard = RunBlackboard(goal="manual_battle")
ledger = blackboard.new_ledger()
intel_budget = None
if _flag("GGGE_INTEL"):
    from ggge_ai.battle.scout_intel import IntelBudget

    intel_budget = IntelBudget()
controller = ManualBattleController(
    perception=perception,
    actuator=actuator,
    keyguard=keyguard,
    ledger=ledger,
    llm=LlmScreenReader.from_env(),
    intel_budget=intel_budget,
    stage_id=os.environ.get("GGGE_STAGE_ID") or None,
    advisor_enabled=_flag("GGGE_ADVISOR"),
    pilot_enabled=_flag("GGGE_PILOT"),
)
try:
    result = controller.run()
finally:
    if ledger.outcome is None:
        ledger.finish("interrupted")
    blackboard.archive(ledger)
print(f"controller finished: {result}")
