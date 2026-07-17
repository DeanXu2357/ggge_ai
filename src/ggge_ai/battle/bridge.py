"""BattleState -> SimState bridge: the perception-to-search hand-off.

The unified board (battle.state) speaks world pixels and optional numbers;
the simulator speaks grid cells and required numbers. This module owns the
geometry half of the hand-off -- quantizing world positions onto the cell
grid, nudging collisions apart, remembering the origin so a sim cell can
be translated back to world pixels -- and delegates the number and
capability half to content.grounding, which reports every assumption so
the ledger can flag advice that ran on guessed numbers.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from ..content.grounding import ground_unit
from ..content.kit import SpecDefaults, UnitSpec
from ..sim import Cell, SimState, nearest_free_cell
from .state import BattleState, Point


@dataclass
class BridgeResult:
    state: SimState
    origin: Point
    cell_size: float
    assumptions: list[str] = field(default_factory=list)

    def to_world(self, cell: Cell) -> Point:
        return (
            self.origin[0] + cell[0] * self.cell_size,
            self.origin[1] + cell[1] * self.cell_size,
        )


def _quantize(world: Point, origin: Point, cell_size: float) -> Cell:
    return (
        round((world[0] - origin[0]) / cell_size),
        round((world[1] - origin[1]) / cell_size),
    )


def build_sim_state(
    battle: BattleState,
    specs: Mapping[str, UnitSpec],
    *,
    cell_size: float,
    defaults: SpecDefaults | None = None,
    pending_events: tuple[str, ...] = (),
) -> BridgeResult:
    defaults = defaults or SpecDefaults()
    assumptions: list[str] = []
    placed = [u for u in battle.units if u.world_pos is not None]
    for u in battle.units:
        if u.world_pos is None:
            assumptions.append(f"{u.unit_id}: no world position, left out of the simulation")
    if placed:
        origin = (
            min(u.world_pos[0] for u in placed),
            min(u.world_pos[1] for u in placed),
        )
    else:
        origin = (0.0, 0.0)

    state = SimState(turn=battle.turn, pending_events=pending_events)
    taken: set[Cell] = set()
    for u in placed:
        cell = _quantize(u.world_pos, origin, cell_size)
        if cell in taken:
            free = nearest_free_cell(cell, taken)
            assumptions.append(f"{u.unit_id}: cell {cell} occupied, nudged to {free}")
            cell = free
        taken.add(cell)

        unit, notes = ground_unit(
            u.unit_id,
            u.faction,
            cell,
            specs.get(u.unit_id),
            defaults,
            hp=u.hp,
            max_hp=u.max_hp,
            en=u.en,
            acted=u.acted,
            capabilities=u.capabilities,
        )
        assumptions.extend(notes)
        state.add_unit(unit)
    return BridgeResult(
        state=state, origin=origin, cell_size=cell_size, assumptions=assumptions
    )
