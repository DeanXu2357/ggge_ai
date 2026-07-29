"""一次攻略的生命週期：StageOrder 進、StageReport 出。"""

from __future__ import annotations

from ..contracts import StageOrder, StageReport


def run_stage(order: StageOrder) -> StageReport:
    raise NotImplementedError("批 1：內層離線")
