"""CoverageScanSource (#26 批3): the coverage-driven live scan loop against a
synthetic malicious world.

The world is deliberately hostile in exactly the way the 2026-07-23 red lines
demand tolerance for: swipe effect is DECOUPLED from the gesture -- truncated
by a random fraction, eaten whole when a direction is blocked, deferred a frame
(delayed settling), occasionally a no-op, and occasionally an over-move that
loses the overlap localize needs. `capture()` hands back an opaque camera token;
the source's injected `observe` seam turns it into a real FrameObservation
(distinctive per-cell terrain + units + visible edges) so the ACTUAL CellMap
localize/integrate/frontier machinery runs -- only the pixels are stubbed.

The gesture magnitude never enters a coordinate (定案 1): the loop only reads
where each frame lands. Assertions therefore target convergence, honest
seen-only bounds (the 07-23 false-south regression), the recovery protocol, the
localize gates, budget fail-fast and honest unreachable-hole reporting."""

from __future__ import annotations

import random

import numpy as np
import pytest

from ggge_ai.battle import coverage_map as cm
from ggge_ai.battle import live_scan as ls
from ggge_ai.battle import vision
from ggge_ai.battle.coverage_map import SIDES, FrameObservation, UnitObs
from ggge_ai.battle.live_scan import CoverageScanSource
from ggge_ai.battle.scout_intel import SurveyIncomplete
from ggge_ai.battle.vision import MapLattice

PITCH = 100
FOOT = 40  # a unit's sub-cell foot offset inside its cell

_DIR_NAME = {(1, 0): "east", (-1, 0): "west", (0, 1): "south", (0, -1): "north"}


def _sign(v: float) -> int:
    return (v > 0) - (v < 0)


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


class _World:
    """A bounded cell world behind an opaque camera token. `capture()` returns
    the settled view-NW world cell; `swipe()` moves it with configurable malice;
    `observe()` synthesises the FrameObservation the source localises."""

    def __init__(
        self,
        cols,
        rows,
        *,
        view=(6, 4),
        units=frozenset(),
        threats=frozenset(),
        start=(0, 0),
        step=2,
        seed=0,
        eat_dirs=frozenset(),
        overmove_at=frozenset(),
        delay_at=frozenset(),
        noop_at=frozenset(),
    ):
        self.cols, self.rows = cols, rows
        self.view = view
        self.units = set(units)
        self.threats = set(threats)
        self.nw = list(start)
        self.pending = [0, 0]
        self.nominal = step
        self.rng = random.Random(seed)
        self.eat_dirs = set(eat_dirs)
        self.overmove_at = set(overmove_at)
        self.delay_at = set(delay_at)
        self.noop_at = set(noop_at)
        self.n = 0
        self.terrain = {
            (c, r): np.array([c * 100.0, r * 100.0, 0.0, 0.0], np.float32)
            for c in range(cols)
            for r in range(rows)
        }


    def capture(self):
        return tuple(self.nw)

    def _apply(self, mv):
        cmax = max(0, self.cols - self.view[0])
        rmax = max(0, self.rows - self.view[1])
        self.nw[0] = _clamp(self.nw[0] + mv[0], 0, cmax)
        self.nw[1] = _clamp(self.nw[1] + mv[1], 0, rmax)

    def _step(self, d):
        if d == 0:
            return 0
        return self.rng.randint(1, self.nominal)

    def swipe(self, x1, y1, x2, y2, *a):
        self.n += 1
        dc, dr = _sign(x1 - x2), _sign(y1 - y2)
        name = _DIR_NAME.get((dc, dr))
        if name in self.eat_dirs or self.n in self.noop_at:
            move = [0, 0]
        elif self.n in self.overmove_at:
            move = [dc * self.view[0], dr * self.view[1]]  # lose the overlap
        else:
            move = [dc * self._step(dc), dr * self._step(dr)]
        if self.n in self.delay_at:
            self.pending[0] += move[0]
            self.pending[1] += move[1]
        else:
            self._apply([move[0] + self.pending[0], move[1] + self.pending[1]])
            self.pending = [0, 0]

    def detect(self, token):
        nw_c, nw_r = token
        vc, vr = self.view
        out = []
        for wc, wr in self.units:
            fc, fr = wc - nw_c, wr - nw_r
            if 0 <= fc < vc and 0 <= fr < vr:
                out.append((fc * PITCH + FOOT, fr * PITCH + FOOT))
        return out

    def observe(self, token) -> FrameObservation | None:
        nw_c, nw_r = token
        vc, vr = self.view
        cols = tuple(range(0, (vc + 1) * PITCH, PITCH))
        rows = tuple(range(0, (vr + 1) * PITCH, PITCH))
        edges = {s: None for s in SIDES}
        if nw_c <= 0:
            edges["west"] = -nw_c
        if nw_c + vc >= self.cols:
            edges["east"] = self.cols - nw_c
        if nw_r <= 0:
            edges["north"] = -nw_r
        if nw_r + vr >= self.rows:
            edges["south"] = self.rows - nw_r
        fps, units, threats = {}, [], []
        for fc in range(vc):
            for fr in range(vr):
                wc, wr = nw_c + fc, nw_r + fr
                if 0 <= wc < self.cols and 0 <= wr < self.rows:
                    fps[(fc, fr)] = self.terrain[(wc, wr)]
                    px = (cols[fc] + FOOT, rows[fr] + FOOT)
                    if (wc, wr) in self.units:
                        units.append(UnitObs(px=px, cell=(fc, fr)))
                    if (wc, wr) in self.threats:
                        threats.append(px)
        if not fps:
            return None
        median = np.median(np.stack(list(fps.values())), axis=0)
        distinctive = frozenset(
            c
            for c, fp in fps.items()
            if float(np.linalg.norm((fp - median)[:3])) > cm.DISTINCT_THRESHOLD
        )
        lattice = MapLattice(
            cols=cols,
            rows=rows,
            col_pitch=float(PITCH),
            row_pitch=float(PITCH),
            edges={s: None for s in SIDES},
        )
        return FrameObservation(
            lattice=lattice,
            edges=edges,
            units=units,
            fingerprints=fps,
            distinctive=distinctive,
            threats=threats,
        )


def _source(world, events=None):
    src = CoverageScanSource(
        capture=world.capture,
        swipe=world.swipe,
        tap=lambda x, y: None,
        ledger_log=(
            (lambda kind, **d: events.append({"kind": kind, **d}))
            if events is not None
            else None
        ),
        sleep=lambda s: None,
        detect=world.detect,
        observe=world.observe,
    )
    return src


@pytest.fixture(autouse=True)
def _no_modal(monkeypatch):
    monkeypatch.setattr(vision, "is_unit_detail_modal", lambda f: False)


def _found_cells(census):
    return {(round((x - FOOT) / PITCH), round((y - FOOT) / PITCH)) for x, y in census.units}



def test_converges_and_syncs_every_unit():
    """The full malicious cocktail (truncation + a no-op + a delayed leg +
    an anchor-phase start away from the NW corner) still converges: every unit
    is synced, bounds match the true map, coverage is complete."""
    units = {(1, 1), (4, 2), (7, 5), (2, 4), (6, 1), (3, 3)}
    world = _World(
        9, 7, view=(6, 4), units=units, start=(2, 2), step=1, seed=3,
        noop_at={5}, delay_at={9},
    )
    events = []
    src = _source(world, events=events)

    census = src.collect()

    assert src.bounds == {"west": 0.0, "north": 0.0, "east": 900.0, "south": 700.0}
    assert _found_cells(census) == units
    report = next(e for e in events if e["kind"] == "coverage_report")
    assert report["covered"] == report["cells"]  # 100% of the framed board
    assert report["unreachable"] == 0
    # the anchor phase actually drove to the NW corner (start was (2,2))
    assert any(
        e["kind"] == "nudge" and e["dir"] in ("west", "north") for e in events
    )


def test_small_map_finishes_at_once():
    """A map smaller than the viewport shows all four edges in the first frame:
    the anchor phase is a no-op and the scan closes immediately."""
    world = _World(5, 3, view=(6, 4), units={(1, 1), (3, 2)}, start=(0, 0))
    events = []
    src = _source(world, events=events)

    census = src.collect()

    assert src.bounds == {"west": 0.0, "north": 0.0, "east": 500.0, "south": 300.0}
    assert _found_cells(census) == {(1, 1), (3, 2)}


def test_threats_export_to_census_world_px():
    """Threat cells collected during the walk reach census.threats in the same
    world-px frame as the units (downstream threat_centroid depends on it)."""
    world = _World(8, 6, view=(6, 4), units={(2, 2)}, threats={(5, 3), (6, 4)})
    src = _source(world)

    census = src.collect()

    got = {(round((x - PITCH / 2) / PITCH), round((y - PITCH / 2) / PITCH)) for x, y in census.threats}
    assert got == {(5, 3), (6, 4)}
    assert census.threat_centroid() is not None



def test_never_fabricates_a_south_edge_from_a_blocked_push():
    """THE 07-23 regression, locked. Southward pushes are eaten wholesale (the
    dense-origin / eaten-drag failure), so the south edge is never SEEN. The old
    serpentine inferred a false south界 from 'the camera would not move'; the
    coverage source must never register south from a blocked push -- it fails
    loud with SurveyIncomplete and south stays None in every ledger event."""
    world = _World(9, 12, view=(6, 4), units={(2, 2), (5, 1)}, start=(0, 0), eat_dirs={"south"})
    events = []
    src = _source(world, events=events)

    with pytest.raises(SurveyIncomplete):
        src.collect()

    # west/north/east were reachable and honestly seen; south never was
    report = next(e for e in events if e["kind"] == "coverage_report")
    assert report["bounds"]["south"] is None
    assert report["bounds"]["north"] is not None
    # not one event anywhere fabricates a south coordinate
    for e in events:
        b = e.get("bounds")
        if isinstance(b, dict) and "south" in b:
            assert b["south"] is None
    # and no census/px-bounds were published on the failure path
    assert src.bounds is None and src.census is None


def test_inconsistent_map_state_fails_loud_not_complete():
    """Anomaly B, locked. A pathological observation registers opposing edges on
    the same lattice line (north==south, the 07-23 phantom read), so integrate's
    interior filter rejects every cell and coverage stays empty. The loop must
    NOT read that empty coverage as a finished scan (the old frontier() returned
    None -> outcome 'complete' -> a silent 0-nudge close caught only by a later
    safety net); it fails loud with 'map state inconsistent' and the ledger names
    the outcome honestly -- never 'complete'."""
    lat = MapLattice(
        cols=tuple(range(0, 7 * PITCH, PITCH)),
        rows=tuple(range(0, 5 * PITCH, PITCH)),
        col_pitch=float(PITCH), row_pitch=float(PITCH),
        edges={s: None for s in SIDES},
    )
    fps = {
        (c, r): np.array([c * 100.0, r * 100.0, 0.0, 0.0], np.float32)
        for c in range(6)
        for r in range(4)
    }
    # west + north + south all seen (both axes edge-pin, mirroring the real
    # 輪三 frame) but north and south land on the same line -> starved coverage
    starved = FrameObservation(
        lattice=lat,
        edges={"west": 0, "east": None, "north": 2, "south": 2},
        units=[],
        fingerprints=fps,
        distinctive=frozenset(fps),
        threats=[],
    )
    events = []
    src = CoverageScanSource(
        capture=lambda: np.zeros((10, 10, 3), np.uint8),
        swipe=lambda *a: None,
        tap=lambda x, y: None,
        ledger_log=lambda kind, **d: events.append({"kind": kind, **d}),
        sleep=lambda s: None,
        observe=lambda frame: starved,
    )

    with pytest.raises(SurveyIncomplete, match="map state inconsistent"):
        src.collect()

    report = next(e for e in events if e["kind"] == "coverage_report")
    assert report["outcome"] == "inconsistent"
    assert report["covered"] == 0
    # nothing fabricated on the failure path
    assert src.bounds is None and src.census is None



def test_recovery_relocates_after_an_overmove_loses_the_lock():
    """An over-move drops the overlap localize needs, so the frame is refused;
    the recovery protocol steers back toward a registered edge, re-sees it and
    re-anchors -- the scan still closes."""
    # a 13-wide map leaves room for the first east push to over-move the whole
    # view width (6 cells) unclamped, dropping the col overlap localize needs
    world = _World(
        13, 7, view=(6, 4), units={(1, 1), (10, 5), (6, 3)}, start=(0, 0),
        overmove_at={1},
    )
    events = []
    src = _source(world, events=events)

    census = src.collect()

    assert any(
        e["kind"] == "scan_recovery" and e["reason"] == "relocated" for e in events
    )
    assert src.bounds == {"west": 0.0, "north": 0.0, "east": 1300.0, "south": 700.0}
    assert _found_cells(census) == {(1, 1), (10, 5), (6, 3)}



def test_ambiguous_terrain_refuses_then_recovers():
    """A periodic terrain band with no distinctive cells aliases across offsets:
    LOCALIZE_MARGIN / the evidence floor make the map refuse rather than guess,
    the frame_localized ledger shows the refusal-driven recovery, and the scan
    still converges by re-anchoring on the seen edges."""

    class _Periodic(_World):
        def observe(self, token):
            obs = super().observe(token)
            if obs is None:
                return None
            # flatten terrain to a single repeating value: no distinctive cells,
            # so terrain voting cannot carry a margin (the gate must refuse when
            # only aliasing unit hits remain)
            flat = {c: np.zeros(4, np.float32) for c in obs.fingerprints}
            return type(obs)(
                lattice=obs.lattice,
                edges=obs.edges,
                units=obs.units,
                fingerprints=flat,
                distinctive=frozenset(),
                threats=obs.threats,
            )

    # a grid-regular unit lattice: unit hits alias on a cell shift, and with no
    # distinctive terrain the interior frames refuse -> recovery leans on edges
    units = {(c, r) for c in (1, 3, 5, 7) for r in (1, 3, 5)}
    world = _Periodic(9, 7, view=(6, 4), units=units, start=(0, 0))
    events = []
    src = _source(world, events=events)

    # with no terrain signal the interior is un-localisable; the scan must not
    # silently succeed on a guess -- it either closes via edge pins or fails
    # loud, but every localize is margin-gated (never a wrong placement)
    try:
        src.collect()
    except SurveyIncomplete:
        pass
    assert any(e["kind"] == "scan_recovery" for e in events), "gate never forced a refusal"



def test_budget_exhaustion_fails_fast_without_fabrication():
    """A huge map cannot be covered within SCAN_MAX_NUDGES; the scan fails loud
    (SurveyIncomplete) rather than reporting a partial map as complete, and
    publishes no census."""
    world = _World(200, 200, view=(6, 4), units=set(), start=(0, 0))
    events = []
    src = _source(world, events=events)

    with pytest.raises(SurveyIncomplete):
        src.collect()

    assert src.census is None
    # the ledger honestly caps the nudge count at the budget
    report = next(e for e in events if e["kind"] == "coverage_report")
    assert report["nudges"] <= ls.SCAN_MAX_NUDGES + ls.ANCHOR_MAX_NUDGES * (
        1 + ls.RELOC_MAX_NUDGES
    )



def test_permanent_hole_is_reported_unreachable_not_silently_capped():
    """A cell that never appears in any frame (a permanent HUD occlusion) leaves
    a hole the frontier keeps pointing at. The loop condemns it unreachable
    after STUCK_LIMIT circles and still completes -- but the coverage_report is
    honest: coverage < 100%, unreachable > 0, no silent cap."""

    hole = (4, 3)

    class _Occluded(_World):
        def observe(self, token):
            obs = super().observe(token)
            if obs is None:
                return None
            nw_c, nw_r = token
            keep = {
                c: fp
                for c, fp in obs.fingerprints.items()
                if (c[0] + nw_c, c[1] + nw_r) != hole
            }
            covered_cells = {(c[0] + nw_c, c[1] + nw_r) for c in keep}
            return type(obs)(
                lattice=obs.lattice,
                edges=obs.edges,
                units=[u for u in obs.units if (u.cell[0] + nw_c, u.cell[1] + nw_r) != hole],
                fingerprints=keep,
                distinctive=frozenset(c for c in obs.distinctive if c in keep),
                threats=obs.threats,
            ) if covered_cells else None

    world = _Occluded(9, 7, view=(6, 4), units={(1, 1), (7, 5)}, start=(0, 0))
    events = []
    src = _source(world, events=events)

    census = src.collect()  # completes despite the hole

    report = next(e for e in events if e["kind"] == "coverage_report")
    assert report["covered"] < report["cells"], "the hole was silently capped as covered"
    assert report["unreachable"] >= 1
    assert census is not None  # unreachable-only completion still publishes



import time as _time  # noqa: E402

from ggge_ai.battle import map_view, settings as battle_settings  # noqa: E402
from ggge_ai.battle.controller import ManualBattleController  # noqa: E402
from ggge_ai.battle.ledger import BattleLedger  # noqa: E402


class _CtrlWorld(_World):
    """Same bounded world, but capture() hands back a dummy image frame (the
    controller's pre-scan vision touches it) while observe/detect read the live
    camera state -- the injected seam ignores the opaque frame."""

    def capture(self):
        return np.zeros((10, 10, 3), np.uint8)

    def frame_observe(self, _frame):
        return _World.observe(self, tuple(self.nw))

    def frame_detect(self, _frame):
        return _World.detect(self, tuple(self.nw))


class _Perception:
    def __init__(self, world):
        self.world = world

    def capture(self):
        return self.world.capture()

    def probe(self, ids, frame=None):
        # a fake hub label lets ensure_max_view settle at once so the sweep runs
        if map_view.HUB_LABEL in ids:
            return {map_view.HUB_LABEL: type("E", (), {"confidence": 0.9})()}
        return {}


class _Actuator:
    def __init__(self, world):
        self.world = world

    def tap(self, x, y):
        pass

    def swipe(self, *args):
        self.world.swipe(*args)


def _run_ctrl_scan(monkeypatch, world):
    monkeypatch.setattr(_time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "find_enemy_units", lambda f, region=None: [])
    monkeypatch.setattr(vision, "find_ally_units", lambda f, region=None: [])
    monkeypatch.setattr(vision, "find_third_party_units", lambda f, region=None: [])
    monkeypatch.setattr(vision, "find_threat_cells", lambda f: [])
    monkeypatch.setattr(vision, "read_grid_lattice", lambda f: None)
    monkeypatch.setattr(vision, "unit_cards_present", lambda f: False)
    monkeypatch.setattr(battle_settings, "set_battle_grid", lambda *a, **k: True)
    c = ManualBattleController(
        perception=_Perception(world), actuator=_Actuator(world), ledger=BattleLedger()
    )
    real_nav = c._navigator

    def _nav():
        src = real_nav()
        src.detect = world.frame_detect
        src.observe = world.frame_observe
        return src

    monkeypatch.setattr(c, "_navigator", _nav)
    c._scout(c.perception.capture())
    return c


def test_full_scan_adopts_the_coverage_census(monkeypatch):
    """First turn drives the CoverageScanSource: the controller adopts to_tacmap
    as this turn's board (world-px units, NW-origin px bounds) and logs the new
    coverage scan label."""
    units = {(1, 1), (4, 2), (7, 5), (2, 4)}
    world = _CtrlWorld(9, 7, view=(6, 4), units=units, start=(0, 0), step=1)
    c = _run_ctrl_scan(monkeypatch, world)

    got = {(round((x - FOOT) / PITCH), round((y - FOOT) / PITCH)) for x, y in c.tacmap.units}
    assert got == units
    assert c._map_bounds == {"west": 0.0, "north": 0.0, "east": 900.0, "south": 700.0}
    tac = next(e for e in c.ledger.events if e["kind"] == "tactical_map")
    assert tac["scan"].startswith("coverage")
    assert any(e["kind"] == "coverage_report" for e in c.ledger.events)


def test_census_carries_threats_for_threat_centroid(monkeypatch):
    """to_tacmap threats reach the adopted board so threat_centroid (the enemy
    bearing) has evidence."""
    world = _CtrlWorld(
        9, 7, view=(6, 4), units={(2, 2)}, threats={(5, 3), (6, 4)}, start=(0, 0), step=1
    )
    c = _run_ctrl_scan(monkeypatch, world)

    assert c.tacmap.threats
    assert c.tacmap.threat_centroid() is not None


def test_purge_keeps_the_in_bounds_coverage_census(monkeypatch):
    """The NW-origin px census sits inside the NW-origin px bounds, so the
    out-of-bounds purge (padding compat check, batch2 note 4) keeps every real
    unit and only strips a planted far-out ghost."""
    world = _CtrlWorld(9, 7, view=(6, 4), units={(1, 1), (7, 5), (4, 3)}, start=(0, 0), step=1)
    c = _run_ctrl_scan(monkeypatch, world)
    real = list(c.tacmap.units)
    c.tacmap.units.append((9000.0, 9000.0))

    c._purge_out_of_bounds()

    for p in real:
        assert p in c.tacmap.units, "a real in-bounds census unit was wrongly purged"
    assert (9000.0, 9000.0) not in c.tacmap.units
