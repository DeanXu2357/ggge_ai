"""LiveScanSource (#26 批3a): the live serpentine walk behind the
FrameSource seam. The harness simulates a bounded world exactly like
test_serpentine_scan does -- swipes move a clamped virtual camera,
measure_camera_shift reports the movement that actually happened -- and
the assertions target the seam's contract: an anchored MapFrame series
whose hints and measured shifts satisfy the integrate() arbitration
gates, with bounds and anchoring verdict readable on the source."""

import numpy as np

from ggge_ai.battle import vision
from ggge_ai.battle import live_scan as live_scan_mod
from ggge_ai.battle.live_scan import (
    PAN_CENTER,
    SCAN_MAX_LEGS,
    LiveScanSource,
)
from ggge_ai.battle.map_grid import _pixel_matches_hint

VIEW_W, VIEW_H = 2340, 1080


class _World:
    def __init__(self, max_x, max_y, start, units):
        self.max = (max_x, max_y)
        self.camera = start
        self.units = units
        self.moves = []
        self.frame_cameras = {}

    def swipe(self, x1, y1, x2, y2, *a):
        requested = (x1 - x2, y1 - y2)
        nx = min(max(self.camera[0] + requested[0], 0), self.max[0])
        ny = min(max(self.camera[1] + requested[1], 0), self.max[1])
        self.moves.append(((nx - self.camera[0]), (ny - self.camera[1])))
        self.camera = (nx, ny)

    def capture(self):
        frame = np.zeros((10, 10, 3), np.uint8)
        self.frame_cameras[id(frame)] = self.camera
        return frame

    def shift(self, prev, cur):
        a = self.frame_cameras.get(id(prev), self.camera)
        b = self.frame_cameras.get(id(cur), self.camera)
        return (b[0] - a[0], b[1] - a[1]), 1.0

    def visible_units(self, frame, region=None):
        cx, cy = self.frame_cameras.get(id(frame), self.camera)
        return [
            (int(x - cx), int(y - cy))
            for x, y in self.units
            if 0 <= x - cx < VIEW_W and 0 <= y - cy < VIEW_H
        ]


def _source(world, taps=None, events=None):
    return LiveScanSource(
        capture=world.capture,
        swipe=world.swipe,
        tap=lambda x, y: (taps.append((x, y)) if taps is not None else None),
        ledger_log=(
            (lambda kind, **data: events.append({"kind": kind, **data}))
            if events is not None
            else None
        ),
        sleep=lambda s: None,
    )


def _wire(monkeypatch, world):
    monkeypatch.setattr(vision, "measure_camera_shift", world.shift)
    monkeypatch.setattr(vision, "find_enemy_units", world.visible_units)
    monkeypatch.setattr(vision, "find_ally_units", lambda f, region=None: [])
    monkeypatch.setattr(vision, "find_third_party_units", lambda f, region=None: [])
    monkeypatch.setattr(vision, "find_threat_cells", lambda f: [])
    monkeypatch.setattr(vision, "is_unit_detail_modal", lambda f: False)


def test_collect_emits_anchored_series_covering_the_map(monkeypatch):
    world = _World(
        max_x=1800,
        max_y=900,
        start=(900, 450),
        units=[(50, 40), (3600, 60), (80, 1900), (4000, 1950), (2000, 1000)],
    )
    _wire(monkeypatch, world)
    events = []
    src = _source(world, events=events)

    frames = src.collect()

    assert src.corner_anchored
    assert src.bounds == {"west": 0.0, "north": 0.0, "east": 1800, "south": 900}
    assert any(e["kind"] == "map_bounds" for e in events)
    assert frames[0].label == "corner"
    assert frames[0].hint is None and frames[0].measured_shift is None
    for f in frames[1:]:
        assert f.label in ("row", "south_step")
        assert f.hint in ("right", "left", "down")
        assert f.measured_shift is not None
    cameras = [world.frame_cameras[id(f.image)] for f in frames]
    xs = [c[0] for c in cameras]
    ys = [c[1] for c in cameras]
    assert min(xs) == 0 and min(ys) == 0, "series does not include the NW corner"
    assert max(xs) == 1800, "series never reached the east edge"
    assert max(ys) == 900, "series never reached the south edge"


def test_measured_shifts_are_negated_camera_deltas(monkeypatch):
    world = _World(max_x=1800, max_y=900, start=(900, 450), units=[(2000, 1000)])
    _wire(monkeypatch, world)
    src = _source(world)

    frames = src.collect()

    cameras = [world.frame_cameras[id(f.image)] for f in frames]
    for prev, cur, frame in zip(cameras, cameras[1:], frames[1:]):
        delta = (cur[0] - prev[0], cur[1] - prev[1])
        assert frame.measured_shift == (-delta[0], -delta[1])


def test_full_travel_shifts_pass_the_hint_gate(monkeypatch):
    """Frames that actually travelled must clear integrate()'s hint
    arbitration; edge-clamped legs may fall below the gate's minimum
    travel, which the arbitration treats as a skipped channel, not an
    error."""
    world = _World(max_x=1800, max_y=900, start=(900, 450), units=[(2000, 1000)])
    _wire(monkeypatch, world)
    src = _source(world)

    frames = src.collect()

    travelled = [
        f
        for f in frames[1:]
        if abs(f.measured_shift[0]) + abs(f.measured_shift[1]) >= 300
    ]
    assert travelled, "no frame recorded meaningful travel"
    for f in travelled:
        assert _pixel_matches_hint(f.measured_shift, f.hint), (
            f.hint,
            f.measured_shift,
        )


def test_eaten_swipe_retries_from_alternate_origin(monkeypatch):
    world = _World(max_x=1800, max_y=900, start=(900, 450), units=[(2000, 1000)])
    dead = PAN_CENTER
    original = world.swipe

    def swipe(x1, y1, x2, y2, *a):
        if ((x1 + x2) // 2, (y1 + y2) // 2) == dead:
            world.moves.append((0.0, 0.0))
            return
        original(x1, y1, x2, y2, *a)

    world.swipe = swipe
    _wire(monkeypatch, world)
    events = []
    src = _source(world, events=events)

    frames = src.collect()

    cameras = [world.frame_cameras[id(f.image)] for f in frames]
    xs = [c[0] for c in cameras]
    ys = [c[1] for c in cameras]
    assert min(xs) == 0 and max(xs) == 1800, "coverage lost to the dead origin"
    assert min(ys) == 0 and max(ys) == 900
    legs = [e for e in events if e["kind"] == "scan_leg"]
    assert any(len(e["attempts"]) > 1 for e in legs), "no leg ever retried"


def test_leg_budget_bounds_a_huge_map(monkeypatch):
    world = _World(max_x=50000, max_y=50000, start=(25000, 25000), units=[])
    _wire(monkeypatch, world)
    src = _source(world)

    frames = src.collect()

    assert len(world.moves) <= SCAN_MAX_LEGS
    assert not src.corner_anchored
    assert src.bounds is None
    assert frames and frames[0].label == "start"


def test_stray_modal_is_closed_during_the_walk(monkeypatch):
    world = _World(max_x=1800, max_y=900, start=(900, 450), units=[])
    _wire(monkeypatch, world)
    hits = iter([True])
    monkeypatch.setattr(
        vision, "is_unit_detail_modal", lambda f: next(hits, False)
    )
    taps, events = [], []
    src = _source(world, taps=taps, events=events)

    src.collect()

    assert live_scan_mod.UNIT_DETAIL_CLOSE in taps
    assert any(e["kind"] == "scan_modal_closed" for e in events)


def test_pan_leg_rejects_a_reverse_direction_landmark_lock(monkeypatch):
    """20260720-232808 corner_west requested (-600, 0) and pool.locate
    handed back a lock implying (+186, +41) -- a star-field alias whose
    main-axis motion points backwards, small enough to clear the
    travel-distance bound but wrong on direction. The gate must reject it
    and fall through to the phase channel instead of adopting the false
    lock, while still recording the rejection on the attempt."""
    world = _World(max_x=1800, max_y=900, start=(900, 450), units=[(2000, 1000)])
    _wire(monkeypatch, world)
    monkeypatch.setattr(vision, "find_enemy_units", lambda f, region=None: [(500, 500)])
    events = []
    src = _source(world, events=events)
    monkeypatch.setattr(src.pool, "locate", lambda visible: (186.0, 41.0))
    prev = world.capture()

    camera, _frame, actual, requested = src.pan_leg((0.0, 0.0), prev, (-1, 0), label="corner_west")

    assert requested == (-600, 0)
    # the false lock (186, 41) must not be adopted; the phase channel's
    # real measurement of the westward swipe wins instead
    assert actual == (-600.0, 0.0)
    assert camera == (-600.0, 0.0)
    legs = [e for e in events if e["kind"] == "scan_leg"]
    assert len(legs) == 1
    assert legs[0]["measured"] == [-600.0, 0.0]
    attempt = legs[0]["attempts"][0]
    assert "landmarks_rejected" in attempt["source"]
    assert attempt["cumulative"] == [-600.0, 0.0]
