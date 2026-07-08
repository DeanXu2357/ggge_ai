"""Pluggable enemy decision models for the expectiminimax solver.

The enemy node is deliberately swappable (docs/agent-architecture.md): a
*policy* model returns a probability distribution over the enemy's move and
the solver takes an expectation; a *min* model returns a candidate set the
solver minimises over for a worst-case, conservative bound. Both are pure
mechanism -- the aggressiveness heuristics here read only board geometry and
the parametrised unit stats already in SimState, never hardcoded stage data.

NearestTargetPolicy is the v0 baseline (attack the nearest reachable target,
else stand by); MinimaxEnemy enumerates every legal attack plus standby as
the min node's candidates.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .sim import (
    Cell,
    Decision,
    MoveValidator,
    SimState,
    SimUnit,
    chebyshev,
    legal_attacks,
    standby,
)

MODE_POLICY = "policy"
MODE_MIN = "min"

ReachProvider = Callable[[SimState, SimUnit], set[Cell]]


class EnemyModel(Protocol):
    """Returns (decision, probability) pairs for one enemy unit.

    In MODE_POLICY the probabilities are a distribution the solver takes an
    expectation over. In MODE_MIN the probabilities are ignored (uniform) and
    the solver minimises over the candidate decisions.
    """

    mode: str

    def decisions(self, state: SimState, unit: SimUnit) -> list[tuple[Decision, float]]: ...


class NearestTargetPolicy:
    """Attack the nearest reachable target; stand by if none is in reach."""

    mode = MODE_POLICY

    def __init__(
        self,
        move_validator: MoveValidator | None = None,
        reach_provider: ReachProvider | None = None,
    ) -> None:
        self._move_validator = move_validator
        self._reach_provider = reach_provider

    def decisions(self, state: SimState, unit: SimUnit) -> list[tuple[Decision, float]]:
        attacks = legal_attacks(
            state,
            unit,
            move_validator=self._move_validator,
            reach=self._reach_provider(state, unit) if self._reach_provider else None,
        )
        if not attacks:
            return [(standby(unit.unit_id), 1.0)]
        best = min(attacks, key=lambda d: _target_distance(state, unit, d))
        return [(best, 1.0)]


class MinimaxEnemy:
    """Worst-case model: every legal attack plus standby as candidates."""

    mode = MODE_MIN

    def __init__(
        self,
        move_validator: MoveValidator | None = None,
        reach_provider: ReachProvider | None = None,
    ) -> None:
        self._move_validator = move_validator
        self._reach_provider = reach_provider

    def decisions(self, state: SimState, unit: SimUnit) -> list[tuple[Decision, float]]:
        attacks = legal_attacks(
            state,
            unit,
            move_validator=self._move_validator,
            reach=self._reach_provider(state, unit) if self._reach_provider else None,
        )
        candidates = [*attacks, standby(unit.unit_id)]
        weight = 1.0 / len(candidates)
        return [(d, weight) for d in candidates]


def _target_distance(state: SimState, unit: SimUnit, decision: Decision) -> int:
    target = state.unit(decision.target_id)
    if target is None:
        return 1_000_000
    origin = decision.move_to if decision.move_to is not None else unit.pos
    return chebyshev(origin, target.pos)
