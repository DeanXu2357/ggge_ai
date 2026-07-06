"""Activation-internal chain planner for the tactical layer.

Scope is one unit's single activation (docs/agent-architecture.md,
tactical layer, evaluation tier 2). Kill-and-move ("re-activation") makes
planning depth = 1 + remaining re-act charges, capped at 3 steps, so an
exhaustive search suffices. With re-activation in hand the planner locks
onto targets it can kill to chain multiple activations; with no capability
or no numeric HP it degrades to the 1-ply greedy equivalent -- pick the
highest expected-damage target, else stand by.

Kills are judged on numeric HP (HP-arc ratios lie about damage). The
KillEstimator interface encodes the rule "expected damage >= numeric HP
kills, unknown HP never kills"; the perception-backed implementation is
left to issue #9 and tests use a fake. `ThresholdKillEstimator` is the
reference comparison -- pure mechanism over whatever numbers perception
supplies.
"""

from __future__ import annotations

from typing import Protocol

from ..domain.roster import CapabilityType
from .actions import ActionCatalog, BattleAction, make_standby_action
from .state import BattleState, UnitState

MAX_DEPTH = 3


class KillEstimator(Protocol):
    def is_kill(self, action: BattleAction, target: UnitState) -> bool: ...


class ThresholdKillEstimator:
    """Reference rule: expected damage >= numeric HP kills; unknown HP never."""

    def is_kill(self, action: BattleAction, target: UnitState) -> bool:
        return (
            action.expected_damage is not None
            and target.hp is not None
            and action.expected_damage >= target.hp
        )


def _react_charges(unit: UnitState) -> int:
    total = 0
    for cap in unit.capabilities:
        if cap.type is CapabilityType.KILL_REMOVE:
            total += cap.charges if cap.charges is not None else 1
    return total


def _targets(state: BattleState) -> dict[str, UnitState]:
    return {u.unit_id: u for u in state.enemies() if u.hp != 0}


def _greedy(unit: UnitState, catalog: ActionCatalog, targets: dict[str, UnitState]) -> list[BattleAction]:
    usable = [
        a
        for a in catalog.attacks()
        if a.target_id in targets and a.expected_damage is not None
    ]
    if not usable:
        return [make_standby_action(unit.unit_id)]
    return [max(usable, key=lambda a: a.expected_damage or 0.0)]


def _chain_search(
    attacks: list[BattleAction],
    targets: dict[str, UnitState],
    dead: frozenset[str],
    reacts_left: int,
    depth_left: int,
    estimator: KillEstimator,
) -> tuple[list[BattleAction], int, float]:
    """Return the best (chain, kills, total_damage) reachable from here."""
    best: tuple[list[BattleAction], int, float] = ([], 0, 0.0)
    if depth_left <= 0:
        return best
    for action in attacks:
        target = targets.get(action.target_id or "")
        if target is None or action.target_id in dead:
            continue
        damage = action.expected_damage or 0.0
        if estimator.is_kill(action, target):
            if reacts_left > 0 and depth_left > 1:
                sub_chain, sub_kills, sub_damage = _chain_search(
                    attacks,
                    targets,
                    dead | {action.target_id},  # type: ignore[arg-type]
                    reacts_left - 1,
                    depth_left - 1,
                    estimator,
                )
                candidate = ([action, *sub_chain], 1 + sub_kills, damage + sub_damage)
            else:
                candidate = ([action], 1, damage)
        else:
            candidate = ([action], 0, damage)
        if (candidate[1], candidate[2]) > (best[1], best[2]):
            best = candidate
    return best


def plan_activation(
    state: BattleState,
    unit: UnitState,
    catalog: ActionCatalog,
    estimator: KillEstimator,
    max_depth: int = MAX_DEPTH,
) -> list[BattleAction]:
    targets = _targets(state)
    reacts = _react_charges(unit)
    if reacts <= 0:
        return _greedy(unit, catalog, targets)

    depth = min(1 + reacts, max_depth)
    chain, _kills, _damage = _chain_search(
        catalog.attacks(), targets, frozenset(), reacts, depth, estimator
    )
    if not chain:
        return _greedy(unit, catalog, targets)
    return chain
