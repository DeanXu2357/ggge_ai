"""Accumulated observation, owned by one object."""

from __future__ import annotations

from dataclasses import dataclass

from ggge_ai.goap.state import Value

from .state import UNKNOWN


@dataclass
class MockBoard:
    """Single owner of everything we have accumulated about the map.

    The real thing is CellMap + TacticalMap + BattleState fused into one
    object: terrain per cell, unit identities, forecast tables, scan residue.
    None of that belongs in `BotState` -- the planner cannot search over a
    cell map, and a symbol space that carries it stops being hashable and
    stops being readable in a log line.

    So the contract is: big data stays here, only `summary_symbols()` crosses
    into the state. Everything the planner is allowed to reason about is one
    of the three verdicts below.
    """

    covered_cells: int = 0
    total_cells: int = 0
    resolved_units: int = 0
    candidates: int = 0
    pose: str = "anchored"
    # covered_cells 是累計的觀測筆數（只增不減），total_cells 是判定覆蓋完成的
    # 門檻，不是上限。

    def coverage_verdict(self) -> str:
        # 鏡頭對位掉了就等於整張覆蓋圖不可信，不是「部分覆蓋」而是「不知道」。
        if self.pose == "lost" or self.total_cells == 0:
            return UNKNOWN
        return "complete" if self.covered_cells >= self.total_cells else "partial"

    def details_verdict(self) -> str:
        if self.candidates == 0:
            return UNKNOWN
        return "complete" if self.resolved_units >= self.candidates else "partial"

    def progress_key(self) -> tuple[int, int]:
        """What counts as accumulated progress, one column per tick in the log.

        An action that holds the head of the plan for many ticks is fine while
        this keeps moving and suspicious the moment it stops.
        """
        return (self.covered_cells, self.resolved_units)

    def summary_symbols(self) -> dict[str, Value]:
        return {
            "coverage": self.coverage_verdict(),
            "details": self.details_verdict(),
            "pose": self.pose,
        }


BOARD_SYMBOLS = frozenset({"coverage", "details", "pose"})
