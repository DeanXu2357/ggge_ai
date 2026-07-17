"""Controller robustness: escape the unit-detail modal, corroborate new turns
with the on-screen TURN number, and instrument the select tap."""

from types import SimpleNamespace

import numpy as np

from ggge_ai.battle import controller as controller_mod
from ggge_ai.battle import vision
from ggge_ai.battle.controller import UNIT_DETAIL_CLOSE, ManualBattleController
from ggge_ai.battle.ledger import BattleLedger
from ggge_ai.domain import screens


class _Perception:
    """First observe stays in-battle so a guard branch runs; the second is a
    terminal screen so run() exits once the branch is handled."""

    def __init__(self):
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
    def __init__(self):
        self.taps = []

    def tap(self, x, y):
        self.taps.append((x, y))

    def swipe(self, *args):
        pass


def _controller(**kw):
    c = ManualBattleController(
        perception=_Perception(), actuator=_Actuator(), ledger=BattleLedger(), **kw
    )
    c.force_manual_auto = lambda *a, **k: "manual"
    return c


def test_modal_escape_taps_close_and_does_not_advance_turn(monkeypatch):
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "is_defeat_screen", lambda *a, **k: False)
    monkeypatch.setattr(vision, "is_hidden_battle_warning", lambda *a, **k: False)
    monkeypatch.setattr(vision, "is_unit_detail_modal", lambda *a, **k: True)

    c = _controller()
    start = c.ledger.turn
    result = c.run()

    assert result == screens.BATTLE_RESULT
    assert UNIT_DETAIL_CLOSE in c.actuator.taps
    # a modal must never be mistaken for a turn boundary
    assert c.ledger.turn == start
    kinds = [e["kind"] for e in c.ledger.events]
    assert "unit_detail_modal" in kinds


def test_unit_detail_modal_is_a_frame_event():
    from ggge_ai.battle.ledger import FRAME_KINDS

    assert "unit_detail_modal" in FRAME_KINDS
    assert "stage_info" in FRAME_KINDS
    assert "post_select_probe" in FRAME_KINDS


def test_probe_after_select_logs_frames(monkeypatch):
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    c = _controller()
    c._probe_after_select(count=3, interval_s=0)
    probes = [e for e in c.ledger.events if e["kind"] == "post_select_probe"]
    assert len(probes) == 3


def _prime_our_turn(monkeypatch, changed: bool):
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "unit_cards_present", lambda f: True)
    monkeypatch.setattr(vision, "crop_turn_marker", lambda f: np.zeros((36, 40), np.uint8))
    monkeypatch.setattr(vision, "turn_marker_changed", lambda a, b: changed)
    c = _controller()
    c._scout = lambda frame: None
    c._snapshot_factions = lambda frame: None
    c._probe_after_select = lambda *a, **k: None
    c._turn_marker = np.zeros((36, 40), np.uint8)
    return c


def test_hub_visit_without_turn_change_does_not_advance(monkeypatch):
    c = _prime_our_turn(monkeypatch, changed=False)
    start = c.ledger.turn
    c._on_our_turn()
    assert c.ledger.turn == start


def test_hub_visit_with_turn_change_advances_and_rescouts(monkeypatch):
    c = _prime_our_turn(monkeypatch, changed=True)
    c._turn_scouted = True
    start = c.ledger.turn
    c._on_our_turn()
    assert c.ledger.turn == start + 1
    # the reset re-arms the once-per-turn scout (the stub does not re-set it)
    assert c._turn_scouted is False


def test_first_hub_visit_sets_baseline_without_advancing(monkeypatch):
    c = _prime_our_turn(monkeypatch, changed=True)
    c._turn_marker = None
    start = c.ledger.turn
    c._on_our_turn()
    assert c.ledger.turn == start
    assert c._turn_marker is not None
