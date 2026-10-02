from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

# Read every time from the clock that the agent uses. The agent compares frame times
# with gesture times directly.
Instant = float
Displacement = tuple[float, float]
NO_DISPLACEMENT: Displacement = (0.0, 0.0)


def add_displacement(a: Displacement, b: Displacement) -> Displacement:
    return (a[0] + b[0], a[1] + b[1])


@dataclass(frozen=True)
class Frame:
    image: np.ndarray
    captured_at: Instant
    seq: int


@dataclass(frozen=True)
class StillWindow:
    since: Instant
    until: Instant
    frame_seq: int


@dataclass(frozen=True)
class Observation:
    frame: Frame
    after: Instant
    still: StillWindow | None
    waited: float
    displacement: Displacement


class Stream(Protocol):
    def latest(self) -> Frame: ...

    def settled(self, after: Instant, deadline: Instant) -> Observation:
        """Wait for a still screen in the frames captured after `after`.

        The screen is still when it does not change for a fixed time length. The
        length is in seconds, not in frames, so the result does not change with the
        sampling interval. At `deadline` the method returns the last frame with
        `still` set to None. The result repeats `after`, and `displacement` is the
        move of the frame content from `after` to the returned frame. The method does
        not send a gesture.
        """
        ...
