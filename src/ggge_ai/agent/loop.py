from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from ..actuation.base import Actuator
from ..core.action import Action, ExecutionContext, Goal
from ..core.planner import PlanNotFound, plan
from ..core.state import Value, WorldState
from ..perception.base import GameState, Perception

logger = logging.getLogger(__name__)

Translator = Callable[[GameState], WorldState]


@dataclass
class LoopConfig:
    max_replans: int = 40
    max_consecutive_failures: int = 3
    settle_delay_s: float = 0.5


class AgentLoop:
    """sense -> plan -> act -> verify.

    The world state the planner sees is the sensed state (from perception)
    merged over a small belief memory. Action effects whose keys are not
    sensed (e.g. `stage_cleared`) are latched into that memory once the
    action's sensed effects hold, so progress toward such goals persists
    after the triggering screen is gone.

    An action that leaves the world unchanged counts as a failure and is
    retried; an action that changes the world to something other than its
    declared effect is treated as progress and triggers a replan rather
    than a failure.
    """

    def __init__(
        self,
        perception: Perception,
        actuator: Actuator,
        translator: Translator,
        actions: Sequence[Action],
        config: LoopConfig | None = None,
        initial_memory: Mapping[str, Value] | None = None,
    ) -> None:
        self.perception = perception
        self.actuator = actuator
        self.translator = translator
        self.actions = list(actions)
        self.config = config or LoopConfig()
        self.memory: dict[str, Value] = dict(initial_memory or {})

    def _sense(self) -> tuple[GameState, WorldState, set[str]]:
        game_state = self.perception.observe()
        sensed = self.translator(game_state)
        merged = WorldState({**self.memory, **sensed})
        return game_state, merged, set(sensed.keys())

    def run(self, goal: Goal) -> bool:
        replans = 0
        failures = 0

        while replans <= self.config.max_replans:
            game_state, state, _ = self._sense()
            if goal.is_satisfied(state):
                logger.info("goal %s satisfied", goal.name)
                return True

            try:
                result = plan(state, goal, self.actions)
            except PlanNotFound:
                logger.error("no plan from %r to goal %s", state, goal.name)
                return False
            replans += 1
            logger.info(
                "plan #%d from %s: %s",
                replans,
                state.get("screen"),
                [a.name for a in result.actions],
            )

            for action in result.actions:
                ctx = ExecutionContext(
                    actuator=self.actuator, perception=self.perception, game_state=game_state
                )
                logger.info("executing %s", action.name)
                ok = action.execute(ctx)
                time.sleep(self.config.settle_delay_s)

                game_state, new_state, sensed_keys = self._sense()
                sensed_effects = {k: v for k, v in action.effects.items() if k in sensed_keys}
                effects_held = ok and new_state.satisfies(sensed_effects)
                progressed = new_state != state

                if effects_held:
                    for k, v in action.effects.items():
                        if k not in sensed_keys:
                            self.memory[k] = v
                    new_state = WorldState({**self.memory, **{k: new_state[k] for k in sensed_keys}})

                state = new_state
                if goal.is_satisfied(state):
                    logger.info("goal %s satisfied", goal.name)
                    return True

                if effects_held:
                    failures = 0
                    continue

                if progressed:
                    failures = 0
                    logger.info("%s -> unplanned %s, replanning", action.name, state.get("screen"))
                else:
                    failures += 1
                    logger.warning("%s made no progress (failures=%d)", action.name, failures)
                    if failures >= self.config.max_consecutive_failures:
                        logger.error("too many consecutive failures, aborting")
                        return False
                break

        logger.error("replan limit reached")
        return False
