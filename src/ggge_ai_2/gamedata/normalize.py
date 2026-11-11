"""Turn a datamine dump into the rows of the game data schema.

The module is pure: it reads the dump files and returns rows. It holds no
database code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

COLUMNS: dict[str, tuple[str, ...]] = {
    "tag": ("stamp", "id", "name"),
    "unit": (
        "stamp",
        "id",
        "name",
        "short_name",
        "rarity",
        "role",
        "area",
        "body_type",
        "series",
        "ult",
        "acquisition",
        "main_unit",
        "defend",
        "evade",
    ),
    "unit_tag": ("stamp", "unit_id", "tag_id"),
    "unit_series": ("stamp", "unit_id", "series_id", "sort"),
    "unit_stat": ("stamp", "unit_id", "stat", "base", "max", "sp_base", "sp_max"),
    "unit_terrain": ("stamp", "unit_id", "terrain", "grade"),
    "unit_ability": ("stamp", "unit_id", "sort", "ability_id", "payload"),
    "unit_ssp_stat": ("stamp", "unit_id", "stat", "base", "max"),
    "unit_ssp_core": ("stamp", "unit_id", "level", "core_id", "release_point"),
    "unit_ssp_release": (
        "stamp",
        "unit_id",
        "core_level",
        "sort_order",
        "kind",
        "target_id",
        "payload",
    ),
    "weapon": (
        "stamp",
        "id",
        "unit_id",
        "name",
        "type",
        "work_type",
        "attack_attr",
        "weapon_attr",
        "power",
        "en",
        "hit_rate",
        "critical_rate",
        "range_min",
        "range_max",
        "ammo",
        "is_ssp",
    ),
    "weapon_growth": (
        "stamp",
        "weapon_id",
        "level",
        "power_rate",
        "en_rate",
        "hit_rate_rate",
        "crit_rate_rate",
    ),
    "weapon_trait": ("stamp", "weapon_id", "sort", "level", "trait_id", "payload"),
    "pilot": ("stamp", "id", "name", "rarity", "role", "main_pilot", "is_playable"),
    "pilot_stat": ("stamp", "pilot_id", "stat", "base", "max", "sp_base", "sp_max"),
    "pilot_tag": ("stamp", "pilot_id", "tag_id"),
    "pilot_series": ("stamp", "pilot_id", "series_id", "sort"),
    "pilot_ability": ("stamp", "pilot_id", "sort", "ability_id", "level", "payload"),
    "pilot_skill": ("stamp", "pilot_id", "sort", "skill_id", "level", "payload"),
    "supporter": ("stamp", "id", "name", "rarity", "max_hp_addition", "max_attack_addition"),
    "supporter_limit_break": ("stamp", "supporter_id", "step", "leader_skill", "active_skill"),
    "supporter_growth": ("stamp", "level", "limit_break", "correction_rate"),
}

RAW_COLUMNS: tuple[str, ...] = ("stamp", "source_table", "row_key", "payload")

RELEASE_KIND: dict[int, str] = {
    1: "weapon_enhance",
    3: "status_up",
    4: "terrain",
    5: "weapon_change",
    6: "ability_change",
    7: "weapon_effect",
}

UNIT_STATS = ("hp", "en", "attack", "defense", "mobility", "movement")
SSP_STATS = ("hp", "en", "attack", "defense", "mobility")
TERRAINS = ("space", "atmospheric", "ground", "surface", "underwater")
PILOT_STATS = ("ranged", "melee", "defense", "reaction", "awaken")

DUMP_FILES = ("unit", "weapon", "character", "supporter", "supporter_growth")


@dataclass(frozen=True)
class Rows:
    """Normalized rows of one stamp, keyed by table name, in insert order."""

    stamp: str
    tables: dict[str, list[tuple]]


@dataclass(frozen=True)
class Dump:
    unit: list[dict]
    weapon: dict
    character: list[dict]
    supporter: list[dict]
    supporter_growth: list[dict]

    @staticmethod
    def read(dump_dir: Path) -> Dump:
        payloads = {name: read_payload(dump_dir, name) for name in DUMP_FILES}
        return Dump(**payloads)


def read_payload(dump_dir: Path, name: str) -> Any:
    return json.loads((dump_dir / f"{name}.json").read_text(encoding="utf-8"))


def normalize(stamp: str, dump: Dump) -> Rows:
    tables: dict[str, list[tuple]] = {name: [] for name in COLUMNS}
    tags: dict[int, str] = {}
    for unit in dump.unit:
        _add_unit(stamp, unit, tables, tags)
    for weapon in dump.weapon["weapons"]:
        _add_weapon(stamp, weapon, tables)
    for pilot in dump.character:
        _add_pilot(stamp, pilot, tables, tags)
    for supporter in dump.supporter:
        _add_supporter(stamp, supporter, tables)
    tables["supporter_growth"] = [
        (stamp, row["level"], row["limit_break"], row["correction_rate"])
        for row in dump.supporter_growth
    ]
    tables["tag"] = [(stamp, tag_id, tags[tag_id]) for tag_id in sorted(tags)]
    return Rows(stamp=stamp, tables=tables)


def raw_rows(stamp: str, name: str, payload: Any) -> list[tuple]:
    if name == "weapon":
        rows = [(stamp, "weapon", str(row["id"]), row) for row in payload["weapons"]]
        rows.extend((stamp, "weapon_unit", key, value) for key, value in payload["units"].items())
    elif not isinstance(payload, list):
        rows = [(stamp, name, name, payload)]
    elif name == "supporter_growth":
        rows = [(stamp, name, f"{row['level']}-{row['limit_break']}", row) for row in payload]
    else:
        rows = [(stamp, name, str(row.get("id", index)), row) for index, row in enumerate(payload)]
    return _one_row_for_each_key(rows)


def _one_row_for_each_key(rows: list[tuple]) -> list[tuple]:
    seen: set[tuple[str, str]] = set()
    for _, source, key, _payload in rows:
        if (source, key) in seen:
            raise ValueError(f"source {source}: two rows share the key {key}")
        seen.add((source, key))
    return rows


def _stat_rows(stamp: str, owner_id: int, stats: dict, names: tuple[str, ...]) -> list[tuple]:
    return [
        (
            stamp,
            owner_id,
            name,
            stats[name],
            stats[f"max_{name}"],
            stats[f"sp_{name}"],
            stats[f"sp_max_{name}"],
        )
        for name in names
    ]


def _add_tags(
    stamp: str, owner_id: int, entries: list[dict], rows: list[tuple], tags: dict
) -> None:
    for entry in entries:
        tags[entry["tag"]["id"]] = entry["tag"]["name"]
        rows.append((stamp, owner_id, entry["tag_id"]))


def _add_series(stamp: str, owner_id: int, entries: list[dict], rows: list[tuple]) -> None:
    for entry in entries:
        rows.append((stamp, owner_id, entry["series_id"], entry["sort"]))


def _add_unit(stamp: str, unit: dict, tables: dict[str, list[tuple]], tags: dict) -> None:
    unit_id = unit["id"]
    tables["unit"].append(
        (
            stamp,
            unit_id,
            unit["name"],
            unit["short_name"],
            unit["rarity"],
            unit["role"],
            unit["area"],
            unit["body_type"],
            unit["series"],
            unit["ult"],
            unit["acquisition"],
            unit["main_unit"],
            unit["defend"],
            unit["evade"],
        )
    )
    _add_tags(stamp, unit_id, unit["tags"], tables["unit_tag"], tags)
    _add_series(stamp, unit_id, unit["series_set"], tables["unit_series"])
    tables["unit_stat"].extend(_stat_rows(stamp, unit_id, unit["stats"], UNIT_STATS))
    for terrain in TERRAINS:
        tables["unit_terrain"].append((stamp, unit_id, terrain, unit["terrain"][terrain]))
    for sort, entry in enumerate(unit["abilities"], start=1):
        tables["unit_ability"].append((stamp, unit_id, sort, entry["ability_id"], entry["ability"]))
    config = unit.get("ssp_config")
    if config is not None:
        _add_ssp(stamp, unit_id, config, tables)


def _add_ssp(stamp: str, unit_id: int, config: dict, tables: dict[str, list[tuple]]) -> None:
    stats = config["stats"]
    for name in SSP_STATS:
        tables["unit_ssp_stat"].append(
            (stamp, unit_id, name, stats[f"ssp_{name}"], stats[f"ssp_max_{name}"])
        )
    initial = config["initial_release"]
    if initial is not None:
        tables["unit_ssp_core"].append((stamp, unit_id, 0, 0, 0))
        tables["unit_ssp_release"].append(_release_row(stamp, unit_id, 0, initial))
    for core in config["cores"]:
        level = core["level"]
        tables["unit_ssp_core"].append((stamp, unit_id, level, core["id"], core["release_point"]))
        for release in core["releases"]:
            tables["unit_ssp_release"].append(_release_row(stamp, unit_id, level, release))


def _release_row(stamp: str, unit_id: int, core_level: int, release: dict) -> tuple:
    index = release["release_function_type_index"]
    kind = RELEASE_KIND.get(index)
    if kind is None:
        raise ValueError(f"unit {unit_id}: unknown release function type index {index}")
    return (
        stamp,
        unit_id,
        core_level,
        release["sort_order"],
        kind,
        release["target_id"],
        release[kind],
    )


def _add_weapon(stamp: str, weapon: dict, tables: dict[str, list[tuple]]) -> None:
    weapon_id = weapon["id"]
    tables["weapon"].append(
        (
            stamp,
            weapon_id,
            weapon["unit_id"],
            weapon["name"],
            weapon["type"],
            weapon["work_type"],
            weapon["attack_attr"],
            weapon["weapon_attr"],
            weapon["power"],
            weapon["en"],
            weapon["hit_rate"],
            weapon["critical_rate"],
            weapon["range_min"],
            weapon["range_max"],
            weapon["ammo"],
            weapon["is_ssp"],
        )
    )
    growth = weapon["growth"]
    for row in growth["wsc"]:
        tables["weapon_growth"].append(
            (
                stamp,
                weapon_id,
                row["level"],
                row["power"],
                row["en"],
                row["hit_rate"],
                row["crit_rate"],
            )
        )
    for sort, row in enumerate(growth.get("wtc") or [], start=1):
        tables["weapon_trait"].append(
            (stamp, weapon_id, sort, row["level"], row["trait_id"], row["trait"])
        )


def _add_pilot(stamp: str, pilot: dict, tables: dict[str, list[tuple]], tags: dict) -> None:
    pilot_id = pilot["id"]
    tables["pilot"].append(
        (
            stamp,
            pilot_id,
            pilot["name"],
            pilot["rarity"],
            pilot["role"],
            pilot["main_character_id"],
            pilot["is_playable"],
        )
    )
    tables["pilot_stat"].extend(_stat_rows(stamp, pilot_id, pilot["stats"], PILOT_STATS))
    _add_tags(stamp, pilot_id, pilot["tags"], tables["pilot_tag"], tags)
    _add_series(stamp, pilot_id, pilot["series_set"], tables["pilot_series"])
    for row in pilot["abilities"]:
        tables["pilot_ability"].append(
            (stamp, pilot_id, row["sort"], row["ability_id"], row["level"], row["ability"])
        )
    for row in pilot["skills"]:
        tables["pilot_skill"].append(
            (stamp, pilot_id, row["sort"], row["character_skill_id"], row["level"], row["skill"])
        )


def _add_supporter(stamp: str, supporter: dict, tables: dict[str, list[tuple]]) -> None:
    supporter_id = supporter["id"]
    tables["supporter"].append(
        (
            stamp,
            supporter_id,
            supporter["name"],
            supporter["rarity"],
            supporter["max_hp_addition_value"],
            supporter["max_attack_addition_value"],
        )
    )
    for row in supporter["lb_skills"]:
        tables["supporter_limit_break"].append(
            (
                stamp,
                supporter_id,
                row["limit_break_step"],
                row["leader_skill"],
                row["active_skill"],
            )
        )
