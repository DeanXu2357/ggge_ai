import numpy as np

from ggge_ai.battle import vision
from ggge_ai.battle.controller import ManualBattleController
from ggge_ai.battle.tacmap import TacticalMap


def _controller(tacmap: TacticalMap, hint=None) -> ManualBattleController:
    c = ManualBattleController(perception=object(), actuator=object())
    c.tacmap = tacmap
    c._enemy_hint = hint
    return c


def _blank():
    return np.zeros((1080, 2340, 3), np.uint8)


def test_scout_hint_drives_heading_when_anchor_fails():
    tm = TacticalMap()
    # two far-apart allies make the anchor refuse without corroboration
    tm.observe((0, 0), enemies=[(2000, 500)], allies=[(100, 100), (2000, 900)])
    cells = [(1100, 500), (1200, 500), (1150, 600)]
    c = _controller(tm, hint=(1.0, 0.0))

    target, basis = c._seek_move_target(_blank(), cells)

    assert basis == "scout_hint"
    origin = vision.centroid(cells)
    assert target[0] > origin[0] + 1000 and abs(target[1] - origin[1]) < 1


def test_on_screen_enemy_picks_nearest_and_excludes_self(monkeypatch):
    # arcs: one near the unit (its own residual arc) and two real enemies at
    # different distances -- the nearest real enemy wins, the self arc is
    # excluded even though it is closest
    monkeypatch.setattr(
        vision,
        "find_enemy_units",
        lambda *a, **k: [(1180, 590), (900, 400), (300, 300)],
    )
    c = _controller(TacticalMap(), hint=None)
    cells = [(1150, 540), (1200, 540), (1175, 600)]

    target, basis = c._seek_move_target(_blank(), cells)

    assert basis == "enemy_onscreen"
    assert round(target[0]) == 900 and round(target[1]) == 400


def test_on_screen_enemy_preferred_over_scout_hint(monkeypatch):
    # even with a scouted heading available, a visible enemy takes priority
    # so each unit steers toward its own closest enemy, not the force heading
    monkeypatch.setattr(vision, "find_enemy_units", lambda *a, **k: [(600, 300)])
    c = _controller(TacticalMap(), hint=(1.0, 0.0))
    cells = [(1150, 540), (1200, 540)]

    target, basis = c._seek_move_target(_blank(), cells)

    assert basis == "enemy_onscreen"
    assert round(target[0]) == 600 and round(target[1]) == 300


def test_only_self_arc_on_screen_falls_back_to_hint(monkeypatch):
    # if the only red arc is the unit's own (within SELF_ARC_RADIUS), it is
    # excluded and seeking falls back to the scouted heading
    monkeypatch.setattr(vision, "find_enemy_units", lambda *a, **k: [(1180, 560)])
    c = _controller(TacticalMap(), hint=(1.0, 0.0))
    cells = [(1150, 540), (1200, 540)]

    target, basis = c._seek_move_target(_blank(), cells)

    assert basis == "scout_hint"


def test_no_on_screen_enemy_falls_back_to_stand_by(monkeypatch):
    # with no visible enemy, an empty map and no scouted heading we stand by
    monkeypatch.setattr(vision, "find_enemy_units", lambda *a, **k: [])
    monkeypatch.setattr(vision, "find_threat_cells", lambda *a, **k: [])
    c = _controller(TacticalMap(), hint=None)

    target, basis = c._seek_move_target(_blank(), [(1150, 540), (1200, 540)])

    assert target is None and basis is None


def test_tacmap_anchor_target_preferred_when_available(monkeypatch):
    tm = TacticalMap()
    tm.observe((0, 0), enemies=[(300, 400)], allies=[(100, 100), (500, 100)])
    cells = [(30, 50), (70, 50), (50, 50)]  # move range centered on the unit (50, 50)
    c = _controller(tm, hint=(1.0, 0.0))
    monkeypatch.setattr(vision, "find_ally_units", lambda *a, **k: [(50, 50), (450, 50), (250, 350)])
    monkeypatch.setattr(vision, "find_enemy_units", lambda *a, **k: [])
    monkeypatch.setattr(vision, "find_third_party_units", lambda *a, **k: [])

    target, basis = c._seek_move_target(_blank(), cells)

    assert basis == "tacmap"
    assert round(target[0]) == 250 and round(target[1]) == 350
