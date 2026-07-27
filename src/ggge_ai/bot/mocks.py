"""Stand-ins for perception and the device. No I/O anywhere."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ggge_ai.goap.state import Value


class MockSensor:
    """Scripted perception: one observation per tick.

    Two layers, because a mock run needs both "the screen changed because we
    tapped something" and "the screen changed because the game did something":

    - `frame` is the steady-state observation. Mock actions call `override()`
      on it, which is how a tap becomes visible to the next tick's `sense`.
    - `script[i]` is what the game does to us at tick i regardless of what we
      did -- a story animation, a popup. It wins over `frame` for the keys it
      names, and its other keys fall through to `frame`. Once the script runs
      out the last entry repeats forever.
    """

    def __init__(
        self,
        frame: Mapping[str, Value],
        script: Sequence[Mapping[str, Value]] | None = None,
    ) -> None:
        self.frame = dict(frame)
        self.script = [dict(entry) for entry in (script or [])]
        self.tick = 0

    def read(self) -> dict[str, Value]:
        entry: Mapping[str, Value] = {}
        if self.script:
            entry = self.script[min(self.tick, len(self.script) - 1)]
        self.tick += 1
        return {**self.frame, **entry}

    def override(self, **observed: Value) -> None:
        self.frame.update(observed)


class MockDevice:
    """Records what would have been sent to the phone."""

    def __init__(self) -> None:
        self.taps: list[tuple[int, int]] = []
        self.swipes: list[tuple[int, int, int, int]] = []

    def tap(self, x: int, y: int) -> None:
        self.taps.append((x, y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self.swipes.append((x1, y1, x2, y2))
