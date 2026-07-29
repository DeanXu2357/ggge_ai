"""adb 截圖與觸控，以及「把一個行動打到裝置上」的接縫。"""

from __future__ import annotations

from typing import Any, Protocol

from .perceive import Observation


class Device(Protocol):
    def screenshot(self) -> Any: ...

    def tap(self, x: int, y: int) -> None: ...

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_s: float) -> None: ...


class Executor[ActionT](Protocol):
    """迴圈一個 tick 至多呼叫一次 perform；一次 perform 內部要按幾下由
    實作決定，但成敗一律由下一張畫面的證據裁決，不回報成功與否。"""

    def perform(self, action: ActionT, observation: Observation[Any]) -> None: ...


class LiveDevice:
    def screenshot(self) -> Any:
        raise NotImplementedError("批 2：內層實機首戰")

    def tap(self, x: int, y: int) -> None:
        raise NotImplementedError("批 2：內層實機首戰")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_s: float) -> None:
        raise NotImplementedError("批 2：內層實機首戰")


class LiveExecutor:
    def perform(self, action: Any, observation: Observation[Any]) -> None:
        raise NotImplementedError("批 2：內層實機首戰")
