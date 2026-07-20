import numpy as np

from ggge_ai.battle.tacmap import TacticalMap
from ggge_ai.battle.vision import measure_camera_shift


def test_measure_camera_shift_recovers_synthetic_pan():
    rng = np.random.default_rng(7)
    prev = rng.integers(0, 255, size=(600, 900, 3), dtype=np.uint8)
    cur = np.roll(prev, shift=(-11, 23), axis=(0, 1))

    (dx, dy), response = measure_camera_shift(prev, cur, region=(0, 0, 900, 600))

    assert response > 0.5
    assert round(dx) == -23
    assert round(dy) == 11


def test_observe_merges_across_views():
    tm = TacticalMap()
    tm.observe((0, 0), [(1000, 500), (300, 400)])
    tm.observe((600, 0), [(410, 495)])

    merged = [p for p in tm.units if abs(p[0] - 1005) < 10 and abs(p[1] - 498) < 10]
    assert len(tm.units) == 2 and len(merged) == 1
    assert tm.nearest_unit((1200, 500)) == merged[0]


def test_observe_keeps_threats_separate():
    tm = TacticalMap()
    tm.observe((0, 0), [(300, 400)], threats=[(700, 200)])

    assert tm.units == [(300.0, 400.0)]
    assert tm.threats == [(700.0, 200.0)]
    assert tm.threat_centroid() == (700.0, 200.0)


def test_anchor_recovers_camera_jump():
    tm = TacticalMap()
    tm.observe((0, 0), [(300, 400), (100, 100), (500, 100)])

    visible = [(50, 50), (450, 50), (250, 350)]
    t = tm.anchor((50, 50), visible)

    assert t is not None
    assert round(t[0]) == 50 and round(t[1]) == 50

    unit = tm.nearest_unit((250 + t[0], 350 + t[1]))
    assert unit == (300, 400)


def test_anchor_refuses_ambiguous_single_arc():
    tm = TacticalMap()
    tm.observe((0, 0), [(100, 100), (900, 100)])

    assert tm.anchor((50, 50), [(50, 50)]) is None


def test_locate_recovers_camera_without_a_selection():
    tm = TacticalMap()
    tm.observe((0, 0), [(300, 400), (600, 400), (100, 100)])

    t = tm.locate([(250, 350), (550, 350), (50, 50)])

    assert t is not None
    assert round(t[0]) == 50 and round(t[1]) == 50


def test_locate_refuses_a_single_coincidence():
    tm = TacticalMap()
    tm.observe((0, 0), [(300, 400), (100, 100)])

    assert tm.locate([(250, 350)]) is None
