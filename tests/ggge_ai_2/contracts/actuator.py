import pytest

from ggge_ai_2.actuator.contract import (
    Actuator,
    DangerBand,
    Gesture,
    GestureBlocked,
    Rect,
    Tap,
    TouchPoint,
)

BAND = DangerBand((Rect(0, 0, 100, 100),))


class ActuatorContract:
    """Subclass per implementation; 'sent' returns the gestures that reached the device."""

    def make(self) -> Actuator:
        raise NotImplementedError

    def sent(self, actuator: Actuator) -> list[Gesture]:
        raise NotImplementedError

    def test_t0_is_not_after_t1(self):
        dispatch = self.make().dispatch(Tap(TouchPoint(500, 500)), BAND)

        assert dispatch.t0 <= dispatch.t1

    def test_gesture_in_the_band_is_blocked_and_not_sent(self):
        actuator = self.make()

        with pytest.raises(GestureBlocked):
            actuator.dispatch(Tap(TouchPoint(50, 50)), BAND)
        assert self.sent(actuator) == []

    def test_gesture_outside_the_band_is_sent_once(self):
        actuator = self.make()
        tap = Tap(TouchPoint(500, 500))

        actuator.dispatch(tap, BAND)

        assert self.sent(actuator) == [tap]
