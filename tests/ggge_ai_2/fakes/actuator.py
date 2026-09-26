from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ggge_ai_2.actuator.contract import (
    DangerBand,
    Dispatch,
    Gesture,
    GestureBlocked,
    Swipe,
    Tap,
)
from ggge_ai_2.clock import Instant, now


@dataclass
class RecordingActuator:
    clock: Callable[[], Instant] = now
    sent: list[Gesture] = field(default_factory=list)

    def dispatch(self, gesture: Gesture, band: DangerBand) -> Dispatch:
        points = (
            (gesture.point,)
            if isinstance(gesture, Tap)
            else (gesture.start, gesture.end)
            if isinstance(gesture, Swipe)
            else ()
        )
        if any(band.contains(point) for point in points):
            raise GestureBlocked(gesture)
        t0 = self.clock()
        self.sent.append(gesture)
        return Dispatch(t0, self.clock())
