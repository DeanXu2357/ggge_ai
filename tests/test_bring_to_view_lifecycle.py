"""CoverageScanSource lifecycle (#26 Round 1.6-A): a fresh source built purely
for the survey's bring_to_view -- the way controller._navigator() builds one,
never running collect() -- must drive the real nudge path without crashing.

The 07-24 輪六 failure: nudge()/bring_to_view() write _nudges/_last_nudge, but
those were only initialised inside collect(). _navigator() hands survey_stage a
brand-new source whose bring_to_view() nudges the moment a target sits off the
tappable region -> AttributeError -> the Python process died. Every prior test
of bring_to_view injected an _identity_view fake, so the real nudge path had
zero coverage; these drive it directly."""

from __future__ import annotations

import numpy as np
import pytest

from ggge_ai.battle import vision
from ggge_ai.battle.live_scan import BRING_MAX_NUDGES, CoverageScanSource
from ggge_ai.battle.tacmap import TacticalMap


@pytest.fixture(autouse=True)
def _no_modal(monkeypatch):
    monkeypatch.setattr(vision, "is_unit_detail_modal", lambda f: False)


def _sign(v: float) -> int:
    return (v > 0) - (v < 0)


class _BringWorld:
    """A camera that pans on swipe; detect() exposes an irregular pool
    constellation at the current camera so pool.locate re-anchors each step
    (the content-only bring_to_view path). collect() is never run."""

    STEP = 400
    UNITS = ((100.0, 100.0), (1700.0, 400.0), (900.0, 1500.0))

    def __init__(self):
        self.cam = [0.0, 0.0]

    def capture(self):
        return np.zeros((10, 10, 3), np.uint8)

    def swipe(self, x1, y1, x2, y2, *a):
        self.cam[0] += _sign(x1 - x2) * self.STEP
        self.cam[1] += _sign(y1 - y2) * self.STEP

    def detect(self, _frame):
        return [(int(wx - self.cam[0]), int(wy - self.cam[1])) for wx, wy in self.UNITS]


def _fresh_source(world):
    src = CoverageScanSource(
        capture=world.capture,
        swipe=world.swipe,
        tap=lambda x, y: None,
        sleep=lambda s: None,
        detect=world.detect,
    )
    src.pool = TacticalMap(units=[tuple(p) for p in _BringWorld.UNITS])
    return src


def test_fresh_source_bring_to_view_converges_without_collect():
    """A never-collected source pans a target into the tappable band and returns
    its screen point. The old code hit AttributeError on the first nudge."""
    world = _BringWorld()
    src = _fresh_source(world)

    screen = src.bring_to_view((2200.0, 1200.0), start_camera=(0.0, 0.0))

    assert screen is not None
    x, y = screen
    assert 210 <= x <= 1600 and 150 <= y <= 730
    assert src._nudges >= 1  # the real nudge path ran (no _identity_view fake)


def test_fresh_source_bring_to_view_reports_failure_without_collect():
    """An unreachable target on a never-collected source fails loud (returns
    None) after exhausting the nudge budget -- it must not crash."""
    world = _BringWorld()
    src = CoverageScanSource(
        capture=world.capture,
        swipe=lambda *a: None,  # camera never moves: target stays off-view
        tap=lambda x, y: None,
        sleep=lambda s: None,
        detect=lambda f: [],
    )

    screen = src.bring_to_view((9000.0, 9000.0), start_camera=(0.0, 0.0))

    assert screen is None
    assert src._nudges == BRING_MAX_NUDGES
