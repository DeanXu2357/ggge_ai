from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from ggge_ai_2.clock import Instant
from ggge_ai_2.stream.contract import Frame, FrameVector, NoFrame, Observation, StillWindow


def frames(*marks: tuple[float, int]) -> list[Frame]:
    """Build frames from (capture time, image code) pairs; equal codes are equal images."""
    return [
        Frame(np.full((1, 1), code, np.uint8), at, seq)
        for seq, (at, code) in enumerate(marks, start=1)
    ]


def steady(code: int, start: float, end: float, step: float = 0.1) -> list[tuple[float, int]]:
    count = round((end - start) / step)
    return [(round(start + i * step, 6), code) for i in range(count + 1)]


def flicker(codes: tuple[int, int], start: float, end: float) -> list[tuple[float, int]]:
    return [(at, codes[i % 2]) for i, (at, _) in enumerate(steady(0, start, end))]


@dataclass
class TimelineStream:
    timeline: Sequence[Frame]
    still_for: float = 0.25
    now: Instant = 0.0
    calls: list[tuple[Instant, Instant]] = field(default_factory=list)

    def clock(self) -> Instant:
        return self.now

    def latest(self) -> Frame:
        later = [f for f in self.timeline if f.captured_at > self.now]
        frame = later[0] if later else self.timeline[-1]
        self.now = max(self.now, frame.captured_at)
        return frame

    def settled(self, after: Instant, deadline: Instant) -> Observation:
        self.calls.append((after, deadline))
        called_at = self.now
        window = [f for f in self.timeline if after < f.captured_at <= deadline]
        if not window:
            raise NoFrame(f"no frame in ({after}, {deadline}]")
        start = window[0]
        for frame in window:
            if not np.array_equal(frame.image, start.image):
                start = frame
            if frame.captured_at - start.captured_at >= self.still_for:
                self.now = max(self.now, frame.captured_at)
                still = StillWindow(start.captured_at, frame.captured_at, frame.seq)
                return Observation(frame, still, frame.captured_at - called_at, FrameVector(0, 0))
        self.now = max(self.now, deadline)
        last = window[-1]
        return Observation(last, None, deadline - called_at, FrameVector(0, 0))
