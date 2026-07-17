"""Battle simulator: the pure, mechanism-only world model and search back end.

This package is the offline forward model for the expectiminimax solver
(docs/agent-architecture.md, "battle simulator and expectiminimax"). It holds
no I/O -- no adb, no vision, no controller state. Everything is parametrised:
callers build SimUnit / SimWeapon from perception or cache and pass a SimParams
for the mechanism multipliers. It depends on nothing but the stdlib: the world
vocabulary (Faction, DecisionKind) is owned here in ``vocab`` and the battle
layer builds on top of it, never the other way around.

The public surface is re-exported here; submodules (vocab, core, formulas,
solver, enemy_model, grid) stay importable directly for callers that want a
namespace.
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
from .enemy_model import (
    MODE_MIN,
    MODE_POLICY,
    EnemyModel,
    MinimaxEnemy,
    NearestTargetPolicy,
    ReachProvider,
)
from .grid import (
    blocking_cells,
    grid_move_validator,
    occupied_cells,
    reach_provider,
    reachable_cells,
)
from .solver import (
    Evaluator,
    EvalWeights,
    Objective,
    SearchContext,
    SearchStats,
    SolverConfig,
    SolverResult,
    TerminalFn,
    default_evaluator,
    solve,
    solve_reaction,
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
    # enemy_model
    "MODE_MIN",
    "MODE_POLICY",
    "EnemyModel",
    "MinimaxEnemy",
    "NearestTargetPolicy",
    "ReachProvider",
    # grid
    "blocking_cells",
    "grid_move_validator",
    "occupied_cells",
    "reach_provider",
    "reachable_cells",
    # solver
    "Evaluator",
    "EvalWeights",
    "Objective",
    "SearchContext",
    "SearchStats",
    "SolverConfig",
    "SolverResult",
    "TerminalFn",
    "default_evaluator",
    "solve",
    "solve_reaction",
]
