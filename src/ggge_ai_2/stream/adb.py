from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field

import cv2
import numpy as np

from ggge_ai_2.agent.clock import now
from ggge_ai_2.stream.contract import (
    NO_DISPLACEMENT,
    Frame,
    Instant,
    Observation,
    StillWindow,
)


def screencap(serial: str) -> np.ndarray:
    result = subprocess.run(
        ["adb", "-s", serial, "exec-out", "screencap", "-p"],
        timeout=10,
        check=True,
        capture_output=True,
        env={**os.environ, "ADB_LIBUSB": "1"},
    )
    image = cv2.imdecode(np.frombuffer(result.stdout, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("screencap output is not a PNG image")
    return image


def _thumbnail(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    h, w = gray.shape[:2]
    return cv2.resize(gray, (w // 8, h // 8), interpolation=cv2.INTER_AREA)


@dataclass
class AdbScreencapStream:
    serial: str
    still_seconds: float = 0.6
    diff_threshold: float = 2.0
    clock: Callable[[], float] = now
    capture: Callable[[], np.ndarray] | None = None
    _seq: int = field(default=0, init=False)

    def _capture(self) -> np.ndarray:
        if self.capture is None:
            return screencap(self.serial)
        return self.capture()

    def _same_screen(self, a: Frame, b: Frame) -> bool:
        diff = cv2.absdiff(_thumbnail(a.image), _thumbnail(b.image))
        return float(np.mean(diff)) < self.diff_threshold

    def latest(self) -> Frame:
        t_before = self.clock()
        image = self._capture()
        t_after = self.clock()
        self._seq += 1
        return Frame(image, (t_before + t_after) / 2, self._seq)

    def settled(self, after: Instant, deadline: Instant) -> Observation:
        start = self.clock()
        # Warning: displacement is always NO_DISPLACEMENT. The map camera tracking
        # is not built.
        frame = self.latest()
        run_start = frame
        while True:
            if frame.captured_at - run_start.captured_at >= self.still_seconds:
                still = StillWindow(run_start.captured_at, frame.captured_at, frame.seq)
                return Observation(frame, after, still, self.clock() - start, NO_DISPLACEMENT)
            checked_at = self.clock()
            if checked_at >= deadline:
                return Observation(frame, after, None, checked_at - start, NO_DISPLACEMENT)
            previous, frame = frame, self.latest()
            if not self._same_screen(previous, frame):
                run_start = frame
