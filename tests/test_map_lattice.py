"""Coverage-scan visual primitives (#26 批1): read_map_lattice's full-frame
gridlines + map-boundary evidence, and cell_fingerprints' per-cell terrain
descriptors. Everything is asserted against the 20260719 ex2if series (nine
min-zoom PNGs, grid ON) -- the same fixtures the offline stitch pipeline uses.

The boundary truth table below was derived by reading each fixture frame
directly (grid runs into starfield at a real edge, off-screen otherwise) and
cross-checked against the stitch cameras in test_map_grid: west is in view
while panning up (pt1-5), east while panned right/down (pt6-9), north at the
top of the up-pan (pt4-6), south only at the sequence ends (pt1, pt9). The
existing map_grid reader false-negatives pt2-west and pt9-south (both truly in
view); read_map_lattice must catch them."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from ggge_ai.battle import vision

SERIES = Path(__file__).parent / "fixtures" / "vision" / "map_scan" / "ex2if_20260719"

FRAMES = {
    "pt1": "01_pt1_first_anchor.png",
    "pt2": "02_pt2_pan_up.png",
    "pt3": "03_pt3_pan_up.png",
    "pt4": "04_pt4_pan_up.png",
    "pt5": "05_pt5_pan_up_small.png",
    "pt6": "06_pt6_pan_right.png",
    "pt7": "07_pt7_pan_down.png",
    "pt8": "08_pt8_pan_down.png",
    "pt9": "09_pt9_pan_down_end.png",
}

# side -> boundary gridline pixel (x for west/east, y for north/south), or
# absent when that side is off-screen. Positions are the outermost map
# gridline confirmed on the fixture; the detector reports the cut-off a little
# outside it (the ridge dies just past the last lit line), so EDGE_TOL is
# generous but stays well inside a half pitch (~46px) so a snap recovers it.
BOUNDARY_TRUTH: dict[str, dict[str, int]] = {
    "pt1": {"west": 207, "south": 946},
    "pt2": {"west": 185},
    "pt3": {"west": 199},
    "pt4": {"west": 243, "north": 131},
    "pt5": {"west": 223, "north": 348},
    "pt6": {"east": 2021, "north": 384},
    "pt7": {"east": 2044},
    "pt8": {"east": 2067},
    "pt9": {"east": 2147, "south": 1019},
}
EDGE_TOL = 55
SIDES = ("west", "east", "north", "south")

# stitch-refined camera px per frame (test_map_grid.CAMERAS); used only to
# derive the independent inter-frame cell offset the fingerprints must recover.
CAMERAS = {
    "pt2": (-12, -484), "pt3": (-30, -895),
    "pt7": (428, -999), "pt8": (399, -584),
}


@pytest.fixture(scope="module")
def images() -> dict[str, np.ndarray]:
    return {name: cv2.imread(str(SERIES / fn)) for name, fn in FRAMES.items()}


@pytest.fixture(scope="module")
def lattices(images) -> dict[str, vision.MapLattice]:
    out = {}
    for name, img in images.items():
        lat = vision.read_map_lattice(img)
        assert lat is not None, f"{name}: no lattice read"
        out[name] = lat
    return out


@pytest.fixture(scope="module")
def answer() -> dict:
    return json.loads((SERIES / "standard_answer.json").read_text(encoding="utf-8"))


# --- boundaries ------------------------------------------------------------

@pytest.mark.parametrize("name", list(FRAMES))
def test_boundary_presence_matches_truth(lattices, name):
    edges = lattices[name].edges
    expected = BOUNDARY_TRUTH[name]
    for side in SIDES:
        seen = edges[side] is not None
        want = side in expected
        assert seen == want, (
            f"{name} {side}: detector {'saw' if seen else 'missed'} an edge, "
            f"truth says {'visible' if want else 'off-screen'}"
        )


@pytest.mark.parametrize("name", list(FRAMES))
def test_boundary_positions_match_truth(lattices, name):
    edges = lattices[name].edges
    for side, px in BOUNDARY_TRUTH[name].items():
        got = edges[side]
        assert got is not None and abs(got - px) <= EDGE_TOL, (
            f"{name} {side}: got {got}, truth {px} (tol {EDGE_TOL})"
        )


def test_pt2_west_and_pt9_south_are_caught(lattices):
    """The two edges the offline map_grid reader false-negatives -- both are
    genuinely in view -- are the batch's regression anchors."""
    assert lattices["pt2"].edges["west"] is not None
    assert lattices["pt9"].edges["south"] is not None


# --- lattice ---------------------------------------------------------------

def test_pitch_matches_standard_answer(lattices, answer):
    col_truth, row_truth = answer["pitch"]
    for name, lat in lattices.items():
        assert abs(lat.col_pitch - col_truth) <= 7, f"{name} col pitch {lat.col_pitch}"
        assert abs(lat.row_pitch - row_truth) <= 7, f"{name} row pitch {lat.row_pitch}"


def test_lattice_covers_full_frame(lattices):
    """Extrapolated lines must bracket every in-frame pixel so any point maps
    to a cell (the whole-frame cell-conversion requirement)."""
    for name, lat in lattices.items():
        assert lat.cols[0] < lat.col_pitch, f"{name} left uncovered"
        assert lat.cols[-1] > vision.MAP_W - lat.col_pitch, f"{name} right uncovered"
        assert lat.rows[0] < lat.row_pitch, f"{name} top uncovered"
        assert lat.rows[-1] > vision.MAP_H - lat.row_pitch, f"{name} bottom uncovered"
        assert list(lat.cols) == sorted(lat.cols)
        assert list(lat.rows) == sorted(lat.rows)


# --- zoom_at_max wide-band fallback (批6) -----------------------------------

GRID_DIR = Path(__file__).parent / "fixtures" / "vision" / "grid"


def test_zoom_at_max_pt2_recovered_by_wide_band(images):
    """07-23 root cause / 批6 fix: the narrow read_grid_lattice band is buried
    by pt2's dense central formation, so grid_pitch reads None and the old
    zoom_at_max returned None (mislabeling a max-zoom camera as undecidable and
    tripping SurveyIncomplete). The read_map_lattice wide-band fallback recovers
    the column pitch and the verdict flips to True -- while the narrow band
    stays blind, proving the fallback is what does the work."""
    assert vision.grid_pitch(images["pt2"])[0] is None
    assert vision.zoom_at_max(images["pt2"]) is True


def test_zoom_at_max_all_frames_true(images):
    """Every frame in this min-zoom series was captured at the furthest zoom;
    the eight clean frames already read True through the narrow band and pt2
    now joins them, so all nine must read True (no regression on the eight)."""
    for name, img in images.items():
        assert vision.zoom_at_max(img) is True, f"{name}: not True"


def test_zoom_at_max_non_max_and_gridless_unchanged():
    """The fallback must not disturb the other two verdicts: a default-zoom
    grid-on hub (col pitch ~127px) stays False -- grid_pitch reads it, the
    fallback never fires -- and a gridless hub stays None -- neither reader
    finds a lattice."""
    hub = cv2.imread(str(GRID_DIR / "hub_grid_on_20260719.png"))
    gridless = cv2.imread(str(GRID_DIR / "hub_gridless_20260719.png"))
    assert vision.zoom_at_max(hub) is False
    assert vision.zoom_at_max(gridless) is None


def test_pick_pinch_center_beats_fixed_on_dense_frame(images):
    """批6 dynamic pinch center: on pt2's packed formation the picked center's
    four finger points clear the detected units far better than the old
    hard-wired (1170,500), so the zoom gesture starts on open map instead of on
    a sprite (which the game eats)."""
    from ggge_ai.actuation import pinch

    peaks = vision.find_unit_density_peaks(images["pt2"])

    def clearance(center):
        a, b = pinch.zoom_out_fingers(center)
        pts = (a[0], a[1], b[0], b[1])
        return min(
            ((px - ux) ** 2 + (py - uy) ** 2) ** 0.5 for px, py in pts for ux, uy in peaks
        )

    chosen = pinch.pick_pinch_center(peaks)
    assert clearance(chosen) > 1.8 * clearance(pinch.PINCH_CENTER_DEFAULT)


# --- fingerprints ----------------------------------------------------------

def _distinctive(fps: dict, thr: float = 12.0) -> set:
    """Cells whose colour stands clear of the frame's uniform-space median --
    the terrain that actually carries localisation signal (the open-space
    majority is ambiguous by construction, per plan section 10)."""
    med = np.median(np.stack(list(fps.values())), axis=0)
    return {k for k, v in fps.items() if float(np.linalg.norm((v - med)[:3])) > thr}


def _expected_offset(la, lb, ca, cb) -> tuple[int, int]:
    dcol = ((la.cols[0] - lb.cols[0]) + (ca[0] - cb[0])) / lb.col_pitch
    drow = ((la.rows[0] - lb.rows[0]) + (ca[1] - cb[1])) / lb.row_pitch
    return round(dcol), round(drow)


@pytest.mark.parametrize("a,b", [("pt2", "pt3"), ("pt7", "pt8")])
def test_fingerprints_recover_interframe_offset(images, lattices, a, b):
    """Voting distinctive-cell fingerprints against every integer offset must
    peak at exactly the offset the stitch cameras predict, with a clear margin
    over the runner-up -- the premise batch2 localisation is built on."""
    fa = vision.cell_fingerprints(images[a], lattices[a])
    fb = vision.cell_fingerprints(images[b], lattices[b])
    da, db = _distinctive(fa), _distinctive(fb)
    expected = _expected_offset(lattices[a], lattices[b], CAMERAS[a], CAMERAS[b])
    scores: dict[tuple[int, int], float] = {}
    for di in range(-8, 9):
        for dj in range(-30, 31):
            ds = [
                float(np.linalg.norm(fa[k] - fb[(k[0] + di, k[1] + dj)]))
                for k in da
                if (k[0] + di, k[1] + dj) in db
            ]
            if len(ds) >= 8:
                scores[(di, dj)] = float(np.median(ds))
    best = min(scores, key=scores.get)
    ordered = sorted(scores.values())
    assert best == expected, f"{a}->{b}: recovered {best}, expected {expected}"
    assert ordered[1] - ordered[0] >= 3.0, f"{a}->{b}: weak margin {ordered[:2]}"


@pytest.mark.parametrize("a,b", [("pt2", "pt3"), ("pt7", "pt8")])
def test_same_cell_stable_vs_adjacent(images, lattices, a, b):
    """Aligned by the true offset, a world cell's fingerprint is far closer to
    its own image across frames than to its in-frame neighbour: cross-frame
    stability and local (adjacent-cell) discriminability at once."""
    fa = vision.cell_fingerprints(images[a], lattices[a])
    fb = vision.cell_fingerprints(images[b], lattices[b])
    da, db = _distinctive(fa), _distinctive(fb)
    di, dj = _expected_offset(lattices[a], lattices[b], CAMERAS[a], CAMERAS[b])
    # pair distinctive terrain to distinctive terrain: a fractional inter-frame
    # shift straddles some cells across a boundary, and matching a distinctive
    # cell to a half-overlapped uniform neighbour is not what localisation does
    same = [
        float(np.linalg.norm(fa[k] - fb[(k[0] + di, k[1] + dj)]))
        for k in da
        if (k[0] + di, k[1] + dj) in db
    ]
    adj = [
        float(np.linalg.norm(fa[k] - fa[(k[0] + 1, k[1])]))
        for k in da
        if (k[0] + 1, k[1]) in fa
    ]
    assert len(same) >= 8 and len(adj) >= 8
    same_med, adj_med = float(np.median(same)), float(np.median(adj))
    assert same_med < 20, f"{a}->{b}: same-cell median {same_med} too high"
    assert adj_med > 30, f"{a}->{b}: adjacent median {adj_med} too low"
    assert same_med < adj_med * 0.6, f"{a}->{b}: same {same_med} vs adj {adj_med}"


def test_fingerprints_exclude_hud(images, lattices):
    """No fingerprint cell may sit on the banner or the bottom prompt strip."""
    lat = lattices["pt7"]
    fps = vision.cell_fingerprints(images["pt7"], lat)
    for (i, j) in fps:
        cx = (lat.cols[i] + lat.cols[i + 1]) / 2
        cy = (lat.rows[j] + lat.rows[j + 1]) / 2
        for hx, hy, hw, hh in vision.CELL_FP_HUD_HOLES:
            assert not (hx <= cx <= hx + hw and hy <= cy <= hy + hh), (
                f"cell ({i},{j}) centre falls in HUD hole"
            )
