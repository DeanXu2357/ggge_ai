"""tick 迴圈：感知→反射→簿記→規劃→至多一次操作。"""

from __future__ import annotations

from ..contracts import StageOrder, StageReport


class StageLoop:
    def __init__(self, order: StageOrder) -> None:
        self.order = order

    def tick(self) -> None:
        raise NotImplementedError("批 1：內層離線")

    def run(self) -> StageReport:
        raise NotImplementedError("批 1：內層離線")
