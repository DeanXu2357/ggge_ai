"""The stage layout: one JSON file of a stage read into a start state.

The unit values come from the intel store, in the 'intel' section. The layout
file itself writes who stands where, and what each one has left. It holds no
rule: the engine answers every question that needs one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from ..engine.contract import Cell, Faction, Terrain
from ..engine.state import (
    BattleState,
    EventTable,
    StageEvent,
    TerrainCell,
    Unit,
)
from . import intel as intel_mod
from .intel import Intelligence, UnitIntel

FORMAT = "sandbox-scenario/1"

VICTORY_ANNIHILATION = "annihilation"
VICTORY_DESTROY_TARGET = "destroy_target"
DEFEAT_ALLY_ANNIHILATION = "ally_annihilation"
DEFEAT_PROTECT = "protect"


@dataclass(frozen=True)
class Board:
    cols: int
    rows: int
    terrain: Terrain | None = None
    terrain_cells: tuple[TerrainCell, ...] = ()

    @property
    def bounds(self) -> tuple[Cell, Cell]:
        return ((0, 0), (self.cols - 1, self.rows - 1))

    def contains(self, cell: Cell) -> bool:
        return 0 <= cell[0] < self.cols and 0 <= cell[1] < self.rows


@dataclass(frozen=True)
class Scenario:
    stage: str
    note: str
    board: Board
    intel: Intelligence
    units: tuple[Unit, ...]
    victory: dict[str, Any]
    defeat: dict[str, Any]
    events: EventTable = field(default_factory=dict)

    def build(self) -> tuple[BattleState, EventTable]:
        state = BattleState(
            units=[unit.clone() for unit in self.units],
            phase=Faction.ALLY,
            turn=1,
            bounds=self.board.bounds,
            pending_events=tuple(self.events),
            terrain=self.board.terrain,
            terrain_cells=self.board.terrain_cells,
        )
        return state, dict(self.events)


def load(path: str | Path) -> Scenario:
    return from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def loads(text: str) -> Scenario:
    return from_dict(json.loads(text))


def from_dict(data: dict[str, Any]) -> Scenario:
    fmt = data.get("format")
    if fmt != FORMAT:
        raise ValueError(f"情境檔格式不符：期待 {FORMAT}，讀到 {fmt!r}")

    board = _board(data.get("board", {}))
    knowledge = intel_mod.from_dict(data.get("intel", {}))

    taken: set[str] = set()
    units = tuple(
        _unit(entry, knowledge, board, taken, "deployment") for entry in data.get("deployment", ())
    )
    events = _events(data.get("events", {}), knowledge, board, taken)

    return Scenario(
        stage=data.get("stage", ""),
        note=data.get("note", ""),
        board=board,
        intel=knowledge,
        units=units,
        victory=dict(data.get("victory", {"type": VICTORY_ANNIHILATION})),
        defeat=dict(data.get("defeat", {"type": DEFEAT_ALLY_ANNIHILATION})),
        events=events,
    )


def _board(raw: dict[str, Any]) -> Board:
    cols, rows = int(raw.get("cols", 0)), int(raw.get("rows", 0))
    if cols <= 0 or rows <= 0:
        raise ValueError(f"盤面尺寸不合法：cols={cols} rows={rows}")
    board = Board(cols=cols, rows=rows, terrain=_optional_terrain(raw.get("terrain")))
    return replace(board, terrain_cells=_terrain_cells(raw.get("terrain_cells", ()), board))


def _optional_terrain(raw: Any) -> Terrain | None:
    return None if raw is None else _terrain(raw)


def _terrain(raw: Any) -> Terrain:
    try:
        return Terrain(raw)
    except ValueError as exc:
        raise ValueError(f"地形不在合約內：{raw!r}") from exc


def _terrain_cells(raw: Any, board: Board) -> tuple[TerrainCell, ...]:
    out: list[TerrainCell] = []
    seen: set[Cell] = set()
    for entry in raw:
        cell = (int(entry["cell"][0]), int(entry["cell"][1]))
        if not board.contains(cell):
            raise ValueError(f"地形格出界：{cell}")
        if cell in seen:
            raise ValueError(f"地形格重複：{cell}")
        seen.add(cell)
        out.append(TerrainCell(cell=cell, terrain=_terrain(entry["terrain"])))
    return tuple(out)


def _record(knowledge: Intelligence, intel_id: str, where: str) -> UnitIntel:
    record = knowledge.record(intel_id)
    if record is None:
        raise ValueError(f"{where} 的 intel_id 在情報庫查無此筆：{intel_id}")
    return record


def _cell(raw: Any, board: Board, where: str) -> Cell:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError(f"{where} 的 cell 要寫成 [x, y]，讀到 {raw!r}")
    cell = (int(raw[0]), int(raw[1]))
    if not board.contains(cell):
        raise ValueError(f"{where} 的格位越界：{list(cell)} 不在 {board.cols}x{board.rows} 盤面內")
    return cell


def _faction(raw: Any, where: str) -> Faction:
    try:
        return Faction(raw)
    except ValueError as exc:
        raise ValueError(f"{where} 的 faction 不合法：{raw!r}") from exc


def _unit(
    entry: dict[str, Any],
    knowledge: Intelligence,
    board: Board,
    taken: set[str],
    where: str,
) -> Unit:
    # uid 是情境檔自己的名稱，只用來擋重複；引擎收到的識別是出場順序。
    uid = entry.get("uid")
    if not uid:
        raise ValueError(f"{where} 有一筆沒寫 uid")
    if uid in taken:
        raise ValueError(f"uid 重複：{uid}")
    taken.add(uid)
    record = _record(knowledge, entry.get("intel_id", ""), f"{where} {uid}")
    return record.to_unit(
        _faction(entry.get("faction", Faction.ENEMY), f"{where} {uid}"),
        pos=_cell(entry.get("cell", [0, 0]), board, f"{where} {uid}"),
        hp=entry.get("hp"),
        en=entry.get("en"),
        acted=bool(entry.get("acted", False)),
    )


def _events(
    raw: dict[str, Any], knowledge: Intelligence, board: Board, taken: set[str]
) -> EventTable:
    table: EventTable = {}
    for event_id, body in raw.items():
        effect = dict(body.get("effect", {}))
        if effect.get("type") == "spawn":
            effect["units"] = [
                _unit(entry, knowledge, board, taken, f"事件 {event_id} spawn")
                for entry in effect.get("units", ())
            ]
        table[event_id] = StageEvent(
            event_id=event_id, trigger=dict(body.get("trigger", {})), effect=effect
        )
    return table
