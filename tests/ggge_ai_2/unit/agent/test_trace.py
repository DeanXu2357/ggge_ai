from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import pytest

from ggge_ai_2.agent.belief import Belief, UiBasis, UiSource
from ggge_ai_2.agent.contract import Evidence, MapReadingRecord, Step
from ggge_ai_2.agent.trace import traced
from ggge_ai_2.agent.trace_json import decode_record, decode_ui
from ggge_ai_2.mapparser.contract import MapReading
from ggge_ai_2.stream.contract import StillWindow
from ggge_ai_2.uisim.contract import UiScreen, UiState
from tests.ggge_ai_2.fakes.domain import FakeDomain

STEP = Step("probe_wait", None, (), 0.0, ())


@dataclass
class ProbePlan:
    def still_valid(self, belief: Belief, evidence: Evidence) -> bool:
        return True

    @traced
    def next(self, belief: Belief, evidence: Evidence) -> Step:
        return STEP


def belief() -> Belief:
    return Belief(
        ui=UiState(UiScreen.PLAYER_PHASE_OVERVIEW),
        ui_basis=UiBasis(UiSource.SEEN),
        domain=FakeDomain(),
        as_of=StillWindow(1.0, 2.0, 7),
    )


def evidence() -> Evidence:
    reading = MapReading({}, frozenset(), (), {}, {}, None, None)
    return Evidence((MapReadingRecord(StillWindow(1.0, 2.0, 7), reading, None, None),))


def test_the_trace_logs_the_input_and_the_output_of_next(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.DEBUG, logger="ggge_ai_2.agent.trace")

    ProbePlan().next(belief(), evidence())

    (given,) = [record for record in caplog.records if record.getMessage() == "plan input"]
    (gave,) = [record for record in caplog.records if record.getMessage() == "plan output"]
    assert (vars(given)["plan"], vars(given)["readings"]) == ("ProbePlan", 1)
    newest = json.loads(json.dumps(vars(given)["newest"]))
    assert decode_record(newest) == evidence().map_readings[-1]
    assert decode_ui(vars(given)["belief"]) == (belief().ui, belief().as_of)
    assert (vars(gave)["plan"], vars(gave)["step"], vars(gave)["gesture"]) == (
        "ProbePlan",
        "probe_wait",
        None,
    )


def test_the_trace_logs_nothing_above_the_debug_level(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO, logger="ggge_ai_2.agent.trace")

    assert ProbePlan().next(belief(), evidence()) is STEP
    assert not [record for record in caplog.records if record.name == "ggge_ai_2.agent.trace"]
