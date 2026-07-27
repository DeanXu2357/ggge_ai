"""Stand-ins for the classifier, the device, and time. No I/O anywhere."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .frame import FrameReading, Tag


class MockScreen:
    """The fake game screen: one capture per tick.

    In the real system `capture()` returns an image and the classifier turns
    it into a FrameReading; the mock world is already symbolic, so its
    "frame" type is FrameReading itself and the classifier is the identity.
    The seam is the point: the loop never fuses capture with classification,
    so the real classifier stays a pure function testable on saved PNGs.

    Three layers, outermost wins:

    - `script[i]` is what the game does to us at tick i regardless of what we
      did -- a story overlay, a popup. `None` means no interference. Past the
      end of the script there is no interference.
    - `overlay` is a screen stacked on top of the base by our own actions
      (the unit panel over the hub). `enter`/`retag_overlay`/`exit` model
      "the hub persists underneath" without every action rebuilding hub tags.
    - `base` is the steady screen. Actions mutate it with `retag_base`, which
      is how a tap becomes visible to the next tick's capture.
    """

    def __init__(
        self,
        base: FrameReading,
        script: Sequence[FrameReading | None] = (),
    ) -> None:
        self.base = base
        self.overlay: FrameReading | None = None
        self.script = list(script)
        self.captures = 0

    def capture(self) -> FrameReading:
        index = self.captures
        self.captures += 1
        if index < len(self.script) and self.script[index] is not None:
            return self.script[index]
        return self.overlay if self.overlay is not None else self.base

    def retag_base(self, add: Iterable[Tag] = (), remove: Iterable[str] = ()) -> None:
        self.base = _retagged(self.base, add, remove)

    def enter(self, tags: Iterable[Tag] = ()) -> None:
        self.overlay = FrameReading(tuple(tags))

    def retag_overlay(self, add: Iterable[Tag] = (), remove: Iterable[str] = ()) -> None:
        assert self.overlay is not None
        self.overlay = _retagged(self.overlay, add, remove)

    def exit(self) -> None:
        self.overlay = None


def _retagged(reading: FrameReading, add: Iterable[Tag], remove: Iterable[str]) -> FrameReading:
    gone = set(remove)
    kept = tuple(tag for tag in reading.tags if tag.name not in gone)
    return FrameReading(kept + tuple(add))


class IdentityClassifier:
    """Mock classifier: the mock screen already speaks FrameReading.

    The real one is `classify(image) -> FrameReading` -- a pure function over
    one frame, regression-tested against saved screenshots.
    """

    def classify(self, frame: FrameReading) -> FrameReading:
        return frame


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
