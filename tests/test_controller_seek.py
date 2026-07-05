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


def test_on_screen_enemy_arc_is_not_a_seek_source(monkeypatch):
    # a red arc on the current frame must never become the move target;
    # with an empty map and no scouted heading we stand by instead
    monkeypatch.setattr(vision, "find_enemy_units", lambda *a, **k: [(1170, 601)])
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
