"""Stage definition -> opening SimState + EventTable + Objective.

The pure-simulation entry (M8-4): the same definition file the live
observer validates against opens a battle offline -- layout units become
board SimUnits, reinforcement spawns become event templates, conditions
compile into the solver objective, and every assumed number is reported.
Cells come verbatim from the definition (the stage grid's own origin);
no BattleState or bridge is involved, so the offline path shares nothing
with perception. This is both the offline stage-solving entry and the
integration carrier for the events/objective machinery.
"""

from __future__ import annotations

from ..sim import Cell, EventTable, SimEvent, SimState, SimUnit, nearest_free_cell
from ..sim import EvalWeights, Objective
from ..sim.vocab import Faction
from .grounding import ground_unit
from .kit import SpecDefaults
from .objectives import make_objective
from .stage_def import StageDefinition, StageUnit

_FACTION = {"enemy": Faction.ENEMY, "third_party": Faction.THIRD_PARTY}


def to_sim_state(
    defn: StageDefinition,
    our_units: list[SimUnit],
    *,
    weights: EvalWeights | None = None,
    defaults: SpecDefaults | None = None,
    fired_events: tuple[str, ...] = (),
) -> tuple[SimState, EventTable, Objective, list[str]]:
    """Open the stage offline. our_units are caller-built SimUnits on the
    same cell grid (the roster is not stage content); fired_events lets a
    mid-battle caller exclude events the live run already observed."""
    defaults = defaults or SpecDefaults()
    notes: list[str] = []
    pending = tuple(
        event.event_id for event in defn.events if event.event_id not in fired_events
    )
    state = SimState(turn=1, pending_events=pending)
    state.fired_events = tuple(fired_events)
    taken: set[Cell] = set()

    def _ground(unit: StageUnit) -> SimUnit:
        cell: Cell = tuple(unit.cell)
        if cell in taken:
            free = nearest_free_cell(cell, taken)
            notes.append(f"{unit.uid}: cell {cell} occupied, nudged to {free}")
            cell = free
        taken.add(cell)
        spec = None
        if unit.stats:
            try:
                spec, spec_notes = unit.to_spec()
            except TypeError:
                notes.append(f"{unit.uid}: stats incomplete, entering spec-less")
            else:
                notes.extend(f"{unit.uid}: {a}" for a in spec_notes)
        stats = unit.stats or {}
        grounded, unit_notes = ground_unit(
            unit.uid,
            _FACTION.get(unit.faction, Faction.ENEMY),
            cell,
            spec,
            defaults,
            hp=stats.get("hp"),
            max_hp=stats.get("hp"),
            en=stats.get("en"),
        )
        notes.extend(unit_notes)
        return grounded

    for unit in defn.layout:
        state.add_unit(_ground(unit))

    templates: dict[str, SimUnit] = {}
    for event in defn.events:
        for unit in event.spawn_units():
            templates[unit.uid] = _ground(unit)

    table: EventTable = {}
    for event in defn.events:
        effect = dict(event.effect)
        if effect.get("type") == "spawn":
            effect["units"] = [
                templates[u.uid] for u in event.spawn_units() if u.uid in templates
            ]
        table[event.event_id] = SimEvent(
            event_id=event.event_id, trigger=dict(event.trigger), effect=effect
        )

    for unit in our_units:
        state.add_unit(unit)

    base_allies = len(state.allies())
    base_enemies = len(state.enemies())
    objective, objective_notes = make_objective(
        defn.conditions, base_allies, base_enemies, weights
    )
    notes.extend(objective_notes)
    return state, table, objective, notes
