"""CellMap.localize_report + verify_offset (#26 批4): the diagnostic path the
coverage loop logs (source / margin / evidence) and the public guardrail that
gates an externally-proposed offset (the LLM assist hypothesis).

localize() is now a thin wrapper over localize_report(); these assert the two
agree and that the report labels the mechanism (edge_pin / vote / refused) and
carries an honest margin."""

from __future__ import annotations

import numpy as np

from ggge_ai.battle import coverage_map as cm
from ggge_ai.battle.coverage_map import SIDES, CellMap, FrameObservation, UnitObs
from ggge_ai.battle.vision import MapLattice


def _lattice(nc: int, nr: int, pitch: int = 100) -> MapLattice:
    return MapLattice(
        cols=tuple(range(0, (nc + 1) * pitch, pitch)),
        rows=tuple(range(0, (nr + 1) * pitch, pitch)),
        col_pitch=float(pitch),
        row_pitch=float(pitch),
        edges={s: None for s in SIDES},
    )


def _obs(lat, cells, fps, edges=None, distinctive=None) -> FrameObservation:
    units = [UnitObs(px=(lat.cols[c] + 40, lat.rows[r] + 40), cell=(c, r)) for c, r in cells]
    return FrameObservation(
        lattice=lat,
        edges=edges or {s: None for s in SIDES},
        units=units,
        fingerprints=fps,
        distinctive=frozenset(distinctive if distinctive is not None else fps),
        threats=[],
    )


def _world_fp():
    return {
        (c, r): np.array([c * 50.0 + r * 370.0, 0.0, 0.0, 0.0], np.float32)
        for c in range(8)
        for r in range(5)
    }


def _view(offset, ncols=6, nrows=4, edges=None) -> FrameObservation:
    world = _world_fp()
    lat = _lattice(ncols, nrows)
    fps = {}
    for c in range(ncols):
        for r in range(nrows):
            w = (c + offset[0], r + offset[1])
            if w in world:
                fps[(c, r)] = world[w]
    return _obs(lat, [], fps, edges=edges)


def test_report_edge_pin_labels_both_axes_pinned():
    """Both axes pinned by visible registered boundaries -> source 'edge_pin',
    no vote, no margin; localize() returns the same offset."""
    lat = _lattice(4, 4)
    fp = {(c, r): np.zeros(4, np.float32) for c in range(4) for r in range(4)}
    anchor = _obs(lat, [], fp, edges={"west": 0, "north": 0, "east": None, "south": None})
    cmap = CellMap()
    cmap.anchor(anchor)  # registers west@0, north@0 and seeds terrain (non-empty)
    probe = _obs(lat, [], {}, edges={"west": 2, "north": 1, "east": None, "south": None})

    rep = cmap.localize_report(probe)
    assert rep.source == "edge_pin"
    assert rep.margin is None
    assert rep.offset == (-2, -1)
    assert cmap.localize(probe) == (-2, -1)


def test_report_vote_carries_source_and_margin():
    """A distinctive-terrain solve -> source 'vote' with a margin over the
    runner-up and a positive terrain fraction."""
    cmap = CellMap()
    cmap.anchor(_view((0, 0)))
    rep = cmap.localize_report(_view((2, 1)))

    assert rep.offset == (2, 1)
    assert rep.source == "vote"
    assert rep.margin is not None and rep.margin >= cm.LOCALIZE_MARGIN
    assert rep.terrain_fraction > 0.0
    assert cmap.localize(_view((2, 1))) == (2, 1)


def test_report_refusal_is_source_none_with_no_offset():
    """A periodic layout aliases under the margin gate -> refused: offset None,
    source None, matching localize()."""
    lat = _lattice(12, 1)
    flat = {(c, 0): np.zeros(4, np.float32) for c in range(12)}
    anchor = _obs(lat, [(0, 0), (3, 0), (6, 0), (9, 0)], flat, distinctive=set())
    cmap = CellMap()
    cmap.anchor(anchor)
    probe = _obs(lat, [(0, 0), (3, 0), (6, 0)], flat, distinctive=set())

    rep = cmap.localize_report(probe)
    assert rep.offset is None
    assert rep.source is None
    assert cmap.localize(probe) is None


def test_verify_offset_empty_map_is_trivially_true():
    e = _obs(_lattice(4, 1), [], {}, edges={"west": 0, "east": None, "north": None, "south": None})
    assert CellMap().verify_offset(e, (0, 0)) is True


def test_verify_offset_culls_an_offset_past_a_seen_edge():
    """Covered col -2, and a frame that SEES a west edge at line 0: an offset that
    leaves covered terrain west of that edge is rejected; one that does not is
    accepted (wraps _edge_consistent)."""
    cmap = CellMap()
    cmap._covered = {(-2, 0), (-1, 0), (0, 0)}
    e = _obs(_lattice(4, 1), [], {}, edges={"west": 0, "east": None, "north": None, "south": None})

    assert cmap.verify_offset(e, (0, 0)) is False   # west edge at col 0, covered -2 sits past it
    assert cmap.verify_offset(e, (-1, 0)) is True    # west edge at col -1, covered -2 within slack
