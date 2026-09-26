from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ggge_ai_2.clock import Instant


@dataclass(frozen=True)
class FramePoint:
    x: float
    y: float


@dataclass(frozen=True)
class FrameVector:
    dx: float
    dy: float


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
    still: StillWindow | None
    waited: float
    # The displacement is the move of the frame content, not of the camera: a
    # positive dx means the content moved right. The camera moves the other way.
    displacement: FrameVector


class NoFrame(Exception):
    pass


class Stream(Protocol):
    def latest(self) -> Frame: ...

    def settled(self, after: Instant, deadline: Instant) -> Observation:
        """Wait for a still screen in the frames captured after `after`.

        The screen is still when it does not change for a fixed time length. The
        length is in seconds, not in frames, so the result does not change with the
        sampling interval. At `deadline` the method returns the last frame with
        `still` set to None. It raises NoFrame when no frame arrives after `after`
        before the deadline. The method does not send a gesture.
        """
        ...
