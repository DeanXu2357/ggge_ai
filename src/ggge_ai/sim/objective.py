"""What a search optimizes over the world model.

Objective bundles the terminal test, the leaf evaluator and the value
bounds pruning is sound against. EvalContext is the only window leaf
evaluation gets into a search: the tunable weights plus the opening
head-counts kills and losses are measured against. Owning these here
rather than in the solver keeps the evaluation vocabulary part of the
world model, so a stage-condition compiler and any alternative search
back end share it without touching expectiminimax internals.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .core import SimState


@dataclass(frozen=True)
class EvalWeights:
    ally_hp: float = 1.0
    enemy_hp: float = 1.0
    kill: float = 5.0
    loss: float = 5.0


@dataclass(frozen=True)
class EvalContext:
    weights: EvalWeights
    base_allies: int
    base_enemies: int


Evaluator = Callable[[SimState, EvalContext], float]
# None = not terminal; a float is the position's terminal value and must
# lie inside the objective's bounds or Star1 pruning turns unsound
TerminalFn = Callable[[SimState, EvalContext], "float | None"]


@dataclass(frozen=True)
class Objective:
    """Stage-condition-driven terminal test, leaf evaluator, and the value
    bounds Star1 prunes against. `bounds` None falls back to eval_bounds;
    a condition objective whose terminal returns win/loss rewards must
    supply bounds that contain them. Built from a stage definition by
    content.objectives.make_objective."""

    terminal: TerminalFn
    evaluator: Evaluator
    bounds: tuple[float, float] | None = None


def default_evaluator(state: SimState, ctx: EvalContext) -> float:
    w = ctx.weights
    allies = state.allies()
    enemies = state.enemies()
    ally_hp = sum(u.hp / u.max_hp for u in allies)
    enemy_hp = sum(u.hp / u.max_hp for u in enemies)
    kills = ctx.base_enemies - len(enemies)
    losses = ctx.base_allies - len(allies)
    return w.ally_hp * ally_hp - w.enemy_hp * enemy_hp + w.kill * kills - w.loss * losses


def eval_bounds(base_allies: int, base_enemies: int, w: EvalWeights) -> tuple[float, float]:
    vmax = w.ally_hp * base_allies + w.kill * base_enemies
    vmin = -(w.enemy_hp * base_enemies + w.loss * base_allies)
    return vmin, vmax


def wiped_out(state: SimState) -> bool:
    return not state.allies() or not state.enemies()


def annihilation_objective(evaluator: Evaluator | None = None) -> Objective:
    """The pre-condition-file behavior: one side wiped out ends the search
    and the leaf evaluator prices the wipeout."""
    chosen = evaluator or default_evaluator

    def terminal(state: SimState, ctx: EvalContext) -> float | None:
        return chosen(state, ctx) if wiped_out(state) else None

    return Objective(terminal=terminal, evaluator=chosen)
