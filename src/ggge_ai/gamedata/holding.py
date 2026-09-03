"""Assemble one holding into the engine payload (docs/reference/growth-model.md)."""

from __future__ import annotations

from dataclasses import dataclass

from ggge_ai.engine import state
from ggge_ai.engine.codec import encode_mech, encode_pilot
from ggge_ai.gamedata import growth
from ggge_ai.gamedata.records import (
    PilotRecord,
    SupporterRecord,
    UnitRecord,
    WeaponRecord,
)

WEAPON_TYPE_DIRECT = 1
WEAPON_TYPES = frozenset({1, 2, 3})
WEAPON_LEVELS = frozenset(range(1, 6))
MAX_LIMIT_BREAK = 3

SCALED_STATS = ("hp", "en", "attack", "defense", "mobility")
STATUS_UP_STATS = {1: "hp", 2: "en", 3: "attack", 4: "defense", 5: "mobility", 6: "movement"}
ENHANCE_FIELDS = {1: "power", 2: "en", 3: "ammo", 4: "range_max"}
CATEGORIES = {
    1: ["ranged"],
    2: ["melee"],
    3: ["awaken"],
    4: ["ranged", "melee"],
    5: ["ranged", "awaken"],
    6: ["melee", "awaken"],
    7: ["ranged", "melee", "awaken"],
}
APPLIED_KINDS = frozenset({"weapon_change", "weapon_enhance", "status_up"})
STORED_KINDS = frozenset({"terrain", "weapon_effect", "ability_change"})


@dataclass(frozen=True)
class Holding:
    stamp: str
    unit_id: int
    level: int
    pilot_id: int
    pilot_level: int
    limit_break: int = 0
    mech_sp: bool = False
    mech_ssp: bool = False
    weapon_level: int = 5
    supporter_id: int | None = None
    supporter_level: int = 1
    supporter_limit_break: int = 0


@dataclass(frozen=True)
class Crew:
    hp: int
    attack: int


@dataclass(frozen=True)
class Assembled:
    mech: state.Mech
    pilot: state.Pilot
    crew: Crew | None


@dataclass
class _Enhancement:
    power: int = 0
    en: int = 0
    ammo: int = 0
    range_max: int = 0


def assemble(
    holding: Holding,
    unit: UnitRecord,
    pilot: PilotRecord,
    supporter: SupporterRecord | None,
    supporter_rate: int | None,
) -> Assembled:
    _check(holding, unit, supporter, supporter_rate)
    return Assembled(
        mech=_mech(holding, unit),
        pilot=_pilot(holding, pilot),
        crew=_crew(supporter, supporter_rate),
    )


def payload(assembled: Assembled) -> dict:
    crew = assembled.crew
    return {
        "mech": encode_mech(assembled.mech),
        "pilot": encode_pilot(assembled.pilot),
        "crew": None if crew is None else {"hp": crew.hp, "attack": crew.attack},
    }


def _check(
    holding: Holding,
    unit: UnitRecord,
    supporter: SupporterRecord | None,
    supporter_rate: int | None,
) -> None:
    if holding.mech_ssp and not holding.mech_sp:
        raise ValueError(f"unit {unit.id}: mech_ssp needs mech_sp")
    if holding.mech_ssp and not unit.ssp_stats:
        raise ValueError(f"unit {unit.id}: the unit holds no SSP stats")
    if not 0 <= holding.limit_break <= MAX_LIMIT_BREAK:
        raise ValueError(f"limit break outside 0..{MAX_LIMIT_BREAK}: {holding.limit_break}")
    if holding.weapon_level not in WEAPON_LEVELS:
        raise ValueError(f"weapon level outside 1..5: {holding.weapon_level}")
    if holding.level < 1:
        raise ValueError(f"level below 1: {holding.level}")
    if holding.pilot_level < 1:
        raise ValueError(f"pilot level below 1: {holding.pilot_level}")
    if (supporter is None) != (supporter_rate is None):
        raise ValueError("a support crew needs its growth rate, and the rate needs a crew")


def _mech(holding: Holding, unit: UnitRecord) -> state.Mech:
    cap = growth.level_cap(unit.rarity, uncapped=holding.mech_sp or holding.mech_ssp or unit.ult)
    level = min(holding.level, cap)
    additions = _status_up(unit) if holding.mech_ssp else {}
    values: dict[str, int] = {}
    for stat in (*SCALED_STATS, "movement"):
        row = unit.stats[stat]
        sp = holding.mech_sp and unit.rarity < 5
        base, top = (row.sp_base, row.sp_max) if sp else (row.base, row.max)
        value = growth.level_value(base, top, level)
        if holding.mech_ssp:
            ssp = unit.ssp_stats.get(stat)
            value += ssp.max if ssp is not None else 0
            value += additions.get(stat, 0)
        values[stat] = value
    stars = 0 if unit.ult else holding.limit_break
    scaled = {stat: growth.limit_break_value(values[stat], stars) for stat in SCALED_STATS}
    return state.Mech(
        hp=scaled["hp"],
        en=scaled["en"],
        attack=float(scaled["attack"]),
        defense=float(scaled["defense"]),
        mobility=float(scaled["mobility"]),
        move_range=values["movement"],
        weapons=_weapons(holding, unit),
        map_weapons=[],
    )


def _status_up(unit: UnitRecord) -> dict[str, int]:
    totals: dict[str, int] = {}
    for release in unit.releases:
        if release.kind != "status_up":
            continue
        index = release.payload["unit_status_type_index"]
        stat = STATUS_UP_STATS.get(index)
        if stat is None:
            raise ValueError(f"unit {unit.id}: unknown status up type {index}")
        totals[stat] = totals.get(stat, 0) + release.payload["effect_value"]
    return totals


def _weapons(holding: Holding, unit: UnitRecord) -> list[state.Weapon]:
    held = [record for record in unit.weapons if not record.is_ssp]
    enhancements: dict[int, _Enhancement] = {}
    if holding.mech_ssp:
        _release_weapons(unit, held, enhancements)
    weapons: list[state.Weapon] = []
    for record in held:
        if record.type not in WEAPON_TYPES:
            raise ValueError(f"weapon {record.name}: unknown weapon type {record.type}")
        if record.type != WEAPON_TYPE_DIRECT:
            continue
        enhancement = enhancements.get(record.id, _Enhancement())
        weapons.append(_weapon(record, holding.weapon_level, enhancement))
    return weapons


def _release_weapons(
    unit: UnitRecord, held: list[WeaponRecord], enhancements: dict[int, _Enhancement]
) -> None:
    by_id = {record.id: record for record in unit.weapons}
    for release in unit.releases:
        if release.kind in STORED_KINDS:
            continue
        if release.kind not in APPLIED_KINDS:
            raise ValueError(f"unit {unit.id}: unknown release kind {release.kind}")
        if release.kind == "weapon_change":
            _change_weapon(unit, held, by_id, release.payload)
        elif release.kind == "weapon_enhance":
            _enhance_weapon(unit, enhancements, release.payload)


def _change_weapon(
    unit: UnitRecord, held: list[WeaponRecord], by_id: dict[int, WeaponRecord], payload: dict
) -> None:
    after = by_id.get(payload["after_weapon_id"])
    if after is None:
        raise ValueError(
            f"unit {unit.id}: the release names weapon {payload['after_weapon_id']},"
            " and the stamp holds no such weapon"
        )
    before = payload["before_weapon_id"]
    if before == 0:
        held.append(after)
        return
    positions = [index for index, record in enumerate(held) if record.id == before]
    if not positions:
        raise ValueError(f"unit {unit.id}: the release replaces weapon {before}, which is absent")
    held[positions[0]] = after


def _enhance_weapon(unit: UnitRecord, enhancements: dict[int, _Enhancement], payload: dict) -> None:
    index = payload["weapon_enhance_type_index"]
    name = ENHANCE_FIELDS.get(index)
    if name is None:
        raise ValueError(f"unit {unit.id}: unknown weapon enhance type {index}")
    enhancement = enhancements.setdefault(payload["target_weapon_id"], _Enhancement())
    setattr(enhancement, name, getattr(enhancement, name) + payload["effect_value"])


def _weapon(record: WeaponRecord, level: int, enhancement: _Enhancement) -> state.Weapon:
    rate = record.growth.get(level)
    if rate is None:
        raise ValueError(f"weapon {record.name}: no growth row for level {level}")
    categories = CATEGORIES.get(record.attack_attr)
    if categories is None:
        raise ValueError(f"weapon {record.name}: unknown attack attribute {record.attack_attr}")
    return state.Weapon(
        name=record.name,
        power=float(growth.weapon_value(record.power, rate.power_rate) + enhancement.power),
        range_min=record.range_min,
        range_max=record.range_max + enhancement.range_max,
        en_cost=growth.weapon_value(record.en, rate.en_rate) - enhancement.en,
        accuracy=float(growth.weapon_value(record.hit_rate, rate.hit_rate_rate)),
        usable_after_move=True,
        debuff_kind=None,
        debuff_magnitude=0.0,
        categories=list(categories),
    )


def _pilot(holding: Holding, pilot: PilotRecord) -> state.Pilot:
    level = min(holding.pilot_level, growth.level_cap(pilot.rarity))
    values = {
        stat: growth.level_value(row.base, row.max, level) for stat, row in pilot.stats.items()
    }
    return state.Pilot(
        ranged=float(values["ranged"]),
        melee=float(values["melee"]),
        awaken=float(values["awaken"]),
        defense=float(values["defense"]),
        reaction=float(values["reaction"]),
        sp=0,
    )


def _crew(supporter: SupporterRecord | None, supporter_rate: int | None) -> Crew | None:
    if supporter is None or supporter_rate is None:
        return None
    return Crew(
        hp=growth.supporter_bonus(supporter.max_hp_addition, supporter_rate),
        attack=growth.supporter_bonus(supporter.max_attack_addition, supporter_rate),
    )
