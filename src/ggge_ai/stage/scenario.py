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

from ..engine.contract import Cell, Faction
from ..engine.state import DEFAULT_RULES, BattleState, EventTable, Rules, StageEvent, Unit
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
    rules: Rules
    intel: Intelligence
    units: tuple[Unit, ...]
    victory: dict[str, Any]
    defeat: dict[str, Any]
    events: EventTable = field(default_factory=dict)

    def build(self) -> tuple[BattleState, Rules, EventTable]:
        state = BattleState(
            units=[unit.clone() for unit in self.units],
            phase=Faction.ALLY,
            turn=1,
            bounds=self.board.bounds,
            pending_events=tuple(self.events),
        )
        return state, self.rules, dict(self.events)


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
    rules = _rules(data.get("rules", {}))

    taken: set[str] = set()
    units = tuple(
        _unit(entry, knowledge, board, taken, "deployment") for entry in data.get("deployment", ())
    )
    events = _events(data.get("events", {}), knowledge, board, taken)

    return Scenario(
        stage=data.get("stage", ""),
        note=data.get("note", ""),
        board=board,
        rules=rules,
        intel=knowledge,
        units=units,
        victory=dict(data.get("victory", {"type": VICTORY_ANNIHILATION})),
        defeat=dict(data.get("defeat", {"type": DEFEAT_ALLY_ANNIHILATION})),
        events=events,
    )


def check_outcome(scenario: Scenario, state: BattleState) -> str | None:
    if _met(scenario.defeat, state, DEFEAT_ALLY_ANNIHILATION, DEFEAT_PROTECT, Faction.ALLY):
        return "defeat"
    if _met(scenario.victory, state, VICTORY_ANNIHILATION, VICTORY_DESTROY_TARGET, Faction.ENEMY):
        return "victory"
    return None


def _met(
    condition: dict[str, Any],
    state: BattleState,
    wipe_type: str,
    unit_type: str,
    side: Faction,
) -> bool:
    kind = condition.get("type")
    if kind == wipe_type:
        return not state.by_faction(side)
    if kind == unit_type:
        target = state.unit(condition.get("uid"))
        return target is None or not target.alive
    return False


def _board(raw: dict[str, Any]) -> Board:
    cols, rows = int(raw.get("cols", 0)), int(raw.get("rows", 0))
    if cols <= 0 or rows <= 0:
        raise ValueError(f"盤面尺寸不合法：cols={cols} rows={rows}")
    return Board(cols=cols, rows=rows)


def _rules(overrides: dict[str, Any]) -> Rules:
    unknown = sorted(set(overrides) - {f.name for f in Rules.__dataclass_fields__.values()})
    if unknown:
        raise ValueError(f"rules 有未知欄位：{'、'.join(unknown)}")
    return replace(DEFAULT_RULES, **overrides)


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
    uid = entry.get("uid")
    if not uid:
        raise ValueError(f"{where} 有一筆沒寫 uid")
    if uid in taken:
        raise ValueError(f"uid 重複：{uid}")
    taken.add(uid)
    record = _record(knowledge, entry.get("intel_id", ""), f"{where} {uid}")
    unit = record.to_unit(
        _faction(entry.get("faction", Faction.ENEMY), f"{where} {uid}"),
        pos=_cell(entry.get("cell", [0, 0]), board, f"{where} {uid}"),
        hp=entry.get("hp"),
        en=entry.get("en"),
        acted=bool(entry.get("acted", False)),
    )
    unit.unit_id = uid
    return unit


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
