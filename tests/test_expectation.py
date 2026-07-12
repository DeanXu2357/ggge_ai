"""Expectation-transition verification: the controller keeps its own model
of where each action should take the game (source -> targets) and audits it
against every confirmed mode read. Reality always wins -- a miss is recorded
evidence, never a fight with the screen; only the eaten-tap case feeds back
into behavior, by repairing the handler flag that assumed success."""

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


def _kinds(c):
    return [e["kind"] for e in c.ledger.events]


def test_verified_transition_records_met_and_clears():
    c = _controller()
    c._dispatched_mode = "label_our_turn"
    c._expect("select_unit", ("label_unit_move",))

    c._check_expectation("label_unit_move")

    assert c._expectation is None
    met = next(e for e in c.ledger.events if e["kind"] == "expectation_met")
    assert met["action"] == "select_unit"
    assert met["observed"] == "label_unit_move"


def test_unexpected_screen_is_a_recorded_miss_not_a_fight():
    c = _controller()
    c._dispatched_mode = "label_weapon_select"
    c._expect("attack", ("label_battle_prep",))

    c._check_expectation("label_skill")

    assert c._expectation is None
    miss = next(e for e in c.ledger.events if e["kind"] == "expectation_miss")
    assert miss["expected"] == ["label_battle_prep"]
    assert miss["observed"] == "label_skill"


def test_eaten_tap_triggers_on_eaten_once_then_expires():
    c = _controller()
    repaired = []
    c._dispatched_mode = "label_unit_move"
    c._expect(
        "open_weapon_select",
        ("label_weapon_select",),
        on_eaten=lambda: repaired.append(True),
    )

    c._check_expectation("label_unit_move")
    assert repaired == [True]
    assert c._expectation is not None  # re-armed, waiting for the retry

    c._check_expectation("label_unit_move")
    assert c._expectation is None
    assert "expectation_expired" in _kinds(c)


def test_label_less_reads_burn_the_budget_not_the_clock():
    c = _controller()
    c._dispatched_mode = "label_weapon_select"
    c._expect("attack", ("label_battle_prep",), checks=3)

    c._check_expectation(None)
    c._check_expectation(None)
    assert c._expectation is not None

    c._check_expectation(None)
    assert c._expectation is None
    assert "expectation_expired" in _kinds(c)


def test_target_after_label_less_stretch_still_verifies():
    c = _controller()
    c._dispatched_mode = "label_battle_prep"
    c._expect("battle_execute", ("label_our_turn",), checks=20)

    for _ in range(5):
        c._check_expectation(None)
    c._check_expectation("label_our_turn")

    assert c._expectation is None
    assert "expectation_met" in _kinds(c)
    assert "expectation_expired" not in _kinds(c)


def test_no_expectation_is_a_noop():
    c = _controller()
    c._check_expectation("label_our_turn")
    c._check_expectation(None)
    assert c.ledger.events == []


def test_eaten_weapon_select_tap_reopens_on_next_visit(monkeypatch):
    """Integration: _on_unit_move taps 選擇武裝 and flags tried_in_place; if
    the tap is eaten the flag must roll back so the next visit re-taps the
    button instead of walking the move branch."""
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    c = _controller()
    c._dispatched_mode = "label_unit_move"

    c._on_unit_move()
    assert c.actuator.taps.count(WEAPON_SELECT_BTN) == 1
    assert c._action.tried_in_place is True

    c._check_expectation("label_unit_move")
    assert c._action.tried_in_place is False

    c._on_unit_move()
    assert c.actuator.taps.count(WEAPON_SELECT_BTN) == 2


def test_standby_registers_a_contract_toward_the_hub(monkeypatch):
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "unit_cards_present", lambda f: False)
    c = _controller()
    c._dispatched_mode = "label_unit_move"

    c._standby("no_target")

    assert c._expectation is not None
    assert c._expectation.action == "standby"
    assert c._expectation.source == "label_unit_move"
    assert "label_our_turn" in c._expectation.targets
