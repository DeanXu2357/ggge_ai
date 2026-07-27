"""Action and Goal types for the bot loop."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ggge_ai.goap.action import Action as GoapAction
from ggge_ai.goap.action import Goal as GoapGoal
from ggge_ai.goap.state import Value, WorldState

if TYPE_CHECKING:
    from .bot import Bot


class Action(GoapAction):
    """One planner operator and one device step.

    `pre`/`eff` are pure symbols -- an action never depends on a screen
    contract. If a step needs a screen feature, the classifier tags it and
    the symbol table translates it; the action only ever reads symbols.

    `do()` performs exactly one device interaction or one pure computation,
    and owns its own transition sleep (`bot.clock.sleep`). No internal loop,
    no polling, no screen inspection: branching is declared as separate
    actions with mutually exclusive `pre`, and re-checking is the next tick.

    `eff` is the exit condition of the step, not a promise that one call
    achieves it: the action holds the head of the queue and fires each tick
    until the screen reports `eff` true (standing instruction). It can also
    pop without ever firing, when the world happens to already satisfy it.

    Carrying a step across ticks is the action's own job: `do()` performs at
    most one interaction and lets go, and the next tick re-enters through the
    symbols the action itself declared. The loop makes no behavioural
    decision about re-entry and holds no frame comparison of its own.
    """

    name: str = "action"
    cost: float = 1.0
    pre: Mapping[str, Value] = {}
    eff: Mapping[str, Value] = {}

    def check(self, state: WorldState) -> bool:
        return state.satisfies(self.pre)

    def apply(self, state: WorldState) -> WorldState:
        return state.with_updates(self.eff)

    def do(self, bot: Bot) -> None:
        raise NotImplementedError(f"{self.name} has no body")


@dataclass
class Goal(GoapGoal):
    """A named set of conditions over the flat symbol space.

    Deliberately no bot-facing `satisfied()` helper: the loop's only judge
    of goal satisfaction is the planner (an empty plan is the done signal),
    and a second predicate here would invite a second checkpoint.
    """

    name: str = "goal"
    conditions: dict[str, Value] = field(default_factory=dict)
