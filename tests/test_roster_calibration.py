import numpy as np

from ggge_ai.battle.roster_calibration import UnitListCalibrator

FRAME = np.zeros((4, 4, 3), np.uint8)


def _calibrator(shifts, row_taps=((10, 20), (10, 60), (10, 100))):
    calls = {"open": 0, "close": 0, "taps": [], "captures": 0}
    shift_iter = iter(shifts)

    def capture():
        calls["captures"] += 1
        return FRAME

    def tap(x, y):
        calls["taps"].append((x, y))

    def measure_shift(prev, cur):
        return next(shift_iter)

    calibrator = UnitListCalibrator(
        capture=capture,
        tap=tap,
        open_list=lambda: calls.__setitem__("open", calls["open"] + 1),
        close_list=lambda: calls.__setitem__("close", calls["close"] + 1),
        row_taps=row_taps,
        measure_shift=measure_shift,
    )
    return calibrator, calls


def test_accumulates_shift_across_rows():
    shifts = [((5.0, 0.0), 0.9), ((0.0, 3.0), 0.9), ((-2.0, -1.0), 0.9)]
    calibrator, calls = _calibrator(shifts)
    result = calibrator.calibrate()

    assert result.positions == {
        "slot_0": (5.0, 0.0),
        "slot_1": (5.0, 3.0),
        "slot_2": (3.0, 2.0),
    }
    assert result.low_confidence_slots == []
    assert calls["open"] == 1
    assert calls["close"] == 1
    assert calls["taps"] == [(10, 20), (10, 60), (10, 100)]
    # one capture before the loop (origin) + one per row
    assert calls["captures"] == 4


def test_low_confidence_shift_excluded_but_still_chained():
    shifts = [((5.0, 0.0), 0.9), ((0.0, 3.0), 0.02), ((1.0, 1.0), 0.9)]
    calibrator, _ = _calibrator(shifts)
    result = calibrator.calibrate()

    assert "slot_1" not in result.positions
    assert result.low_confidence_slots == ["slot_1"]
    # a later high-confidence shift still chains off the (untrustworthy)
    # accumulated offset -- flagging, not silently dropping, is the point
    assert result.positions["slot_2"] == (6.0, 4.0)


def test_empty_roster_still_opens_and_closes_list():
    calibrator, calls = _calibrator([], row_taps=())
    result = calibrator.calibrate()

    assert result.positions == {}
    assert result.low_confidence_slots == []
    assert calls["open"] == 1
    assert calls["close"] == 1
    assert calls["captures"] == 1
