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
    specs_by_id: dict | None = None,
    id_positions: dict[str, Point] | None = None,
    ally_id_positions: dict[str, Point] | None = None,
    turn: int = 1,
    hub_poisoned: bool = False,
    notes: list[str] | None = None,
) -> BattleState:
    """Arc color is a first-layer heuristic, never a faction verdict on its
    own (user-settled 2026-07-14): blue/teal arcs have no known
    counterexample and pass through, but a red-band arc on an our-turn hub
    scan is "enemy OR un-acted ally" (the pinned pink-arc bug, per-pixel
    inseparable). hub_poisoned marks such a scan; each red-band point is
    then resolved by evidence -- an enemy sig position first (intel taps,
    per-turn refresh), a tracked ally position second (positions learned
    from card-driven activations: tap card -> camera centers -> anchor),
    and dropped with a note when neither claims it, instead of entering
    the sim as a default-stat ghost.

    ally_id_positions lets allies adopt their name signature the same way
    enemies do (learned incrementally as units act, tracker-fed) -- a
    sig-named ally keeps its identity across turns and can carry a spec."""
    specs_by_id = specs_by_id or {}
    id_positions = id_positions or {}
    ally_id_positions = ally_id_positions or {}
    battle = BattleState(turn=turn)
    taken_allies: set[str] = set()
    for i, point in enumerate(tacmap.allies, start=1):
        sig = _nearest_sig(point, ally_id_positions, taken_allies)
        max_hp = None
        if sig is not None:
            taken_allies.add(sig)
            spec = specs_by_id.get(sig)
            if spec is not None:
                max_hp = spec.max_hp
        battle.add_unit(
            UnitState(
                unit_id=sig if sig is not None else f"ally_{i}",
                faction=Faction.ALLY,
                world_pos=point,
                max_hp=max_hp,
            )
        )
    taken: set[str] = set()
    for i, point in enumerate(tacmap.enemies, start=1):
        sig = _nearest_sig(point, id_positions, taken)
        if sig is None and hub_poisoned:
            ally_sig = _nearest_sig(point, ally_id_positions, taken_allies)
            if ally_sig is not None:
                taken_allies.add(ally_sig)
                spec = specs_by_id.get(ally_sig)
                battle.add_unit(
                    UnitState(
                        unit_id=ally_sig,
                        faction=Faction.ALLY,
                        world_pos=point,
                        max_hp=spec.max_hp if spec is not None else None,
                    )
                )
                if notes is not None:
                    notes.append(
                        f"red-band arc at ({point[0]:.0f}, {point[1]:.0f}) "
                        f"resolved as un-acted ally {ally_sig[:6]} "
                        "(tracked position)"
                    )
                continue
            if notes is not None:
                notes.append(
                    f"enemy arc at ({point[0]:.0f}, {point[1]:.0f}) dropped: "
                    "no sig confirmation on a poisoned hub scan"
                )
            continue
        unit_id = sig if sig is not None else f"enemy_{i}"
        max_hp = None
        if sig is not None:
            taken.add(sig)
            spec = specs_by_id.get(sig)
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
