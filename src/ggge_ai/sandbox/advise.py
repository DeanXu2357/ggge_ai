"""內層門面：戰術定價。"""

from __future__ import annotations

from .model import BattleState


def price(state: BattleState, move: object) -> float:
    raise NotImplementedError("批 1：內層離線")
