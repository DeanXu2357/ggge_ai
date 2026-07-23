"""Cache bounds preload (#26 批5): the coverage scan's optional size hint.

A cached stage definition's (cols, rows) is a PLANNING hint only -- it steers
the frontier toward where the cache says an edge is and scales the nudge budget
to the known map size. It NEVER registers an edge (架構紅線: 邊界必須目視看見),
and the instant a SEEN edge contradicts it the hint is dropped and the scan
reverts to pure exploration. These tests lock the three required behaviours:
hint acceleration (frontier points at the projected unseen edge), hint conflict
(drop + normal completion), and no-cache equivalence.

Reuses the malicious synthetic world from test_coverage_scan so the hint runs
through the real CellMap/CoverageScanSource machinery, not a mock."""

from __future__ import annotations

import pytest

from ggge_ai.battle import vision
from ggge_ai.battle.coverage_map import SIDES, CellMap
from ggge_ai.battle.ledger import BattleLedger
from ggge_ai.battle.live_scan import SCAN_MAX_NUDGES
from ggge_ai.battle.vision import MapLattice
from ggge_ai.content import stage_def as sd
from tests.test_coverage_scan import _found_cells, _source, _World


@pytest.fixture(autouse=True)
def _no_modal(monkeypatch):
    monkeypatch.setattr(vision, "is_unit_detail_modal", lambda f: False)


def _lattice(ncols: int, nrows: int, pitch: int = 100) -> MapLattice:
    return MapLattice(
        cols=tuple(range(0, (ncols + 1) * pitch, pitch)),
        rows=tuple(range(0, (nrows + 1) * pitch, pitch)),
        col_pitch=float(pitch),
        row_pitch=float(pitch),
        edges={s: None for s in SIDES},
    )


# --- frontier projection (hint acceleration) -------------------------------

def test_frontier_hint_points_at_projected_edge():
    """With west registered and a wide hint, the frontier steers toward the
    hint-projected east line (west + cols), far past the naive one-cell-past
    coverage target the cold scan would use."""
    covered = {(c, r) for c in range(4) for r in range(4)}
    reg = {"west": 0, "east": None, "north": 0, "south": None}

    cold = CellMap()
    cold._covered, cold._reg = set(covered), dict(reg)
    hot = CellMap(size_hint=(20, 8))
    hot._covered, hot._reg = set(covered), dict(reg)

    # east is the first unseen edge; cold points one cell past coverage, the hint
    # projects it all the way to west(0) + cols(20)
    assert cold.frontier() == (4, 1)
    assert hot.frontier() == (20, 1)


def test_frontier_projects_from_opposite_registered_edge():
    """A north-registered map projects the south target to north + rows."""
    cmap = CellMap(size_hint=(12, 15))
    cmap._covered = {(c, r) for c in range(6) for r in range(3)}
    cmap._reg = {"west": 0, "east": 12, "north": 0, "south": None}
    # west+east seen, north seen, south unseen -> frontier goes south to row 15
    assert cmap.frontier() == (2, 15)


# --- hint drop (conflict) --------------------------------------------------

def test_hint_dropped_on_span_mismatch():
    """Both opposing edges seen at a span that disagrees with the hint drops
    it (the cache lied about the size)."""
    cmap = CellMap(size_hint=(5, 5))
    cmap._covered = {(0, 0), (7, 0)}
    cmap._reg = {"west": 0, "east": 8, "north": None, "south": None}
    cmap._check_hint()
    assert cmap.hint_dropped
    assert cmap.size_hint is None
    assert cmap.hint_drop_reason == "seen_geometry_contradicts_cache"


def test_hint_dropped_on_coverage_overshoot():
    """Covered terrain reaching past the hint-projected edge (from a registered
    opposite edge) drops the hint -- the real map is bigger than the cache."""
    cmap = CellMap(size_hint=(5, 5))
    cmap._reg = {"west": 0, "east": None, "north": None, "south": None}
    cmap._covered = {(c, 0) for c in range(7)}  # col 6 >= west(0) + cols(5)
    cmap._check_hint()
    assert cmap.hint_dropped


def test_hint_kept_when_consistent():
    """A hint the seen geometry does not contradict survives untouched."""
    cmap = CellMap(size_hint=(10, 8))
    cmap._reg = {"west": 0, "east": None, "north": 0, "south": None}
    cmap._covered = {(c, r) for c in range(4) for r in range(4)}
    cmap._check_hint()
    assert not cmap.hint_dropped
    assert cmap.size_hint == (10, 8)


# --- source-level: hint through the real loop ------------------------------

def test_source_consistent_hint_completes_without_drop():
    """A correct hint neither changes the outcome nor gets dropped: the scan
    closes on the true bounds and never logs cache_bounds_dropped."""
    units = {(1, 1), (4, 2), (7, 5), (2, 4)}
    world = _World(9, 7, view=(6, 4), units=units, start=(0, 0), step=1)
    events: list[dict] = []
    src = _source(world, events=events)
    src.bounds_hint = (9, 7)

    census = src.collect()

    assert src.bounds == {"west": 0.0, "north": 0.0, "east": 900.0, "south": 700.0}
    assert src.size == (9, 7)
    assert _found_cells(census) == units
    assert not any(e["kind"] == "cache_bounds_dropped" for e in events)


def test_source_wrong_hint_dropped_and_still_completes():
    """A hint far too small is dropped once a real edge contradicts it, and the
    scan finishes normally on the true (visually seen) bounds."""
    units = {(1, 1), (4, 2), (7, 5), (2, 4)}
    world = _World(9, 7, view=(6, 4), units=units, start=(0, 0), step=1)
    events: list[dict] = []
    src = _source(world, events=events)
    src.bounds_hint = (4, 4)  # the real map is 9x7

    census = src.collect()

    drops = [e for e in events if e["kind"] == "cache_bounds_dropped"]
    assert len(drops) == 1  # logged exactly once
    assert drops[0]["hint"] == [4, 4]
    assert src.bounds == {"west": 0.0, "north": 0.0, "east": 900.0, "south": 700.0}
    assert _found_cells(census) == units


def test_hint_does_not_change_the_census():
    """No-cache equivalence: a run with a correct hint and a run with no hint
    at all produce the identical census and bounds (the hint is planning only)."""
    units = {(1, 1), (4, 2), (7, 5), (2, 4)}

    def run(hint):
        world = _World(9, 7, view=(6, 4), units=units, start=(0, 0), step=1)
        src = _source(world)
        src.bounds_hint = hint
        census = src.collect()
        return src.bounds, _found_cells(census)

    assert run(None) == run((9, 7))


def test_scan_budget_scales_with_large_hint():
    """A large hint raises the fill-loop ceiling above the cold default so a
    warm rescan of a big stage does not fail-fast spuriously; no hint leaves the
    ceiling untouched."""
    world = _World(9, 7, view=(6, 4), start=(0, 0))
    src = _source(world)
    obs = world.observe(world.capture())

    src.bounds_hint = None
    assert src._scan_budget(obs) == SCAN_MAX_NUDGES

    src.bounds_hint = (60, 60)
    assert src._scan_budget(obs) > SCAN_MAX_NUDGES


# --- stage definition round-trip -------------------------------------------

def test_stage_def_map_size_round_trip(tmp_path):
    defn = sd.StageDefinition(stage_id="ex-2-if", map_cols=23, map_rows=24)
    sd.save_stage_def(defn, tmp_path)
    loaded = sd.load_stage_def("ex-2-if", tmp_path)
    assert loaded is not None
    assert (loaded.map_cols, loaded.map_rows) == (23, 24)


def test_stage_def_map_size_absent_is_none(tmp_path):
    sd.save_stage_def(sd.StageDefinition(stage_id="s"), tmp_path)
    loaded = sd.load_stage_def("s", tmp_path)
    assert loaded is not None
    assert loaded.map_cols is None and loaded.map_rows is None


# --- controller cache read -------------------------------------------------

class _Dummy:
    def capture(self):
        return None

    def probe(self, *a, **k):
        return {}

    def tap(self, *a):
        pass

    def swipe(self, *a):
        pass


def _controller(**kw):
    from ggge_ai.battle.controller import ManualBattleController

    return ManualBattleController(
        perception=_Dummy(), actuator=_Dummy(), ledger=BattleLedger(), **kw
    )


def test_cached_bounds_hint_from_definition(tmp_path):
    sd.save_stage_def(
        sd.StageDefinition(stage_id="ex", map_cols=23, map_rows=24), tmp_path
    )
    c = _controller(intel_enabled=True, stage_id="ex", intel_cache_root=tmp_path)
    assert c._cached_bounds_hint() == (23, 24)


def test_cached_bounds_hint_none_when_intel_off(tmp_path):
    sd.save_stage_def(
        sd.StageDefinition(stage_id="ex", map_cols=23, map_rows=24), tmp_path
    )
    c = _controller(intel_enabled=False, stage_id="ex", intel_cache_root=tmp_path)
    assert c._cached_bounds_hint() is None


def test_cached_bounds_hint_none_without_size(tmp_path):
    sd.save_stage_def(sd.StageDefinition(stage_id="ex"), tmp_path)
    c = _controller(intel_enabled=True, stage_id="ex", intel_cache_root=tmp_path)
    assert c._cached_bounds_hint() is None


def test_cached_bounds_hint_none_without_file(tmp_path):
    c = _controller(intel_enabled=True, stage_id="missing", intel_cache_root=tmp_path)
    assert c._cached_bounds_hint() is None
