from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

# Read every time from the clock that the agent uses. The agent compares gesture times
# with frame times directly.
Instant = float
ScreenPoint = tuple[int, int]


@dataclass(frozen=True)
class Tap:
    point: ScreenPoint


@dataclass(frozen=True)
class Swipe:
    start: ScreenPoint
    end: ScreenPoint
    duration: float


@dataclass(frozen=True)
class Key:
    code: str


Gesture = Tap | Swipe | Key


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    def contains(self, point: ScreenPoint) -> bool:
        x, y = point
        return self.left <= x < self.right and self.top <= y < self.bottom


@dataclass(frozen=True)
class Dispatch:
    t0: Instant
    t1: Instant


class GestureBlocked(Exception):
    pass


class Actuator(Protocol):
    def dispatch(self, gesture: Gesture, band: tuple[Rect, ...]) -> Dispatch:
        """Send one gesture and return the host-clock times around the command.

        `t0` is read before the command is sent and `t1` after the command returns.
        The touch lands between the two, on the assumption that the command waits for
        the injection. This assumption is not verified on the device. A return does
        not show that the game took the touch; only a later frame shows that.

        Raise GestureBlocked when the gesture touches the band. Return or raise
        within a fixed timeout, so that the main loop cannot hang here.
        """
        ...
