"""Offline tests for battle.flow.actions: each repair/navigation action's
execute delegates to the right existing helper, ensure-idempotent semantics hold
at planning time, and ZoomToMax's pinch-verify reuses the pinch primitives.
Helpers are monkeypatched; no device."""

from __future__ import annotations

import pytest

from ggge_ai.battle import map_view
from ggge_ai.battle.flow import actions
from ggge_ai.battle.flow import vocabulary as V


class _Perception:
    def __init__(self):
        self.captures = 0

    def capture(self):
        self.captures += 1
        return ("frame", self.captures)

    def probe(self, ids, frame=None):
        return {}


class _Actuator:
    def __init__(self):
        self.taps = []

    def tap(self, x, y):
        self.taps.append((x, y))


class _RecordingPincher:
    def __init__(self):
        self.calls = 0

    def pinch(self, finger_a, finger_b):
        self.calls += 1


def _ctx(monkeypatch=None, **kw):
    kw.setdefault("sleep", lambda *a, **k: None)
    return actions.FlowContext(perception=_Perception(), actuator=_Actuator(), **kw)


def test_reach_hub_delegates_to_return_to_top(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        actions.map_view,
        "return_to_top",
        lambda perc, act, **kw: seen.update(kw) or True,
    )
    guard = object()
    ok = actions.ReachHub().execute(_ctx(keyguard=guard))
    assert ok is True
    assert seen.get("keyguard") is guard  # R1.5 escape carries the keyguard


def test_clear_obstruction_is_modal_only(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        actions.map_view,
        "clear_obstruction",
        lambda perc, act, frame, **kw: seen.update(frame=frame, kw=kw) or frame,
    )
    ok = actions.ClearObstruction().execute(_ctx(frame=("f", 1)))
    assert ok is True
    # modal-only clearing: never the enemy-selection residue leg (no detector)
    assert seen["kw"].get("detect") is None


def test_clear_selection_residue_supplies_a_detector(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        actions.map_view,
        "clear_obstruction",
        lambda perc, act, frame, **kw: seen.update(kw) or frame,
    )
    ok = actions.ClearSelectionResidue().execute(_ctx(frame=("f", 1)))
    assert ok is True
    assert seen.get("detect") is not None  # the R1.7 empty-land chain runs


def test_clear_selection_residue_fails_soft_when_stuck(monkeypatch):
    def _raise(perc, act, frame, **kw):
        raise map_view.SelectionResidueStuck("stuck")

    monkeypatch.setattr(actions.map_view, "clear_obstruction", _raise)
    # a residue that will not dismiss returns False (no progress) rather than
    # propagating; the tick loop owns what that means.
    assert actions.ClearSelectionResidue().execute(_ctx(frame=("f", 1))) is False


def test_expand_and_collapse_delegate_to_map_view(monkeypatch):
    calls = []
    monkeypatch.setattr(
        actions.map_view, "expand_unit_list", lambda perc, act, **kw: calls.append("expand") or True
    )
    monkeypatch.setattr(
        actions.map_view,
        "collapse_unit_list",
        lambda perc, act, **kw: calls.append("collapse") or True,
    )
    assert actions.ExpandUnitList().execute(_ctx()) is True
    assert actions.CollapseUnitList().execute(_ctx()) is True
    assert calls == ["expand", "collapse"]


def test_enable_and_disable_grid_pass_the_desired_state(monkeypatch):
    seen = []
    monkeypatch.setattr(
        actions.battle_settings,
        "set_battle_grid",
        lambda cap, tap, desired, **kw: seen.append(desired) or True,
    )
    assert actions.EnableGrid().execute(_ctx()) is True
    assert actions.DisableGrid().execute(_ctx()) is True
    assert seen == [True, False]


def test_zoom_to_max_without_pincher_fails_soft():
    # no pincher: cannot zoom, so no-progress False (never a raise, never a
    # grid release -- that is the macro layer's concern in Round 2.1).
    assert actions.ZoomToMax().execute(_ctx(pincher=None)) is False


def test_zoom_to_max_reuses_pinch_primitives_and_verifies(monkeypatch):
    def fake_zoom(capture, pinch_step, *, obstruction=None, on_step=None, **kw):
        for _ in range(2):
            pinch_step()
        return []

    monkeypatch.setattr(actions.pinch, "zoom_out_max", fake_zoom)
    monkeypatch.setattr(actions.vision, "zoom_at_max", lambda f: True)
    monkeypatch.setattr(
        actions.map_view, "clear_obstruction", lambda perc, act, frame, **kw: frame
    )
    pincher = _RecordingPincher()
    assert actions.ZoomToMax().execute(_ctx(pincher=pincher, frame=("f", 1))) is True
    assert pincher.calls == 2  # a single pass verified at max


def test_zoom_to_max_returns_false_when_never_verified(monkeypatch):
    def fake_zoom(capture, pinch_step, *, obstruction=None, on_step=None, **kw):
        pinch_step()
        return []

    monkeypatch.setattr(actions.pinch, "zoom_out_max", fake_zoom)
    monkeypatch.setattr(actions.vision, "zoom_at_max", lambda f: False)
    monkeypatch.setattr(
        actions.map_view, "clear_obstruction", lambda perc, act, frame, **kw: frame
    )
    pincher = _RecordingPincher()
    assert actions.ZoomToMax().execute(_ctx(pincher=pincher, frame=("f", 1))) is False
    assert pincher.calls == 2  # first pass + one retry, both non-verifying


def test_detect_unit_peaks_unions_and_guards(monkeypatch):
    monkeypatch.setattr(actions.vision, "find_unit_density_peaks", lambda f: [(10, 20)])
    monkeypatch.setattr(actions.vision, "find_enemy_units", lambda f: [(30, 40)])

    def _boom(f):
        raise RuntimeError("bad frame")

    monkeypatch.setattr(actions.vision, "find_ally_units", _boom)  # guarded, contributes nothing
    monkeypatch.setattr(actions.vision, "find_third_party_units", lambda f: [(50, 60)])
    peaks = actions.detect_unit_peaks(("f", 1))
    assert (10, 20) in peaks and (30, 40) in peaks and (50, 60) in peaks


def test_catalog_effects_are_ensure_targets():
    # ensure/idempotent: every action declares a target value it sets, never a
    # relative toggle -- so planning on "unknown" is always safe.
    by_name = {a.name: a for a in actions.REPAIR_NAV_ACTIONS}
    assert by_name["enable_grid"].effects == {V.GRID: V.GRID_ON}
    assert by_name["collapse_unit_list"].effects == {V.UNIT_LIST: V.UNIT_LIST_COLLAPSED}
    assert by_name["zoom_to_max"].effects == {V.ZOOM: V.ZOOM_MAX}
    # zoom needs the grid up first (a lattice to verify against)
    assert by_name["zoom_to_max"].preconditions[V.GRID] == V.GRID_ON


@pytest.mark.parametrize("action", actions.REPAIR_NAV_ACTIONS, ids=lambda a: a.name)
def test_every_action_shares_the_clean_screen_precondition(action):
    # the global invariant: no main-line action runs on a dirty screen. Either
    # it requires obstruction=none, or it IS the obstruction owner (a clear_*
    # action whose precondition names the obstruction it removes).
    pre = dict(action.preconditions)
    if action.name.startswith("clear_"):
        assert pre[V.OBSTRUCTION] in (V.OBSTRUCTION_MODAL, V.OBSTRUCTION_SELECTION)
    else:
        assert pre[V.OBSTRUCTION] == V.OBSTRUCTION_NONE
