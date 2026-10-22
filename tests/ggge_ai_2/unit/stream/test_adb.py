from __future__ import annotations

import numpy as np

from ggge_ai_2.stream.adb import AdbScreencapStream
from ggge_ai_2.stream.contract import NO_DISPLACEMENT, StillWindow

DARK = np.zeros((16, 16, 3), np.uint8)
BRIGHT = np.full((16, 16, 3), 255, np.uint8)


class Script:
    def __init__(self, images: list[np.ndarray]) -> None:
        self.images = iter(images)
        self.t = -1.0

    def clock(self) -> float:
        self.t += 1.0
        return self.t

    def capture(self) -> np.ndarray:
        return next(self.images)


def make(images: list[np.ndarray]) -> AdbScreencapStream:
    script = Script(images)
    return AdbScreencapStream(
        serial="SER", still_seconds=5.0, clock=script.clock, capture=script.capture
    )


def test_still_run_returns_window_from_first_equal_frame() -> None:
    obs = make([DARK, DARK, DARK]).settled(after=-1.0, deadline=100.0)
    assert obs.still == StillWindow(1.5, 7.5, 3)
    assert obs.frame.seq == 3
    assert obs.after == -1.0
    assert obs.waited == 9.0
    assert obs.displacement == NO_DISPLACEMENT


def test_change_restarts_still_run() -> None:
    obs = make([DARK, BRIGHT, BRIGHT, BRIGHT]).settled(after=0.0, deadline=100.0)
    assert obs.still == StillWindow(4.5, 10.5, 4)
    assert obs.frame.image is BRIGHT


def test_deadline_returns_last_frame_without_still() -> None:
    obs = make([DARK, BRIGHT, DARK]).settled(after=0.0, deadline=8.0)
    assert obs.still is None
    assert obs.frame.seq == 3
    assert obs.frame.captured_at == 7.5
    assert obs.waited == 9.0
    assert obs.displacement == NO_DISPLACEMENT


def test_latest_counts_seq_and_stamps_midpoint() -> None:
    stream = make([DARK, BRIGHT])
    first = stream.latest()
    second = stream.latest()
    assert (first.seq, first.captured_at) == (1, 0.5)
    assert (second.seq, second.captured_at) == (2, 2.5)
