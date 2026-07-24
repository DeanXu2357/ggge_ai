"""Offline tests for battle.flow.vocabulary: the frame -> WorldState translator.
Every reader is monkeypatched; frames are opaque tokens. The point is the
three-value discipline -- "unknown" is never silently turned into a known value.
No device."""

from __future__ import annotations

import pytest

from ggge_ai.battle.flow import vocabulary as V

_FRAME = object()


def _patch(
    monkeypatch,
    *,
    view="hub",
    modal=False,
    selection=False,
    unit_list="collapsed",
    lattice=((1, 2, 3), (1, 2, 3)),
    zoom_at_max=True,
):
    monkeypatch.setattr(V.map_view, "classify_frame", lambda f, probe: view)
    monkeypatch.setattr(V.vision, "is_unit_detail_modal", lambda f: modal)
    monkeypatch.setattr(V.vision, "enemy_selection_active", lambda f: selection)
    monkeypatch.setattr(V.vision, "unit_list_state", lambda f: unit_list)
    monkeypatch.setattr(V.vision, "read_grid_lattice", lambda f: lattice)
    monkeypatch.setattr(V.vision, "zoom_at_max", lambda f: zoom_at_max)


def test_clean_hub_reads_all_known(monkeypatch):
    _patch(monkeypatch)
    s = V.translate(_FRAME, probe=None)
    assert s[V.VIEW] == V.VIEW_HUB
    assert s[V.OBSTRUCTION] == V.OBSTRUCTION_NONE
    assert s[V.UNIT_LIST] == V.UNIT_LIST_COLLAPSED
    assert s[V.GRID] == V.GRID_ON
    assert s[V.ZOOM] == V.ZOOM_MAX


def test_hub_with_collapsed_list_is_expressible(monkeypatch):
    # 定案 1 / 輪四 root cause: "我方回合可行動、單位列表收合" must be a legal,
    # nameable state -- view=hub AND unit_list=collapsed, both from independent
    # readers, never collapsed into one another.
    _patch(monkeypatch, view="hub", unit_list="collapsed", lattice=None)
    s = V.translate(_FRAME, probe=None)
    assert s[V.VIEW] == V.VIEW_HUB
    assert s[V.UNIT_LIST] == V.UNIT_LIST_COLLAPSED


def test_modal_is_obstruction_not_a_silent_known(monkeypatch):
    # a covering modal: obstruction=modal, and every map-dependent predicate is
    # honestly unknown -- never a stray "collapsed"/"on"/"max".
    _patch(monkeypatch, view="modal", modal=True, unit_list="unknown")
    s = V.translate(_FRAME, probe=None)
    assert s[V.OBSTRUCTION] == V.OBSTRUCTION_MODAL
    assert s[V.VIEW] == "modal"
    assert s[V.UNIT_LIST] == V.UNKNOWN
    assert s[V.GRID] == V.UNKNOWN
    assert s[V.ZOOM] == V.UNKNOWN


def test_selection_residue_detected(monkeypatch):
    _patch(monkeypatch, view="hub", selection=True)
    s = V.translate(_FRAME, probe=None)
    assert s[V.OBSTRUCTION] == V.OBSTRUCTION_SELECTION


def test_modal_beats_selection_in_obstruction(monkeypatch):
    _patch(monkeypatch, view="modal", modal=True, selection=True, unit_list="unknown")
    assert V.translate(_FRAME, probe=None)[V.OBSTRUCTION] == V.OBSTRUCTION_MODAL


def test_no_gridline_at_hub_is_grid_off_and_zoom_unknown(monkeypatch):
    # no lattice on a clean hub means the grid toggle is off (a known value);
    # zoom is unknown because there is no pitch to measure -- and stays unknown
    # even though zoom_at_max would answer, because grid gates it ("格線 off 時
    # unknown").
    _patch(monkeypatch, view="hub", lattice=None, zoom_at_max=True)
    s = V.translate(_FRAME, probe=None)
    assert s[V.GRID] == V.GRID_OFF
    assert s[V.ZOOM] == V.UNKNOWN


def test_grid_unknown_off_hub_even_with_a_lattice(monkeypatch):
    # off the hub the central lattice band is unreliable (overlays), so grid is
    # unknown regardless of what read_grid_lattice returned -- honest, not a
    # false "on".
    _patch(monkeypatch, view="unit_move", lattice=((1, 2, 3), (1, 2, 3)))
    s = V.translate(_FRAME, probe=None)
    assert s[V.GRID] == V.UNKNOWN
    assert s[V.ZOOM] == V.UNKNOWN


def test_zoom_not_max(monkeypatch):
    _patch(monkeypatch, view="hub", zoom_at_max=False)
    assert V.translate(_FRAME, probe=None)[V.ZOOM] == V.ZOOM_NOT_MAX


def test_zoom_unknown_when_lattice_present_but_verdict_none(monkeypatch):
    # grid reads on (a lattice) yet zoom_at_max cannot decide -> zoom unknown,
    # never a guessed max/not_max.
    _patch(monkeypatch, view="hub", lattice=((1, 2, 3), (1, 2, 3)), zoom_at_max=None)
    s = V.translate(_FRAME, probe=None)
    assert s[V.GRID] == V.GRID_ON
    assert s[V.ZOOM] == V.UNKNOWN


def test_missing_frame_is_all_unknown(monkeypatch):
    # a capture failure (None) must not crash a reader on None; every perception
    # predicate is honestly unknown.
    s = V.translate(None, probe=None)
    for key in (V.VIEW, V.UNIT_LIST, V.GRID, V.ZOOM, V.OBSTRUCTION):
        assert s[key] == V.UNKNOWN


def test_progress_predicates_merged_from_blackboard(monkeypatch):
    _patch(monkeypatch)
    s = V.translate(_FRAME, probe=None, progress={"census_built": True, "sim_synced": False})
    assert s["census_built"] is True
    assert s["sim_synced"] is False
    # perception predicates still present alongside the merged progress
    assert s[V.VIEW] == V.VIEW_HUB


@pytest.mark.parametrize("bad", [None])
def test_dimmed_value_reserved_but_never_emitted(monkeypatch, bad):
    # 缺樣: no calibrated dimmed detector yet, so the translator must never emit
    # OBSTRUCTION_DIMMED. The value stays in the domain for a future detector.
    _patch(monkeypatch, view="hub")
    s = V.translate(_FRAME, probe=None)
    assert s[V.OBSTRUCTION] != V.OBSTRUCTION_DIMMED
