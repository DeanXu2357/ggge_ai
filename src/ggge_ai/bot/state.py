"""Flat symbolic state with two write doors on a fixed schedule."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ggge_ai.goap.state import Value, WorldState

if TYPE_CHECKING:
    from .action import Goal

UNKNOWN = "unknown"


@dataclass
class BotState:
    """One flat symbol space; every symbol belongs to exactly one door.

    Perception door (`sense_update`): opened once per tick, at the top, by the
    router's symbol table plus the board summary. Facts the screen can attest
    live here and are fully recomputed from the current frame every tick --
    an action's eff over these is a *prediction* the screen must confirm,
    never a write.

    Memory door (`remember`): opened only inside `Action.do`. Decisions the
    screen cannot show (intent, sim_ready) live here; the router never
    touches them.

    Between those two moments the symbol space is read-only. After `act` the
    symbols are stale by definition, and that is fine: nothing reads them
    until the next tick rewrites them.
    """

    facts: dict[str, Value] = field(default_factory=dict)
    goal: Goal | None = None
    # goal 是 None 代表沒有要達成的事，不是錯誤狀態——decide 直接收工。

    def get(self, key: str, default: Value = UNKNOWN) -> Value:
        return self.facts.get(key, default)

    def symbols(self) -> dict[str, Value]:
        return dict(self.facts)

    def satisfies(self, conditions: Mapping[str, Value]) -> bool:
        return self.to_world_state().satisfies(conditions)

    def sense_update(self, observed: Mapping[str, Value]) -> None:
        """Perception door: called once per tick, at the top, by the router."""
        self.facts.update(observed)

    def remember(self, **decided: Value) -> None:
        """Memory door: called from inside `Action.do` only."""
        self.facts.update(decided)

    def to_world_state(self) -> WorldState:
        return WorldState(self.facts)
