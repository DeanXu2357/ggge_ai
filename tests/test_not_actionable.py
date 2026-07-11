"""NOT_ACTIONABLE phase (docs/battle-phase-states.md): no MODE_LABELS
matched, so the controller either advances a death dialogue or just waits.
Turn boundaries are detected by the on-screen TURN marker in _on_our_turn,
not by counting label-less iterations (which also occur mid-turn during
attack animations now that no static gate runs)."""

from types import SimpleNamespace

import numpy as np

from ggge_ai.battle import controller as controller_mod
from ggge_ai.battle import vision
from ggge_ai.battle.controller import ManualBattleController
from ggge_ai.battle.ledger import BattleLedger


class _Perception:
    def capture(self):
        return np.zeros((1080, 2340, 3), np.uint8)


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


def test_dialog_cursor_found_counts_as_activity_and_taps(monkeypatch):
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "locate_dialog_cursor", lambda frame: (500, 900))
    c = _controller()

    activity = c._on_not_actionable()

    assert activity is True
    assert (500, 900) in c.actuator.taps


def test_no_dialog_is_not_activity(monkeypatch):
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "locate_dialog_cursor", lambda frame: None)
    c = _controller()

    activity = c._on_not_actionable()

    assert activity is False
    assert c.actuator.taps == []


def test_run_updates_last_activity_only_when_not_actionable_returns_true(monkeypatch):
    """Regression pin for the run() refactor: dispatch on mode is None must
    still gate the idle-timeout clock exactly like before -- a bare miss
    should not look like activity, or a stuck NOT_ACTIONABLE loop would
    never idle-time-out."""
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "is_defeat_screen", lambda *a, **k: False)
    monkeypatch.setattr(vision, "is_hidden_battle_warning", lambda *a, **k: False)
    monkeypatch.setattr(vision, "is_unit_detail_modal", lambda *a, **k: False)
    monkeypatch.setattr(vision, "locate_story_menu", lambda *a, **k: None)

    class _P(_Perception):
        def observe(self):
            return SimpleNamespace(screen="unknown", screen_confidence=0.1)

        def probe(self, ids):
            return {}

    c = ManualBattleController(
        perception=_P(), actuator=_Actuator(), ledger=BattleLedger(), idle_timeout_s=0.0
    )
    c.ensure_manual_auto = lambda *a, **k: True
    result = c.run()

    assert result == "unknown"
    kinds = [e["kind"] for e in c.ledger.events]
    assert kinds[-1] == "finish"
