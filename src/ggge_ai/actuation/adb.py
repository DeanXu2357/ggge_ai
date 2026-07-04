from __future__ import annotations

REFERENCE_RESOLUTION = (2340, 1080)  # 遊戲為橫向


class AdbActuator:
    """Sends input via uiautomator2. Coordinates are defined against the
    reference resolution and scaled to the current screen size, queried per
    call so device rotation cannot desync the mapping."""

    def __init__(self, device, reference: tuple[int, int] = REFERENCE_RESOLUTION) -> None:
        self.device = device
        self.reference = reference

    def _scale(self, x: int, y: int) -> tuple[int, int]:
        rx, ry = self.reference
        ax, ay = self.device.window_size()
        return (round(x * ax / rx), round(y * ay / ry))

    def tap(self, x: int, y: int) -> None:
        self.device.click(*self._scale(x, y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        sx1, sy1 = self._scale(x1, y1)
        sx2, sy2 = self._scale(x2, y2)
        self.device.swipe(sx1, sy1, sx2, sy2, duration=duration_ms / 1000)

    def key(self, keycode: str) -> None:
        self.device.press(keycode)
