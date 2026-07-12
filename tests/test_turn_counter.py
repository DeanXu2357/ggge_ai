"""Turn counting driven by the on-screen TURN number (OCR primary, marker
compare fallback) -- the HARD 1 ledger sat on turn=1 for a five-turn battle
because the marker-diff compare never fired."""

import numpy as np

from ggge_ai.battle import controller as controller_mod
from ggge_ai.battle import vision
from ggge_ai.battle.controller import ManualBattleController
from ggge_ai.battle.ledger import BattleLedger


class _Perception:
    def capture(self):
        return np.zeros((1080, 2340, 3), np.uint8)

    def probe(self, ids):
        return {}


class _Actuator:
    def tap(self, x, y):
        pass

    def swipe(self, *args):
        pass


def _hub_visit(c, monkeypatch, turn_read):
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "unit_cards_present", lambda f: True)
    monkeypatch.setattr(vision, "read_turn_number", lambda f: turn_read)
    monkeypatch.setattr(vision, "find_ally_units", lambda f, region=None: [])
    monkeypatch.setattr(vision, "find_enemy_units", lambda f, region=None: [])
    monkeypatch.setattr(vision, "find_third_party_units", lambda f, region=None: [])
    c._turn_scouted = True
    c._on_our_turn()


def _controller():
    c = ManualBattleController(
        perception=_Perception(), actuator=_Actuator(), ledger=BattleLedger()
    )
    c._guard_auto = lambda: None
    c._probe_after_select = lambda *a, **k: None
    return c


def test_same_turn_number_does_not_advance(monkeypatch):
    c = _controller()
    _hub_visit(c, monkeypatch, 1)
    assert c.ledger.turn == 1
    assert not any(e["kind"] == "end_turn" for e in c.ledger.events)


def test_new_turn_number_advances_and_rescouts(monkeypatch):
    c = _controller()
    scouts = []
    c._scout = lambda frame: scouts.append(c._turn_scouted)
    _hub_visit(c, monkeypatch, 1)
    _hub_visit(c, monkeypatch, 2)
    assert c.ledger.turn == 2
    assert scouts == [True, False]


def test_skipped_turn_pins_to_the_screen_number(monkeypatch):
    c = _controller()
    _hub_visit(c, monkeypatch, 3)
    assert c.ledger.turn == 3


def test_absurd_jump_is_rejected_as_misread(monkeypatch):
    c = _controller()
    _hub_visit(c, monkeypatch, 77)
    assert c.ledger.turn == 1


def test_unreadable_chip_falls_back_to_marker_compare(monkeypatch):
    c = _controller()
    one = np.zeros((36, 40), np.uint8)
    one[:, :20] = 255
    two = np.zeros((36, 40), np.uint8)
    two[:, 20:] = 255
    markers = iter([one, two])
    monkeypatch.setattr(vision, "crop_turn_marker", lambda f: next(markers))
    _hub_visit(c, monkeypatch, None)
    assert c.ledger.turn == 1
    _hub_visit(c, monkeypatch, None)
    assert c.ledger.turn == 2
