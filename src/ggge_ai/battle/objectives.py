"""Stage conditions -> solver Objective.

The v1 taxonomy: victory = annihilate / decapitate{targets} /
turn_limit{turns} / reach{cell, radius}; defeat = all_allies_lost
(always implied) / ward_lost{wards} / turn_limit{turns}. Anything else
was recorded verbatim at transcription time and stays inert here -- and
when no victory condition is recognized at all, the objective degrades
to annihilate with a loud note, never silently.

Terminal values sit at a fixed margin outside the leaf-evaluation range
(win positive, loss negative; defeat checked first when both hold), so
a reachable win outranks any HP arithmetic -- a decapitation stage
walks to the commander instead of farming kills. The bounds returned
with the objective contain those terminal values; Star1 pruning is
unsound without that. Leaf evaluation stays deliberately simple in v1
(condition shaping on top of the default evaluator: extra HP pressure
on decapitation targets, ward health counted like our own); terminal
correctness is the value here, evaluator tuning is live-battle
iteration work.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from ..sim import SimState
from ..sim.objective import (
    EvalContext,
    EvalWeights,
    Objective,
    default_evaluator,
    eval_bounds,
)
from ..content.stage_def import Condition, StageConditions
from .state import Faction

log = logging.getLogger(__name__)

TERMINAL_MARGIN = 2.0

_Check = Callable[[SimState], bool]


def _dead(state: SimState, uid: str) -> bool:
    unit = state.unit(uid)
    return unit is None or not unit.alive


def _annihilate(state: SimState) -> bool:
    return not state.enemies()


def _all_allies_lost(state: SimState) -> bool:
    return not state.allies()


def _decapitate(targets: tuple[str, ...]) -> _Check:
    return lambda state: all(_dead(state, uid) for uid in targets)


def _ward_lost(wards: tuple[str, ...]) -> _Check:
    return lambda state: any(_dead(state, uid) for uid in wards)


def _turn_expired(turns: int) -> _Check:
    return lambda state: state.turn > turns


def _reach(cell: tuple[int, int], radius: int) -> _Check:
    def check(state: SimState) -> bool:
        return any(
            max(abs(u.pos[0] - cell[0]), abs(u.pos[1] - cell[1])) <= radius
            for u in state.allies()
        )

    return check


def _compile_victory(cond: Condition, notes: list[str]) -> _Check | None:
    if cond.type == "annihilate":
        return _annihilate
    if cond.type == "decapitate":
        targets = tuple(cond.params.get("targets", ()))
        if not targets:
            notes.append("decapitate condition without targets, inert")
            return None
        return _decapitate(targets)
    if cond.type == "turn_limit":
        return _turn_expired(int(cond.params["turns"]))
    if cond.type == "reach":
        cell = tuple(cond.params["cell"])
        return _reach(cell, int(cond.params.get("radius", 0)))
    notes.append(f"victory condition '{cond.type}' is outside the taxonomy, inert")
    return None


def _compile_defeat(cond: Condition, notes: list[str]) -> _Check | None:
    if cond.type == "all_allies_lost":
        return _all_allies_lost
    if cond.type == "ward_lost":
        wards = tuple(cond.params.get("wards", ()))
        if not wards:
            notes.append("ward_lost condition without wards, inert")
            return None
        return _ward_lost(wards)
    if cond.type == "turn_limit":
        return _turn_expired(int(cond.params["turns"]))
    notes.append(f"defeat condition '{cond.type}' is outside the taxonomy, inert")
    return None


def make_objective(
    conditions: StageConditions,
    base_allies: int,
    base_enemies: int,
    weights: EvalWeights | None = None,
) -> tuple[Objective, list[str]]:
    weights = weights or EvalWeights()
    notes: list[str] = []

    victory = [c for c in (_compile_victory(v, notes) for v in conditions.victory) if c]
    if not victory:
        notes.append("no recognized victory condition, degrading to annihilate")
        victory.append(_annihilate)

    defeat = [c for c in (_compile_defeat(d, notes) for d in conditions.defeat) if c]
    if not any(d is _all_allies_lost for d in defeat):
        defeat.insert(0, _all_allies_lost)

    decap_targets: tuple[str, ...] = ()
    wards: tuple[str, ...] = ()
    for cond in conditions.victory:
        if cond.type == "decapitate":
            decap_targets += tuple(cond.params.get("targets", ()))
    for cond in conditions.defeat:
        if cond.type == "ward_lost":
            wards += tuple(cond.params.get("wards", ()))

    vmin, vmax = eval_bounds(base_allies, base_enemies, weights)
    vmin -= weights.enemy_hp * len(decap_targets)
    vmax += weights.ally_hp * len(wards)
    terminal_value = TERMINAL_MARGIN * max(abs(vmin), abs(vmax), 1.0)

    def terminal(state: SimState, ctx: EvalContext) -> float | None:
        for check in defeat:
            if check(state):
                return -terminal_value
        for check in victory:
            if check(state):
                return terminal_value
        return None

    def evaluator(state: SimState, ctx: EvalContext) -> float:
        value = default_evaluator(state, ctx)
        w = ctx.weights
        for uid in decap_targets:
            unit = state.unit(uid)
            if unit is not None and unit.alive and unit.faction is Faction.ENEMY:
                value -= w.enemy_hp * (unit.hp / unit.max_hp)
        for uid in wards:
            unit = state.unit(uid)
            if unit is not None and unit.alive:
                value += w.ally_hp * (unit.hp / unit.max_hp)
        return value

    for note in notes:
        log.warning("objective: %s", note)
    return (
        Objective(
            terminal=terminal,
            evaluator=evaluator,
            bounds=(-terminal_value, terminal_value),
        ),
        notes,
    )
