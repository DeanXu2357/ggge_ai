"""Round 1.10: the anchor-evidence gate + the anchor-phase brake, driven against
the synthetic malicious world reused from test_coverage_scan.

輪十 crashed a brand-new way: the camera was parked in the empty north-east void
(0 units, uniform starfield, only the east+north cut-off edges), the scan
anchored on it, and every later frame refused to localise against a reference
with no unit constellation and no distinctive terrain -- 98 nudges, every
recovery exhausted, margin=null forever. Two guards, both provable offline:

1. The anchor-evidence gate refuses to anchor on that void. When the start view
   carries no localisation evidence it seeks toward the map interior, steered by
   the visible cut-off edges (see the east edge -> go west, see north -> go
   south), until a localisable frame appears; the budget spent without one fails
   loud ("anchor without units") rather than stranding.

2. The anchor-phase brake stops the drive to the NW corner starving on a camera
   that will not re-anchor: K consecutive refused corner pushes whose recovery
   cannot relocate fails loud instead of burning ANCHOR_MAX_NUDGES x
   RELOC_MAX_NUDGES.

Each is proved red-then-green by disabling exactly the new guard (the idiom the
sibling residue/starve tests already use). The 0-unit-but-distinctive frame (the
輪七/輪八 starving worlds, the north==south inconsistency frame) is NOT diverted --
it localises on terrain alone -- so the whole existing test_coverage_scan* suite
stays green untouched; a units-present start (輪九型) skips the gate entirely.
"""

from __future__ import annotations

import numpy as np
import pytest

from ggge_ai.battle import live_scan as ls
from ggge_ai.battle import vision
from ggge_ai.battle.coverage_map import SIDES, FrameObservation
from ggge_ai.battle.live_scan import (
    ANCHOR_MAX_NUDGES,
    RELOC_MAX_NUDGES,
    STARVE_LIMIT,
    CoverageScanSource,
)
from ggge_ai.battle.scout_intel import SurveyIncomplete
from ggge_ai.battle.vision import MapLattice
from tests.test_coverage_scan import PITCH, _found_cells, _source, _World


@pytest.fixture(autouse=True)
def _no_obstruction(monkeypatch):
    # the synthetic worlds hand back opaque tokens; keep both obstruction probes
    # off them (mirrors the sibling coverage-scan fixtures)
    monkeypatch.setattr(vision, "is_unit_detail_modal", lambda f: False)
    monkeypatch.setattr(vision, "enemy_selection_active", lambda f: False)


# --- 1. anchor-evidence gate: seek out of the void, converge ----------------


class _VoidStartWorld(_World):
    """輪十 shape: the camera is parked in a uniform-starfield void that shows 0
    units and no distinctive terrain, carrying only the east/north cut-off edges
    the corner exposes. Two ways to place the void model two facets of the same
    real failure a single synthetic world cannot hold at once:

    - `void_frames`: the first N observations are flat, then the world is its
      normal distinctive self. This models the parked camera without poisoning any
      map edge, so a scan that SEEKS out of the void (evidence gate) anchors on
      distinctive terrain and converges on every unit. (A clean synthetic edge-pin
      lets a scan that anchors ON such a short void recover, so it cannot also
      show stranding -- that is the other facet.)
    - `void_positions`: the listed camera positions are permanently flat. A scan
      that anchors ON the void is trapped: its flat reference can only edge-pin
      back into the same corner (no constellation, no distinctive terrain to
      re-localise a frame elsewhere), so it strands -- the pre-gate failure. (The
      permanent corner blocks the fill loop's outward frontier, so this facet
      cannot also show full convergence.)"""

    def __init__(self, *a, void_frames: int = 0, void_positions=(), **kw):
        super().__init__(*a, **kw)
        self._void_frames = void_frames
        self._void_positions = {tuple(p) for p in void_positions}
        self._obs_n = 0

    def observe(self, token):
        obs = super().observe(token)
        if obs is None:
            return None
        self._obs_n += 1
        if self._obs_n <= self._void_frames or tuple(token) in self._void_positions:
            flat = {c: np.zeros(4, np.float32) for c in obs.fingerprints}
            return type(obs)(
                lattice=obs.lattice,
                edges=obs.edges,
                units=[],
                fingerprints=flat,
                distinctive=frozenset(),
                threats=[],
            )
        return obs


# the proven-converging constellation from test_converges_and_syncs_every_unit,
# reused so a full census is the expected healthy outcome
_PROVEN_UNITS = {(1, 1), (4, 2), (7, 5), (2, 4), (6, 1), (3, 3)}


def test_zero_unit_start_seeks_south_west_then_converges():
    """後綠: the void start carries no evidence, so the gate seeks toward the map
    interior -- the visible east edge steers west, the north edge steers south --
    reaches the distinctive/units band, anchors, and the scan converges on every
    unit. (Time-boxed void: the seek escapes and the map is otherwise intact.)"""
    world = _VoidStartWorld(
        9, 7, view=(6, 4), units=_PROVEN_UNITS, start=(3, 0), step=1, seed=3,
        void_frames=2,
    )
    events: list[dict] = []
    src = _source(world, events=events)

    census = src.collect()

    seeks = [e for e in events if e["kind"] == "anchor_seek"]
    assert seeks, "the void start never triggered the anchor-evidence gate"
    assert any(e["dir"] == "west" for e in seeks), "the east edge never steered west"
    assert any(e["dir"] == "south" for e in seeks), "the north edge never steered south"
    assert all(e["basis"] == "edge" for e in seeks)  # every step had a visible edge
    assert _found_cells(census) == world.units


def test_old_code_strands_on_the_void_without_the_gate(monkeypatch):
    """先紅: with the gate disabled (anchor straight onto the start frame, the
    pre-輪十 behaviour) a void the scan anchors ON strands -- the flat reference
    can never re-localise a frame outside its corner. The gate above is exactly
    what turns this green by anchoring on evidence instead. (Permanent corner
    void: the failure needs the void to persist, not just the first frames.)"""
    monkeypatch.setattr(
        CoverageScanSource, "_anchor_seek", lambda self, frame, obs: (frame, obs)
    )
    world = _VoidStartWorld(
        9, 7, view=(6, 4), units=_PROVEN_UNITS, start=(3, 0), step=1, seed=3,
        void_positions={(3, 0), (2, 0), (3, 1)},
    )
    events: list[dict] = []
    src = _source(world, events=events)

    with pytest.raises(SurveyIncomplete):
        src.collect()
    assert src.census is None
    assert not any(e["kind"] == "anchor_seek" for e in events)  # gate never ran


# --- 2. anchor-evidence gate: nowhere to anchor, honest loud stop -----------


class _VoidEverywhereWorld(_World):
    """A map with no units and uniform terrain everywhere: every frame is the 輪十
    void. The seek can never find a localisable anchor; it must fail loud within
    the ANCHOR_MAX_NUDGES budget rather than drift-burn the fill budget."""

    def observe(self, token):
        obs = super().observe(token)
        if obs is None:
            return None
        flat = {c: np.zeros(4, np.float32) for c in obs.fingerprints}
        return type(obs)(
            lattice=obs.lattice,
            edges=obs.edges,
            units=[],
            fingerprints=flat,
            distinctive=frozenset(),
            threats=[],
        )


def test_unit_free_map_fails_loud_without_drift_burning():
    """後綠: no unit exists anywhere, so the seek exhausts its budget and stops
    honestly with 'anchor without units' -- it never reaches (let alone burns) the
    fill loop, and publishes no census."""
    world = _VoidEverywhereWorld(40, 40, view=(6, 4), units=set(), start=(0, 0), step=1)
    events: list[dict] = []
    src = _source(world, events=events)

    with pytest.raises(SurveyIncomplete, match="anchor without units"):
        src.collect()

    assert src.census is None
    report = next(e for e in events if e["kind"] == "coverage_report")
    assert report["outcome"] == "anchor_starved"
    # bounded by the seek budget -- no fill-loop drift burn
    assert report["nudges"] <= ANCHOR_MAX_NUDGES


# --- 3. anchor-phase brake: stop starving on the drive to the corner --------


class _CornerNeverReanchors:
    """Anchorable start (distinctive terrain, no edges -> west/north unseen) so the
    gate passes and the map anchors; but every push toward the NW corner lands on
    a fresh uniform region localise refuses, and recovery cannot re-anchor either.
    Without the brake the anchor phase burns ANCHOR_MAX_NUDGES x RELOC_MAX_NUDGES."""

    def __init__(self):
        self.n = 0

    def capture(self):
        return ("frame", self.n)

    def swipe(self, *a):
        self.n += 1

    def detect(self, token):
        return []

    def observe(self, token):
        lat = MapLattice(
            cols=tuple(range(0, 7 * PITCH, PITCH)),
            rows=tuple(range(0, 5 * PITCH, PITCH)),
            col_pitch=float(PITCH),
            row_pitch=float(PITCH),
            edges={s: None for s in SIDES},
        )
        if self.n == 0:
            fps = {
                (c, r): np.array([c * 50.0 + 1.0, r * 50.0 + 1.0, 0.0, 0.0], np.float32)
                for c in range(6)
                for r in range(4)
            }
            return FrameObservation(
                lattice=lat,
                edges={s: None for s in SIDES},
                units=[],
                fingerprints=fps,
                distinctive=frozenset(fps),
                threats=[],
            )
        fps = {(c, r): np.zeros(4, np.float32) for c in range(6) for r in range(4)}
        return FrameObservation(
            lattice=lat,
            edges={s: None for s in SIDES},
            units=[],
            fingerprints=fps,
            distinctive=frozenset(),
            threats=[],
        )


def _corner_source(world, events):
    return CoverageScanSource(
        capture=world.capture,
        swipe=world.swipe,
        tap=lambda x, y: None,
        ledger_log=lambda k, **d: events.append({"kind": k, **d}),
        sleep=lambda s: None,
        detect=world.detect,
        observe=world.observe,
    )


def test_anchor_phase_brakes_at_K_not_full_budget():
    """後綠: the corner never re-anchors, so K consecutive refused pushes with no
    relocation fail loud with 'anchor phase starving' after exactly
    STARVE_LIMIT x (1 + RELOC_MAX_NUDGES) nudges -- not the full anchor budget."""
    world = _CornerNeverReanchors()
    events: list[dict] = []
    src = _corner_source(world, events)

    with pytest.raises(SurveyIncomplete, match="anchor phase starving"):
        src.collect()

    report = next(e for e in events if e["kind"] == "coverage_report")
    assert report["outcome"] == "anchor_phase_starved"
    nudges = sum(1 for e in events if e["kind"] == "nudge")
    assert nudges == STARVE_LIMIT * (1 + RELOC_MAX_NUDGES)


def test_anchor_phase_without_brake_burns_past_the_corner(monkeypatch):
    """先紅: with the brake disarmed (STARVE_LIMIT out of reach) the same corner
    burns all ANCHOR_MAX_NUDGES iterations and spills into the fill loop -- far
    more nudges than the braked stop, the empty burn the brake exists to cut."""
    monkeypatch.setattr(ls, "STARVE_LIMIT", 10**9)
    world = _CornerNeverReanchors()
    events: list[dict] = []
    src = _corner_source(world, events)

    with pytest.raises(SurveyIncomplete):
        src.collect()

    nudges = sum(1 for e in events if e["kind"] == "nudge")
    assert nudges > ANCHOR_MAX_NUDGES * (1 + RELOC_MAX_NUDGES)


# --- 4. units-present start (輪九型) is unchanged ----------------------------


def test_units_present_start_skips_the_gate():
    """A start view with units already visible localises on its own constellation,
    so the gate is a no-op -- no anchor_seek event fires and the scan converges
    exactly as before (輪九型 behaviour preserved)."""
    units = {(1, 1), (4, 2), (7, 5), (2, 4)}
    world = _World(9, 7, view=(6, 4), units=units, start=(0, 0), step=1)
    events: list[dict] = []
    src = _source(world, events=events)

    census = src.collect()

    assert _found_cells(census) == units
    assert not any(e["kind"] == "anchor_seek" for e in events)
