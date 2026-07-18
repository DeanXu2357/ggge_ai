"""Controller wiring of the timeline's act -> verify contracts: handlers
report actions through timeline.acted(), observe() verdicts flow back into
handler flags (the eaten-tap repair) and every contract registers the phase
the screen last confirmed as its source. The pure verdict logic itself is
covered in test_timeline.py."""

import numpy as np

from ggge_ai.battle import controller as controller_mod
from ggge_ai.battle import vision
from ggge_ai.battle.controller import WEAPON_SELECT_BTN, ManualBattleController
from ggge_ai.battle.ledger import BattleLedger


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


def test_eaten_weapon_select_tap_reopens_on_next_visit(monkeypatch):
    """Integration: _on_unit_move taps 選擇武裝 and flags tried_in_place; if
    the tap is eaten the flag must roll back so the next visit re-taps the
    button instead of walking the move branch."""
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    c = _controller()
    c.timeline.phase = "unit_move"

    c._on_unit_move()
    assert c.actuator.taps.count(WEAPON_SELECT_BTN) == 1
    assert c.timeline.activation.tried_in_place is True

    c.timeline.observe("unit_move")
    assert c.timeline.activation.tried_in_place is False

    c._on_unit_move()
    assert c.actuator.taps.count(WEAPON_SELECT_BTN) == 2


def test_standby_registers_a_contract_toward_the_hub(monkeypatch):
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "unit_cards_present", lambda f: False)
    c = _controller()
    c.timeline.phase = "unit_move"

    c._standby("no_target")

    exp = c.timeline._expectation
    assert exp is not None
    assert exp.action == "standby"
    assert exp.source == "unit_move"
    assert "our_turn" in exp.targets
