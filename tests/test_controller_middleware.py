"""The tick seam and its middleware: _classify reads the frame in screen
z-order (overlays before the phase label) and returns one state; _dispatch
routes that state through the matching middleware. Handlers declare their
ledger intent via LoopStep.log/.finish and never touch the ledger themselves;
the phase dispatch records one envelope event per completed _on_* handler and
turns the two aborts into a terminal step."""

from types import SimpleNamespace

import numpy as np

from ggge_ai.battle import controller as controller_mod
from ggge_ai.battle import vision
from ggge_ai.battle.controller import LoopStep, ManualBattleController, PilotAbort
from ggge_ai.battle.ledger import BattleLedger
from ggge_ai.battle.scout_intel import SurveyIncomplete
from ggge_ai.domain import screens


class _Perception:
    def capture(self):
        return np.zeros((1080, 2340, 3), np.uint8)


class _ScenePerception(_Perception):
    """Perception stub for _classify: `screen` drives the terminal detector,
    `labels` drives every probe (steady, so two-read confirms agree)."""

    def __init__(self, screen="unknown", labels=None):
        self.screen = screen
        self.labels = labels or {}

    def observe(self, frame):
        return SimpleNamespace(screen=self.screen, screen_confidence=0.99)

    def probe(self, ids, frame=None):
        return {
            eid: SimpleNamespace(confidence=conf)
            for eid, conf in self.labels.items()
            if eid in ids
        }


def _quiet_overlays(monkeypatch):
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(vision, "is_defeat_screen", lambda *a, **k: False)
    monkeypatch.setattr(vision, "is_hidden_battle_warning", lambda *a, **k: False)
    monkeypatch.setattr(vision, "is_unit_detail_modal", lambda *a, **k: False)
    monkeypatch.setattr(vision, "locate_story_menu", lambda *a, **k: None)


class _Actuator:
    def __init__(self):
        self.taps = []

    def tap(self, x, y):
        self.taps.append((x, y))


def _controller():
    return ManualBattleController(
        perception=_Perception(), actuator=_Actuator(), ledger=BattleLedger()
    )


def _kinds(c):
    return [e["kind"] for e in c.ledger.events]


def test_dispatch_interrupt_records_declared_log_against_the_frame():
    c = _controller()

    def handle(frame, payload):
        return LoopStep(log=("story_skip", {"menu": (10, 20)}))

    step = c._dispatch_interrupt(handle, object(), None)

    assert step.done is False
    event = next(e for e in c.ledger.events if e["kind"] == "story_skip")
    assert event["menu"] == (10, 20)


def test_dispatch_interrupt_routes_finish_to_the_ledger():
    c = _controller()
    step = c._dispatch_interrupt(
        c._handle_terminal, None, screens.BATTLE_RESULT
    )
    assert step.done is True
    assert step.screen == screens.BATTLE_RESULT
    assert c.ledger.outcome == screens.BATTLE_RESULT


def test_handler_without_intent_records_nothing():
    c = _controller()

    def handle(frame, payload):
        return LoopStep()

    c._dispatch_interrupt(handle, None, None)
    assert c.ledger.events == []


def test_end_turn_is_no_longer_a_silent_handler(monkeypatch):
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    c = _controller()
    c._dispatch_interrupt(c._handle_end_turn, None, None)
    assert "end_turn" in _kinds(c)


def test_dispatch_phase_records_the_completed_envelope():
    c = _controller()
    c._on_probe = lambda: None
    step = c._dispatch_phase("probe")

    assert step is None
    event = next(e for e in c.ledger.events if e["kind"] == "phase")
    assert event["phase"] == "probe"
    assert event["outcome"] == "ok"
    assert "elapsed_ms" in event


def test_dispatch_phase_turns_pilot_abort_into_a_terminal_step():
    c = _controller()

    def boom():
        raise PilotAbort("alignment lost")

    c._on_boom = boom
    step = c._dispatch_phase("boom")

    assert step.done is True
    assert step.screen == screens.UNKNOWN
    assert c.ledger.outcome == "pilot_abort"
    # the abort path keeps its own record, no phase-ok envelope
    assert not any(e["kind"] == "phase" for e in c.ledger.events)


def test_dispatch_phase_reports_survey_incomplete_then_ends():
    c = _controller()

    def boom():
        raise SurveyIncomplete("no stage_id")

    c._on_survey = boom
    step = c._dispatch_phase("survey")

    assert step.done is True
    assert step.screen == screens.UNKNOWN
    abort = next(e for e in c.ledger.events if e["kind"] == "survey_abort")
    assert abort["reason"] == "no stage_id"
    assert c.ledger.outcome == "survey_abort"


def test_classify_overlay_wins_before_the_phase_label_is_read(monkeypatch):
    """z-order: a terminal screen claims the tick even though a phase label
    would also read -- the label is never consulted."""
    _quiet_overlays(monkeypatch)
    p = _ScenePerception(screen=screens.BATTLE_RESULT, labels={"label_our_turn": 0.9})
    c = ManualBattleController(perception=p, actuator=_Actuator(), ledger=BattleLedger())

    state, payload = c._classify(p.capture())

    assert state == "terminal"
    assert payload == screens.BATTLE_RESULT


def test_classify_returns_the_stripped_phase_state(monkeypatch):
    _quiet_overlays(monkeypatch)
    p = _ScenePerception(labels={"label_our_turn": 0.9})
    c = ManualBattleController(perception=p, actuator=_Actuator(), ledger=BattleLedger())

    state, payload = c._classify(p.capture())

    assert state == "our_turn"
    assert payload is None


def test_classify_without_a_label_is_not_actionable(monkeypatch):
    _quiet_overlays(monkeypatch)
    p = _ScenePerception()
    c = ManualBattleController(perception=p, actuator=_Actuator(), ledger=BattleLedger())

    assert c._classify(p.capture()) == ("not_actionable", None)


def test_overlay_ticks_never_burn_expectation_budget(monkeypatch):
    """An overlay-claimed tick returns before the mode read, so the open
    expectation keeps its checks; a label-less phase tick burns one."""
    _quiet_overlays(monkeypatch)
    p = _ScenePerception(screen=screens.BATTLE_RESULT)
    c = ManualBattleController(perception=p, actuator=_Actuator(), ledger=BattleLedger())
    c._expect("attack", ("label_battle_prep",), checks=3)

    c._classify(p.capture())
    assert c._expectation.checks_left == 3

    p.screen = "unknown"
    c._classify(p.capture())
    assert c._expectation.checks_left == 2


def test_dispatch_routes_an_overlay_state_through_the_intent_middleware(monkeypatch):
    monkeypatch.setattr(controller_mod.time, "sleep", lambda *a, **k: None)
    c = ManualBattleController(
        perception=_Perception(), actuator=_Actuator(), ledger=BattleLedger()
    )

    step = c._dispatch("end_turn", True, None)

    assert step.done is False
    assert step.activity is True
    assert controller_mod.END_TURN_STANDBY_OPTION in c.actuator.taps
    assert "end_turn" in _kinds(c)


def test_dispatch_wraps_the_not_actionable_verdict_into_activity():
    c = ManualBattleController(
        perception=_Perception(), actuator=_Actuator(), ledger=BattleLedger()
    )
    c._on_not_actionable = lambda: False
    assert c._dispatch("not_actionable", None, None).activity is False
    c._on_not_actionable = lambda: True
    assert c._dispatch("not_actionable", None, None).activity is True


def test_dispatch_arms_the_phase_bookkeeping_before_the_handler():
    c = ManualBattleController(
        perception=_Perception(), actuator=_Actuator(), ledger=BattleLedger()
    )
    seen = {}
    c._on_probe = lambda: seen.setdefault("mode", c._dispatched_mode)
    c._miss_streak = 2

    step = c._dispatch("probe", None, None)

    assert step == LoopStep()
    assert seen["mode"] == "label_probe"
    assert c._miss_streak == 0
