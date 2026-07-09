"""Unit-list + camera-jump calibration: an authoritative alternative to
HP-arc color for locating our own units.

Design background (2026-07-09, see conversation with the user): arc-color
faction detection is unreliable exactly where it matters most -- the
our-turn, unit-select hub -- because not-yet-acted allies render in a hue
that is nearly indistinguishable from the enemy band there (CLAUDE.md
視覺辨識避坑; tests/fixtures/vision/hp_arc/our_turn_hub_pink_bug.*).
Colour is also a poor foundation for any future story event that changes
a unit's controllable side, since it is read fresh every frame rather than
carrying an identity forward.

The 單位列表 (unit list) panel does not have this problem: every row is,
by construction, a unit currently under our control, whatever the story
state. Tapping a row recenters the camera on that unit -- an "untracked
jump" -- but `vision.measure_camera_shift` already recovers camera deltas
from pure terrain phase-correlation (Hanning-windowed, on MAP_REGION), a
signal that never looks at a unit's paint at all. Chaining the shift
across every row in one pass turns a sequence of taps into an
authoritative slot -> world_position map.

This is a per-turn calibration, not a per-decision one: each round trip
costs a tap + two captures, so running it every activation would undo the
saving. Calibrate once at turn start (before anyone has acted, so no
in-turn movement has invalidated a position yet); track movement for the
rest of the turn from the controller's own issued move targets, which are
already known exactly, not re-observed.

Identity is by list slot index for now (`slot_0`, `slot_1`, ...), stable
within one calibration pass. Carrying identity across turns (so "this unit
already acted" survives a re-scan) needs either an assumption that list
order is stable turn to turn, or a portrait/name read this module does not
attempt -- content recognition stays out of a mechanism module; see #9.

Everything here needing real device constants (the list button position,
row tap spacing, the screen point a selected unit recenters to) is
injected, not hardcoded: this file has not been calibrated against a live
device (blocked on 2026-07-09 by device access -- see docs/roadmap.md),
so no placeholder screen coordinates are invented here. The chaining
arithmetic is pure and is exercised with fake capture/tap callables in
tests/test_roster_calibration.py; wiring real constants and verifying
against the device is separate follow-up work.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

from . import vision

Point = tuple[float, float]

CameraShiftFn = Callable[[np.ndarray, np.ndarray], tuple[Point, float]]

# below this phase-correlation response, treat the shift as unreliable
# (featureless view) rather than trusting a noisy vector -- mirrors the
# "confidence, not certainty" contract vision.measure_camera_shift already
# documents for pan-scanning.
MIN_SHIFT_CONFIDENCE = 0.1


def _default_shift(prev: np.ndarray, cur: np.ndarray) -> tuple[Point, float]:
    return vision.measure_camera_shift(prev, cur)


@dataclass
class RosterCalibration:
    """slot -> world position, plus which shifts were too low-confidence
    to trust (those slots are omitted from positions, not guessed)."""

    positions: dict[str, Point] = field(default_factory=dict)
    low_confidence_slots: list[str] = field(default_factory=list)


@dataclass
class UnitListCalibrator:
    """Drives one calibration pass: open the list, tap each row in turn,
    accumulate camera shift, close the list. `row_taps` yields the tap
    coordinates for each row in list order -- injected because the real
    row positions/spacing need on-device measurement this module does not
    have yet (see module docstring)."""

    capture: Callable[[], np.ndarray]
    tap: Callable[[int, int], None]
    open_list: Callable[[], None]
    close_list: Callable[[], None]
    row_taps: Sequence[tuple[int, int]]
    measure_shift: CameraShiftFn = _default_shift

    def calibrate(self) -> RosterCalibration:
        result = RosterCalibration()
        self.open_list()
        origin_frame = self.capture()
        offset: Point = (0.0, 0.0)
        prev = origin_frame
        for i, (x, y) in enumerate(self.row_taps):
            slot = f"slot_{i}"
            self.tap(x, y)
            cur = self.capture()
            (dx, dy), confidence = self.measure_shift(prev, cur)
            offset = (offset[0] + dx, offset[1] + dy)
            if confidence < MIN_SHIFT_CONFIDENCE:
                result.low_confidence_slots.append(slot)
            else:
                # the game recenters the selected unit to the same screen
                # anchor every time; that anchor point is itself a device
                # constant this module does not hardcode (see docstring),
                # so callers combine `offset` with it themselves until a
                # real one is measured and threaded through here.
                result.positions[slot] = offset
            prev = cur
        self.close_list()
        return result
