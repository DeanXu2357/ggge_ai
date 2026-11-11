"""Read and write the game data store (docs/how-to/game-data-db.md)."""

from __future__ import annotations

import os
from collections.abc import Iterable
from types import TracebackType
from typing import LiteralString

import psycopg
from psycopg import sql
from psycopg.abc import QueryNoTemplate
from psycopg.rows import TupleRow
from psycopg.types.json import Jsonb

from ggge_ai_2.gamedata.growth import GrowthTables
from ggge_ai_2.gamedata.normalize import COLUMNS, RAW_COLUMNS, Row, Rows

DEFAULT_URL = "postgresql://ggge:ggge@localhost:5432/ggge"

JSON_COLUMNS = frozenset({"payload", "leader_skill", "active_skill"})
DELETE_ORDER = (
    "holding",
    "unit",
    "pilot",
    "weapon",
    "supporter",
    "supporter_growth",
    "tag",
    "datamine_raw",
)
STAMPED_TABLES = tuple(COLUMNS) + ("datamine_raw",)

KEY_COLUMNS: dict[str, tuple[str, ...]] = {
    "tag": ("id",),
    "unit": ("id",),
    "unit_tag": ("unit_id", "tag_id"),
    "unit_series": ("unit_id", "series_id"),
    "unit_stat": ("unit_id", "stat"),
    "unit_terrain": ("unit_id", "terrain"),
    "unit_ability": ("unit_id", "sort"),
    "unit_ssp_stat": ("unit_id", "stat"),
    "unit_ssp_core": ("unit_id", "level"),
    "unit_ssp_release": ("unit_id", "core_level", "sort_order"),
    "weapon": ("id",),
    "weapon_growth": ("weapon_id", "level"),
    "weapon_trait": ("weapon_id", "sort"),
    "pilot": ("id",),
    "pilot_stat": ("pilot_id", "stat"),
    "pilot_tag": ("pilot_id", "tag_id"),
    "pilot_series": ("pilot_id", "series_id"),
    "pilot_ability": ("pilot_id", "sort"),
    "pilot_skill": ("pilot_id", "sort"),
    "supporter": ("id",),
    "supporter_limit_break": ("supporter_id", "step"),
    "supporter_growth": ("level", "limit_break"),
}


def database_url() -> str:
    return os.environ.get("GGGE_DATABASE_URL", DEFAULT_URL)


def _names(names: Iterable[str]) -> sql.Composed:
    return sql.SQL(", ").join(sql.Identifier(name) for name in names)


def _insert(table: str, columns: tuple[str, ...]) -> sql.Composed:
    return sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        sql.Identifier(table), _names(columns), sql.SQL(", ").join(sql.Placeholder() * len(columns))
    )


def _select(table: str) -> sql.Composed:
    return sql.SQL("SELECT {} FROM {} WHERE stamp = %s ORDER BY {}").format(
        _names(COLUMNS[table]), sql.Identifier(table), _names(KEY_COLUMNS[table])
    )


def _wrapped(table: str, row: Row) -> Row:
    columns = COLUMNS[table]
    return tuple(
        Jsonb(value) if columns[index] in JSON_COLUMNS and value is not None else value
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

    def read_growth_tables(self) -> GrowthTables:
        return GrowthTables(
            level_curve=self._pairs("SELECT level, rate FROM level_curve"),
            limit_break_rate_percent=self._pairs("SELECT step, rate_percent FROM limit_break_rate"),
            rarity_level_cap=self._pairs("SELECT rarity, cap FROM rarity_level_cap"),
        )

    def write_stamp(self, rows: Rows, raw: list[Row]) -> None:
        with self._connection.transaction(), self._connection.cursor() as cursor:
            self._delete(cursor, rows.stamp)
            for table, table_rows in rows.tables.items():
                if not table_rows:
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

    def read_rows(self, stamp: str) -> Rows:
        tables = {table: self._rows(_select(table), (stamp,)) for table in COLUMNS}
        if not tables["unit"]:
            raise LookupError(f"the store holds no unit at stamp {stamp}")
        return Rows(stamp=stamp, tables=tables)

    def delete_stamp(self, stamp: str) -> None:
        with self._connection.transaction(), self._connection.cursor() as cursor:
            self._delete(cursor, stamp)

    def stamps(self) -> list[str]:
        return [row[0] for row in self._rows("SELECT DISTINCT stamp FROM unit ORDER BY stamp", ())]

    def counts(self, stamp: str) -> dict[str, int]:
        return {table: self._count(table, stamp) for table in STAMPED_TABLES}

    def _delete(self, cursor: psycopg.Cursor[TupleRow], stamp: str) -> None:
        for table in DELETE_ORDER:
            cursor.execute(
                sql.SQL("DELETE FROM {} WHERE stamp = %s").format(sql.Identifier(table)), (stamp,)
            )

    def _count(self, table: str, stamp: str) -> int:
        query = sql.SQL("SELECT count(*) FROM {} WHERE stamp = %s").format(sql.Identifier(table))
        with self._connection.cursor() as cursor:
            cursor.execute(query, (stamp,))
            row = cursor.fetchone()
        assert row is not None, "count(*) returns one row"
        return row[0]

    def _pairs(self, query: LiteralString) -> dict[int, int]:
        return {row[0]: row[1] for row in self._rows(query, ())}

    def _rows(self, query: QueryNoTemplate, params: tuple[object, ...]) -> list[TupleRow]:
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()
