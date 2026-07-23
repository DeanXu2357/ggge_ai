"""Controller robustness: escape the unit-detail modal, corroborate new turns
with the on-screen TURN number, and instrument the select tap."""

from types import SimpleNamespace

import numpy as np

from ggge_ai.battle import controller as controller_mod
from ggge_ai.battle import vision
from ggge_ai.battle.controller import (
    END_TURN_BTN,
    UNIT_DETAIL_CLOSE,
    ManualBattleController,
)
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


def test_on_our_turn_repairs_covered_list_before_ending_turn(monkeypatch):
    """07-23 輪四 regression. unit_cards_present reads False but a modal covers
    the strip (unit_list_state -> unknown), so the turn is NOT over. Before
    concluding "no actable units" and tapping END_TURN, the handler must repair
    -- clear the obstruction + re-expand the list -- and re-read. The old code
    went straight to END_TURN on any no-cards frame."""
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "unit_cards_present", lambda f: False)
    monkeypatch.setattr(vision, "is_unit_detail_modal", lambda f: True)

    c = _controller()
    c._on_our_turn()

    # the repair (modal clear) happened, and before any END_TURN tap
    assert UNIT_DETAIL_CLOSE in c.actuator.taps
    if END_TURN_BTN in c.actuator.taps:
        assert c.actuator.taps.index(UNIT_DETAIL_CLOSE) < c.actuator.taps.index(END_TURN_BTN)


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
    c.timeline._marker = np.zeros((36, 40), np.uint8)
    return c


def test_hub_visit_without_turn_change_does_not_advance(monkeypatch):
    c = _prime_our_turn(monkeypatch, changed=False)
    start = c.ledger.turn
    c._on_our_turn()
    assert c.ledger.turn == start


def test_hub_visit_with_turn_change_advances_and_rescouts(monkeypatch):
    c = _prime_our_turn(monkeypatch, changed=True)
    c.timeline.mark_done("scout")
    start = c.ledger.turn
    c._on_our_turn()
    assert c.ledger.turn == start + 1
    # the reset re-arms the once-per-turn scout (the stub does not re-set it)
    assert "turn:scout" not in c.timeline._done_jobs


def test_first_hub_visit_sets_baseline_without_advancing(monkeypatch):
    c = _prime_our_turn(monkeypatch, changed=True)
    c.timeline._marker = None
    start = c.ledger.turn
    c._on_our_turn()
    assert c.ledger.turn == start
    assert c.timeline._marker is not None


def test_late_arrival_runs_scout_gate_before_selecting(monkeypatch):
    """07-24 輪六-B regression. A collapsed-list start reads no cards until the
    list is re-expanded (the 批8 repair), so selection necessarily flows through
    the late-arrival branch. That branch must run the same per-turn gate as the
    happy path -- turn bookkeeping + _scout -- BEFORE selecting a unit. The old
    code tapped FIRST_UNIT_CARD directly, skipping both."""
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "crop_turn_marker", lambda f: np.zeros((36, 40), np.uint8))
    monkeypatch.setattr(vision, "unit_list_state", lambda f: vision.UNIT_LIST_COLLAPSED)

    state = {"open": False}
    monkeypatch.setattr(vision, "unit_cards_present", lambda f: state["open"])

    c = _controller()
    calls = []

    def _open(want_open):
        state["open"] = True  # the repair reveals the strip
        calls.append("repair")
        return True

    c._set_unit_list_open = _open
    c._scout = lambda frame: calls.append("scout")
    c._snapshot_factions = lambda frame: None
    c._snapshot_board_belief = lambda: None
    c._probe_after_select = lambda *a, **k: None

    otr = c.timeline.on_turn_read
    c.timeline.on_turn_read = lambda *a, **k: (calls.append("on_turn_read"), otr(*a, **k))[1]

    real_tap = c.actuator.tap

    def _tap(x, y):
        if (x, y) == vision.FIRST_UNIT_CARD:
            calls.append("select")
        real_tap(x, y)

    c.actuator.tap = _tap

    c._on_our_turn()

    assert "select" in calls, "the late-arrival branch never selected the unit"
    assert "scout" in calls and calls.index("scout") < calls.index("select")
    assert "on_turn_read" in calls and calls.index("on_turn_read") < calls.index("select")
