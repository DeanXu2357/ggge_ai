"""adb 截圖與觸控。"""

from __future__ import annotations

from typing import Any, Protocol


class Device(Protocol):
    def screenshot(self) -> Any: ...

    def tap(self, x: int, y: int) -> None: ...

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_s: float) -> None: ...
