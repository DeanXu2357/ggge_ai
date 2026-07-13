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

reactions() covers the other half of the enemy's agency: the defence response
when *we* attack. The policy baseline is "counter, intercept, join" -- every
live observation (user cases 2026-07-13, incl. the case-2 correction) shows
enemies fighting back and eligible supporters intercepting; step() degrades
each ineligible part to a no-op. The trigger rule has few samples and no
reconciliation evidence yet, so the min model still enumerates every stance
with and without interception for a worst-case bound.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .sim import (
    DEFENSE_STANCES,
    Cell,
    Decision,
    DefenseKind,
    DefenseResponse,
    MoveValidator,
    SimState,
    SimUnit,
    chebyshev,
    find_support_defender,
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

    reactions() returns (response, probability) pairs for the enemy defender
    when one of our attacks carries no DefenseResponse yet; the solver
    resolves them with the same expectation-or-min rule.
    """

    mode: str

    def decisions(self, state: SimState, unit: SimUnit) -> list[tuple[Decision, float]]: ...

    def reactions(
        self, state: SimState, decision: Decision
    ) -> list[tuple[DefenseResponse, float]]: ...


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

    def reactions(
        self, state: SimState, decision: Decision
    ) -> list[tuple[DefenseResponse, float]]:
        return [(DefenseResponse(kind=DefenseKind.COUNTER, support_defend=True), 1.0)]


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

    def reactions(
        self, state: SimState, decision: Decision
    ) -> list[tuple[DefenseResponse, float]]:
        responses = [DefenseResponse(kind=k) for k in DEFENSE_STANCES]
        target = state.unit(decision.target_id)
        if target is not None and find_support_defender(state, target) is not None:
            responses.extend(
                DefenseResponse(kind=k, support_defend=True) for k in DEFENSE_STANCES
            )
        weight = 1.0 / len(responses)
        return [(r, weight) for r in responses]


def _target_distance(state: SimState, unit: SimUnit, decision: Decision) -> int:
    target = state.unit(decision.target_id)
    if target is None:
        return 1_000_000
    origin = decision.move_to if decision.move_to is not None else unit.pos
    return chebyshev(origin, target.pos)
