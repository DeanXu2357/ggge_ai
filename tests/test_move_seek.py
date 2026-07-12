"""Move-target seeking after the 20260712 diagnosis: threat cells outrank
the poisonable tacmap/scout-hint signals, and a known direction without
extractable move cells becomes a directional map step instead of a standby
(snow maps saturate the white-outline cell mask, so cells came back empty on
every unit of two full battles)."""

from types import SimpleNamespace

import numpy as np

from ggge_ai.battle import controller as controller_mod
from ggge_ai.battle import vision
from ggge_ai.battle.controller import (
    MOVE_STEP_NEAR_PX,
    MOVE_STEP_PX,
    PAN_CENTER,
    ManualBattleController,
)
from ggge_ai.battle.ledger import BattleLedger
from ggge_ai.battle.tacmap import TacticalMap


class _Perception:
    def capture(self):
        return np.zeros((1080, 2340, 3), np.uint8)

    def probe(self, ids):
        return {}


class _Actuator:
    def __init__(self):
        self.taps = []

    def tap(self, x, y):
        self.taps.append((x, y))

    def swipe(self, *args):
        pass


def _controller():
    return ManualBattleController(
        perception=_Perception(), actuator=_Actuator(), ledger=BattleLedger()
    )


def _quiet_vision(monkeypatch, enemies=(), threats=(), allies=()):
    monkeypatch.setattr(vision, "find_enemy_units", lambda f, region=None: list(enemies))
    monkeypatch.setattr(vision, "find_threat_cells", lambda f: list(threats))
    monkeypatch.setattr(vision, "find_ally_units", lambda f, region=None: list(allies))
    monkeypatch.setattr(vision, "find_third_party_units", lambda f, region=None: [])


def test_threat_centroid_outranks_the_tacmap(monkeypatch):
    c = _controller()
    _quiet_vision(monkeypatch, threats=[(1170, 100), (1270, 100)])
    c.tacmap = SimpleNamespace(
        enemies=[(-500.0, 500.0)],
        anchor=lambda origin, arcs: (0.0, 0.0),
        nearest_enemy=lambda p: (-500.0, 500.0),
    )

    target, basis = c._seek_move_target(c.perception.capture(), [(1100, 480)])

    assert basis == "threat_centroid"
    assert target == (1220.0, 100.0)


def test_onscreen_enemy_still_wins_over_threats(monkeypatch):
    c = _controller()
    _quiet_vision(monkeypatch, enemies=[(1600, 200)], threats=[(400, 800)])

    target, basis = c._seek_move_target(c.perception.capture(), [(1100, 480)])

    assert basis == "enemy_onscreen"
    assert target == (1600.0, 200.0)


def test_directional_step_moves_toward_threats_without_cells(monkeypatch):
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    c = _controller()
    c._dispatched_mode = "label_unit_move"
    c._action.tried_in_place = True
    _quiet_vision(monkeypatch, threats=[(1170, 150)])
    monkeypatch.setattr(vision, "find_move_cells", lambda f: [])

    c._on_unit_move()

    x0, y0, w, h = vision.MAP_REGION
    expected = (PAN_CENTER[0], max(PAN_CENTER[1] - MOVE_STEP_PX, y0 + 30))
    assert c.actuator.taps == [expected]
    assert c._action.moved is True
    move = next(e for e in c.ledger.events if e["kind"] == "move")
    assert move["basis"] == "directional_threat_centroid"


def test_directional_step_pulls_back_from_a_unit_arc(monkeypatch):
    c = _controller()
    far = (PAN_CENTER[0] + MOVE_STEP_PX, PAN_CENTER[1])
    _quiet_vision(monkeypatch, allies=[far])

    point = c._directional_step(
        c.perception.capture(), (PAN_CENTER[0] + 1000.0, float(PAN_CENTER[1]))
    )

    assert point == (PAN_CENTER[0] + MOVE_STEP_NEAR_PX, PAN_CENTER[1])


def test_no_signals_still_stands_by(monkeypatch):
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    c = _controller()
    c._dispatched_mode = "label_unit_move"
    c._action.tried_in_place = True
    _quiet_vision(monkeypatch)
    monkeypatch.setattr(vision, "find_move_cells", lambda f: [])
    monkeypatch.setattr(vision, "unit_cards_present", lambda f: False)

    c._on_unit_move()

    standby = next(e for e in c.ledger.events if e["kind"] == "standby")
    assert standby["reason"] == "no_target"


def test_scout_hint_prefers_the_threat_layer():
    c = _controller()
    c.tacmap = TacticalMap(
        allies=[(0.0, 0.0)],
        enemies=[(-500.0, 0.0)],
        threats=[(300.0, 0.0), (500.0, 0.0)],
    )

    hint = c._hint_from_map()

    assert hint is not None
    assert hint[0] > 0.99  # toward the threats, not the phantom enemy


def test_tacmap_observe_and_reset_cover_threats():
    m = TacticalMap()
    m.observe((100.0, 0.0), enemies=[], allies=[], threats=[(50, 50), (60, 55)])
    assert len(m.threats) == 1  # merged within MERGE_RADIUS
    assert m.threat_centroid() == (155.0, 52.5)
    m.reset()
    assert m.threats == []
    assert m.threat_centroid() is None
