"""Corner-start serpentine full-map scan (tacmap v2): the first scan of a
battle must sync every unit on the map into the backend, not just the
neighborhood of the hub view.

The harness simulates a bounded world: swipes move a virtual camera that
clamps at the map edges, measure_camera_shift reports the movement that
actually happened, and the unit finders return whichever world units fall
inside the current view.
"""

import numpy as np

from ggge_ai.battle import controller as controller_mod
from ggge_ai.battle import vision
from ggge_ai.battle.controller import ManualBattleController
from ggge_ai.battle.ledger import BattleLedger

VIEW_W, VIEW_H = 2340, 1080


class _World:
    """Camera clamped to [0, max_x] x [0, max_y] in world coordinates;
    the scan starts wherever the hub camera happens to sit."""

    def __init__(self, max_x, max_y, start, enemies):
        self.max = (max_x, max_y)
        self.camera = start
        self.enemies = enemies
        self.moves = []
        self.observed_cameras = []

    def swipe(self, x1, y1, x2, y2, *a):
        requested = (x1 - x2, y1 - y2)
        nx = min(max(self.camera[0] + requested[0], 0), self.max[0])
        ny = min(max(self.camera[1] + requested[1], 0), self.max[1])
        self.moves.append(((nx - self.camera[0]), (ny - self.camera[1])))
        self.camera = (nx, ny)

    def shift(self, prev, cur):
        return (self.moves[-1] if self.moves else (0.0, 0.0)), 1.0

    def visible_enemies(self, frame, region=None):
        cx, cy = self.camera
        return [
            (int(x - cx), int(y - cy))
            for x, y in self.enemies
            if 0 <= x - cx < VIEW_W and 0 <= y - cy < VIEW_H
        ]


class _Perception:
    def capture(self):
        return np.zeros((10, 10, 3), np.uint8)

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
        perception=_Perception(), actuator=_Actuator(world), ledger=BattleLedger()
    )
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "measure_camera_shift", world.shift)
    monkeypatch.setattr(vision, "find_enemy_units", world.visible_enemies)
    monkeypatch.setattr(vision, "find_ally_units", lambda f, region=None: [])
    monkeypatch.setattr(vision, "find_third_party_units", lambda f, region=None: [])
    monkeypatch.setattr(vision, "find_threat_cells", lambda f: [])

    original = c._observe_map

    def observing(frame, camera):
        world.observed_cameras.append(world.camera)
        original(frame, camera)

    c._observe_map = observing
    c._scout(c.perception.capture())
    return c


def test_first_scan_reaches_all_corners_and_syncs_every_unit(monkeypatch):
    world = _World(
        max_x=1800,
        max_y=900,
        start=(900, 450),
        enemies=[(50, 40), (3600, 60), (80, 1900), (4000, 1950), (2000, 1000)],
    )
    c = _run_scan(monkeypatch, world)

    xs = [p[0] for p in world.observed_cameras]
    ys = [p[1] for p in world.observed_cameras]
    assert min(xs) == 0 and min(ys) == 0, "scan never reached the NW corner"
    assert max(xs) == 1800, "scan never reached the east edge"
    assert max(ys) == 900, "scan never reached the south edge"
    assert len(c.tacmap.enemies) == len(world.enemies), (
        f"synced {len(c.tacmap.enemies)} of {len(world.enemies)} units: "
        f"{c.tacmap.enemies}"
    )
    tac = next(e for e in c.ledger.events if e["kind"] == "tactical_map")
    assert tac["scan"].startswith("serpentine")


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
    assert len(world.moves) <= controller_mod.SCAN_MAX_LEGS


def test_eaten_swipe_retries_from_alternate_origin(monkeypatch):
    """A swipe whose start point sits on a unit gets eaten by the game and
    reads exactly like an edge (zero shift, healthy response) -- the leg
    must retry from the alternate origins before accepting the verdict
    (the 20260719 star-map row legs)."""
    world = _World(max_x=1800, max_y=900, start=(900, 450), enemies=[(2000, 1000)])
    dead = controller_mod.PAN_CENTER
    original = world.swipe

    def swipe(x1, y1, x2, y2, *a):
        if ((x1 + x2) // 2, (y1 + y2) // 2) == dead:
            world.moves.append((0.0, 0.0))
            return
        original(x1, y1, x2, y2, *a)

    world.swipe = swipe
    c = _run_scan(monkeypatch, world)

    xs = [p[0] for p in world.observed_cameras]
    ys = [p[1] for p in world.observed_cameras]
    assert min(xs) == 0 and max(xs) == 1800, "coverage lost to the dead origin"
    assert min(ys) == 0 and max(ys) == 900
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
