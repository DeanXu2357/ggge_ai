"""LLM localisation layer 3 (#26 批4): CoverageScanSource._llm_assist and its
guardrail chain, driven by a deterministic fake reader.

The tier's whole safety claim is that an LLM landmark hypothesis touches a
coordinate only after two deterministic guards pass: a patch cropped at each
claimed cell must cross-correlate (proof the two positions are the same content,
so the offset is a real correspondence), and the offset must be edge-consistent.
These tests render REAL textured frames so the patch guard runs for real, then a
fake reader returns crafted grid cells to exercise accept / patch-reject /
edge-reject / unparseable / reader-None. A final pair asserts the pure-
deterministic loop is untouched when no reader is wired (plan: llm=None
bit-identical)."""

from __future__ import annotations

import numpy as np

from ggge_ai.battle import live_scan as ls
from ggge_ai.battle.coverage_map import SIDES, CellMap, FrameObservation, UnitObs
from ggge_ai.battle.live_scan import CoverageScanSource
from ggge_ai.battle.vision import MapLattice

PITCH = 100
VIEW = (6, 4)


def _cell_texture(wc: int, wr: int) -> np.ndarray:
    """A deterministic, high-variance PITCH x PITCH BGR patch, unique per world
    cell: the same world cell renders byte-identically in any frame (patch
    correlation 1.0), different cells decorrelate."""
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
        edges={s: None for s in SIDES},
    )


def _obs(
    edges: dict[str, int | None] | None = None,
    units: list[UnitObs] | None = None,
) -> FrameObservation:
    return FrameObservation(
        lattice=_lattice(),
        edges=edges or {s: None for s in SIDES},
        units=units or [],
        fingerprints={},
        distinctive=frozenset(),
        threats=[],
    )


class _FakeLlm:
    def __init__(self, reply):
        self.reply = reply
        self.calls: list[tuple] = []

    def localize_pair(self, a, b, instruction, force=False):
        self.calls.append((a, b, force))
        return self.reply


def _source(llm, events=None) -> CoverageScanSource:
    src = CoverageScanSource(
        capture=lambda: _render((0, 0)),
        swipe=lambda *a, **k: None,
        tap=lambda x, y: None,
        ledger_log=(lambda kind, **d: events.append({"kind": kind, **d})) if events is not None else None,
        sleep=lambda s: None,
        llm=llm,
    )
    src._map = CellMap()
    src._last_offset = (0, 0)
    return src


def _cell(col, row):
    return {"col": col, "row": row}



def test_assist_accepts_a_patch_verified_edge_consistent_hypothesis():
    """The anchor and current frames share world cell (4,4); the reader points at
    it correctly in each frame. The patch matches (same content) and the offset
    breaks no seen edge, so the assist places the frame with source llm_assist."""
    events = []
    reply = {"landmark": "textured block", "frame1": _cell(2, 2), "frame2": _cell(1, 1)}
    src = _source(_FakeLlm(reply), events)
    src._anchor_frame = _render((2, 2))  # cell (2,2) == world (4,4)
    src._anchor_obs = _obs()
    cur_frame = _render((3, 3))  # cell (1,1) == world (4,4)

    report = src._llm_assist(cur_frame, _obs())

    assert report is not None
    assert report.source == "llm_assist"
    assert report.offset == (1, 1)  # last_offset (0,0) + (2-1, 2-1)
    assert report.margin >= ls.LLM_PATCH_MIN
    ev = next(e for e in events if e["kind"] == "llm_assist")
    assert ev["accepted"] is True
    assert src.llm.calls[0][2] is True  # force=True bypasses the 60s rate limit



def test_assist_rejects_when_the_two_claimed_patches_are_different_content():
    """Same camera, but the reader names cells that are DIFFERENT world content
    (a hallucinated correspondence). The patch guard fails, so no coordinate is
    touched and the caller falls through to recovery."""
    events = []
    reply = {"landmark": "wrong", "frame1": _cell(2, 2), "frame2": _cell(0, 0)}
    src = _source(_FakeLlm(reply), events)
    src._anchor_frame = _render((2, 2))
    src._anchor_obs = _obs()

    report = src._llm_assist(_render((2, 2)), _obs())

    assert report is None
    ev = next(e for e in events if e["kind"] == "llm_assist")
    assert ev["accepted"] is False
    assert ev["patch"] < ls.LLM_PATCH_MIN


def test_assist_rejects_a_flat_patch_it_cannot_verify():
    """A uniform patch (empty starfield) is refused outright: TM_CCOEFF aliases
    high on flat regions, so it cannot verify a correspondence there."""
    src = _source(_FakeLlm({"frame1": _cell(2, 2), "frame2": _cell(2, 2)}))
    flat = np.full((VIEW[1] * PITCH, VIEW[0] * PITCH, 3), 40, np.uint8)
    src._anchor_frame = flat
    src._anchor_obs = _obs()

    assert src._llm_assist(flat, _obs()) is None



def test_assist_rejects_an_offset_that_contradicts_a_seen_edge():
    """Patches match, but the hypothesised offset would place already-covered
    terrain west of a west edge the current frame SEES. verify_offset culls it
    (plan 4: nothing exists past a visible boundary)."""
    events = []
    src = _source(_FakeLlm({"frame1": _cell(2, 2), "frame2": _cell(2, 2)}), events)
    src._map._covered = {(-2, 0), (-2, 1)}
    src._anchor_frame = _render((2, 2))
    src._anchor_obs = _obs()
    cur = _obs(edges={"west": 0, "east": None, "north": None, "south": None})

    report = src._llm_assist(_render((2, 2)), cur)

    assert report is None  # offset (0,0) leaves covered col -2 west of west edge 0
    ev = next(e for e in events if e["kind"] == "llm_assist")
    assert ev["accepted"] is False
    assert ev["patch"] >= ls.LLM_PATCH_MIN  # the patch matched; only the edge failed



def test_assist_none_on_unparseable_reply():
    src = _source(_FakeLlm({"landmark": "only prose, no coords"}))
    src._anchor_frame = _render((2, 2))
    src._anchor_obs = _obs()
    assert src._llm_assist(_render((2, 2)), _obs()) is None


def test_assist_none_when_reader_returns_none():
    src = _source(_FakeLlm(None))
    src._anchor_frame = _render((2, 2))
    src._anchor_obs = _obs()
    assert src._llm_assist(_render((2, 2)), _obs()) is None


def test_assist_none_without_an_anchor_frame():
    src = _source(_FakeLlm({"frame1": _cell(0, 0), "frame2": _cell(0, 0)}))
    assert src._llm_assist(_render((0, 0)), _obs()) is None



def _abstract_world_source(llm, events):
    """A batch3-style abstract world (opaque camera token, injected observe) so
    _place never touches pixels -- the point is that wiring a reader that can
    never help changes nothing versus llm=None."""
    from tests.test_coverage_scan import _World, _source as _det_source

    world = _World(9, 7, view=(6, 4), units={(1, 1), (4, 2), (7, 5), (2, 4)}, start=(2, 2), step=1, seed=3)
    src = _det_source(world, events=events)
    src.llm = llm
    return src


def test_llm_none_matches_a_reader_that_never_helps(monkeypatch):
    """The scan result is identical whether llm is None or a reader whose
    localize_pair always returns None: the tier is inert when it cannot help, so
    the deterministic loop is untouched."""
    monkeypatch.setattr(ls.vision, "is_unit_detail_modal", lambda f: False)
    ev_none: list = []
    ev_dead: list = []
    census_none = _abstract_world_source(None, ev_none).collect()
    census_dead = _abstract_world_source(_FakeLlm(None), ev_dead).collect()

    def _cells(c):
        return {(round((x - 40) / PITCH), round((y - 40) / PITCH)) for x, y in c.units}

    assert _cells(census_none) == _cells(census_dead)
    kinds_none = [e["kind"] for e in ev_none]
    kinds_dead = [e["kind"] for e in ev_dead]
    assert kinds_none == kinds_dead
    assert "llm_assist" not in kinds_none  # deterministic run never invoked the tier
