"""Router middleware: handlers declare their ledger intent, the dispatch
layer executes it. Interrupt handlers return LoopStep.log/.finish and never
touch the ledger themselves; the phase dispatch records one envelope event
per completed _on_* handler and turns the two aborts into a terminal step."""

import numpy as np

from ggge_ai.battle import controller as controller_mod
from ggge_ai.battle.controller import LoopStep, ManualBattleController, PilotAbort
from ggge_ai.battle.ledger import BattleLedger
from ggge_ai.battle.scout_intel import SurveyIncomplete
from ggge_ai.domain import screens


class _Perception:
    def capture(self):
        return np.zeros((1080, 2340, 3), np.uint8)


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
    step = c._dispatch_phase("label_probe")

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
    step = c._dispatch_phase("label_boom")

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
    step = c._dispatch_phase("label_survey")

    assert step.done is True
    assert step.screen == screens.UNKNOWN
    abort = next(e for e in c.ledger.events if e["kind"] == "survey_abort")
    assert abort["reason"] == "no stage_id"
    assert c.ledger.outcome == "survey_abort"
