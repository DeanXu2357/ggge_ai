"""Solver-backed decision advice over the live BattleState.

advise() is the one-call pipeline the controller will consume: bridge the
perceived board into a SimState, run the anytime expectiminimax with the
grid-aware validators, and translate the best first decision back into
controller vocabulary -- world-pixel move target, target unit id, weapon
name -- together with the bridge's assumption list and search stats for
the ledger. Wiring this into ManualBattleController is device-gated (the
handlers must be exercised on the phone), so the controller side stops at
this interface for now.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .bridge import BridgeDefaults, UnitSpec, build_sim_state
from .enemy_model import MODE_MIN, MODE_POLICY, MinimaxEnemy, NearestTargetPolicy
from .grid import grid_move_validator, reach_provider
from .sim import SimState
from .solver import SearchStats, SolverConfig, solve
from .state import BattleState, Faction, Point


@dataclass
class AdvisorConfig:
    cell_size: float = 1.0
    time_budget_s: float = 5.0
    max_depth: int = 16
    enemy_mode: str = MODE_POLICY
    use_grid: bool = True
    defaults: BridgeDefaults = field(default_factory=BridgeDefaults)


@dataclass
class Advice:
    """The best first decision, in controller vocabulary."""

    unit_id: str
    kind: str
    move_world: Point | None
    target_id: str | None
    weapon: str | None
    value: float
    pv_kinds: list[str]
    assumptions: list[str]
    stats: SearchStats


def _promote_actor(state: SimState, unit_id: str) -> bool:
    """Move the unit to the front of the list so the simulator activates it
    first (allies act in list order; the solver never branches over that
    order). False when the unit is not an eligible actor right now."""
    unit = state.unit(unit_id)
    if unit is None or unit.faction is not Faction.ALLY or unit.acted or not unit.alive:
        return False
    state.units.remove(unit)
    state.units.insert(0, unit)
    return True


def advise(
    battle: BattleState,
    specs: Mapping[str, UnitSpec],
    config: AdvisorConfig | None = None,
    *,
    unit_id: str | None = None,
) -> Advice | None:
    """Bridge, solve, translate; None when there is nothing to decide.

    unit_id pins the root actor for pilot execution: the game has already
    selected that unit, so the search must optimise its activation rather
    than the default list-order one. None when the unit cannot act -- the
    caller decides whether that is a fallback or an abort."""
    config = config or AdvisorConfig()
    bridged = build_sim_state(
        battle, specs, cell_size=config.cell_size, defaults=config.defaults
    )
    state = bridged.state
    if not state.allies() or not state.enemies():
        return None
    if unit_id is not None and not _promote_actor(state, unit_id):
        return None

    validator = grid_move_validator if config.use_grid else None
    reach = reach_provider if config.use_grid else None
    if config.enemy_mode == MODE_MIN:
        model = MinimaxEnemy(validator, reach)
    else:
        model = NearestTargetPolicy(validator, reach)

    result = solve(
        state,
        model,
        SolverConfig(
            time_budget_s=config.time_budget_s,
            max_depth=config.max_depth,
            move_validator=validator,
            reach_provider=reach,
        ),
    )
    decision = result.decision
    if decision is None:
        return None
    return Advice(
        unit_id=decision.unit_id,
        kind=decision.kind,
        move_world=(
            bridged.to_world(decision.move_to) if decision.move_to is not None else None
        ),
        target_id=decision.target_id,
        weapon=decision.weapon,
        value=result.value,
        pv_kinds=[d.kind for d in result.pv],
        assumptions=bridged.assumptions,
        stats=result.stats,
    )
