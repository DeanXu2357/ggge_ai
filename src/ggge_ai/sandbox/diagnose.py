"""外層門面：勝率＋瓶頸類型＋缺口數值。"""

from __future__ import annotations

from ..contracts import Diagnosis
from .model import BattleState


def diagnose(state: BattleState, depth: int) -> Diagnosis:
    raise NotImplementedError("批 4：診斷門面")
