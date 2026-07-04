from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .state import Value, WorldState

if TYPE_CHECKING:
    from ..actuation.base import Actuator
    from ..perception.base import GameState, Perception


@dataclass
class ExecutionContext:
    actuator: Actuator
    perception: Perception
    game_state: GameState | None = None
    extras: dict[str, Any] = field(default_factory=dict)


class Action:
    """A planning-time operator that is also executable against the device.

    Declarative preconditions/effects cover most cases; override the check/apply
    methods for conditions that cannot be expressed as exact key-value matches.
    """

    name: str = "action"
    cost: float = 1.0
    preconditions: Mapping[str, Value] = {}
    effects: Mapping[str, Value] = {}

    def check(self, state: WorldState) -> bool:
        return state.satisfies(self.preconditions)

    def apply(self, state: WorldState) -> WorldState:
        return state.with_updates(self.effects)

    def execute(self, ctx: ExecutionContext) -> bool:
        raise NotImplementedError(f"{self.name} is not executable")

    def __repr__(self) -> str:
        return f"<Action {self.name}>"


class Goal:
    name: str = "goal"
    conditions: Mapping[str, Value] = {}

    def is_satisfied(self, state: WorldState) -> bool:
        return state.satisfies(self.conditions)

    def heuristic(self, state: WorldState) -> float:
        return float(state.count_unmet(self.conditions))

    def __repr__(self) -> str:
        return f"<Goal {self.name}>"
