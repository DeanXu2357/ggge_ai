"""Drive the GOAP agent to clear the currently selected stage.

usage: uv run python scripts/run_clear_loop.py
"""

from __future__ import annotations

import logging

from ggge_ai.agent.loop import AgentLoop, LoopConfig
from ggge_ai.app import connect
from ggge_ai.domain.actions.flow import CLEAR_STAGE_ACTIONS
from ggge_ai.domain.goals import ClearCurrentStage
from ggge_ai.domain.translate import to_world_state


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    perception, actuator = connect(save_shots=True)
    loop = AgentLoop(
        perception=perception,
        actuator=actuator,
        translator=to_world_state,
        actions=CLEAR_STAGE_ACTIONS,
        config=LoopConfig(settle_delay_s=1.0),
    )
    ok = loop.run(ClearCurrentStage())
    logging.getLogger("run").info("clear loop result: %s", "SUCCESS" if ok else "FAILED")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
