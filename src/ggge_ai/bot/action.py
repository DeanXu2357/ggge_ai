"""Action and Goal types for the bot skeleton."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ggge_ai.goap.action import Action as GoapAction
from ggge_ai.goap.action import Goal as GoapGoal
from ggge_ai.goap.state import Value, WorldState

if TYPE_CHECKING:
    from .bot import Bot
    from .state import BotState


class Action(GoapAction):
    """One planner operator and one device step.

    The adapter to `ggge_ai.goap` is deliberately the smallest one available:
    subclass the planner's Action and re-point `check`/`apply` at this
    package's `pre`/`eff` names. Nothing else is inherited that matters --
    the base `execute(ctx)` stays unused, because this loop hands one action
    per tick to `do(bot)` instead of handing a whole plan to an executor.

    `do()` performs exactly one device interaction or one pure computation.
    No internal loop, no polling, no sleep-until-settled: waiting is its own
    action (`WaitOut`) and re-checking is the next tick's `sense`. An action
    that loops internally is a tick the log cannot see into.

    `eff` is the exit condition of this step, not a promise that one call
    achieves it. The action stays at the head of the plan and fires again
    every tick until the screen reports `eff` as true, so `PanToFrontier`
    (`eff={"coverage": "complete"}`) pans until the map is covered -- no
    repeat counter, no staged goal, no loop inside `do()`.

    That has a price, and it is `cost`. A step can now be one tap or twenty,
    so a plan's total cost is no longer an estimate of the effort to run it
    and must not be used to choose between routes. A fork that used to be
    decided by cost (the warm path when a panel is already open vs the cold
    path that has to open it) has to be split by preconditions instead: two
    actions, mutually exclusive `pre`, only one of them applicable.

    `repeat_safe=False` marks actions that must not be fired twice in a row
    (a double tap opens and closes a panel); `settle_ticks` is how many ticks
    the loop will hold off before firing the same action again.
    """

    name: str = "action"
    cost: float = 1.0
    pre: Mapping[str, Value] = {}
    eff: Mapping[str, Value] = {}
    repeat_safe: bool = True
    settle_ticks: int = 0

    def check(self, state: WorldState) -> bool:
        return state.satisfies(self.pre)

    def apply(self, state: WorldState) -> WorldState:
        return state.with_updates(self.eff)

    def still_relevant(self, state: BotState) -> bool:
        """Is this step worth doing at all any more?

        Asked only when the step is blocked, and it decides between repairing
        the way to it and dropping it. Default True: most flow-level steps are
        still worth reaching. The ones that are not live in tactical
        sequences -- the target of a planned attack is already dead, the unit
        that was going to move has already acted -- where the honest answer is
        to drop the step and carry on with the rest of the sequence rather
        than spend actions restoring a precondition for something pointless.
        """
        return True

    def do(self, bot: Bot) -> None:
        raise NotImplementedError(f"{self.name} has no body")


@dataclass
class Goal(GoapGoal):
    """A named set of conditions over the flat symbol space.

    Same adapter trick as Action: the goap base already supplies the
    `is_satisfied`/`heuristic` the planner calls, so this only adds
    `satisfied`, the bot-facing form that takes a `BotState`.
    """

    name: str = "goal"
    conditions: dict[str, Value] = field(default_factory=dict)

    def satisfied(self, state: BotState) -> bool:
        return state.to_world_state().satisfies(self.conditions)
