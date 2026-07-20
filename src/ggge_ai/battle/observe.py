"""Factionless scan pool -> BattleState: the advisor's view of the board.

Arc detection only ever says "a unit stands here" (定案 5); faction and
identity are claimed by evidence, the same ladder for every point:

1. a resolver identity (survey/refresh position) claims it -- faction
   comes from the definition (enemy or third party);
2. a tracker-learned ally sig claims it (positions learned from
   card-driven activations: tap card -> camera centers -> anchor);
3. a census ally position claims it (deploy-slot matches from the
   opening seed / identify pass -- our machines that have not acted
   yet and therefore have not moved);
4. nothing claims it: dropped with a note, never a default-stat ghost.

This replaces the hub_poisoned special case wholesale -- the pinned
pink-arc bug made red-band arcs untrustworthy on our-turn hubs, and the
settled answer is that NO arc color is ever a faction verdict, so every
scan is treated the same way.
"""

from __future__ import annotations

from .state import BattleState, Faction, UnitState
from .tacmap import Point

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


def _nearest_point(
    point: Point, candidates: list[Point], taken: set[int]
) -> int | None:
    best_i, best_d2 = None, SIG_MATCH_RADIUS**2
    for i, pos in enumerate(candidates):
        if i in taken:
            continue
        d2 = (pos[0] - point[0]) ** 2 + (pos[1] - point[1]) ** 2
        if d2 <= best_d2:
            best_i, best_d2 = i, d2
    return best_i


def build_battle_state(
    units: list[Point],
    *,
    specs_by_id: dict | None = None,
    id_positions: dict[str, Point] | None = None,
    ally_id_positions: dict[str, Point] | None = None,
    ally_points: list[Point] | None = None,
    faction_by_id: dict[str, Faction] | None = None,
    turn: int = 1,
    notes: list[str] | None = None,
) -> BattleState:
    """Evidence-claimed board over the factionless pool. id_positions
    carries resolver identities (their faction from faction_by_id,
    default ENEMY); ally_id_positions carries tracker-learned ally sigs
    (a sig-named ally keeps its identity across turns and can carry a
    spec); ally_points carries the census ally positions for machines
    that have not acted yet. Unclaimed points are dropped with a note."""
    specs_by_id = specs_by_id or {}
    id_positions = id_positions or {}
    ally_id_positions = ally_id_positions or {}
    ally_points = ally_points or []
    faction_by_id = faction_by_id or {}
    battle = BattleState(turn=turn)
    taken: set[str] = set()
    taken_allies: set[str] = set()
    taken_census: set[int] = set()
    anon = 0
    for point in units:
        uid = _nearest_sig(point, id_positions, taken)
        if uid is not None:
            taken.add(uid)
            spec = specs_by_id.get(uid)
            battle.add_unit(
                UnitState(
                    unit_id=uid,
                    faction=faction_by_id.get(uid, Faction.ENEMY),
                    world_pos=point,
                    max_hp=spec.max_hp if spec is not None else None,
                )
            )
            continue
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
            continue
        census_i = _nearest_point(point, ally_points, taken_census)
        if census_i is not None:
            taken_census.add(census_i)
            anon += 1
            battle.add_unit(
                UnitState(
                    unit_id=f"ally_{anon}",
                    faction=Faction.ALLY,
                    world_pos=point,
                )
            )
            continue
        if notes is not None:
            notes.append(
                f"unit at ({point[0]:.0f}, {point[1]:.0f}) dropped: "
                "no identity, ally sig or census position claims it"
            )
    return battle
