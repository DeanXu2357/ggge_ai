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
    tm.observe((0, 0), enemies=[(1000, 500)], allies=[(300, 400)])
    tm.observe((600, 0), enemies=[(410, 495)], allies=[])

    assert len(tm.enemies) == 1
    ex, ey = tm.enemies[0]
    assert abs(ex - 1005) < 10 and abs(ey - 498) < 10
    assert tm.nearest_enemy((0, 0)) == tm.enemies[0]


def test_anchor_recovers_camera_jump():
    tm = TacticalMap()
    tm.observe(
        (0, 0),
        enemies=[(300, 400)],
        allies=[(100, 100), (500, 100)],
    )

    visible = [(50, 50), (450, 50), (250, 350)]
    t = tm.anchor((50, 50), visible)

    assert t is not None
    assert round(t[0]) == 50 and round(t[1]) == 50

    enemy = tm.nearest_enemy((50 + t[0], 50 + t[1]))
    assert enemy == (300, 400)


def test_anchor_refuses_ambiguous_single_arc():
    tm = TacticalMap()
    tm.observe((0, 0), enemies=[], allies=[(100, 100), (900, 100)])

    assert tm.anchor((50, 50), [(50, 50)]) is None
