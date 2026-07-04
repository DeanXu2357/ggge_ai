from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from ..actuation.base import Actuator
from ..core.action import Action, ExecutionContext, Goal
from ..core.planner import PlanNotFound, plan
from ..core.state import WorldState
from ..perception.base import GameState, Perception

logger = logging.getLogger(__name__)

Translator = Callable[[GameState], WorldState]


@dataclass
class LoopConfig:
    max_replans: int = 20
    max_consecutive_failures: int = 3
    settle_delay_s: float = 1.0


class AgentLoop:
    """sense -> plan -> act -> verify. After each action the world is
    re-observed; if the action's declared effects did not materialize the
    failure counter increments and the loop replans from the fresh state."""

    def __init__(
        self,
        perception: Perception,
        actuator: Actuator,
        translator: Translator,
        actions: Sequence[Action],
        config: LoopConfig | None = None,
    ) -> None:
        self.perception = perception
        self.actuator = actuator
        self.translator = translator
        self.actions = list(actions)
        self.config = config or LoopConfig()

    def run(self, goal: Goal) -> bool:
        replans = 0
        failures = 0

        while replans <= self.config.max_replans:
            game_state = self.perception.observe()
            state = self.translator(game_state)

            if goal.is_satisfied(state):
                logger.info("goal %s satisfied", goal.name)
                return True

            try:
                result = plan(state, goal, self.actions)
            except PlanNotFound:
                logger.error("no plan from state %r to goal %s", state, goal.name)
                return False
            replans += 1
            logger.info(
                "plan #%d: %s (cost=%.1f)",
                replans,
                [a.name for a in result.actions],
                result.total_cost,
            )

            for action in result.actions:
                ctx = ExecutionContext(
                    actuator=self.actuator, perception=self.perception, game_state=game_state
                )
                ok = action.execute(ctx)
                time.sleep(self.config.settle_delay_s)

                game_state = self.perception.observe()
                state = self.translator(game_state)

                if not ok or not state.satisfies(action.effects):
                    failures += 1
                    logger.warning(
                        "action %s did not produce expected effects (failures=%d)",
                        action.name,
                        failures,
                    )
                    if failures >= self.config.max_consecutive_failures:
                        logger.error("too many consecutive failures, aborting")
                        return False
                    break
                failures = 0

                if goal.is_satisfied(state):
                    logger.info("goal %s satisfied", goal.name)
                    return True

        logger.error("replan limit reached")
        return False
