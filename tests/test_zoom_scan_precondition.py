"""Offline tests for the T3 cold-scan zoom precondition: before the full-map
sweep the controller backs out to the top hub, turns the grid on and pinches
the camera to its furthest zoom, verifying with vision.zoom_at_max and
fail-fasting (SurveyIncomplete, grid released) when it will not reach it. A
missing pincher skips the pinch and scans at the current zoom. Perception/
actuator are fakes and every seam is monkeypatched. No device."""

from __future__ import annotations

import numpy as np
import pytest

from ggge_ai.battle import controller as controller_mod
from ggge_ai.battle import map_view
from ggge_ai.battle.controller import ManualBattleController
from ggge_ai.battle.ledger import BattleLedger
from ggge_ai.battle.scout_intel import SurveyIncomplete
from ggge_ai.battle.tacmap import TacticalMap


class _El:
    def __init__(self, confidence):
        self.confidence = confidence


class _Perception:
    def capture(self):
        return np.zeros((4, 4, 3), np.uint8)

    def probe(self, ids, frame=None):
        if map_view.HUB_LABEL in ids:
            return {map_view.HUB_LABEL: _El(0.9)}
        return {}


class _Actuator:
    def __init__(self):
        self.taps = []
        self.swipes = []

    def tap(self, x, y):
        self.taps.append((x, y))

    def swipe(self, *args):
        self.swipes.append(args)


class _RecordingPincher:
    def __init__(self):
        self.calls = 0

    def pinch(self, finger_a, finger_b):
        self.calls += 1


def _controller(pincher):
    return ManualBattleController(
        perception=_Perception(),
        actuator=_Actuator(),
        ledger=BattleLedger(),
        pincher=pincher,
    )


def _stub_zoom_out_max(monkeypatch, pinches_per_pass=2):
    """Replace the convergence loop with a fixed number of pinch_step calls so
    the pincher fires without exercising the (separately unit-tested) pitch
    math on fake frames."""

    def fake(capture, pinch_step, *, obstruction=None, on_step=None, **kw):
        for _ in range(pinches_per_pass):
            pinch_step()
        return []

    monkeypatch.setattr(controller_mod.pinch, "zoom_out_max", fake)


@pytest.fixture(autouse=True)
def _quiet_vision(monkeypatch):
    monkeypatch.setattr(controller_mod.vision, "is_unit_detail_modal", lambda f: False)
    monkeypatch.setattr(controller_mod.vision, "unit_cards_present", lambda f: False)
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    yield


def test_zoom_to_max_verifies_then_returns(monkeypatch):
    _stub_zoom_out_max(monkeypatch, pinches_per_pass=2)
    monkeypatch.setattr(controller_mod.vision, "zoom_at_max", lambda f: True)
    pincher = _RecordingPincher()
    c = _controller(pincher)

    out = c._zoom_to_max(c._frame())

    assert out is not None
    assert pincher.calls == 2  # a single pass, verified at max on the first check


def test_zoom_to_max_fail_fast_after_two_passes_and_releases_grid(monkeypatch):
    _stub_zoom_out_max(monkeypatch, pinches_per_pass=1)
    monkeypatch.setattr(controller_mod.vision, "zoom_at_max", lambda f: False)
    released = []
    monkeypatch.setattr(
        controller_mod.battle_settings,
        "set_battle_grid",
        lambda cap, tap, desired, **kw: released.append(desired) or True,
    )
    pincher = _RecordingPincher()
    c = _controller(pincher)
    c._grid_active = True  # the precondition turned the grid on before zooming

    with pytest.raises(SurveyIncomplete):
        c._zoom_to_max(c._frame())

    assert pincher.calls == 2  # first pass + one retry, both non-verifying
    assert released == [False]  # grid released on the fail-fast exit


def test_zoom_to_max_none_verdict_is_also_fail_fast(monkeypatch):
    _stub_zoom_out_max(monkeypatch, pinches_per_pass=1)
    monkeypatch.setattr(controller_mod.vision, "zoom_at_max", lambda f: None)
    monkeypatch.setattr(
        controller_mod.battle_settings,
        "set_battle_grid",
        lambda cap, tap, desired, **kw: True,
    )
    c = _controller(_RecordingPincher())

    with pytest.raises(SurveyIncomplete):
        c._zoom_to_max(c._frame())


def test_zoom_to_max_retry_recovers_on_second_pass(monkeypatch):
    _stub_zoom_out_max(monkeypatch, pinches_per_pass=1)
    verdicts = iter([False, True])
    monkeypatch.setattr(controller_mod.vision, "zoom_at_max", lambda f: next(verdicts))
    pincher = _RecordingPincher()
    c = _controller(pincher)

    out = c._zoom_to_max(c._frame())

    assert out is not None
    assert pincher.calls == 2  # first pass missed, retry landed at max


def test_zoom_to_max_skips_without_a_pincher(monkeypatch):
    seen = []
    monkeypatch.setattr(
        controller_mod.vision, "zoom_at_max", lambda f: seen.append("verify") or True
    )
    c = _controller(None)
    frame = c._frame()

    out = c._zoom_to_max(frame)

    assert out is frame  # untouched, scans at the current zoom
    assert seen == []  # no verification because no pinch was attempted


def _wire_full_scan(monkeypatch, source_factory):
    """Stub every full-scan seam except the CoverageScanSource (supplied by
    source_factory) and return the release recorder."""
    monkeypatch.setattr(
        controller_mod.map_view, "ensure_max_view", lambda perc, act, **kw: True
    )
    released: list = []
    monkeypatch.setattr(
        controller_mod.battle_settings,
        "set_battle_grid",
        lambda cap, tap, desired, **kw: released.append(desired) or True,
    )

    def fake_zoom(capture, pinch_step, *, obstruction=None, on_step=None, **kw):
        return []

    monkeypatch.setattr(controller_mod.pinch, "zoom_out_max", fake_zoom)
    monkeypatch.setattr(controller_mod.vision, "zoom_at_max", lambda f: True)
    monkeypatch.setattr(controller_mod.vision, "read_grid_lattice", lambda f: None)
    for name in ("find_enemy_units", "find_ally_units", "find_third_party_units"):
        monkeypatch.setattr(controller_mod.vision, name, lambda f, region=None: [])
    monkeypatch.setattr(controller_mod.vision, "find_threat_cells", lambda f: [])
    return released


def test_full_scan_releases_grid_when_survey_incomplete_even_with_intel_pending(
    monkeypatch,
):
    """Anomaly C: a SurveyIncomplete out of the coverage sweep must release the
    battle grid on the way out even when intel is enabled and its pass is still
    pending -- because that intel pass never runs (the exception propagates), so
    the 'leave the grid for intel to close' branch would strand it ON. The old
    finally skipped release exactly here."""

    class _Raising:
        def __init__(self):
            self.start_frame = None
            self.pool = TacticalMap()

        def collect(self):
            raise SurveyIncomplete("coverage scan did not close")

    released = _wire_full_scan(monkeypatch, _Raising)
    c = _controller(_RecordingPincher())
    c.intel_enabled = True  # and battle:intel is pending by default
    assert c.timeline.pending("intel", scope="battle")
    monkeypatch.setattr(c, "_navigator", _Raising)

    with pytest.raises(SurveyIncomplete):
        c._scout(c._frame())

    # grid was turned on (True) then released (False) despite intel pending
    assert released == [True, False]
    assert c._grid_active is False


def test_full_scan_keeps_grid_for_intel_on_success(monkeypatch):
    """The counterpart: a SUCCESSFUL sweep with intel enabled+pending keeps the
    grid up (the intel pass releases it later), unchanged by the anomaly-C fix."""

    class _Ok:
        def __init__(self):
            self.start_frame = None
            self.pool = TacticalMap()
            self.bounds = {"west": 0.0, "north": 0.0, "east": 100, "south": 100}
            self.size = (1, 1)
            self.nudges = 1
            self.census = TacticalMap()

        def collect(self):
            return self.census

    released = _wire_full_scan(monkeypatch, _Ok)
    c = _controller(_RecordingPincher())
    c.intel_enabled = True
    monkeypatch.setattr(c, "_navigator", _Ok)

    c._scout(c._frame())

    # grid turned on, NOT released here (left for the pending intel pass)
    assert released == [True]
    assert c._grid_active is True


def test_full_scan_precondition_runs_in_order(monkeypatch):
    """The cold-scan entry point sequences: back out to the hub -> grid on ->
    pinch iterations -> zoom_at_max verify -> the sweep starts."""
    events: list = []
    monkeypatch.setattr(
        controller_mod.map_view,
        "ensure_max_view",
        lambda perc, act, **kw: events.append("max_view") or True,
    )
    monkeypatch.setattr(
        controller_mod.battle_settings,
        "set_battle_grid",
        lambda cap, tap, desired, **kw: events.append(("grid", desired)) or True,
    )

    def fake_zoom(capture, pinch_step, *, obstruction=None, on_step=None, **kw):
        events.append("zoom")
        pinch_step()
        return []

    monkeypatch.setattr(controller_mod.pinch, "zoom_out_max", fake_zoom)
    monkeypatch.setattr(
        controller_mod.vision, "zoom_at_max", lambda f: events.append("verify") or True
    )
    monkeypatch.setattr(controller_mod.vision, "read_grid_lattice", lambda f: None)
    for name in ("find_enemy_units", "find_ally_units", "find_third_party_units"):
        monkeypatch.setattr(controller_mod.vision, name, lambda f, region=None: [])
    monkeypatch.setattr(controller_mod.vision, "find_threat_cells", lambda f: [])

    class _FakeSource:
        def __init__(self):
            self.start_frame = None
            self.pool = TacticalMap()
            self.bounds = {"west": 0.0, "north": 0.0, "east": 100, "south": 100}
            self.nudges = 1
            self.census = TacticalMap()

        def collect(self):
            events.append("sweep")
            return self.census

    pincher = _RecordingPincher()
    c = _controller(pincher)
    monkeypatch.setattr(c, "_navigator", _FakeSource)

    c._scout(c._frame())

    assert events[: events.index("sweep") + 1] == [
        "max_view",
        ("grid", True),
        "zoom",
        "verify",
        "sweep",
    ]
    assert pincher.calls == 1
