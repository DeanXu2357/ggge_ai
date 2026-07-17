"""Stage definition -> opening SimState + EventTable + Objective.

The pure-simulation entry (M8-4): the same definition file the live
observer validates against opens a battle offline -- layout units become
board SimUnits, reinforcement spawns become event templates (quantized
on the same grid as the layout so their cells line up), conditions
compile into the solver objective, and every assumed number is reported.
This is both the offline stage-solving entry and the integration
carrier for the events/objective machinery.
"""

from __future__ import annotations

from ..content.kit import SpecDefaults, UnitSpec
from .bridge import build_sim_state
from .objectives import make_objective
from ..sim import EventTable, SimEvent, SimState, SimUnit
from ..sim import EvalWeights, Objective
from .stage_def import StageDefinition
from .state import BattleState, Faction, UnitState

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
    battle = BattleState(turn=1)
    specs: dict[str, UnitSpec] = {}
    notes: list[str] = []

    def _admit(unit) -> None:
        world = (
            unit.cell[0] * defn.cell_size,
            unit.cell[1] * defn.cell_size,
        )
        stats = unit.stats or {}
        battle.add_unit(
            UnitState(
                unit_id=unit.uid,
                faction=_FACTION.get(unit.faction, Faction.ENEMY),
                world_pos=world,
                hp=stats.get("hp"),
                en=stats.get("en"),
                max_hp=stats.get("hp"),
            )
        )
        if unit.stats:
            try:
                spec, assumptions = unit.to_spec()
            except TypeError:
                notes.append(f"{unit.uid}: stats incomplete, entering spec-less")
            else:
                specs[unit.uid] = spec
                notes.extend(f"{unit.uid}: {a}" for a in assumptions)

    spawn_uids: set[str] = set()
    for unit in defn.layout:
        _admit(unit)
    for event in defn.events:
        for unit in event.spawn_units():
            spawn_uids.add(unit.uid)
            _admit(unit)

    pending = tuple(
        event.event_id for event in defn.events if event.event_id not in fired_events
    )
    bridged = build_sim_state(
        battle,
        specs,
        cell_size=defn.cell_size,
        defaults=defaults,
        pending_events=pending,
    )
    state = bridged.state
    state.fired_events = tuple(fired_events)
    notes.extend(bridged.assumptions)

    templates = {u.unit_id: u for u in state.units if u.unit_id in spawn_uids}
    state.units = [u for u in state.units if u.unit_id not in spawn_uids]
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
