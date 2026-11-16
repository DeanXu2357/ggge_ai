from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from ggge_ai_2.actuator.contract import (
    Dispatch,
    Gesture,
    GestureBlocked,
    Key,
    Rect,
    Swipe,
    Tap,
)
from ggge_ai_2.agent.clock import now


def run_adb(argv: list[str], timeout: float) -> None:
    # The program runs outside Claude Code, so the env block of .claude/settings.json
    # does not set ADB_LIBUSB; the project requires it for every adb call.
    subprocess.run(
        argv,
        timeout=timeout,
        check=True,
        capture_output=True,
        env={**os.environ, "ADB_LIBUSB": "1"},
    )


def _touched_points(gesture: Gesture) -> tuple[tuple[int, int], ...]:
    match gesture:
        case Tap(point):
            return (point,)
        case Swipe(start, end, _):
            return (start, end)
        case Key():
            return ()


def _input_args(gesture: Gesture) -> list[str]:
    match gesture:
        case Tap((x, y)):
            return ["tap", str(x), str(y)]
        case Swipe((x1, y1), (x2, y2), duration):
            return [
                "swipe",
                str(x1),
                str(y1),
                str(x2),
                str(y2),
                str(round(duration * 1000)),
            ]
        case Key(code):
            return ["keyevent", code]


@dataclass(frozen=True)
class AdbActuator:
    serial: str
    timeout: float = 5.0
    clock: Callable[[], float] = now
    run: Callable[[list[str], float], None] = run_adb

    def dispatch(self, gesture: Gesture, band: tuple[Rect, ...]) -> Dispatch:
        if any(r.contains(p) for p in _touched_points(gesture) for r in band):
            raise GestureBlocked(gesture)
        argv = ["adb", "-s", self.serial, "shell", "input", *_input_args(gesture)]
        t0 = self.clock()
        self.run(argv, self.timeout)
        t1 = self.clock()
        return Dispatch(t0, t1)
