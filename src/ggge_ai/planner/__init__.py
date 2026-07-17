"""Battle search: how to find good moves inside the simulated world.

The expectiminimax solver and the pluggable enemy-node models live here,
strictly one layer above ggge_ai.sim: this package consumes the world
model (step, legal moves, Objective/EvalContext) and never the other way
around, so an alternative back end (MCTS, deeper heuristics) can sit
beside solve() without touching the simulator. Nothing in here may
import perception, vision, actuation or the controller.
"""

from __future__ import annotations

from .enemy_model import (
    MODE_MIN,
    MODE_POLICY,
    EnemyModel,
    MinimaxEnemy,
    NearestTargetPolicy,
    ReachProvider,
)
from .solver import (
    SearchContext,
    SearchStats,
    SolverConfig,
    SolverResult,
    solve,
    solve_reaction,
)

__all__ = [
    # enemy_model
    "MODE_MIN",
    "MODE_POLICY",
    "EnemyModel",
    "MinimaxEnemy",
    "NearestTargetPolicy",
    "ReachProvider",
    # solver
    "SearchContext",
    "SearchStats",
    "SolverConfig",
    "SolverResult",
    "solve",
    "solve_reaction",
]
