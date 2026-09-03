"""Read and write the game data store (docs/how-to/game-data-db.md)."""

from __future__ import annotations

import os
from types import TracebackType

import psycopg
from psycopg.types.json import Jsonb

from ggge_ai.gamedata import growth
from ggge_ai.gamedata.normalize import COLUMNS, RAW_COLUMNS, Rows
from ggge_ai.gamedata.records import (
    PilotRecord,
    SspRelease,
    SspStat,
    StatRow,
    SupporterRecord,
    UnitRecord,
    WeaponGrowth,
    WeaponRecord,
)

DEFAULT_URL = "postgresql://ggge:ggge@localhost:5432/ggge"

JSON_COLUMNS = frozenset({"payload", "leader_skill", "active_skill"})
CONSTANT_TABLES = frozenset({"supporter_growth"})
DELETE_ORDER = ("unit", "pilot", "weapon", "supporter", "tag", "datamine_raw")
STAMPED_TABLES = tuple(name for name in COLUMNS if name not in CONSTANT_TABLES) + ("datamine_raw",)

WEAPON_FIELDS = COLUMNS["weapon"][1:]


def database_url() -> str:
    return os.environ.get("GGGE_DATABASE_URL", DEFAULT_URL)


def _insert(table: str, columns: tuple[str, ...]) -> str:
    marks = ", ".join(["%s"] * len(columns))
    return f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({marks})"


def _upsert(table: str, columns: tuple[str, ...], key: tuple[str, ...]) -> str:
    updates = ", ".join(f"{name} = EXCLUDED.{name}" for name in columns if name not in key)
    return f"{_insert(table, columns)} ON CONFLICT ({', '.join(key)}) DO UPDATE SET {updates}"


def _wrapped(table: str, row: tuple) -> tuple:
    columns = COLUMNS[table]
    return tuple(
        Jsonb(value) if columns[index] in JSON_COLUMNS else value
        for index, value in enumerate(row)
    )


class Store:
    def __init__(self, conninfo: str | None = None) -> None:
        self._connection = psycopg.connect(conninfo or database_url(), autocommit=True)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def write_constants(self) -> None:
        with self._connection.transaction(), self._connection.cursor() as cursor:
            cursor.executemany(
                _upsert("level_curve", ("level", "rate"), ("level",)),
                growth.level_curve_rows(),
            )
            cursor.executemany(
                _upsert("limit_break_rate", ("step", "rate_percent"), ("step",)),
                growth.limit_break_rate_rows(),
            )
            cursor.executemany(
                _upsert("rarity_level_cap", ("rarity", "cap"), ("rarity",)),
                growth.rarity_level_cap_rows(),
            )

    def write_stamp(self, rows: Rows, raw: list[tuple]) -> None:
        with self._connection.transaction(), self._connection.cursor() as cursor:
            self._delete(cursor, rows.stamp)
            for table, table_rows in rows.tables.items():
                if not table_rows:
                    continue
                if table in CONSTANT_TABLES:
                    cursor.executemany(
                        _upsert("supporter_growth", COLUMNS[table], ("level", "limit_break")),
                        table_rows,
                    )
                    continue
                cursor.executemany(
                    _insert(table, COLUMNS[table]),
                    [_wrapped(table, row) for row in table_rows],
                )
            if raw:
                cursor.executemany(
                    _insert("datamine_raw", RAW_COLUMNS),
                    [(stamp, source, key, Jsonb(payload)) for stamp, source, key, payload in raw],
                )

    def delete_stamp(self, stamp: str) -> None:
        with self._connection.transaction(), self._connection.cursor() as cursor:
            self._delete(cursor, stamp)

    def stamps(self) -> list[str]:
        return [row[0] for row in self._rows("SELECT DISTINCT stamp FROM unit ORDER BY stamp", ())]

    def counts(self, stamp: str) -> dict[str, int]:
        return {
            table: self._one(f"SELECT count(*) FROM {table} WHERE stamp = %s", (stamp,))[0]
            for table in STAMPED_TABLES
        }

    def read_unit(self, stamp: str, unit_id: int) -> UnitRecord:
        head = self._one(
            "SELECT name, rarity, ult FROM unit WHERE stamp = %s AND id = %s", (stamp, unit_id)
        )
        if head is None:
            raise LookupError(f"no unit {unit_id} at stamp {stamp}")
        releases = self._releases(stamp, unit_id)
        extra = [
            release.payload["after_weapon_id"]
            for release in releases
            if release.kind == "weapon_change"
        ]
        return UnitRecord(
            id=unit_id,
            name=head[0],
            rarity=head[1],
            ult=head[2],
            stats=self._stats("unit_stat", "unit_id", stamp, unit_id),
            ssp_stats=self._ssp_stats(stamp, unit_id),
            releases=releases,
            weapons=self._weapons(stamp, unit_id, extra),
        )

    def read_pilot(self, stamp: str, pilot_id: int) -> PilotRecord:
        head = self._one(
            "SELECT name, rarity FROM pilot WHERE stamp = %s AND id = %s", (stamp, pilot_id)
        )
        if head is None:
            raise LookupError(f"no pilot {pilot_id} at stamp {stamp}")
        return PilotRecord(
            id=pilot_id,
            name=head[0],
            rarity=head[1],
            stats=self._stats("pilot_stat", "pilot_id", stamp, pilot_id),
        )

    def read_supporter(self, stamp: str, supporter_id: int) -> SupporterRecord:
        head = self._one(
            "SELECT name, rarity, max_hp_addition, max_attack_addition"
            " FROM supporter WHERE stamp = %s AND id = %s",
            (stamp, supporter_id),
        )
        if head is None:
            raise LookupError(f"no supporter {supporter_id} at stamp {stamp}")
        return SupporterRecord(
            id=supporter_id,
            name=head[0],
            rarity=head[1],
            max_hp_addition=head[2],
            max_attack_addition=head[3],
        )

    def supporter_rate(self, level: int, limit_break: int) -> int:
        row = self._one(
            "SELECT correction_rate FROM supporter_growth WHERE level = %s AND limit_break = %s",
            (level, limit_break),
        )
        if row is None:
            raise LookupError(f"no support crew growth row for level {level} step {limit_break}")
        return row[0]

    def _delete(self, cursor: psycopg.Cursor, stamp: str) -> None:
        for table in DELETE_ORDER:
            cursor.execute(f"DELETE FROM {table} WHERE stamp = %s", (stamp,))

    def _one(self, query: str, params: tuple) -> tuple | None:
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()

    def _rows(self, query: str, params: tuple) -> list[tuple]:
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def _stats(self, table: str, key: str, stamp: str, owner_id: int) -> dict[str, StatRow]:
        rows = self._rows(
            f"SELECT stat, base, max, sp_base, sp_max FROM {table}"
            f" WHERE stamp = %s AND {key} = %s",
            (stamp, owner_id),
        )
        return {row[0]: StatRow(*row[1:]) for row in rows}

    def _ssp_stats(self, stamp: str, unit_id: int) -> dict[str, SspStat]:
        rows = self._rows(
            "SELECT stat, base, max FROM unit_ssp_stat WHERE stamp = %s AND unit_id = %s",
            (stamp, unit_id),
        )
        return {row[0]: SspStat(row[1], row[2]) for row in rows}

    def _releases(self, stamp: str, unit_id: int) -> tuple[SspRelease, ...]:
        rows = self._rows(
            "SELECT core_level, sort_order, kind, target_id, payload FROM unit_ssp_release"
            " WHERE stamp = %s AND unit_id = %s ORDER BY core_level, sort_order",
            (stamp, unit_id),
        )
        return tuple(SspRelease(*row) for row in rows)

    def _weapons(self, stamp: str, unit_id: int, extra: list[int]) -> tuple[WeaponRecord, ...]:
        rows = self._rows(
            f"SELECT {', '.join(WEAPON_FIELDS)} FROM weapon"
            " WHERE stamp = %s AND (unit_id = %s OR id = ANY(%s)) ORDER BY id",
            (stamp, unit_id, extra),
        )
        growth_rows = self._growth(stamp, [row[0] for row in rows])
        return tuple(WeaponRecord(*row, growth=growth_rows.get(row[0], {})) for row in rows)

    def _growth(self, stamp: str, weapon_ids: list[int]) -> dict[int, dict[int, WeaponGrowth]]:
        rows = self._rows(
            "SELECT weapon_id, level, power_rate, en_rate, hit_rate_rate, crit_rate_rate"
            " FROM weapon_growth WHERE stamp = %s AND weapon_id = ANY(%s) ORDER BY level",
            (stamp, weapon_ids),
        )
        table: dict[int, dict[int, WeaponGrowth]] = {}
        for weapon_id, level, *rates in rows:
            table.setdefault(weapon_id, {})[level] = WeaponGrowth(*rates)
        return table
