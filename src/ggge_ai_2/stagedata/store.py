"""Read and write the stage data in the game data store (docs/how-to/game-data-db.md)."""

from __future__ import annotations

from collections import defaultdict
from types import TracebackType

import cv2
import numpy as np
import psycopg
from psycopg.rows import TupleRow

from ggge_ai_2.gamedata.store import database_url
from ggge_ai_2.stagedata.contract import (
    Faction,
    NameMask,
    PilotState,
    StageCell,
    StageData,
    StageUnit,
    Terrain,
    UnitBrief,
    UnitDetail,
    UnitRole,
)

UNIT_COLUMNS = (
    "sort",
    "anchor_column",
    "anchor_row",
    "width",
    "height",
    "faction",
    "controllable",
    "mech_role",
    "mech_name_mask",
    "hp",
    "en",
    "pilot_role",
    "pilot_name_mask",
    "mp",
    "mp_max",
    "pilot_state",
)
KEY = "stage_id = %s AND stage_app_version = %s"


class PostgresStageStore:
    def __init__(self, conninfo: str | None = None) -> None:
        self._connection = psycopg.connect(conninfo or database_url(), autocommit=True)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> PostgresStageStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def load(self, stage: str, app_version: str) -> StageData | None:
        key = (stage, app_version)
        with self._connection.cursor() as cursor:
            head = cursor.execute(
                "SELECT code_version, column_count, row_count FROM stage"
                " WHERE id = %s AND app_version = %s",
                key,
            ).fetchone()
            if head is None:
                return None
            terrain: defaultdict[StageCell, set[Terrain]] = defaultdict(set)
            for column, row, name in cursor.execute(
                f"SELECT cell_column, cell_row, terrain FROM stage_terrain WHERE {KEY}", key
            ):
                terrain[(column, row)].add(Terrain(name))
            deploy_cells = tuple(
                (column, row)
                for column, row in cursor.execute(
                    f"SELECT cell_column, cell_row FROM stage_deploy_cell WHERE {KEY}"
                    " ORDER BY slot",
                    key,
                )
            )
            units = tuple(
                _unit(row)
                for row in cursor.execute(
                    f"SELECT {', '.join(UNIT_COLUMNS)} FROM stage_unit WHERE {KEY} ORDER BY sort",
                    key,
                )
            )
        code_version, columns, rows = head
        return StageData(
            stage=stage,
            app_version=app_version,
            code_version=code_version,
            columns=columns,
            rows=rows,
            terrain={cell: frozenset(names) for cell, names in terrain.items()},
            deploy_cells=deploy_cells,
            units=units,
            victory=(),
            events=(),
        )

    def save(self, data: StageData) -> None:
        key = (data.stage, data.app_version)
        with self._connection.transaction(), self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO stage (id, app_version, code_version, column_count, row_count)"
                " VALUES (%s, %s, %s, %s, %s)",
                (*key, data.code_version, data.columns, data.rows),
            )
            cursor.executemany(
                "INSERT INTO stage_terrain"
                " (stage_id, stage_app_version, cell_column, cell_row, terrain)"
                " VALUES (%s, %s, %s, %s, %s)",
                [
                    (*key, column, row, terrain.value)
                    for (column, row), terrains in data.terrain.items()
                    for terrain in terrains
                ],
            )
            cursor.executemany(
                "INSERT INTO stage_deploy_cell"
                " (stage_id, stage_app_version, slot, cell_column, cell_row)"
                " VALUES (%s, %s, %s, %s, %s)",
                [(*key, slot, column, row) for slot, (column, row) in enumerate(data.deploy_cells)],
            )
            placeholders = ", ".join(("%s",) * (len(UNIT_COLUMNS) + 2))
            cursor.executemany(
                f"INSERT INTO stage_unit (stage_id, stage_app_version, {', '.join(UNIT_COLUMNS)})"
                f" VALUES ({placeholders})",
                [(*key, *_unit_row(sort, unit)) for sort, unit in enumerate(data.units)],
            )


def _unit_row(sort: int, unit: StageUnit) -> tuple[object, ...]:
    brief = unit.brief
    return (
        sort,
        *unit.pos,
        *unit.size,
        unit.faction.value,
        unit.controllable,
        brief.mech_role.value,
        _png(brief.mech_name),
        brief.hp,
        brief.en,
        brief.pilot_role.value,
        _png(brief.pilot_name),
        brief.mp,
        brief.mp_max,
        brief.state.value,
    )


def _unit(row: TupleRow) -> StageUnit:
    (
        _,
        column,
        anchor_row,
        width,
        height,
        faction,
        controllable,
        mech_role,
        mech_name,
        hp,
        en,
        pilot_role,
        pilot_name,
        mp,
        mp_max,
        state,
    ) = row
    brief = UnitBrief(
        mech_role=UnitRole(mech_role),
        mech_name=_mask(mech_name),
        hp=hp,
        en=en,
        pilot_role=UnitRole(pilot_role),
        pilot_name=_mask(pilot_name),
        mp=mp,
        mp_max=mp_max,
        state=PilotState(state),
    )
    return StageUnit(
        (column, anchor_row),
        (width, height),
        Faction(faction),
        controllable,
        brief,
        UnitDetail(),
    )


def _png(name: NameMask) -> bytes:
    encoded, buffer = cv2.imencode(".png", name.mask)
    assert encoded, "PNG encodes every 8-bit gray mask"
    return buffer.tobytes()


def _mask(data: bytes) -> NameMask:
    mask = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    assert mask is not None, "the store holds only the PNG that '_png' writes"
    return NameMask(mask)
