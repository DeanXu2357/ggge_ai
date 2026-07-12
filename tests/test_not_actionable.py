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


def test_neutral_tap_after_consecutive_unrecognized_scenes(monkeypatch):
    """An unrecognized scene (no label, no dialog cursor, no modal) gets
    nudged at a non-button spot after a few misses instead of stalling until
    the idle timeout -- dialog-style scenes advance on any tap."""
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "locate_dialog_cursor", lambda frame: None)
    c = _controller()

    for _ in range(controller_mod.NEUTRAL_TAP_AFTER_MISSES - 1):
        c._on_not_actionable()
    assert c.actuator.taps == []

    c._on_not_actionable()
    assert c.actuator.taps == [controller_mod.NEUTRAL_TAP]
    kinds = [e["kind"] for e in c.ledger.events]
    assert "neutral_tap" in kinds
    # the streak restarts after a nudge, no rapid-fire tapping
    c._on_not_actionable()
    assert c.actuator.taps == [controller_mod.NEUTRAL_TAP]


def test_describe_state_covers_the_four_verdicts():
    c = _controller()

    c._last_probe = {"label_unit_move": 0.87}
    assert c._describe_state("label_unit_move") == "ACTIONABLE unit_move (0.87)"

    c._mode_flicker = ("label_unit_move", None)
    assert c._describe_state(None) == "TRANSITION (label_unit_move -> None)"

    c._mode_flicker = None
    c._last_probe = {"label_enemy_turn": 0.99, "label_our_turn": 0.83}
    assert c._describe_state(None) == "NOT_ACTIONABLE enemy_turn (0.99)"

    c._last_probe = {}
    assert c._describe_state(None) == "NOT_ACTIONABLE no-label"


def test_log_state_logs_only_on_transition(caplog):
    import logging

    c = _controller()
    c._last_probe = {"label_unit_move": 0.87}
    with caplog.at_level(logging.INFO, logger="ggge_ai.battle.controller"):
        c._log_state("label_unit_move")
        c._log_state("label_unit_move")
        c._log_state("label_unit_move")
        c._last_probe = {"label_enemy_turn": 0.99}
        c._log_state(None)
    state_lines = [r.message for r in caplog.records if r.message.startswith("state")]
    assert len(state_lines) == 2
    assert "held 3 checks" in state_lines[1]
    assert "NOT_ACTIONABLE enemy_turn" in state_lines[1]


def test_dialog_resets_the_miss_streak(monkeypatch):
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    cursors = iter([None, None, (500, 900)])
    monkeypatch.setattr(vision, "locate_dialog_cursor", lambda frame: next(cursors))
    c = _controller()

    c._on_not_actionable()
    c._on_not_actionable()
    c._on_not_actionable()

    assert c.actuator.taps == [(500, 900)]
    assert c._miss_streak == 0


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
    c.force_manual_auto = lambda *a, **k: "manual"
    result = c.run()

    assert result == "unknown"
    kinds = [e["kind"] for e in c.ledger.events]
    assert kinds[-1] == "finish"
