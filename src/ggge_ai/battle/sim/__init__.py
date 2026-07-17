"""Battle simulator: the pure, mechanism-only search back end.

This package is the offline forward model for the expectiminimax solver
(docs/agent-architecture.md, "battle simulator and expectiminimax"). It holds
no I/O -- no adb, no vision, no controller state. Everything is parametrised:
callers build SimUnit / SimWeapon from perception or cache and pass a SimParams
for the mechanism multipliers. It depends only on the shared battle vocabulary
(``..state`` Faction/BattleState, ``..actions`` ActionKind) plus the stdlib;
it must never import perception, actuation, vision or the controller.

The public surface is re-exported here so callers keep writing
``from ggge_ai.battle.sim import SimState`` unchanged after the split out of
the flat battle/ package. Submodules (core, formulas, solver, enemy_model,
grid) stay importable directly for callers that want a namespace.
"""

from __future__ import annotations

from . import formulas
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
