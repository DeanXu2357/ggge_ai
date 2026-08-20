"""The wire form of the battle state (spec: docs/spec/battle-engine-protocol.md).

'ggge_ai/sandbox/model.py' is the authority for every field. The Go package
'engine/protocol' holds the same structs, and 'tests/test_engine_codec.py'
compares the two field lists.

Rules of the wire form:

- A cell is a JSON pair, in the order of the Python tuple.
- A field that holds None is null on the wire, and null decodes back to None.
- The encoder writes every field. A decoder that meets an absent field takes
  the zero of the type of the field, because the Go decoder does the same.
- The stance 'none' does not reach the wire: the reaction menu of the game
  holds no decline button, so the contract lists no such option.
"""

from __future__ import annotations

from typing import Any

from ..sandbox.model import (
    BattleState,
    Cell,
    Debuff,
    Decision,
    EventTable,
    Faction,
    MoveKind,
    Reaction,
    Rules,
    Skill,
    SkillAffects,
    SkillSource,
    Stance,
    StageEvent,
    Unit,
    Weapon,
)

SPAWN = "spawn"


def encode_rules(rules: Rules) -> dict[str, Any]:
    return {
        "defend_multiplier": rules.defend_multiplier,
        "shield_multiplier": rules.shield_multiplier,
        "support_defend_multiplier": rules.support_defend_multiplier,
        "dodge_hit_penalty": rules.dodge_hit_penalty,
        "terrain": rules.terrain,
        "max_support_attackers": rules.max_support_attackers,
        "en_regen_fraction": rules.en_regen_fraction,
    }


def decode_rules(payload: dict[str, Any]) -> Rules:
    _known(payload, encode_rules(Rules()), "rules")
    return Rules(
        defend_multiplier=_float(payload, "defend_multiplier"),
        shield_multiplier=_float(payload, "shield_multiplier"),
        support_defend_multiplier=_float(payload, "support_defend_multiplier"),
        dodge_hit_penalty=_float(payload, "dodge_hit_penalty"),
        terrain=_float(payload, "terrain"),
        max_support_attackers=_int(payload, "max_support_attackers"),
        en_regen_fraction=_float(payload, "en_regen_fraction"),
    )


def encode_weapon(weapon: Weapon) -> dict[str, Any]:
    return {
        "name": weapon.name,
        "power": weapon.power,
        "range_min": weapon.range_min,
        "range_max": weapon.range_max,
        "en_cost": weapon.en_cost,
        "accuracy": weapon.accuracy,
        "can_counter": weapon.can_counter,
        "map_weapon": weapon.map_weapon,
        "usable_after_move": weapon.usable_after_move,
        "blast": weapon.blast,
        "debuff_kind": weapon.debuff_kind,
        "debuff_magnitude": weapon.debuff_magnitude,
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
        can_counter=_bool(payload, "can_counter"),
        map_weapon=_bool(payload, "map_weapon"),
        usable_after_move=_bool(payload, "usable_after_move"),
        blast=_int(payload, "blast"),
        debuff_kind=_optional_str(payload, "debuff_kind"),
        debuff_magnitude=_float(payload, "debuff_magnitude"),
    )


def encode_skill(skill: Skill) -> dict[str, Any]:
    return {
        "kind": str(skill.kind),
        "source": str(skill.source),
        "amount": skill.amount,
        "uses": skill.uses,
        "ends_activation": skill.ends_activation,
        "usable_after_move": skill.usable_after_move,
        "range_min": skill.range_min,
        "range_max": skill.range_max,
        "blast": skill.blast,
        "affects": str(skill.affects),
    }


def decode_skill(payload: dict[str, Any]) -> Skill:
    _known(payload, encode_skill(Skill(kind=MoveKind.STANDBY)), "skill")
    return Skill(
        kind=_move_kind(payload.get("kind")),
        source=_skill_source(payload.get("source")),
        amount=_optional_float(payload, "amount"),
        uses=_int(payload, "uses"),
        ends_activation=_bool(payload, "ends_activation"),
        usable_after_move=_bool(payload, "usable_after_move"),
        range_min=_int(payload, "range_min"),
        range_max=_int(payload, "range_max"),
        blast=_int(payload, "blast"),
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


def encode_unit(unit: Unit) -> dict[str, Any]:
    return {
        "unit_id": unit.unit_id,
        "faction": str(unit.faction),
        "pos": _cell(unit.pos),
        "size": _cell(unit.size),
        "hp": unit.hp,
        "max_hp": unit.max_hp,
        "en": unit.en,
        "en_max": unit.en_max,
        "unit_attack": unit.unit_attack,
        "unit_defense": unit.unit_defense,
        "pilot_attack": unit.pilot_attack,
        "pilot_defense": unit.pilot_defense,
        "reaction": unit.reaction,
        "mobility": unit.mobility,
        "move_range": unit.move_range,
        "weapons": [encode_weapon(weapon) for weapon in unit.weapons],
        "skills": [encode_skill(skill) for skill in unit.skills],
        "acted": unit.acted,
        "chance_steps": unit.chance_steps,
        "chance_steps_max": unit.chance_steps_max,
        "support_defend_charges": unit.support_defend_charges,
        "support_defend_charges_max": unit.support_defend_charges_max,
        "support_attack_charges": unit.support_attack_charges,
        "support_attack_charges_max": unit.support_attack_charges_max,
        "has_shield": unit.has_shield,
        "attack_shield": unit.attack_shield,
        "interception_reduction": unit.interception_reduction,
        "ammo": dict(unit.ammo),
        "debuffs": [encode_debuff(debuff) for debuff in unit.debuffs],
    }


def decode_unit(payload: dict[str, Any]) -> Unit:
    _known(payload, encode_unit(Unit(unit_id="", faction=Faction.ALLY)), "unit")
    return Unit(
        unit_id=_str(payload, "unit_id"),
        faction=_faction(payload.get("faction")),
        pos=_as_cell(payload.get("pos"), "unit.pos"),
        size=_as_cell(payload.get("size", (1, 1)), "unit.size"),
        hp=_int(payload, "hp"),
        max_hp=_int(payload, "max_hp"),
        en=_int(payload, "en"),
        en_max=_int(payload, "en_max"),
        unit_attack=_float(payload, "unit_attack"),
        unit_defense=_float(payload, "unit_defense"),
        pilot_attack=_float(payload, "pilot_attack"),
        pilot_defense=_float(payload, "pilot_defense"),
        reaction=_float(payload, "reaction"),
        mobility=_float(payload, "mobility"),
        move_range=_int(payload, "move_range"),
        weapons=[decode_weapon(entry) for entry in payload.get("weapons") or ()],
        skills=[decode_skill(entry) for entry in payload.get("skills") or ()],
        acted=_bool(payload, "acted"),
        chance_steps=_int(payload, "chance_steps"),
        chance_steps_max=_int(payload, "chance_steps_max"),
        support_defend_charges=_int(payload, "support_defend_charges"),
        support_defend_charges_max=_int(payload, "support_defend_charges_max"),
        support_attack_charges=_int(payload, "support_attack_charges"),
        support_attack_charges_max=_int(payload, "support_attack_charges_max"),
        has_shield=_bool(payload, "has_shield"),
        attack_shield=_bool(payload, "attack_shield"),
        interception_reduction=_float(payload, "interception_reduction"),
        ammo={str(name): int(count) for name, count in (payload.get("ammo") or {}).items()},
        debuffs=[decode_debuff(entry) for entry in payload.get("debuffs") or ()],
    )


def encode_reaction(reaction: Reaction) -> dict[str, Any]:
    if reaction.stance is Stance.NONE:
        raise ValueError("The stance 'none' is not in the contract of the reaction list")
    return {
        "stance": str(reaction.stance),
        "weapon": reaction.weapon,
        "support_defend": reaction.support_defend,
        "support_attack": reaction.support_attack,
    }


def decode_reaction(payload: dict[str, Any]) -> Reaction:
    _known(payload, encode_reaction(Reaction(stance=Stance.DODGE)), "reaction")
    stance = _stance(payload.get("stance"))
    return Reaction(
        stance=stance,
        weapon=_optional_str(payload, "weapon"),
        support_defend=_bool(payload, "support_defend"),
        support_attack=_bool(payload, "support_attack"),
    )


def encode_decision(decision: Decision) -> dict[str, Any]:
    return {
        "unit_id": decision.unit_id,
        "kind": str(decision.kind),
        "move_to": _optional_cell(decision.move_to),
        "target_id": decision.target_id,
        "weapon": decision.weapon,
        "amount": decision.amount,
        "reaction": None if decision.reaction is None else encode_reaction(decision.reaction),
        "support": decision.support,
        "aim": _optional_cell(decision.aim),
        "hit": decision.hit,
        "counter_hit": decision.counter_hit,
        "support_hit": decision.support_hit,
    }


def decode_decision(payload: dict[str, Any]) -> Decision:
    _known(payload, encode_decision(Decision(unit_id="", kind=MoveKind.STANDBY)), "decision")
    reaction = payload.get("reaction")
    return Decision(
        unit_id=_str(payload, "unit_id"),
        kind=_move_kind(payload.get("kind")),
        move_to=_optional_as_cell(payload.get("move_to"), "decision.move_to"),
        target_id=_optional_str(payload, "target_id"),
        weapon=_optional_str(payload, "weapon"),
        amount=_optional_float(payload, "amount"),
        reaction=None if reaction is None else decode_reaction(reaction),
        support=_bool(payload, "support"),
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


def encode_state(state: BattleState) -> dict[str, Any]:
    return {
        "units": [encode_unit(unit) for unit in state.units],
        "phase": str(state.phase),
        "turn": state.turn,
        "bounds": None if state.bounds is None else [_cell(state.bounds[0]), _cell(state.bounds[1])],
        "pending_events": list(state.pending_events),
        "fired_events": list(state.fired_events),
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


def _faction(raw: Any) -> Faction:
    try:
        return Faction(raw)
    except ValueError as exc:
        raise ValueError(f"faction {raw!r} is not in the contract") from exc


def _move_kind(raw: Any) -> MoveKind:
    try:
        return MoveKind(raw)
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


def _stance(raw: Any) -> Stance:
    try:
        stance = Stance(raw)
    except ValueError as exc:
        raise ValueError(f"stance {raw!r} is not in the contract") from exc
    if stance is Stance.NONE:
        raise ValueError("The stance 'none' is not in the contract of the reaction list")
    return stance


def _str(payload: dict[str, Any], name: str) -> str:
    return str(payload.get(name, ""))


def _optional_str(payload: dict[str, Any], name: str) -> str | None:
    raw = payload.get(name)
    return None if raw is None else str(raw)


def _int(payload: dict[str, Any], name: str) -> int:
    return int(payload.get(name, 0))


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
