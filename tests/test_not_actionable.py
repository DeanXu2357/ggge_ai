"""NOT_ACTIONABLE phase (docs/battle-phase-states.md): no MODE_LABELS
matched, so the controller either advances a death dialogue or just waits
and tracks the none-streak used to corroborate a real phase break."""

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
    c._none_streak = 1

    activity = c._on_not_actionable()

    assert activity is True
    assert (500, 900) in c.actuator.taps
    assert c._none_streak == 0
    assert c._phase_break is False


def test_no_dialog_first_miss_is_not_activity_and_no_phase_break(monkeypatch):
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "locate_dialog_cursor", lambda frame: None)
    c = _controller()

    activity = c._on_not_actionable()

    assert activity is False
    assert c._none_streak == 1
    assert c._phase_break is False


def test_second_consecutive_miss_sets_phase_break(monkeypatch):
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "locate_dialog_cursor", lambda frame: None)
    c = _controller()

    c._on_not_actionable()
    activity = c._on_not_actionable()

    assert activity is False
    assert c._none_streak == 2
    assert c._phase_break is True


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
    monkeypatch.setattr(controller_mod, "is_static", lambda *a, **k: True)

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
