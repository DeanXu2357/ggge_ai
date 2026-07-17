"""Battle simulator: the pure, mechanism-only world model.

This package is the offline forward model the search layer (ggge_ai.planner)
runs on (docs/agent-architecture.md, "battle simulator and expectiminimax").
It holds no I/O -- no adb, no vision, no controller state. Everything is
parametrised: callers build SimUnit / SimWeapon from perception or cache and
pass a SimParams for the mechanism multipliers. It depends on nothing but the
stdlib: the world vocabulary (Faction, DecisionKind) is owned here in
``vocab`` and the battle layer builds on top of it, never the other way
around.

The public surface is re-exported here; submodules (vocab, core, formulas,
objective, grid) stay importable directly for callers that want a namespace.
"""

from __future__ import annotations

from . import formulas
from .vocab import DecisionKind, Faction
from .core import (
    DEFAULT_PARAMS,
    DEFENSE_STANCES,
    PHASE_ORDER,
    Cell,
    Decision,
    DefenseKind,
    DefenseResponse,
    EventTable,
    MoveValidator,
    Phase,
    SimDebuff,
    SimEvent,
    SimParams,
    SimSkill,
    SimState,
    SimUnit,
    SimWeapon,
    approach,
    chebyshev,
    compute_damage,
    default_move_validator,
    find_support_attackers,
    find_support_defender,
    legal_attacks,
    legal_map_attacks,
    legal_skills,
    move_toward,
    opposing_faction,
    reposition_moves,
    standby,
    step,
    targets_of,
)
from .grid import (
    blocking_cells,
    grid_move_validator,
    nearest_free_cell,
    occupied_cells,
    reach_provider,
    reachable_cells,
)
from .objective import (
    EvalContext,
    EvalWeights,
    Evaluator,
    Objective,
    TerminalFn,
    annihilation_objective,
    default_evaluator,
    eval_bounds,
    wiped_out,
)

__all__ = [
    "formulas",
    # vocab
    "DecisionKind",
    "Faction",
    # core
    "DEFAULT_PARAMS",
    "DEFENSE_STANCES",
    "PHASE_ORDER",
    "Cell",
    "Decision",
    "DefenseKind",
    "DefenseResponse",
    "EventTable",
    "MoveValidator",
    "Phase",
    "SimDebuff",
    "SimEvent",
    "SimParams",
    "SimSkill",
    "SimState",
    "SimUnit",
    "SimWeapon",
    "approach",
    "chebyshev",
    "compute_damage",
    "default_move_validator",
    "find_support_attackers",
    "find_support_defender",
    "legal_attacks",
    "legal_map_attacks",
    "legal_skills",
    "move_toward",
    "opposing_faction",
    "reposition_moves",
    "standby",
    "step",
    "targets_of",
    # grid
    "blocking_cells",
    "grid_move_validator",
    "nearest_free_cell",
    "occupied_cells",
    "reach_provider",
    "reachable_cells",
    # objective
    "EvalContext",
    "EvalWeights",
    "Evaluator",
    "Objective",
    "TerminalFn",
    "annihilation_objective",
    "default_evaluator",
    "eval_bounds",
    "wiped_out",
]
