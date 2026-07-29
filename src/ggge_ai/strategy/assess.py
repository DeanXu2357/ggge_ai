"""隊伍實力評估：沙盤診斷門面＋參數微調實驗。"""

from __future__ import annotations

from ..contracts import Bottleneck, Diagnosis


def assess(stage: str) -> Diagnosis:
    raise NotImplementedError("批 4：診斷門面")


def probe_requirements(stage: str, target_win_rate: float) -> tuple[Bottleneck, ...]:
    raise NotImplementedError("批 4：參數微調實驗")
