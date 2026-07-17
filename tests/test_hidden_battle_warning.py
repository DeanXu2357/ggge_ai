from types import SimpleNamespace

import numpy as np
import pytest

from ggge_ai.battle import controller as controller_mod
from ggge_ai.battle import vision
from ggge_ai.battle.controller import (
    CHALLENGE_HIDDEN_BATTLE,
    DECLINE_HIDDEN_BATTLE,
    ManualBattleController,
)
from ggge_ai.battle.ledger import BattleLedger
from ggge_ai.domain import screens


class _Perception:
    """First observe stays in-battle so the modal branch runs; the second
    returns a terminal screen so run() exits after the modal is handled."""

    def __init__(self) -> None:
        self.calls = 0

    def observe(self, frame=None):
        self.calls += 1
        if self.calls >= 2:
            return SimpleNamespace(screen=screens.BATTLE_RESULT, screen_confidence=0.95)
        return SimpleNamespace(screen=screens.UNKNOWN, screen_confidence=0.1)

    def capture(self):
        return np.zeros((1080, 2340, 3), np.uint8)

    def probe(self, ids, frame=None):
        return {}


class _Actuator:
    def __init__(self) -> None:
        self.taps: list[tuple[int, int]] = []

    def tap(self, x: int, y: int) -> None:
        self.taps.append((x, y))


def _run_once(monkeypatch, policy: str):
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "is_defeat_screen", lambda *a, **k: False)
    monkeypatch.setattr(vision, "is_hidden_battle_warning", lambda *a, **k: True)

    ledger = BattleLedger()
    actuator = _Actuator()
    c = ManualBattleController(
        perception=_Perception(),
        actuator=actuator,
        ledger=ledger,
        hidden_battle_policy=policy,
    )
    c.ensure_manual_auto = lambda *a, **k: True

    result = c.run()
    return result, actuator, ledger


def _warning_events(ledger: BattleLedger):
    return [e for e in ledger.events if e["kind"] == "hidden_battle_warning"]


def test_challenge_policy_taps_challenge_button(monkeypatch):
    result, actuator, ledger = _run_once(monkeypatch, "challenge")

    assert result == screens.BATTLE_RESULT
    assert CHALLENGE_HIDDEN_BATTLE in actuator.taps
    assert DECLINE_HIDDEN_BATTLE not in actuator.taps

    events = _warning_events(ledger)
    assert len(events) == 1
    assert events[0]["decision"] == "challenge"


def test_decline_policy_taps_decline_button(monkeypatch):
    result, actuator, ledger = _run_once(monkeypatch, "decline")

    assert result == screens.BATTLE_RESULT
    assert DECLINE_HIDDEN_BATTLE in actuator.taps
    assert CHALLENGE_HIDDEN_BATTLE not in actuator.taps

    events = _warning_events(ledger)
    assert len(events) == 1
    assert events[0]["decision"] == "decline"


def test_default_policy_is_challenge(monkeypatch):
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "is_defeat_screen", lambda *a, **k: False)
    monkeypatch.setattr(vision, "is_hidden_battle_warning", lambda *a, **k: True)

    actuator = _Actuator()
    c = ManualBattleController(
        perception=_Perception(), actuator=actuator, ledger=BattleLedger()
    )
    c.ensure_manual_auto = lambda *a, **k: True

    c.run()

    assert CHALLENGE_HIDDEN_BATTLE in actuator.taps


@pytest.mark.parametrize("kind", ["hidden_battle_warning"])
def test_warning_kind_is_a_frame_event(kind):
    from ggge_ai.battle.ledger import FRAME_KINDS

    assert kind in FRAME_KINDS
