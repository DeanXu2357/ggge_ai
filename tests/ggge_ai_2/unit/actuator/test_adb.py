from __future__ import annotations

import pytest

from ggge_ai_2.actuator.adb import AdbActuator
from ggge_ai_2.actuator.contract import (
    Dispatch,
    Gesture,
    GestureBlocked,
    Key,
    Rect,
    Swipe,
    Tap,
)


class Recorder:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.calls: list[tuple[list[str], float]] = []
        self.ticks = iter([10.0, 11.0])

    def clock(self) -> float:
        t = next(self.ticks)
        self.events.append(f"clock {t}")
        return t

    def run(self, argv: list[str], timeout: float) -> None:
        self.events.append("run")
        self.calls.append((argv, timeout))


def make(rec: Recorder) -> AdbActuator:
    return AdbActuator(serial="SER", timeout=3.0, clock=rec.clock, run=rec.run)


PREFIX = ["adb", "-s", "SER", "shell", "input"]


@pytest.mark.parametrize(
    ("gesture", "args"),
    [
        (Tap((100, 200)), ["tap", "100", "200"]),
        (Swipe((1, 2), (3, 4), 0.25), ["swipe", "1", "2", "3", "4", "250"]),
        (Key("KEYCODE_BACK"), ["keyevent", "KEYCODE_BACK"]),
    ],
)
def test_argv(gesture: Gesture, args: list[str]) -> None:
    rec = Recorder()
    make(rec).dispatch(gesture, ())
    assert rec.calls == [(PREFIX + args, 3.0)]


BAND = (Rect(0, 0, 50, 50),)


@pytest.mark.parametrize(
    "gesture",
    [Tap((10, 10)), Swipe((500, 500), (10, 10), 0.3)],
)
def test_blocked_gesture_does_not_run(gesture: Gesture) -> None:
    rec = Recorder()
    with pytest.raises(GestureBlocked):
        make(rec).dispatch(gesture, BAND)
    assert rec.calls == []


def test_key_is_never_blocked() -> None:
    rec = Recorder()
    make(rec).dispatch(Key("KEYCODE_BACK"), (Rect(-10000, -10000, 10000, 10000),))
    assert len(rec.calls) == 1


def test_times_surround_run() -> None:
    rec = Recorder()
    result = make(rec).dispatch(Tap((100, 100)), BAND)
    assert result == Dispatch(10.0, 11.0)
    assert rec.events == ["clock 10.0", "run", "clock 11.0"]
