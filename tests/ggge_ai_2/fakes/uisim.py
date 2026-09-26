from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

from ggge_ai_2.uisim.contract import Operation, Outcome, UiState


@dataclass(frozen=True)
class FrozenUiSim:
    state: UiState
    table: Mapping[UiState, tuple[Operation, ...]] = field(default_factory=dict, compare=False)

    def successors(self) -> Sequence[Operation]:
        return self.table.get(self.state, ())

    def predecessors(self) -> Sequence[tuple[UiState, Operation]]:
        return tuple(
            (source, op)
            for source, ops in self.table.items()
            for op in ops
            if any(outcome.then == self.state for outcome in op.outcomes)
        )

    def advance(self, outcome: Outcome) -> FrozenUiSim:
        return replace(self, state=outcome.then)

    def sync(self, observed: UiState) -> FrozenUiSim:
        return replace(self, state=observed)
