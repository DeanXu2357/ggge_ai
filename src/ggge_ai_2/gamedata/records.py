"""Records that the store reads out of the game data schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeVar

from ggge_ai_2.gamedata.normalize import COLUMNS, Rows

Record = TypeVar("Record")


@dataclass(frozen=True)
class StatRow:
    base: int
    max: int
    sp_base: int
    sp_max: int


@dataclass(frozen=True)
class SspStat:
    base: int
    max: int


@dataclass(frozen=True)
class SspRelease:
    core_level: int
    sort_order: int
    kind: str
    target_id: int
    payload: dict


@dataclass(frozen=True)
class WeaponGrowth:
    power_rate: int
    en_rate: int
    hit_rate_rate: int
    crit_rate_rate: int


@dataclass(frozen=True)
class WeaponRecord:
    id: int
    unit_id: int
    name: str
    type: int
    work_type: int
    attack_attr: int
    weapon_attr: int
    power: int
    en: int
    hit_rate: int
    critical_rate: int
    range_min: int
    range_max: int
    ammo: int
    is_ssp: bool
    growth: dict[int, WeaponGrowth] = field(default_factory=dict)


@dataclass(frozen=True)
class UnitRecord:
    id: int
    name: str
    rarity: int
    ult: bool
    stats: dict[str, StatRow]
    ssp_stats: dict[str, SspStat]
    releases: tuple[SspRelease, ...]
    weapons: tuple[WeaponRecord, ...]


@dataclass(frozen=True)
class PilotRecord:
    id: int
    name: str
    rarity: int
    stats: dict[str, StatRow]


@dataclass(frozen=True)
class SupporterRecord:
    id: int
    name: str
    rarity: int
    max_hp_addition: int
    max_attack_addition: int


@dataclass(frozen=True)
class Catalog:
    """The records of one stamp, built from normalized rows without a database."""

    units: dict[int, UnitRecord]
    pilots: dict[int, PilotRecord]
    supporters: dict[int, SupporterRecord]
    supporter_rates: dict[tuple[int, int], int]

    @classmethod
    def from_rows(cls, rows: Rows) -> Catalog:
        tables = rows.tables
        return cls(
            units=_unit_records(tables, _weapon_records(tables)),
            pilots=_pilot_records(tables),
            supporters=_supporter_records(tables),
            supporter_rates=_supporter_rates(tables),
        )

    def unit(self, unit_id: int) -> UnitRecord:
        return _found(self.units, unit_id, "unit")

    def pilot(self, pilot_id: int) -> PilotRecord:
        return _found(self.pilots, pilot_id, "pilot")

    def supporter(self, supporter_id: int) -> SupporterRecord:
        return _found(self.supporters, supporter_id, "supporter")

    def supporter_rate(self, level: int, limit_break: int) -> int:
        try:
            return self.supporter_rates[(level, limit_break)]
        except KeyError:
            raise LookupError(
                f"no support crew growth row for level {level} step {limit_break}"
            ) from None


def _found(records: dict[int, Record], key: int, name: str) -> Record:
    try:
        return records[key]
    except KeyError:
        raise LookupError(f"no {name} {key} in the catalog") from None


def _fields(table: str) -> dict[str, int]:
    return {name: position for position, name in enumerate(COLUMNS[table])}


def _stats(table_rows: list[tuple], table: str, key: str) -> dict[int, dict[str, StatRow]]:
    index = _fields(table)
    grouped: dict[int, dict[str, StatRow]] = {}
    for row in table_rows:
        grouped.setdefault(row[index[key]], {})[row[index["stat"]]] = StatRow(
            row[index["base"]],
            row[index["max"]],
            row[index["sp_base"]],
            row[index["sp_max"]],
        )
    return grouped


def _ssp_stats(table_rows: list[tuple]) -> dict[int, dict[str, SspStat]]:
    index = _fields("unit_ssp_stat")
    grouped: dict[int, dict[str, SspStat]] = {}
    for row in table_rows:
        grouped.setdefault(row[index["unit_id"]], {})[row[index["stat"]]] = SspStat(
            row[index["base"]], row[index["max"]]
        )
    return grouped


def _releases(table_rows: list[tuple]) -> dict[int, tuple[SspRelease, ...]]:
    index = _fields("unit_ssp_release")
    grouped: dict[int, list[SspRelease]] = {}
    for row in table_rows:
        grouped.setdefault(row[index["unit_id"]], []).append(
            SspRelease(
                core_level=row[index["core_level"]],
                sort_order=row[index["sort_order"]],
                kind=row[index["kind"]],
                target_id=row[index["target_id"]],
                payload=row[index["payload"]],
            )
        )
    return {
        unit_id: tuple(sorted(items, key=lambda item: (item.core_level, item.sort_order)))
        for unit_id, items in grouped.items()
    }


def _weapon_records(tables: dict[str, list[tuple]]) -> dict[int, WeaponRecord]:
    index = _fields("weapon_growth")
    rates: dict[int, dict[int, WeaponGrowth]] = {}
    for row in sorted(tables["weapon_growth"], key=lambda row: row[index["level"]]):
        rates.setdefault(row[index["weapon_id"]], {})[row[index["level"]]] = WeaponGrowth(
            row[index["power_rate"]],
            row[index["en_rate"]],
            row[index["hit_rate_rate"]],
            row[index["crit_rate_rate"]],
        )
    return {
        row[1]: WeaponRecord(*row[1:], growth=rates.get(row[1], {})) for row in tables["weapon"]
    }


def _unit_records(
    tables: dict[str, list[tuple]], weapons: dict[int, WeaponRecord]
) -> dict[int, UnitRecord]:
    index = _fields("unit")
    stats = _stats(tables["unit_stat"], "unit_stat", "unit_id")
    ssp_stats = _ssp_stats(tables["unit_ssp_stat"])
    releases = _releases(tables["unit_ssp_release"])
    owned: dict[int, set[int]] = {}
    for record in weapons.values():
        owned.setdefault(record.unit_id, set()).add(record.id)
    records: dict[int, UnitRecord] = {}
    for row in tables["unit"]:
        unit_id = row[index["id"]]
        held = set(owned.get(unit_id, ()))
        held.update(
            release.payload["after_weapon_id"]
            for release in releases.get(unit_id, ())
            if release.kind == "weapon_change"
        )
        records[unit_id] = UnitRecord(
            id=unit_id,
            name=row[index["name"]],
            rarity=row[index["rarity"]],
            ult=row[index["ult"]],
            stats=stats.get(unit_id, {}),
            ssp_stats=ssp_stats.get(unit_id, {}),
            releases=releases.get(unit_id, ()),
            weapons=tuple(weapons[key] for key in sorted(held) if key in weapons),
        )
    return records


def _pilot_records(tables: dict[str, list[tuple]]) -> dict[int, PilotRecord]:
    index = _fields("pilot")
    stats = _stats(tables["pilot_stat"], "pilot_stat", "pilot_id")
    return {
        row[index["id"]]: PilotRecord(
            id=row[index["id"]],
            name=row[index["name"]],
            rarity=row[index["rarity"]],
            stats=stats.get(row[index["id"]], {}),
        )
        for row in tables["pilot"]
    }


def _supporter_rates(tables: dict[str, list[tuple]]) -> dict[tuple[int, int], int]:
    index = _fields("supporter_growth")
    return {
        (row[index["level"]], row[index["limit_break"]]): row[index["correction_rate"]]
        for row in tables["supporter_growth"]
    }


def _supporter_records(tables: dict[str, list[tuple]]) -> dict[int, SupporterRecord]:
    index = _fields("supporter")
    return {
        row[index["id"]]: SupporterRecord(
            id=row[index["id"]],
            name=row[index["name"]],
            rarity=row[index["rarity"]],
            max_hp_addition=row[index["max_hp_addition"]],
            max_attack_addition=row[index["max_attack_addition"]],
        )
        for row in tables["supporter"]
    }
