"""Tactical map -> BattleState: the advisor's view of the board.

Enemy points that landed near an intel-sweep tap adopt that unit's name
signature as their unit_id, which is what lets an advisor proposal be
reconciled against the weapon-select forecast later (both speak sigs).
Units without a matched signature get positional ids and stay spec-less;
the bridge's assumption machinery reports them.
"""

from __future__ import annotations

from .state import BattleState, Faction, UnitState
from .tacmap import Point, TacticalMap

# a tap and the arc-scan center of the same unit can sit a cell apart;
# 1.5 cells at the measured ~95px pitch keeps neighbors unambiguous
SIG_MATCH_RADIUS = 145.0


def _nearest_sig(
    point: Point, sig_positions: dict[str, Point], taken: set[str]
) -> str | None:
    best_sig, best_d2 = None, SIG_MATCH_RADIUS**2
    for sig, pos in sig_positions.items():
        if sig in taken:
            continue
        d2 = (pos[0] - point[0]) ** 2 + (pos[1] - point[1]) ** 2
        if d2 <= best_d2:
            best_sig, best_d2 = sig, d2
    return best_sig


def build_battle_state(
    tacmap: TacticalMap,
    *,
    specs_by_sig: dict | None = None,
    sig_positions: dict[str, Point] | None = None,
    turn: int = 1,
) -> BattleState:
    specs_by_sig = specs_by_sig or {}
    sig_positions = sig_positions or {}
    battle = BattleState(turn=turn)
    for i, point in enumerate(tacmap.allies, start=1):
        battle.add_unit(
            UnitState(unit_id=f"ally_{i}", faction=Faction.ALLY, world_pos=point)
        )
    taken: set[str] = set()
    for i, point in enumerate(tacmap.enemies, start=1):
        sig = _nearest_sig(point, sig_positions, taken)
        unit_id = sig if sig is not None else f"enemy_{i}"
        max_hp = None
        if sig is not None:
            taken.add(sig)
            spec = specs_by_sig.get(sig)
            if spec is not None:
                max_hp = spec.max_hp
        battle.add_unit(
            UnitState(
                unit_id=unit_id,
                faction=Faction.ENEMY,
                world_pos=point,
                max_hp=max_hp,
            )
        )
    for i, point in enumerate(tacmap.third_party, start=1):
        battle.add_unit(
            UnitState(unit_id=f"third_{i}", faction=Faction.THIRD_PARTY, world_pos=point)
        )
    return battle
