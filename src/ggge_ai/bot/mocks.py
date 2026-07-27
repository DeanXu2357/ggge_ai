"""Stand-ins for the classifier, the device, and time. No I/O anywhere."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .frame import FrameReading, Tag


class MockClassifier:
    """Scripted classification: one FrameReading per tick.

    Three layers, outermost wins:

    - `script[i]` is what the game does to us at tick i regardless of what we
      did -- a story overlay, a popup. `None` means no interference. Past the
      end of the script there is no interference.
    - `overlay` is a screen stacked on top of the base by our own actions
      (the unit panel over the hub). `enter`/`retag_overlay`/`exit` model
      "the hub persists underneath" without every action rebuilding hub tags.
    - `base` is the steady screen. Actions mutate it with `retag_base`, which
      is how a tap becomes visible to the next tick's read.
    """

    def __init__(
        self,
        base: FrameReading,
        script: Sequence[FrameReading | None] = (),
    ) -> None:
        self.base = base
        self.overlay: FrameReading | None = None
        self.script = list(script)
        self.reads = 0

    def read(self) -> FrameReading:
        index = self.reads
        self.reads += 1
        if index < len(self.script) and self.script[index] is not None:
            return self.script[index]
        return self.overlay if self.overlay is not None else self.base

    def retag_base(self, add: Iterable[Tag] = (), remove: Iterable[str] = ()) -> None:
        gone = set(remove)
        kept = tuple(tag for tag in self.base.tags if tag.name not in gone)
        self.base = FrameReading(self.base.phase, kept + tuple(add))

    def enter(self, phase: str, tags: Iterable[Tag] = ()) -> None:
        self.overlay = FrameReading(phase, tuple(tags))

    def retag_overlay(self, tags: Iterable[Tag]) -> None:
        assert self.overlay is not None
        self.overlay = FrameReading(self.overlay.phase, tuple(tags))

    def exit(self) -> None:
        self.overlay = None


class MockDevice:
    """Records what would have been sent to the phone."""

    def __init__(self) -> None:
        self.taps: list[tuple[int, int]] = []
        self.swipes: list[tuple[int, int, int, int]] = []

    def tap(self, x: int, y: int) -> None:
        self.taps.append((x, y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self.swipes.append((x1, y1, x2, y2))

    @property
    def interactions(self) -> int:
        return len(self.taps) + len(self.swipes)


class MockClock:
    """Time that only advances when someone sleeps.

    Handlers and actions own their settle sleeps (`clock.sleep`); the tick
    loop reads `now_ms` before and after to put the cost in the record. The
    real clock sleeps for real and reports wall time.
    """

    def __init__(self) -> None:
        self._now_ms = 0

    def now_ms(self) -> int:
        return self._now_ms

    def slept_ms(self) -> int:
        # mock 的時間只因 sleep 前進，牆鐘＝睡眠鐘；真實時鐘兩者分開計。
        return self._now_ms

    def sleep(self, seconds: float) -> None:
        self._now_ms += int(seconds * 1000)
