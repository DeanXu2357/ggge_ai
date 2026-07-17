"""Advice execution primitives: the solver's best decision, as tap points.

Pure functions with no device I/O -- the controller's reactive handlers
call them and perform the taps, so every step keeps the existing
act -> verify contract. Failure taxonomy per the user's 2026-07-14 call:
"no opinion" (the solver has nothing to say) demotes one activation to the
greedy path, while an alignment failure (executor, observer and game
disagree about the board) aborts the battle immediately -- early
development wants loud early errors, not papering-over.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import vision
from .advisor import Advice
from ..content.kit import UnitSpec
from .identity import IdentityResolver
from .observe import SIG_MATCH_RADIUS
from .state import BattleState, Point
from .tacmap import TacticalMap
from .tracker import SIG_ALIAS_MAX_DISTANCE


@dataclass
class ActivationPlan:
    """One unit's pilot activation, carried on _ActionState and cleared by
    its reset() alongside the greedy flags."""

    advice: Advice
    ally_id: str
    unit_world: Point
    camera: Point
    weapon_slot: int | None = None
    switch_budget: int = 4
    move_done: bool = False


def identify(
    frame, tacmap: TacticalMap, origin: tuple[int, int]
) -> tuple[Point, Point] | None:
    """Recover (unit_world, camera) for the selected unit via constellation
    anchoring. The game recentered on the unit, so `origin` (move-cell
    centroid, else screen center) is its screen position; the anchor
    translation lifts it to world coordinates. None = alignment failure."""
    arcs = (
        vision.find_ally_units(frame)
        + vision.find_enemy_units(frame)
        + vision.find_third_party_units(frame)
    )
    camera = tacmap.anchor(origin, arcs)
    if camera is None:
        return None
    unit_world = (origin[0] + camera[0], origin[1] + camera[1])
    return unit_world, camera


def resolve_ally(battle: BattleState, unit_world: Point) -> str | None:
    """The BattleState ally the identified unit is, required unique within
    the sig-match radius; a contested match is an alignment failure."""
    radius2 = SIG_MATCH_RADIUS**2
    in_radius = []
    for unit in battle.allies():
        if unit.world_pos is None:
            continue
        d2 = (unit.world_pos[0] - unit_world[0]) ** 2 + (
            unit.world_pos[1] - unit_world[1]
        ) ** 2
        if d2 <= radius2:
            in_radius.append(unit.unit_id)
    if len(in_radius) != 1:
        return None
    return in_radius[0]


def move_tap(
    advice: Advice, camera: Point, cells: list[tuple[int, int]]
) -> tuple[str, tuple[int, int]] | None:
    """Screen tap executing advice.move_world: snap to the nearest extracted
    move cell, or the raw screen point when no cells were extracted (bright
    maps); a nearest cell farther than the match radius from the desired
    point means the board and the game disagree -- alignment failure."""
    if advice.move_world is None:
        return None
    desired = (advice.move_world[0] - camera[0], advice.move_world[1] - camera[1])
    if cells:
        cell = vision.nearest_point(cells, desired)
        d2 = (cell[0] - desired[0]) ** 2 + (cell[1] - desired[1]) ** 2
        if d2 > SIG_MATCH_RADIUS**2:
            return None
        return "cell", (int(cell[0]), int(cell[1]))
    return "direct", (round(desired[0]), round(desired[1]))


def verifiable_target(target_id: str | None, resolver: IdentityResolver) -> bool:
    """Only a target whose uid maps to an expected name signature can
    pass the forecast check; a positional id (unconfirmed arc) leaves
    the attack unverifiable."""
    if target_id is None:
        return False
    return resolver.expected_sig(target_id) is not None


def slot_for(advice: Advice, spec: UnitSpec | None) -> int | None:
    """Weapon slot for advice.weapon via the slot i <-> spec.weapons[i-1]
    convention (reconcile.py); None when the spec cannot name it."""
    if spec is None or advice.weapon is None:
        return None
    for i, weapon in enumerate(spec.weapons, start=1):
        if weapon.name == advice.weapon:
            return i
    return None


def target_ok(
    forecast,
    advice: Advice,
    resolver: IdentityResolver,
    *,
    believed_hp: int | None = None,
) -> bool:
    """Composite verification that the locked target is the advised uid:
    the forecast signature must sit within jitter tolerance of the uid's
    expected signature (necessary), and when several uids share that
    machine signature the forecast HP must agree with the tracked belief
    (compared only when both sides are known) -- same machine, different
    pilot, different HP history. A positional id (unconfirmed arc, no
    expected signature) can never be verified."""
    if forecast is None or forecast.target_name_sig is None or advice.target_id is None:
        return False
    expected = resolver.expected_sig(advice.target_id)
    if expected is None:
        return False
    try:
        distance = vision.signature_distance(forecast.target_name_sig, expected)
    except ValueError:
        return False
    if distance > SIG_ALIAS_MAX_DISTANCE:
        return False
    if len(resolver.candidates(forecast.target_name_sig)) > 1:
        if (
            believed_hp is not None
            and forecast.target_hp is not None
            and forecast.target_hp != believed_hp
        ):
            return False
    return True
