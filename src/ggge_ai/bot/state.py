"""Flat symbolic state for the bot skeleton."""

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
    """One flat symbol space, no outer / in-stage split.

    `in_stage`, `view`, `coverage`, `phase`, `sim_ready`, `intent` all live in
    the same dict; "which layer am I in" is just another symbol the planner
    reads, not a separate state machine.

    There is exactly one goal, and it is the outer one ("this stage is
    cleared", "the simulator is in sync"). Staged goals do not exist any more:
    the order of `Bot.plan` is what says "positions first, then details" --
    a sequence the planner produced, not a list a human pre-decided.

    Two disciplines this class exists to keep visible:

    1. Perception symbols are overwritten by `sense` every tick. If a symbol
       cannot be read this tick it is written `UNKNOWN` -- never left at its
       last value, because a stale symbol is indistinguishable from a fresh
       one to the planner. `sense_update` is the only door for these.
    2. Memory symbols are written by actions only. `sense` never touches them,
       so nothing on screen can silently revoke a decision we made. `remember`
       is the only door for these.

    Both doors write into the same dict on purpose: the planner sees one flat
    space. The split is a discipline about who writes what, not two storages.
    """

    facts: dict[str, Value] = field(default_factory=dict)
    goal: Goal | None = None
    # goal 是 None 代表沒有要達成的事，不是錯誤狀態——decide 直接收工。

    def get(self, key: str, default: Value = UNKNOWN) -> Value:
        return self.facts.get(key, default)

    def set(self, key: str, value: Value) -> None:
        self.facts[key] = value

    def update(self, values: Mapping[str, Value]) -> None:
        self.facts.update(values)

    def symbols(self) -> dict[str, Value]:
        return dict(self.facts)

    def satisfies(self, conditions: Mapping[str, Value]) -> bool:
        """One reading of the screen, asked twice per tick.

        `decide` asks it about the head's effect (is this step done?) and about
        the head's preconditions (may this step run?). Same question form, so
        the two must not drift apart into separate comparison rules.
        """
        return self.to_world_state().satisfies(conditions)

    def sense_update(self, **observed: Value) -> None:
        """Perception door: called once per tick by `Bot.sense`.

        The caller is expected to pass `UNKNOWN` for anything it failed to
        read, so the write is always a full overwrite of what it owns.
        """
        self.facts.update(observed)

    def remember(self, **decided: Value) -> None:
        """Memory door: called from inside `Action.do` only."""
        self.facts.update(decided)

    def to_world_state(self) -> WorldState:
        return WorldState(self.facts)
