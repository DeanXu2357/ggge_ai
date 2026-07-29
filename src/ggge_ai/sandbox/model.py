"""戰局狀態與轉移（承接遊戲機制事實：公式、結算順序）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BattleState:
    """欄位待批 1 從 docs/combat-formulas.md 與現有 sim 搬入。"""


def transition(state: BattleState, move: object) -> BattleState:
    raise NotImplementedError("批 1：內層離線")
