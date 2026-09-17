"""The wire form of the battle state (spec: docs/spec/battle-engine-protocol.md).

'ggge_ai/engine/state.py' holds the Python structs and the Go package
'engine/battle' holds the same ones. 'tests/test_engine_codec.py' compares
the two field lists.

Rules of the wire form:

- A cell is a JSON pair, in the order of the Python tuple.
- A field that holds None is null on the wire, and null decodes back to None.
- The encoder writes every field. A decoder that meets an absent field takes
  the zero of the type of the field, because the Go decoder does the same.
- The stance 'none' does not reach the wire: the response attack menu of the
  game holds no decline button, so the contract lists no such option.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contract import (
    ActionKind,
    Cell,
    Direction,
    Faction,
    MapWeaponAffects,
    SkillAffects,
    SkillSource,
    Stance,
    Terrain,
)
from .state import (
    Ability,
    BattleState,
    Debuff,
    Decision,
    EventTable,
    MapWeapon,
    Mech,
    Pilot,
    ResponseAttack,
    Stated,
    SupportAttacker,
    ShapeRange,
    Skill,
    StageEvent,
    TerrainCell,
    Unit,
    Weapon,
)

SPAWN = "spawn"


def encode_shape_range(shape: ShapeRange) -> dict[str, Any]:
    return {
        "cells": [_cell(cell) for cell in shape.cells],
        "direction": str(shape.direction),
    }


def decode_shape_range(payload: dict[str, Any]) -> ShapeRange:
    _known(payload, encode_shape_range(ShapeRange()), "shape range")
    return ShapeRange(
        cells=[_as_cell(raw, "shape cell") for raw in payload.get("cells") or ()],
        direction=_direction(payload.get("direction")),
    )


def encode_weapon(weapon: Weapon) -> dict[str, Any]:
    return {
        "name": weapon.name,
        "power": weapon.power,
        "range_min": weapon.range_min,
        "range_max": weapon.range_max,
        "en_cost": weapon.en_cost,
        "accuracy": weapon.accuracy,
        "usable_after_move": weapon.usable_after_move,
        "debuff_kind": weapon.debuff_kind,
        "debuff_magnitude": weapon.debuff_magnitude,
        "categories": list(weapon.categories) or None,
    }


def decode_weapon(payload: dict[str, Any]) -> Weapon:
    _known(payload, encode_weapon(Weapon(name="", power=0.0)), "weapon")
    return Weapon(
        name=_str(payload, "name"),
        power=_float(payload, "power"),
        range_min=_int(payload, "range_min"),
        range_max=_int(payload, "range_max"),
        en_cost=_int(payload, "en_cost"),
        accuracy=_float(payload, "accuracy"),
        usable_after_move=_bool(payload, "usable_after_move"),
        debuff_kind=_optional_str(payload, "debuff_kind"),
        debuff_magnitude=_float(payload, "debuff_magnitude"),
        categories=[str(name) for name in payload.get("categories") or ()],
    )


def encode_map_weapon(weapon: MapWeapon) -> dict[str, Any]:
    return {
        "name": weapon.name,
        "power": weapon.power,
        "apply_shape": encode_shape_range(weapon.apply_shape),
        "effect_shape": encode_shape_range(weapon.effect_shape),
        "ammo_max": weapon.ammo_max,
        "en_cost": weapon.en_cost,
        "accuracy": weapon.accuracy,
        "affects": str(weapon.affects),
        "usable_after_move": weapon.usable_after_move,
        "debuff_kind": weapon.debuff_kind,
        "debuff_magnitude": weapon.debuff_magnitude,
        "categories": list(weapon.categories) or None,
    }


def decode_map_weapon(payload: dict[str, Any]) -> MapWeapon:
    _known(payload, encode_map_weapon(MapWeapon(name="", power=0.0)), "map weapon")
    return MapWeapon(
        name=_str(payload, "name"),
        power=_float(payload, "power"),
        apply_shape=decode_shape_range(payload.get("apply_shape") or {}),
        effect_shape=decode_shape_range(payload.get("effect_shape") or {}),
        ammo_max=_int(payload, "ammo_max"),
        en_cost=_int(payload, "en_cost"),
        accuracy=_float(payload, "accuracy"),
        affects=_map_weapon_affects(payload.get("affects")),
        usable_after_move=_bool(payload, "usable_after_move"),
        debuff_kind=_optional_str(payload, "debuff_kind"),
        debuff_magnitude=_float(payload, "debuff_magnitude"),
        categories=[str(name) for name in payload.get("categories") or ()],
    )


def encode_skill(skill: Skill) -> dict[str, Any]:
    return {
        "kind": str(skill.kind),
        "source": str(skill.source),
        "amount": skill.amount,
        "uses": skill.uses,
        "ends_activation": skill.ends_activation,
        "usable_after_move": skill.usable_after_move,
        "apply_shape": encode_shape_range(skill.apply_shape),
        "effect_shape": encode_shape_range(skill.effect_shape),
        "affects": str(skill.affects),
    }


def decode_skill(payload: dict[str, Any]) -> Skill:
    _known(payload, encode_skill(Skill(kind="")), "skill")
    return Skill(
        kind=_str(payload, "kind"),
        source=_skill_source(payload.get("source")),
        amount=_optional_float(payload, "amount"),
        uses=_int(payload, "uses"),
        ends_activation=_bool(payload, "ends_activation"),
        usable_after_move=_bool(payload, "usable_after_move"),
        apply_shape=decode_shape_range(payload.get("apply_shape") or {}),
        effect_shape=decode_shape_range(payload.get("effect_shape") or {}),
        affects=_skill_affects(payload.get("affects")),
    )


def encode_debuff(debuff: Debuff) -> dict[str, Any]:
    return {
        "kind": debuff.kind,
        "magnitude": debuff.magnitude,
        "applied_phase": debuff.applied_phase,
    }


def decode_debuff(payload: dict[str, Any]) -> Debuff:
    _known(payload, encode_debuff(Debuff("", 0.0, 0)), "debuff")
    return Debuff(
        kind=_str(payload, "kind"),
        magnitude=_float(payload, "magnitude"),
        applied_phase=_int(payload, "applied_phase"),
    )


def encode_ability(ability: Ability) -> dict[str, Any]:
    return {
        "kind": ability.kind,
        "percent": ability.percent,
        "plus": ability.plus,
        "enemy_tag": ability.enemy_tag,
        "mech_tag": ability.mech_tag,
        "pilot_tag": ability.pilot_tag,
        "hp_rate_lte": ability.hp_rate_lte,
        "hp_rate_gte": ability.hp_rate_gte,
        "mech_type": ability.mech_type,
        "strike_role": ability.strike_role,
        "weapon_attribute": ability.weapon_attribute,
        "weapon_category": ability.weapon_category,
    }


def decode_ability(payload: dict[str, Any]) -> Ability:
    _known(payload, encode_ability(Ability(kind="k")), "ability")
    return Ability(
        kind=_str(payload, "kind"),
        percent=_float(payload, "percent"),
        plus=_int(payload, "plus"),
        enemy_tag=_int(payload, "enemy_tag"),
        mech_tag=_int(payload, "mech_tag"),
        pilot_tag=_int(payload, "pilot_tag"),
        hp_rate_lte=_int(payload, "hp_rate_lte"),
        hp_rate_gte=_int(payload, "hp_rate_gte"),
        mech_type=_int(payload, "mech_type"),
        strike_role=_optional_str(payload, "strike_role"),
        weapon_attribute=_optional_str(payload, "weapon_attribute"),
        weapon_category=_optional_str(payload, "weapon_category"),
    )


def encode_pilot(pilot: Pilot) -> dict[str, Any]:
    return {
        "ranged": pilot.ranged,
        "melee": pilot.melee,
        "awaken": pilot.awaken,
        "defense": pilot.defense,
        "reaction": pilot.reaction,
        "sp": pilot.sp,
        "tags": list(pilot.tags),
        "abilities": [encode_ability(entry) for entry in pilot.abilities],
    }


def decode_pilot(payload: dict[str, Any]) -> Pilot:
    _known(payload, encode_pilot(Pilot()), "pilot")
    return Pilot(
        ranged=_float(payload, "ranged"),
        melee=_float(payload, "melee"),
        awaken=_float(payload, "awaken"),
        defense=_float(payload, "defense"),
        reaction=_float(payload, "reaction"),
        sp=_int(payload, "sp"),
        tags=list(_ids(payload, "tags")),
        abilities=[decode_ability(entry) for entry in payload.get("abilities") or ()],
    )


def encode_mech(mech: Mech) -> dict[str, Any]:
    return {
        "hp": mech.hp,
        "en": mech.en,
        "attack": mech.attack,
        "defense": mech.defense,
        "mobility": mech.mobility,
        "move_range": mech.move_range,
        "weapons": [encode_weapon(weapon) for weapon in mech.weapons],
        "map_weapons": [encode_map_weapon(weapon) for weapon in mech.map_weapons],
        "tags": list(mech.tags),
        "type": mech.type,
        "abilities": [encode_ability(entry) for entry in mech.abilities],
    }


def decode_mech(payload: dict[str, Any]) -> Mech:
    _known(payload, encode_mech(Mech()), "mech")
    return Mech(
        hp=_int(payload, "hp"),
        en=_int(payload, "en"),
        attack=_float(payload, "attack"),
        defense=_float(payload, "defense"),
        mobility=_float(payload, "mobility"),
        move_range=_int(payload, "move_range"),
        weapons=[decode_weapon(entry) for entry in payload.get("weapons") or ()],
        map_weapons=[decode_map_weapon(entry) for entry in payload.get("map_weapons") or ()],
        tags=list(_ids(payload, "tags")),
        type=_int(payload, "type"),
        abilities=[decode_ability(entry) for entry in payload.get("abilities") or ()],
    )


def encode_unit(unit: Unit) -> dict[str, Any]:
    return {
        "faction": str(unit.faction),
        "size": _cell(unit.size),
        "pos": _cell(unit.pos),
        "hp": unit.hp,
        "en": unit.en,
        "sp": unit.sp,
        "mp": unit.mp,
        "move_range": unit.move_range,
        "acted": unit.acted,
        "chance_steps": unit.chance_steps,
        "support_attack_charges": unit.support_attack_charges,
        "support_defend_charges": unit.support_defend_charges,
        "skills": [encode_skill(skill) for skill in unit.skills],
        "map_weapon_ammo": list(unit.map_weapon_ammo),
        "debuffs": [encode_debuff(debuff) for debuff in unit.debuffs],
        "pilot": encode_pilot(unit.pilot),
        "mech": encode_mech(unit.mech),
        "has_shield": unit.has_shield,
        "support_defend_when_attack": unit.support_defend_when_attack,
    }


def decode_unit(payload: dict[str, Any]) -> Unit:
    _known(payload, encode_unit(Unit(faction=Faction.ALLY)), "unit")
    return Unit(
        faction=_faction(payload.get("faction")),
        size=_as_cell(payload.get("size", (1, 1)), "unit.size"),
        pos=_as_cell(payload.get("pos"), "unit.pos"),
        hp=_int(payload, "hp"),
        en=_int(payload, "en"),
        sp=_int(payload, "sp"),
        mp=_int(payload, "mp"),
        move_range=_int(payload, "move_range"),
        acted=_bool(payload, "acted"),
        chance_steps=_int(payload, "chance_steps"),
        support_attack_charges=_int(payload, "support_attack_charges"),
        support_defend_charges=_int(payload, "support_defend_charges"),
        skills=[decode_skill(entry) for entry in payload.get("skills") or ()],
        map_weapon_ammo=[int(count) for count in payload.get("map_weapon_ammo") or ()],
        debuffs=[decode_debuff(entry) for entry in payload.get("debuffs") or ()],
        pilot=decode_pilot(payload.get("pilot") or {}),
        mech=decode_mech(payload.get("mech") or {}),
        has_shield=_bool(payload, "has_shield"),
        support_defend_when_attack=_bool(payload, "support_defend_when_attack"),
    )


def encode_response_attack(response_attack: ResponseAttack) -> dict[str, Any]:
    if response_attack.stance is None:
        raise ValueError("A response attack with no stance does not reach the wire")
    return {
        "stance": str(response_attack.stance),
        "weapon_id": response_attack.weapon_id,
        "stated": None if response_attack.stated is None else encode_stated(response_attack.stated),
        "support_attackers": [
            encode_support_attacker(one) for one in response_attack.support_attackers
        ],
        "support_defender_id": response_attack.support_defender_id,
    }


def encode_stated(stated: Stated) -> dict[str, Any]:
    return {"crit": stated.crit, "hit": stated.hit}


def decode_stated(payload: dict[str, Any] | None) -> Stated | None:
    if payload is None:
        return None
    return Stated(crit=_bool(payload, "crit"), hit=_bool(payload, "hit"))


def encode_support_attacker(one: SupportAttacker) -> dict[str, Any]:
    return {
        "unit_id": one.unit_id,
        "weapon_id": one.weapon_id,
        "stated": None if one.stated is None else encode_stated(one.stated),
    }


def decode_support_attacker(payload: dict[str, Any]) -> SupportAttacker:
    return SupportAttacker(
        unit_id=_int(payload, "unit_id"),
        weapon_id=_int(payload, "weapon_id"),
        stated=decode_stated(payload.get("stated")),
    )


def decode_response_attack(payload: dict[str, Any]) -> ResponseAttack:
    _known(
        payload,
        encode_response_attack(ResponseAttack(stance=Stance.DODGE)),
        "response_attack",
    )
    stance = _stance(payload.get("stance"))
    return ResponseAttack(
        stance=stance,
        weapon_id=_optional_int(payload, "weapon_id"),
        stated=decode_stated(payload.get("stated")),
        support_attackers=tuple(
            decode_support_attacker(one) for one in payload.get("support_attackers") or ()
        ),
        support_defender_id=_optional_int(payload, "support_defender_id"),
    )


def encode_decision(decision: Decision) -> dict[str, Any]:
    return {
        "unit_id": decision.unit_id,
        "kind": str(decision.kind),
        "move_to": _optional_cell(decision.move_to),
        "target_id": decision.target_id,
        "weapon_id": decision.weapon_id,
        "map_weapon_id": decision.map_weapon_id,
        "amount": decision.amount,
        "response_attack": (
            None
            if decision.response_attack is None
            else encode_response_attack(decision.response_attack)
        ),
        "support_defender_id": decision.support_defender_id,
        "support_attacker_ids": list(decision.support_attacker_ids),
        "aim": _optional_cell(decision.aim),
        "hit": decision.hit,
        "counter_hit": decision.counter_hit,
        "support_hit": decision.support_hit,
    }


def decode_decision(payload: dict[str, Any]) -> Decision:
    _known(payload, encode_decision(Decision(unit_id=0, kind=ActionKind.STANDBY)), "decision")
    response_attack = payload.get("response_attack")
    return Decision(
        unit_id=_int(payload, "unit_id"),
        kind=_move_kind(payload.get("kind")),
        move_to=_optional_as_cell(payload.get("move_to"), "decision.move_to"),
        target_id=_optional_int(payload, "target_id"),
        weapon_id=_optional_int(payload, "weapon_id"),
        map_weapon_id=_optional_int(payload, "map_weapon_id"),
        amount=_optional_float(payload, "amount"),
        response_attack=(
            None if response_attack is None else decode_response_attack(response_attack)
        ),
        support_defender_id=_optional_int(payload, "support_defender_id"),
        support_attacker_ids=_ids(payload, "support_attacker_ids"),
        aim=_optional_as_cell(payload.get("aim"), "decision.aim"),
        hit=_optional_bool(payload, "hit"),
        counter_hit=_optional_bool(payload, "counter_hit"),
        support_hit=_optional_bool(payload, "support_hit"),
    )


def encode_event(event: StageEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "trigger": dict(event.trigger),
        "effect": _encode_effect(event.effect),
    }


def decode_event(payload: dict[str, Any]) -> StageEvent:
    _known(payload, {"event_id": "", "trigger": {}, "effect": {}}, "event")
    return StageEvent(
        event_id=_str(payload, "event_id"),
        trigger=dict(payload.get("trigger") or {}),
        effect=_decode_effect(payload.get("effect") or {}),
    )


def encode_events(events: EventTable) -> dict[str, Any]:
    return {event_id: encode_event(event) for event_id, event in sorted(events.items())}


def decode_events(payload: dict[str, Any]) -> EventTable:
    return {event_id: decode_event(body) for event_id, body in payload.items()}


def encode_terrain_cell(entry: TerrainCell) -> dict[str, Any]:
    return {"cell": _cell(entry.cell), "terrain": str(entry.terrain)}


def decode_terrain_cell(payload: dict[str, Any]) -> TerrainCell:
    _known(payload, encode_terrain_cell(TerrainCell((0, 0), Terrain.SPACE)), "terrain_cell")
    return TerrainCell(
        cell=_as_cell(payload.get("cell"), "terrain_cell.cell"),
        terrain=_terrain(payload.get("terrain")),
    )


def encode_state(state: BattleState) -> dict[str, Any]:
    return {
        "units": [encode_unit(unit) for unit in state.units],
        "phase": str(state.phase),
        "turn": state.turn,
        "bounds": None
        if state.bounds is None
        else [_cell(state.bounds[0]), _cell(state.bounds[1])],
        "pending_events": list(state.pending_events),
        "fired_events": list(state.fired_events),
        "terrain": None if state.terrain is None else str(state.terrain),
        "terrain_cells": [encode_terrain_cell(entry) for entry in state.terrain_cells],
    }


def decode_state(payload: dict[str, Any]) -> BattleState:
    _known(payload, encode_state(BattleState()), "state")
    bounds = payload.get("bounds")
    return BattleState(
        units=[decode_unit(entry) for entry in payload.get("units") or ()],
        phase=_faction(payload.get("phase")),
        turn=_int(payload, "turn"),
        bounds=None if bounds is None else _as_bounds(bounds),
        pending_events=tuple(str(name) for name in payload.get("pending_events") or ()),
        fired_events=tuple(str(name) for name in payload.get("fired_events") or ()),
        terrain=None if payload.get("terrain") is None else _terrain(payload["terrain"]),
        terrain_cells=tuple(
            decode_terrain_cell(entry) for entry in payload.get("terrain_cells") or ()
        ),
    )


def _encode_effect(effect: dict[str, Any]) -> dict[str, Any]:
    out = dict(effect)
    if out.get("type") == SPAWN:
        out["units"] = [encode_unit(unit) for unit in out.get("units") or ()]
    return out


def _decode_effect(effect: dict[str, Any]) -> dict[str, Any]:
    out = dict(effect)
    if out.get("type") == SPAWN:
        out["units"] = [decode_unit(entry) for entry in out.get("units") or ()]
    return out


def _cell(cell: Cell) -> list[int]:
    return [int(cell[0]), int(cell[1])]


def _optional_cell(cell: Cell | None) -> list[int] | None:
    return None if cell is None else _cell(cell)


def _as_cell(raw: Any, where: str) -> Cell:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError(f"{where} must be a pair of integers. Got {raw!r}")
    return (int(raw[0]), int(raw[1]))


def _optional_as_cell(raw: Any, where: str) -> Cell | None:
    return None if raw is None else _as_cell(raw, where)


def _as_bounds(raw: Any) -> tuple[Cell, Cell]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError(f"bounds must be a pair of cells. Got {raw!r}")
    return (_as_cell(raw[0], "bounds[0]"), _as_cell(raw[1], "bounds[1]"))


def _known(payload: dict[str, Any], sample: dict[str, Any], where: str) -> None:
    unknown = sorted(set(payload) - set(sample))
    if unknown:
        raise ValueError(f"{where} carries a field outside the contract: {', '.join(unknown)}")


def _terrain(raw: Any) -> Terrain:
    try:
        return Terrain(raw)
    except ValueError as exc:
        raise ValueError(f"terrain {raw!r} is not in the contract") from exc


def _faction(raw: Any) -> Faction:
    try:
        return Faction(raw)
    except ValueError as exc:
        raise ValueError(f"faction {raw!r} is not in the contract") from exc


def _move_kind(raw: Any) -> ActionKind:
    try:
        return ActionKind(raw)
    except ValueError as exc:
        raise ValueError(f"kind {raw!r} is not in the contract") from exc


def _skill_source(raw: Any) -> SkillSource:
    try:
        return SkillSource(raw)
    except ValueError as exc:
        raise ValueError(f"source {raw!r} is not in the contract") from exc


def _skill_affects(raw: Any) -> SkillAffects:
    try:
        return SkillAffects(raw)
    except ValueError as exc:
        raise ValueError(f"affects {raw!r} is not in the contract") from exc


def _direction(raw: Any) -> Direction:
    try:
        return Direction(raw)
    except ValueError as exc:
        raise ValueError(f"direction {raw!r} is not in the contract") from exc


def _map_weapon_affects(raw: Any) -> MapWeaponAffects:
    try:
        return MapWeaponAffects(raw)
    except ValueError as exc:
        raise ValueError(f"affects {raw!r} is not in the contract") from exc


def _stance(raw: Any) -> Stance:
    try:
        stance = Stance(raw)
    except ValueError as exc:
        raise ValueError(f"stance {raw!r} is not in the contract") from exc
    return stance


def _str(payload: dict[str, Any], name: str) -> str:
    return str(payload.get(name, ""))


def _optional_str(payload: dict[str, Any], name: str) -> str | None:
    raw = payload.get(name)
    return None if raw is None else str(raw)


def _ids(payload: dict[str, Any], name: str) -> tuple[int, ...]:
    return tuple(int(entry) for entry in payload.get(name) or ())


def _int(payload: dict[str, Any], name: str) -> int:
    return int(payload.get(name, 0))


def _optional_int(payload: dict[str, Any], name: str) -> int | None:
    raw = payload.get(name)
    return None if raw is None else int(raw)


def _float(payload: dict[str, Any], name: str) -> float:
    return float(payload.get(name, 0.0))


def _optional_float(payload: dict[str, Any], name: str) -> float | None:
    raw = payload.get(name)
    return None if raw is None else float(raw)


def _bool(payload: dict[str, Any], name: str) -> bool:
    return bool(payload.get(name, False))


def _optional_bool(payload: dict[str, Any], name: str) -> bool | None:
    raw = payload.get(name)
    return None if raw is None else bool(raw)


def encode_action(
    candidate: Mapping[str, Any],
    response_attack: Mapping[str, Any] | None = None,
    stated: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The payload of 'act': the candidate of the menu, read by presence.

    A candidate is the decision shape that 'actions' and 'response_attacks'
    speak. The act carries no kind: a move alone is a reposition, nothing is
    a standby, an attack travels with its response attack. A stated behavior
    rides on the main strike.
    """
    action: dict[str, Any] = {"actor_id": candidate["unit_id"]}
    if candidate.get("move_to") is not None:
        action["move_to"] = list(candidate["move_to"])
    kind = candidate.get("kind")
    if kind == "attack":
        attack: dict[str, Any] = {
            "weapon_id": candidate["weapon_id"],
            "target_id": candidate["target_id"],
            "support_attackers": _support_attackers(candidate),
            "support_defender_id": candidate.get("support_defender_id"),
        }
        if stated is not None:
            attack["stated"] = dict(stated)
        action["attack"] = attack
        if response_attack is not None:
            action["response_attack"] = encode_response(response_attack)
    elif kind == "map_attack":
        action["map_attack"] = {
            "map_weapon_id": candidate["map_weapon_id"],
            "anchor": list(candidate["aim"]),
            "direction": candidate.get("direction", "none"),
        }
    return action


def encode_response(response_attack: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "stance": response_attack["stance"],
        "weapon_id": response_attack.get("weapon_id"),
        "support_attackers": _support_attackers(response_attack),
        "support_defender_id": response_attack.get("support_defender_id"),
    }
    if response_attack.get("stated") is not None:
        out["stated"] = dict(response_attack["stated"])
    return out


def _support_attackers(side: Mapping[str, Any]) -> list[dict[str, Any]]:
    named = side.get("support_attackers")
    if named:
        return [dict(one) for one in named]
    if side.get("support_attacker_ids"):
        raise ValueError("a support attacker names its weapon: use 'support_attackers'")
    return []
