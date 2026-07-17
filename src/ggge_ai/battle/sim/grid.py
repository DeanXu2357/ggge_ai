"""Grid reachability and path blocking (simulator v1 geometry).

Movement rules (docs/agent-architecture.md): units of another faction block
the route -- enemies obstruct our paths and, symmetrically, we obstruct
theirs; own-faction units can be passed through but no move may end on any
occupied cell. Third-party units block both sides under the same rule
(assumed until calibrated on device).

Reachability is a BFS over king moves (Chebyshev metric, every step costs 1)
bounded by the unit's move_range and, when the state carries them, the map
bounds. The results plug into the simulator through the existing
MoveValidator seam and the `reach` parameter of legal_attacks, which makes
destination legality and attack-candidate generation path-aware: blocking a
choke point now actually removes the attacks that needed to pass it, so the
search can discover blocking and support-splitting placements on its own.
"""

from __future__ import annotations

from collections import deque

from .core import Cell, SimState, SimUnit

_KING_STEPS: tuple[Cell, ...] = (
    (-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1),
)


def blocking_cells(state: SimState, unit: SimUnit) -> set[Cell]:
    """Cells the unit may not enter nor pass through: other factions' units."""
    return {
        u.pos
        for u in state.units
        if u.alive and u is not unit and u.faction is not unit.faction
    }


def occupied_cells(state: SimState, unit: SimUnit) -> set[Cell]:
    """Cells the unit may not end on: every other living unit."""
    return {u.pos for u in state.units if u.alive and u is not unit}


def _in_bounds(state: SimState, cell: Cell) -> bool:
    if state.bounds is None:
        return True
    (min_x, min_y), (max_x, max_y) = state.bounds
    return min_x <= cell[0] <= max_x and min_y <= cell[1] <= max_y


def reachable_cells(state: SimState, unit: SimUnit) -> set[Cell]:
    """Every cell the unit can end its move on, path blocking included."""
    blocked = blocking_cells(state, unit)
    occupied = occupied_cells(state, unit)
    seen = {unit.pos}
    out = {unit.pos}
    frontier = deque([(unit.pos, 0)])
    while frontier:
        pos, dist = frontier.popleft()
        if dist == unit.move_range:
            continue
        for dx, dy in _KING_STEPS:
            nxt = (pos[0] + dx, pos[1] + dy)
            if nxt in seen or nxt in blocked or not _in_bounds(state, nxt):
                continue
            seen.add(nxt)
            frontier.append((nxt, dist + 1))
            if nxt not in occupied:
                out.add(nxt)
    return out


def grid_move_validator(state: SimState, unit: SimUnit, dest: Cell) -> bool:
    """MoveValidator drop-in: destination must be BFS-reachable."""
    return dest in reachable_cells(state, unit)


def reach_provider(state: SimState, unit: SimUnit) -> set[Cell]:
    """ReachProvider drop-in for SolverConfig and the enemy models."""
    return reachable_cells(state, unit)
