"""Round 1.8: terrain fingerprint first-write-wins + conflict count + refused
telemetry (輪八 敗因蒸餾).

輪八 root cause: CellMap.integrate wrote terrain last-write-wins. One barely-
passing mislocalised integration (t=86.7, margin 4.5 over a 2.5 gate) could
overwrite hundreds of reference cells; every later honest frame then found the
corrupted reference un-matchable at any offset and refused forever (the east
dead-lock). 批2 gave unit evidence a support consensus; this batch gives terrain
the same via first-write-wins -- the first frame to see a cell fixes its
reference and no later frame can rewrite it.

The distillation (test_first_write_wins_*): a correct reference strip, one
wrong-offset integration that paints a swath the same residue colour (the 輪七/
輪八 red threat-range blob), then an honest same-view probe. Under last-write-wins
the corrupted reference makes the honest probe refuse; under first-write-wins the
reference survives and the probe localises. All localise gates
(LOCALIZE_MARGIN / evidence floor), frontier, steering and recovery-direction
semantics are untouched -- the only behaviour change is which fingerprint a
re-seen cell keeps, and that diverges only on the wrong-overwrite case.

terrain_conflict counts overlapped cells whose stored fingerprint disagrees with
the incoming frame's by TERRAIN_MATCH or more: high on the mislocalised offset,
zero on an honest re-integration (and within tolerance under sub-threshold
sampling noise). It rides frame_localized and the relocated scan_recovery event.
The refused telemetry (margin / unit_hits / terrain_fraction + edge visibility)
rides refused_frame and the localize_refused scan_recovery event.
"""

from __future__ import annotations

import numpy as np
import pytest

from ggge_ai.battle import vision
from ggge_ai.battle.coverage_map import (
    SIDES,
    TERRAIN_MATCH,
    CellMap,
    FrameObservation,
)
from ggge_ai.battle.vision import MapLattice
from tests.test_coverage_scan import _World, _source


# a residue-blob colour that matches no real world cell (the 輪七/輪八 red
# threat-range swath): far past TERRAIN_MATCH from every _fp(c) below.
BLOB = np.array([9999.0, 0.0, 0.0, 0.0], np.float32)


def _lattice(ncols: int, nrows: int = 1, pitch: int = 100) -> MapLattice:
    return MapLattice(
        cols=tuple(range(0, (ncols + 1) * pitch, pitch)),
        rows=tuple(range(0, (nrows + 1) * pitch, pitch)),
        col_pitch=float(pitch),
        row_pitch=float(pitch),
        edges={s: None for s in SIDES},
    )


def _fp(col: int) -> np.ndarray:
    """A distinctive per-world-col fingerprint; adjacent cols sit 50 apart, well
    over TERRAIN_MATCH, so exactly one offset can align a contiguous run."""
    return np.array([col * 50.0, 0.0, 0.0, 0.0], np.float32)


def _strip_obs(world_cols, *, fp=_fp) -> FrameObservation:
    """A single-row frame viewing consecutive `world_cols`: frame cell k holds
    the fingerprint of world_cols[k], all cells distinctive, no edges seen."""
    cols = list(world_cols)
    lat = _lattice(len(cols))
    fps = {(k, 0): fp(wc) for k, wc in enumerate(cols)}
    return FrameObservation(
        lattice=lat,
        edges={s: None for s in SIDES},
        units=[],
        fingerprints=fps,
        distinctive=frozenset(fps),
        threats=[],
    )


def _blob_obs(width: int) -> FrameObservation:
    lat = _lattice(width)
    fps = {(k, 0): BLOB for k in range(width)}
    return FrameObservation(
        lattice=lat,
        edges={s: None for s in SIDES},
        units=[],
        fingerprints=fps,
        distinctive=frozenset(fps),
        threats=[],
    )


def _reference_strip(width: int = 12) -> CellMap:
    """A correct reference: internal cell (c, 0) already holds _fp(c) for the
    whole strip (the state an honest scan converges to before the bad frame)."""
    cmap = CellMap()
    cmap._terrain = {(c, 0): _fp(c) for c in range(width)}
    cmap._covered = {(c, 0) for c in range(width)}
    cmap._col_pitch = 100.0
    cmap._row_pitch = 100.0
    return cmap




def test_first_write_wins_localises_after_a_wrong_offset_integration():
    """後綠: a correct reference, one mislocalised residue-blob integration folded
    at the wrong offset over cells 3..8, then an honest probe that truly views
    world cols 4..9. First-write-wins keeps the reference intact, so the probe
    localises to its true (4, 0). (Under last-write-wins -- the next test -- the
    same blob corrupts the reference and the probe refuses.)"""
    cmap = _reference_strip(12)
    cmap.integrate(_blob_obs(6), (3, 0))  # mislocalised: true offset would be 6
    probe = _strip_obs(range(4, 10))
    rep = cmap.localize_report(probe)
    assert rep.offset == (4, 0)
    assert rep.source == "vote"


def test_last_write_wins_would_have_refused_the_same_probe(monkeypatch):
    """先紅 pinned: with integrate reverted to last-write-wins, the residue blob
    overwrites cells 3..8, W4..W8 vanish from the reference, and the honest probe
    can no longer clear the evidence floor -> refused. This is exactly the outcome
    the test above turns green; it stays here as the executable 先紅 witness."""

    def _lww_integrate(self, obs, offset):
        dcol, drow = offset
        for cell, fp in obs.fingerprints.items():
            self._terrain[(cell[0] + dcol, cell[1] + drow)] = fp  # unconditional
        return 0

    monkeypatch.setattr(CellMap, "integrate", _lww_integrate, raising=True)
    cmap = _reference_strip(12)
    cmap.integrate(_blob_obs(6), (3, 0))
    probe = _strip_obs(range(4, 10))
    rep = cmap.localize_report(probe)
    assert rep.offset is None
    assert rep.source is None




def test_wrong_offset_integration_reports_high_conflict():
    """A mislocalised integration (residue blob over a real reference swath)
    disagrees with every overlapped cell -> a high terrain_conflict, the immediate
    ledger warning of a bad placement."""
    cmap = _reference_strip(12)
    conflict = cmap.integrate(_blob_obs(6), (3, 0))
    assert conflict == 6


def test_shifted_real_frame_reports_high_conflict():
    """The literal 輪八 failure shape: a real frame folded one cell off (world cols
    6..11 placed at offset 3 instead of 6). Every overlapped cell's stored
    fingerprint disagrees, so the conflict count flags it."""
    cmap = _reference_strip(12)
    conflict = cmap.integrate(_strip_obs(range(6, 12)), (3, 0))
    assert conflict == 6


def test_same_view_reintegration_reports_zero_conflict():
    """An honest re-integration at the true offset writes identical fingerprints
    -> zero conflict (the healthy re-sighting path)."""
    cmap = _reference_strip(12)
    conflict = cmap.integrate(_strip_obs(range(3, 9)), (3, 0))
    assert conflict == 0


def test_subthreshold_noise_reintegration_stays_within_tolerance():
    """Frame-to-frame sampling noise below TERRAIN_MATCH must not read as a
    conflict -- the 'near-zero on same view' tolerance the equivalence argument
    rests on."""
    noise = np.array([TERRAIN_MATCH - 1.0, 0.0, 0.0, 0.0], np.float32)
    cmap = _reference_strip(12)
    noisy = _strip_obs(range(3, 9), fp=lambda c: _fp(c) + noise)
    conflict = cmap.integrate(noisy, (3, 0))
    assert conflict == 0


def test_first_write_wins_does_not_overwrite_existing_terrain():
    """First-write-wins is literal: the blob never enters _terrain where a cell is
    already known; only genuinely new cells are filled."""
    cmap = _reference_strip(12)
    cmap.integrate(_blob_obs(6), (3, 0))
    for c in range(12):
        assert np.array_equal(cmap._terrain[(c, 0)], _fp(c)), f"cell {c} was overwritten"


def test_first_write_wins_still_fills_unseen_cells():
    """A frame reaching past the known strip still registers its new cells (first
    write for those); only already-known cells are protected."""
    cmap = _reference_strip(12)
    cmap.integrate(_strip_obs(range(12, 15)), (12, 0))  # cells 12,13,14 are new
    for c in (12, 13, 14):
        assert (c, 0) in cmap._terrain
        assert np.array_equal(cmap._terrain[(c, 0)], _fp(c))




@pytest.fixture(autouse=True)
def _no_obstruction(monkeypatch):
    # the synthetic world hands back opaque tuple tokens; keep both obstruction
    # probes off them (mirrors the sibling coverage-scan fixtures)
    monkeypatch.setattr(vision, "is_unit_detail_modal", lambda f: False)
    monkeypatch.setattr(vision, "enemy_selection_active", lambda f: False)


def _overmove_run():
    """The over-move world from test_coverage_scan: the first fill push loses the
    lock (a refused frame + a localize_refused recovery + a relocated recovery),
    then the scan converges (many frame_localized events)."""
    world = _World(
        13, 7, view=(6, 4), units={(1, 1), (10, 5), (6, 3)}, start=(0, 0),
        overmove_at={1},
    )
    events: list[dict] = []
    _source(world, events=events).collect()
    return events


def test_refused_frame_event_carries_refused_report_and_edges():
    """refused_frame events gain the refused report's margin / unit_hits /
    terrain_fraction and the frame's edge visibility (輪八 forensics without a
    re-probe)."""
    events = _overmove_run()
    refused = [e for e in events if e["kind"] == "refused_frame"]
    assert refused, "the over-move never forced a logged refusal"
    for e in refused:
        assert set(e) >= {"n", "path", "margin", "unit_hits", "terrain_fraction", "edges"}
        assert isinstance(e["unit_hits"], int)
        assert isinstance(e["terrain_fraction"], float)
        assert e["margin"] is None or isinstance(e["margin"], float)
        assert set(e["edges"]) == set(SIDES)


def test_scan_recovery_localize_refused_carries_refused_report():
    """The localize_refused scan_recovery event carries the same refused
    telemetry."""
    events = _overmove_run()
    refused = [
        e for e in events
        if e["kind"] == "scan_recovery" and e["reason"] == "localize_refused"
    ]
    assert refused, "no localize_refused recovery event was emitted"
    for e in refused:
        assert set(e) >= {"margin", "unit_hits", "terrain_fraction", "edges"}
        assert isinstance(e["unit_hits"], int)
        assert isinstance(e["terrain_fraction"], float)
        assert e["margin"] is None or isinstance(e["margin"], float)
        assert set(e["edges"]) == set(SIDES)


def test_relocated_scan_recovery_carries_terrain_conflict():
    """The relocated scan_recovery event carries the relocation integration's
    terrain_conflict count."""
    events = _overmove_run()
    relocated = [
        e for e in events
        if e["kind"] == "scan_recovery" and e["reason"] == "relocated"
    ]
    assert relocated, "the over-move never relocated"
    for e in relocated:
        assert "terrain_conflict" in e and isinstance(e["terrain_conflict"], int)


def test_frame_localized_carries_terrain_conflict_and_stays_zero_on_healthy_scan():
    """frame_localized events gain terrain_conflict; on a clean converging world
    every integration lands at its true offset, so the count is zero throughout --
    the equivalence witness that first-write-wins does not perturb the healthy
    path."""
    world = _World(9, 7, view=(6, 4), units={(1, 1), (4, 2), (7, 5), (2, 4)}, start=(0, 0), step=1)
    events: list[dict] = []
    _source(world, events=events).collect()
    localized = [e for e in events if e["kind"] == "frame_localized"]
    assert localized
    for e in localized:
        assert "terrain_conflict" in e and isinstance(e["terrain_conflict"], int)
    assert sum(e["terrain_conflict"] for e in localized) == 0
