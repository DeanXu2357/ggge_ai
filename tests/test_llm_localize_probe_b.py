"""Pure-function tests for the probe B offline tool (scripts/llm_localize_probe_b).

Everything that does not need a live ollama: the percentage->pixel map, lattice
cell indexing, patch crop / std / template search, intra-frame uniqueness, the
deterministic candidate picker, the unit mask, the consensus vote, and the whole
crop-A / find-in-B / cell-offset mechanic on a synthetic textured world with a
known camera offset. The LLM (llm / gap-llm) modes are measured by the script
against a live server and are out of scope here."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

from ggge_ai.battle.vision import MapLattice

_SPEC = importlib.util.spec_from_file_location(
    "llm_localize_probe_b",
    Path(__file__).resolve().parents[1] / "scripts" / "llm_localize_probe_b.py",
)
pb = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(pb)

PITCH = 100
VIEW = (8, 8)


def _cell_texture(wc: int, wr: int) -> np.ndarray:
    """A deterministic high-variance PITCH x PITCH BGR patch, unique per world
    cell -- same world cell is byte-identical in any frame, other cells
    decorrelate (the fixture pattern from test_coverage_scan_llm)."""
    seed = ((wc * 73856093) ^ (wr * 19349663)) & 0xFFFFFFFF
    return np.random.default_rng(seed).integers(0, 256, (PITCH, PITCH, 3), dtype=np.uint8)


def _render(nw: tuple[int, int], vc: int = VIEW[0], vr: int = VIEW[1]) -> np.ndarray:
    img = np.zeros((vr * PITCH, vc * PITCH, 3), np.uint8)
    for fc in range(vc):
        for fr in range(vr):
            img[fr * PITCH:(fr + 1) * PITCH, fc * PITCH:(fc + 1) * PITCH] = _cell_texture(
                nw[0] + fc, nw[1] + fr
            )
    return img


def _lattice(vc: int = VIEW[0], vr: int = VIEW[1]) -> MapLattice:
    return MapLattice(
        cols=tuple(range(0, (vc + 1) * PITCH, PITCH)),
        rows=tuple(range(0, (vr + 1) * PITCH, PITCH)),
        col_pitch=float(PITCH),
        row_pitch=float(PITCH),
        edges={},
    )


# --- percentage -> pixel ------------------------------------------------------

def test_pct_to_px_center_and_clamp():
    assert pb.pct_to_px(50, 50, 2340, 1080) == (round(0.5 * 2339), round(0.5 * 1079))
    assert pb.pct_to_px(0, 0, 2340, 1080) == (0, 0)
    assert pb.pct_to_px(100, 100, 2340, 1080) == (2339, 1079)
    # out of range clamps into the frame
    assert pb.pct_to_px(-20, 250, 2340, 1080) == (0, 1079)


# --- lattice cell index -------------------------------------------------------

def test_cell_index_counts_gridlines():
    cols = (0, 100, 200, 300)
    rows = (0, 100, 200)
    assert pb.cell_index(cols, rows, 250, 150) == (2, 1)
    assert pb.cell_index(cols, rows, 0, 0) == (0, 0)
    # right/below the last line -> off lattice
    assert pb.cell_index(cols, rows, 5000, 150) is None
    assert pb.cell_index(cols, rows, 250, 5000) is None


# --- patch crop / std ---------------------------------------------------------

def test_crop_patch_center_and_edge():
    frame = _render((0, 0))
    crop = pb.crop_patch(frame, 400, 400, 40)
    assert crop is not None
    patch, center = crop
    assert patch.shape == (80, 80, 3)
    assert center == (400, 400)
    # too close to the top-left edge -> refused
    assert pb.crop_patch(frame, 10, 10, 40) is None


def test_patch_std_flat_vs_textured():
    flat = np.full((80, 80, 3), 128, np.uint8)
    assert pb.patch_std(flat) == 0.0
    assert pb.patch_std(_cell_texture(3, 4)) > pb.LLM_PATCH_MIN_STD


# --- template search ----------------------------------------------------------

def test_template_search_finds_shifted_patch():
    frame_a = _render((10, 10))
    frame_b = _render((11, 8))  # camera moved +1 col, -2 rows
    patch, _ = pb.crop_patch(frame_a, 350, 250, 40)  # world cell (13, 12)
    hit = pb.template_search(patch, frame_b)
    assert hit is not None
    (cx, cy), score = hit
    assert score > 0.99
    assert (cx, cy) == (250, 450)  # same world cell, shifted by the camera move


def test_template_search_rejects_oversized_patch():
    small = np.zeros((30, 30, 3), np.uint8)
    big = np.zeros((80, 80, 3), np.uint8)
    assert pb.template_search(big, small) is None


# --- uniqueness ---------------------------------------------------------------

def test_uniqueness_high_for_distinct_low_for_tiled():
    unique = _render((0, 0))
    patch, center = pb.crop_patch(unique, 350, 250, 40)
    assert pb.patch_uniqueness(patch, unique, center, 40) > 0.5
    # a frame tiled from ONE repeated cell: the patch recurs, so uniqueness sinks
    tile = _cell_texture(5, 5)
    tiled = np.tile(tile, (VIEW[1], VIEW[0], 1))
    tpatch, tcenter = pb.crop_patch(tiled, 350, 250, 40)
    assert pb.patch_uniqueness(tpatch, tiled, tcenter, 40) < 0.5


# --- deterministic candidate picker ------------------------------------------

def test_auto_candidates_flat_frame_yields_none():
    flat = np.full((800, 800, 3), 128, np.uint8)
    assert pb.auto_candidates(flat, 40, None, region=(50, 50, 700, 700), step=100) == []


def test_auto_candidates_skip_masked_region():
    frame = _render((0, 0))
    mask = np.zeros(frame.shape[:2], np.uint8)
    mask[:, :400] = 1  # mask the whole left half
    cands = pb.auto_candidates(frame, 40, mask, region=(80, 80, 640, 640), step=80)
    assert cands
    assert all(cx >= 400 for cx, _, _ in cands)


# --- unit mask ----------------------------------------------------------------

def test_build_and_apply_mask():
    frame = _render((0, 0))
    mask = pb.build_unit_mask(frame.shape, [(400, 400)], half=50)
    assert mask[400, 400] == 1
    assert mask[100, 100] == 0
    painted = pb.apply_mask(frame, mask)
    # the masked footprint is now a single flat colour
    region = painted[350:450, 350:450]
    assert region.std() < 1.0
    assert pb._mask_hit(mask, 400, 400, 20) is True
    assert pb._mask_hit(mask, 100, 100, 20) is False


# --- consensus vote -----------------------------------------------------------

def test_consensus_variants():
    assert pb.consensus([]) == (None, 0, 0)
    assert pb.consensus([((1, -2), 0.9)]) == ((1, -2), 1, 1)
    assert pb.consensus([((1, -2), 0.9), ((1, -2), 0.8)]) == ((1, -2), 2, 2)
    # two lone disagreeing votes -> no consensus
    assert pb.consensus([((1, -2), 0.9), ((0, 0), 0.8)]) == (None, 1, 2)
    # plurality wins
    assert pb.consensus([((1, -2), 0.5), ((1, -2), 0.5), ((0, 0), 0.9)]) == ((1, -2), 2, 3)


# --- end-to-end offset mechanic ----------------------------------------------

def test_landmark_offset_recovers_known_camera_move():
    frame_a = _render((10, 10))
    frame_b = _render((11, 8))  # offset (colA-colB, rowA-rowB) = (+1, -2)
    lat = _lattice()
    off = pb.landmark_offset(frame_a, frame_b, lat, lat, 350, 250, 40)
    assert off is not None
    offset, score = off
    assert offset == (1, -2)
    assert score > 0.99


def test_landmark_offset_refuses_flat_patch():
    flat = np.full((800, 800, 3), 128, np.uint8)
    lat = _lattice()
    assert pb.landmark_offset(flat, flat, lat, lat, 400, 400, 40) is None
