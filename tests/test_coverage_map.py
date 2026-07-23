"""Coverage-scan cell map (#26 批2): observe_frame + CellMap localise /
integrate / frontier / to_tacmap, asserted against the 20260719 ex2if series
(nine min-zoom PNGs) and its user-confirmed standard answer.

Localisation is relative-only (no gesture / displacement input): the truth for
each frame pairing is derived here from the standard answer's north-west cell
positions (map_cell) plus which frames each unit appears in, so the expected
offsets are independent of the algorithm under test."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest

from ggge_ai.battle import coverage_map as cm
from ggge_ai.battle.coverage_map import CellMap, FrameObservation, UnitObs, observe_frame
from ggge_ai.battle.vision import MapLattice

SERIES = Path(__file__).parent / "fixtures" / "vision" / "map_scan" / "ex2if_20260719"
FRAMES = [
    "01_pt1_first_anchor.png", "02_pt2_pan_up.png", "03_pt3_pan_up.png",
    "04_pt4_pan_up.png", "05_pt5_pan_up_small.png", "06_pt6_pan_right.png",
    "07_pt7_pan_down.png", "08_pt8_pan_down.png", "09_pt9_pan_down_end.png",
]


@pytest.fixture(scope="module")
def answer() -> dict:
    return json.loads((SERIES / "standard_answer.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def observations() -> list[FrameObservation]:
    out = []
    for name in FRAMES:
        obs = observe_frame(cv2.imread(str(SERIES / name)))
        assert obs is not None, f"{name}: no lattice read"
        out.append(obs)
    return out


@pytest.fixture(scope="module")
def gt_nw(observations, answer) -> dict[int, tuple[int, int]]:
    """Per-frame offset (frame cell -> north-west map_cell) recovered by aligning
    the frame's observed unit cells onto the standard answer's map_cells for the
    units that frame shows. This is the ground-truth geometry the localiser must
    reproduce, taken from the user-confirmed answer, not from the localiser."""
    frame_cells: dict[int, set[tuple[int, int]]] = {i: set() for i in range(1, 10)}
    for unit in answer["units"]:
        for f in unit["frames"]:
            for cell in unit["cells"]:
                frame_cells[f].add(tuple(cell))
    truth = {}
    for idx, obs in enumerate(observations, start=1):
        expected = frame_cells[idx]
        cells = [u.cell for u in obs.units]
        best = None
        for ox in range(-6, 26):
            for oy in range(-6, 26):
                hits = sum(1 for c in cells if (c[0] + ox, c[1] + oy) in expected)
                if best is None or hits > best[0]:
                    best = (hits, (ox, oy))
        truth[idx] = best[1]
    return truth


# --- observe_frame ---------------------------------------------------------

def test_observe_frame_shape(observations):
    for obs in observations:
        assert isinstance(obs.lattice, MapLattice)
        assert set(obs.edges) == set(cm.SIDES)
        assert obs.units and all(isinstance(u, UnitObs) for u in obs.units)
        assert obs.fingerprints
        assert obs.distinctive <= set(obs.fingerprints)
        assert isinstance(obs.threats, list)


def test_observe_frame_units_snap_inside_lattice(observations):
    for obs in observations:
        for u in obs.units:
            col, row = u.cell
            assert 0 <= col < len(obs.lattice.cols) - 1
            assert 0 <= row < len(obs.lattice.rows) - 1


def test_observe_frame_none_without_lattice():
    assert observe_frame(np.zeros((1080, 2340, 3), np.uint8)) is None


def test_observe_frame_detector_injected():
    frame = cv2.imread(str(SERIES / FRAMES[1]))
    obs = observe_frame(frame, detect=lambda _f: [])
    assert obs is not None and obs.units == []


# --- pairwise localisation -------------------------------------------------

MUST_SOLVE_PAIRS = {(2, 3), (7, 8)}


@pytest.mark.parametrize("a", list(range(1, 9)))
def test_pairwise_localize_correct_or_refuse(observations, gt_nw, a):
    """Each consecutive pair either solves to the standard-answer offset or
    refuses; it never returns a wrong offset. The near-integer strong-overlap
    pairs (pt2-3, pt7-8) must solve."""
    b = a + 1
    expected = (gt_nw[b][0] - gt_nw[a][0], gt_nw[b][1] - gt_nw[a][1])
    cmap = CellMap()
    cmap.anchor(observations[a - 1])
    got = cmap.localize(observations[b - 1])
    assert got is None or got == expected, f"pt{a}->pt{b}: wrong {got}, truth {expected}"
    if (a, b) in MUST_SOLVE_PAIRS:
        assert got == expected, f"pt{a}->pt{b} must solve, got {got}"


def test_localize_empty_map_returns_none(observations):
    assert CellMap().localize(observations[0]) is None


@pytest.mark.parametrize("pair", [(2, 3), (7, 8)])
def test_terrain_only_localize(observations, gt_nw, pair):
    """The zero-unit-density worst case: with every unit masked out, the strong
    pairs still localise on distinctive terrain fingerprints alone."""
    a, b = pair
    anchor = replace(observations[a - 1], units=[])
    target = replace(observations[b - 1], units=[])
    cmap = CellMap()
    cmap.anchor(anchor)
    expected = (gt_nw[b][0] - gt_nw[a][0], gt_nw[b][1] - gt_nw[a][1])
    assert cmap.localize(target) == expected


# --- synthetic: margin refusal & edge hard constraint ----------------------

def _lattice(ncols: int, nrows: int, pitch: int = 100) -> MapLattice:
    cols = tuple(range(0, (ncols + 1) * pitch, pitch))
    rows = tuple(range(0, (nrows + 1) * pitch, pitch))
    return MapLattice(
        cols=cols, rows=rows, col_pitch=float(pitch), row_pitch=float(pitch),
        edges={s: None for s in cm.SIDES},
    )


def _obs(
    lattice: MapLattice,
    unit_cells: list[tuple[int, int]],
    fingerprints: dict[tuple[int, int], np.ndarray],
    edges: dict[str, int | None] | None = None,
    distinctive: set[tuple[int, int]] | None = None,
) -> FrameObservation:
    units = [
        UnitObs(px=(lattice.cols[c] + 40, lattice.rows[r] + 40), cell=(c, r))
        for c, r in unit_cells
    ]
    return FrameObservation(
        lattice=lattice,
        edges=edges or {s: None for s in cm.SIDES},
        units=units,
        fingerprints=fingerprints,
        distinctive=frozenset(distinctive if distinctive is not None else fingerprints),
        threats=[],
    )


def test_periodic_layout_refused():
    """A perfectly periodic unit layout on uniform terrain aliases across
    offsets with no margin, so the map refuses to place it (寧可不定位)."""
    lat = _lattice(12, 1)
    flat = {(c, 0): np.zeros(4, np.float32) for c in range(12)}
    anchor = _obs(lat, [(0, 0), (3, 0), (6, 0), (9, 0)], flat, distinctive=set())
    cmap = CellMap()
    cmap.anchor(anchor)
    probe = _obs(lat, [(0, 0), (3, 0), (6, 0)], flat, distinctive=set())
    assert cmap.localize(probe) is None


WORLD_COLS, WORLD_ROWS = 8, 5


def _world_fp() -> dict[tuple[int, int], np.ndarray]:
    # distinctive per world cell: any misalignment lands >= 50 apart, well over
    # TERRAIN_MATCH, so exactly one offset can match.
    return {
        (c, r): np.array([c * 50.0 + r * 370.0, 0.0, 0.0, 0.0], np.float32)
        for c in range(WORLD_COLS)
        for r in range(WORLD_ROWS)
    }


def _view(
    offset: tuple[int, int],
    edges: dict[str, int | None] | None = None,
    world_units: set[tuple[int, int]] = frozenset(),
    ncols: int = 6,
    nrows: int = 4,
) -> FrameObservation:
    """A synthetic frame whose cell (c, r) shows world cell (c + offset)."""
    world = _world_fp()
    lat = _lattice(ncols, nrows)
    fps = {}
    for c in range(ncols):
        for r in range(nrows):
            w = (c + offset[0], r + offset[1])
            if w in world:
                fps[(c, r)] = world[w]
    units = [
        (wc - offset[0], wr - offset[1])
        for wc, wr in world_units
        if 0 <= wc - offset[0] < ncols and 0 <= wr - offset[1] < nrows
    ]
    return _obs(lat, units, fps, edges=edges)


def test_edge_pin_forces_axis():
    """A visible, already-registered boundary pins that axis exactly (定案 1),
    while the free axis is resolved by terrain voting."""
    anchor = _view((0, 0), edges={"west": 0, "east": None, "north": None, "south": None})
    cmap = CellMap()
    cmap.anchor(anchor)  # registers west at internal col 0
    # probe views the world shifted by (-2, 1); its west edge sits at frame line
    # index 2, so the west pin forces dcol = 0 - 2 = -2, terrain fixes drow = 1.
    probe = _view((-2, 1), edges={"west": 2, "east": None, "north": None, "south": None})
    assert cmap.localize(probe) == (-2, 1)


def test_edge_consistency_culls_contradicting_candidate():
    """A candidate offset that places already-covered terrain beyond a boundary
    the frame SEES is culled (plan 4 / 定案 1: nothing exists past a visible
    edge)."""
    cmap = CellMap()
    cmap._covered = {(0, 0), (1, 0), (2, 0), (3, 0)}
    bbox = cmap._covered_bbox()
    west_edge = _obs(_lattice(4, 1), [], {}, edges={"west": 0, "east": None, "north": None, "south": None})
    # west boundary at internal col dcol; covered cols 0..3 must not fall west of it
    assert cmap._edge_consistent(west_edge, 0, 0, bbox)      # boundary col 0, ok
    assert not cmap._edge_consistent(west_edge, 2, 0, bbox)  # boundary col 2, covered 0/1 west of it
    east_edge = _obs(_lattice(4, 1), [], {}, edges={"west": None, "east": 4, "north": None, "south": None})
    assert cmap._edge_consistent(east_edge, 0, 0, bbox)      # boundary col 4, covered <=3, ok
    assert not cmap._edge_consistent(east_edge, -3, 0, bbox)  # boundary col 1, covered 2/3 east of it


# --- end to end ------------------------------------------------------------

@pytest.fixture(scope="module")
def built_map(observations) -> CellMap:
    cmap = CellMap()
    cmap.anchor(observations[0])
    for obs in observations[1:]:
        off = cmap.localize(obs)
        assert off is not None, "a frame refused during the reference chain"
        cmap.integrate(obs, off)
    return cmap


def test_end_to_end_bounds(built_map, answer):
    assert built_map.size() == tuple(answer["map"]["size_cells"])


def test_end_to_end_units(built_map, answer):
    """Every one of the 27 standard-answer units is found (a large unit counts
    when any footprint cell is hit), with only a handful of detector-noise
    strays -- the map_grid reference tolerance."""
    got = set(built_map.units())
    for unit in answer["units"]:
        cells = {tuple(c) for c in unit["cells"]}
        assert cells & got, f"{unit['id']} {sorted(cells)} not found"
    footprints = {tuple(c) for u in answer["units"] for c in u["cells"]}
    strays = got - footprints
    assert len(strays) <= 6, f"unexplained cells: {sorted(strays)}"


def test_end_to_end_coverage(built_map):
    covered, total = built_map.coverage()
    assert total > 0
    assert covered / total >= 0.95


def test_end_to_end_to_tacmap(built_map):
    tac, bounds = built_map.to_tacmap()
    assert bounds["west"] == 0.0 and bounds["north"] == 0.0
    assert bounds["east"] is not None and bounds["south"] is not None
    assert len(tac.units) == len(built_map.units())
    for x, y in tac.units:
        assert 0.0 <= x <= bounds["east"] + built_map._col_pitch
        assert 0.0 <= y <= bounds["south"] + built_map._row_pitch


# --- frontier priority -----------------------------------------------------

def _map_with_coverage(
    covered: set[tuple[int, int]], reg: dict[str, int | None]
) -> CellMap:
    cmap = CellMap()
    cmap._covered = set(covered)
    cmap._reg = dict(reg)
    return cmap


def test_frontier_unseen_edge_before_hole():
    """An unseen edge outranks an interior hole: with east unregistered the
    frontier points east even though a hole sits inside the known frame."""
    covered = {(c, r) for c in range(5) for r in range(5)} - {(2, 2)}
    cmap = _map_with_coverage(
        covered, {"west": 0, "east": None, "north": 0, "south": 5}
    )
    target = cmap.frontier()
    assert target is not None and target[0] > 4


def test_frontier_prefers_largest_hole_when_bounded():
    """All edges seen: the frontier is the centroid of the largest uncovered
    region inside the frame, not a one-cell speck."""
    frame = {(c, r) for c in range(6) for r in range(6)}
    big = {(1, 1), (1, 2), (2, 1), (2, 2)}
    covered = frame - big - {(5, 5)}
    cmap = _map_with_coverage(
        covered, {"west": 0, "east": 6, "north": 0, "south": 6}
    )
    target = cmap.frontier()
    assert target is not None
    assert 1 <= target[0] <= 2 and 1 <= target[1] <= 2


def test_frontier_none_when_complete():
    frame = {(c, r) for c in range(4) for r in range(4)}
    cmap = _map_with_coverage(frame, {"west": 0, "east": 4, "north": 0, "south": 4})
    assert cmap.frontier() is None


def test_frontier_none_on_empty_map():
    assert CellMap().frontier() is None


def test_frontier_raises_on_inconsistent_starved_coverage():
    """The 07-23 anomaly B: opposing edges registered on the same lattice line
    make integrate()'s interior filter reject every cell, so coverage stays empty
    though terrain was integrated. frontier() must not read that empty coverage as
    a finished scan (returning None); it is an upstream contradiction and raises
    MapStateInconsistent so the loop fails honestly instead of a 0-nudge
    'complete'."""
    lat = _lattice(6, 4)
    fps = {(c, r): np.zeros(4, np.float32) for c in range(6) for r in range(4)}
    starved = _obs(
        lat, [], fps,
        edges={"west": 0, "east": None, "north": 2, "south": 2},
    )
    cmap = CellMap()
    cmap.anchor(starved)
    assert not cmap.is_empty()  # terrain integrated
    assert cmap.coverage()[0] == 0  # yet nothing covered
    with pytest.raises(cm.MapStateInconsistent):
        cmap.frontier()


def test_frontier_healthy_map_does_not_raise():
    """A normally-covered map (the anomaly-B guard must not fire on healthy
    state): frontier returns a real target, never the inconsistency signal."""
    covered = {(c, r) for c in range(5) for r in range(5)}
    cmap = _map_with_coverage(covered, {"west": 0, "east": None, "north": 0, "south": 5})
    target = cmap.frontier()
    assert target is not None
