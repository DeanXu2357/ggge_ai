"""Controller-side full-map scan integration (the LiveScanSource walk's
pool adopted as the turn's census) plus the bounds purge and the cheap
local scan. The walk's own mechanics -- corner coverage, budget, eaten
swipes, shift/hint contract -- live in test_live_scan.py; here the
harness checks what the CONTROLLER does with the walk: pool adoption,
bounds, ledger events, ghost purge and the local-scan path."""

import numpy as np

from ggge_ai.battle import vision
from ggge_ai.battle import live_scan as live_scan_mod
from ggge_ai.battle.controller import ManualBattleController
from ggge_ai.battle.ledger import BattleLedger

VIEW_W, VIEW_H = 2340, 1080


class _World:
    def __init__(self, max_x, max_y, start, enemies):
        self.max = (max_x, max_y)
        self.camera = start
        self.enemies = enemies
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

    def visible_enemies(self, frame, region=None):
        cx, cy = self.frame_cameras.get(id(frame), self.camera)
        return [
            (int(x - cx), int(y - cy))
            for x, y in self.enemies
            if 0 <= x - cx < VIEW_W and 0 <= y - cy < VIEW_H
        ]


class _Perception:
    def __init__(self, world):
        self.world = world

    def capture(self):
        return self.world.capture()

    def probe(self, ids):
        return {}


class _Actuator:
    def __init__(self, world):
        self.world = world

    def tap(self, x, y):
        pass

    def swipe(self, *args):
        self.world.swipe(*args)


def _run_scan(monkeypatch, world):
    c = ManualBattleController(
        perception=_Perception(world), actuator=_Actuator(world), ledger=BattleLedger()
    )
    monkeypatch.setattr(live_scan_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "measure_camera_shift", world.shift)
    monkeypatch.setattr(vision, "find_enemy_units", world.visible_enemies)
    monkeypatch.setattr(vision, "find_ally_units", lambda f, region=None: [])
    monkeypatch.setattr(vision, "find_third_party_units", lambda f, region=None: [])
    monkeypatch.setattr(vision, "find_threat_cells", lambda f: [])
    monkeypatch.setattr(vision, "is_unit_detail_modal", lambda f: False)
    c._scout(c.perception.capture())
    return c


def test_first_scan_adopts_the_walk_pool_and_bounds(monkeypatch):
    world = _World(
        max_x=1800,
        max_y=900,
        start=(900, 450),
        enemies=[(50, 40), (3600, 60), (80, 1900), (4000, 1950), (2000, 1000)],
    )
    c = _run_scan(monkeypatch, world)

    assert len(c.tacmap.units) == len(world.enemies), (
        f"synced {len(c.tacmap.units)} of {len(world.enemies)} units: "
        f"{c.tacmap.units}"
    )
    # the harness world happens to share the corner frame, so unit world
    # coordinates come out exact, not merely deduplicated
    assert sorted(c.tacmap.units) == sorted(
        (float(x), float(y)) for x, y in world.enemies
    )
    tac = next(e for e in c.ledger.events if e["kind"] == "tactical_map")
    assert tac["scan"].startswith("serpentine")
    assert c._map_bounds == {"west": 0.0, "north": 0.0, "east": 1800, "south": 900}
    assert any(e["kind"] == "map_bounds" for e in c.ledger.events)
    assert any(e["kind"] == "scan_leg" for e in c.ledger.events)


def test_out_of_bounds_ghosts_are_purged(monkeypatch):
    world = _World(
        max_x=1800,
        max_y=900,
        start=(900, 450),
        enemies=[(2000, 1000), (500, 500), (3000, 800)],
    )
    c = _run_scan(monkeypatch, world)
    c.tacmap.units.append((6000.0, 400.0))
    c.tacmap.units.append((-900.0, 200.0))

    c._purge_out_of_bounds()

    assert (6000.0, 400.0) not in c.tacmap.units
    assert (-900.0, 200.0) not in c.tacmap.units
    assert (2000.0, 1000.0) in c.tacmap.units
    outliers = [e for e in c.ledger.events if e["kind"] == "scan_outlier"]
    assert len(outliers) == 1
    assert len(outliers[0]["points"]) == 2


def test_purge_fuse_refuses_to_erase_most_of_the_board(monkeypatch):
    """Bounds that would delete over half the board are themselves the
    error (a mis-anchored corner) -- run 9 erased 10 of 11 real units."""
    world = _World(max_x=1800, max_y=900, start=(900, 450), enemies=[(2000, 1000)])
    c = _run_scan(monkeypatch, world)
    c.tacmap.units.append((6000.0, 400.0))
    c.tacmap.units.append((-900.0, 200.0))

    c._purge_out_of_bounds()

    assert (6000.0, 400.0) in c.tacmap.units
    assert (-900.0, 200.0) in c.tacmap.units
    assert any(e["kind"] == "scan_outlier_skipped" for e in c.ledger.events)


def test_second_turn_uses_the_cheap_local_scan(monkeypatch):
    world = _World(max_x=1800, max_y=900, start=(900, 450), enemies=[])
    c = _run_scan(monkeypatch, world)
    legs_full = len(world.moves)

    c.timeline.mark_pending("scout")
    world.moves.clear()
    c._scout(c.perception.capture())

    tac = [e for e in c.ledger.events if e["kind"] == "tactical_map"]
    assert tac[-1]["scan"] == "local"
    assert len(world.moves) == 8
    assert legs_full > 8


def test_leg_budget_bounds_a_huge_map(monkeypatch):
    world = _World(max_x=50000, max_y=50000, start=(25000, 25000), enemies=[])
    _run_scan(monkeypatch, world)
    assert len(world.moves) <= live_scan_mod.SCAN_MAX_LEGS


def test_eaten_swipe_retries_from_alternate_origin(monkeypatch):
    """A swipe whose start point sits on a unit gets eaten by the game and
    reads exactly like an edge (zero shift, healthy response) -- the leg
    must retry from the alternate origins before accepting the verdict
    (the 20260719 star-map row legs)."""
    world = _World(max_x=1800, max_y=900, start=(900, 450), enemies=[(2000, 1000)])
    dead = live_scan_mod.PAN_CENTER
    original = world.swipe

    def swipe(x1, y1, x2, y2, *a):
        if ((x1 + x2) // 2, (y1 + y2) // 2) == dead:
            world.moves.append((0.0, 0.0))
            return
        original(x1, y1, x2, y2, *a)

    world.swipe = swipe
    c = _run_scan(monkeypatch, world)

    assert sorted(c.tacmap.units) == [(2000.0, 1000.0)], "coverage lost to the dead origin"
    legs = [e for e in c.ledger.events if e["kind"] == "scan_leg"]
    assert any(len(e["attempts"]) > 1 for e in legs), "no leg ever retried"


def test_arc_shift_consensus_fallback():
    a_arcs = [(100, 100), (400, 200), (800, 500)]
    shift = (150.0, -60.0)
    b_arcs = [(int(x - shift[0]), int(y - shift[1])) for x, y in a_arcs]
    f_a, f_b = object(), object()
    frames = {id(f_a): a_arcs, id(f_b): b_arcs}
    import unittest.mock as mock

    with mock.patch.object(vision, "find_enemy_units", lambda f, region=None: frames[id(f)]), \
         mock.patch.object(vision, "find_ally_units", lambda f, region=None: []), \
         mock.patch.object(vision, "find_third_party_units", lambda f, region=None: []):
        assert vision.measure_arc_shift(f_a, f_b) == (150.0, -60.0)
        # a lone arc cannot form a consensus
        frames[id(f_b)] = b_arcs[:1]
        assert vision.measure_arc_shift(f_a, f_b) is None
        # two equally-supported translations = ambiguity, never a guess
        frames[id(f_a)] = [(0, 0), (100, 0), (1000, 0), (1100, 0)]
        frames[id(f_b)] = [(50, 0), (150, 0)]
        assert vision.measure_arc_shift(f_a, f_b) is None
