from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from threading import Event

import numpy as np
import pytest

from ggge_ai_2.actuator.contract import Dispatch, Gesture, GestureBlocked, Rect, Tap
from ggge_ai_2.agent.belief import Belief, ScreenLock, UiBasis, UiSource
from ggge_ai_2.agent.contract import Plan, Step
from ggge_ai_2.agent.loop import MISMATCH_LIMIT, Agent, Predicted, RunResult
from ggge_ai_2.interpreter.contract import Screen, Situation
from ggge_ai_2.mapgeom.contract import Alignment, KnownMap
from ggge_ai_2.mapparser.contract import MapReading, ViewCell
from ggge_ai_2.stream.contract import NO_DISPLACEMENT, Frame, Observation, StillWindow
from ggge_ai_2.uisim.contract import UiScreen, UiState
from tests.ggge_ai_2.fakes.domain import FakeDomain
from tests.ggge_ai_2.fakes.mapgeom import NoMapGeometry
from tests.ggge_ai_2.fakes.uisim import FakeUiSim

LIST = UiState(UiScreen.STORY_STAGE_LIST)
INFO = UiState(UiScreen.SORTIE_PREP)
DEADLINE = 3.0
BAND = (Rect(0, 0, 50, 50),)
TAP = Tap((100, 100))
DISPATCHED = Dispatch(10.0, 10.1)


def frame(seq: int, at: float) -> Frame:
    return Frame(np.zeros((1, 1, 3), np.uint8), at, seq)


Settle = tuple[Frame, StillWindow | None]


def still(seq: int, at: float) -> Settle:
    return frame(seq, at), StillWindow(at - 0.5, at, seq)


def moving(seq: int, at: float) -> Settle:
    return frame(seq, at), None


def expected(ui: UiState, camera: Alignment | None = None) -> Belief:
    return Belief(ui, UiBasis(UiSource.ASSUMED), camera, KnownMap({}), FakeDomain(), None)


def step(then: UiState = INFO, name: str = "open_info") -> Step:
    return Step(name, TAP, BAND, DEADLINE, expected(then))


@dataclass
class FakeStream:
    settles: list[Settle]
    calls: list[tuple[float, float]] = field(default_factory=list)

    def latest(self) -> Frame:
        raise AssertionError("the loop reads the world only through settled frames")

    def settled(self, after: float, deadline: float) -> Observation:
        self.calls.append((after, deadline))
        shown, window = self.settles.pop(0)
        return Observation(shown, after, window, 0.5, NO_DISPLACEMENT)


@dataclass
class FakeActuator:
    blocks: list[bool] = field(default_factory=list)
    sent: list[tuple[Gesture, tuple[Rect, ...]]] = field(default_factory=list)

    def dispatch(self, gesture: Gesture, band: tuple[Rect, ...]) -> Dispatch:
        if self.blocks and self.blocks.pop(0):
            raise GestureBlocked
        self.sent.append((gesture, band))
        return DISPATCHED


@dataclass
class FakeInterpreter:
    shows: dict[int, Screen]

    def interpret(self, frame: Frame) -> Situation | None:
        screen = self.shows.get(frame.seq)
        return None if screen is None else Situation(frame.seq, screen)


class NoMapParser:
    def parse(self, frame: Frame) -> MapReading | None:
        raise AssertionError("no map on these screens")

    def locate(self, frame: Frame, cell: ViewCell) -> tuple[int, int] | None:
        raise AssertionError("no map on these screens")


@dataclass
class ScriptedPlan:
    steps: list[Step]
    valid: list[bool] = field(default_factory=list)

    def still_valid(self, belief: Belief) -> bool:
        return self.valid.pop(0) if self.valid else True

    def next(self, belief: Belief) -> Step:
        return self.steps.pop(0)


@dataclass
class ScriptedController:
    plans: list[ScriptedPlan | None]
    goals: list[bool]
    checked: list[Belief] = field(default_factory=list)
    thought: list[tuple[Belief, tuple[object, ...]]] = field(default_factory=list)
    reviewed: list[Plan] = field(default_factory=list)

    def goal_reached(self, belief: Belief) -> bool:
        self.checked.append(belief)
        return self.goals.pop(0)

    def think(self, belief: Belief, history: Sequence[object]) -> Plan | None:
        self.thought.append((belief, tuple(history)))
        return self.plans.pop(0)

    def review(self, plan: Plan, belief: Belief) -> object:
        self.reviewed.append(plan)
        return plan


def start() -> Belief:
    return Belief(LIST, UiBasis(UiSource.ASSUMED), None, KnownMap({}), FakeDomain(), None)


def make_agent(
    stream: FakeStream,
    shows: dict[int, Screen],
    controller: ScriptedController,
    actuator: FakeActuator | None = None,
    stop: Event | None = None,
) -> Agent:
    return Agent(
        stream=stream,
        actuator=actuator or FakeActuator(),
        interpreter=FakeInterpreter(shows),
        mapparser=NoMapParser(),
        mapgeom=NoMapGeometry(),
        uisim=FakeUiSim(),
        plan_controller=controller,
        belief=start(),
        idle_deadline=2.0,
        stop=stop or Event(),
    )


def logged(caplog: pytest.LogCaptureFixture, message: str) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.getMessage() == message]


def test_sense_hands_only_the_still_frame_to_the_belief():
    stream = FakeStream([moving(1, 1.0), still(2, 1.5)])
    controller = ScriptedController([], goals=[True])

    assert make_agent(stream, {2: Screen.STORY_STAGE_LIST}, controller).run() is RunResult.DONE
    assert [after for after, _ in stream.calls] == [0.0, 1.0]
    assert controller.checked[0].ui == LIST
    assert controller.checked[0].as_of == StillWindow(1.0, 1.5, 2)


def test_lock_screen_reaches_the_belief_as_a_screen_lock():
    controller = ScriptedController([], goals=[True])
    agent = make_agent(FakeStream([still(1, 1.0)]), {1: Screen.POWER_SAVE_LOCK}, controller)

    assert agent.run() is RunResult.DONE
    assert controller.checked[0] == replace(
        start(), screen_lock=ScreenLock.ICON, as_of=still(1, 1.0)[1]
    )


def test_controller_without_a_plan_halts_the_loop():
    controller = ScriptedController([None], goals=[False])
    actuator = FakeActuator()
    agent = make_agent(
        FakeStream([still(1, 1.0)]), {1: Screen.STORY_STAGE_LIST}, controller, actuator
    )

    assert agent.run() is RunResult.HALTED
    assert controller.thought == [(controller.checked[0], ())]
    assert actuator.sent == []


def test_step_that_passes_the_guard_sends_its_gesture_and_band():
    plan = ScriptedPlan([step()])
    controller = ScriptedController([plan], goals=[False, True])
    stream = FakeStream([still(1, 1.0), still(2, 11.0)])
    actuator = FakeActuator()
    shows = {1: Screen.STORY_STAGE_LIST, 2: Screen.SORTIE_PREP}

    assert make_agent(stream, shows, controller, actuator).run() is RunResult.DONE
    assert actuator.sent == [(TAP, BAND)]
    assert stream.calls[1][0] == DISPATCHED.t0
    assert controller.reviewed == [plan]


def test_guard_on_an_unreadable_screen_halts_and_logs_the_evidence(
    caplog: pytest.LogCaptureFixture,
):
    caplog.set_level(logging.ERROR, logger="ggge_ai_2.agent.loop")
    controller = ScriptedController([ScriptedPlan([step()])], goals=[False])
    actuator = FakeActuator()
    agent = make_agent(FakeStream([still(4, 1.0)]), {}, controller, actuator)

    assert agent.run() is RunResult.HALTED
    assert actuator.sent == []
    [record] = logged(caplog, "guard on an unreadable screen")
    assert record.__dict__["unreadable_since_frame_seq"] == 4


def test_mismatches_up_to_the_limit_end_the_plan():
    plan = ScriptedPlan([step()] * MISMATCH_LIMIT)
    controller = ScriptedController([plan, None], goals=[False] * (MISMATCH_LIMIT + 1))
    unchanged = [still(n, 10.0 + n) for n in range(1, MISMATCH_LIMIT + 2)]
    actuator = FakeActuator()
    shows = dict.fromkeys(range(1, MISMATCH_LIMIT + 2), Screen.STORY_STAGE_LIST)

    agent = make_agent(FakeStream(unchanged), shows, controller, actuator)

    assert agent.run() is RunResult.HALTED
    assert len(actuator.sent) == MISMATCH_LIMIT
    assert controller.reviewed == [plan]
    assert len(controller.thought) == 2


def test_new_plan_restarts_the_count():
    first = ScriptedPlan([step()] * MISMATCH_LIMIT)
    second = ScriptedPlan([step()] * 2)
    cycles = MISMATCH_LIMIT + 3
    controller = ScriptedController([first, second, None], goals=[False] * (cycles - 1) + [True])
    frames = [still(n, 10.0 + n * 0.5) for n in range(1, cycles + 1)]
    shows = dict.fromkeys(range(1, cycles + 1), Screen.STORY_STAGE_LIST)

    assert make_agent(FakeStream(frames), shows, controller).run() is RunResult.DONE
    assert len(controller.thought) == 2


def test_match_between_mismatches_restarts_the_count():
    opens = [step()] * MISMATCH_LIMIT
    plan = ScriptedPlan([*opens, step(LIST, "close_info"), step(LIST, "close_info")])
    cycles = MISMATCH_LIMIT + 3
    controller = ScriptedController([plan, None], goals=[False] * (cycles - 1) + [True])
    frames = [still(n, 10.0 + n * 0.5) for n in range(1, cycles + 1)]
    shows = dict.fromkeys(range(1, MISMATCH_LIMIT + 1), Screen.STORY_STAGE_LIST)
    shows[MISMATCH_LIMIT + 1] = Screen.SORTIE_PREP
    shows[MISMATCH_LIMIT + 2] = Screen.SORTIE_PREP

    assert make_agent(FakeStream(frames), shows, controller).run() is RunResult.DONE
    assert len(controller.thought) == 1


def test_invalid_plan_is_reviewed_and_replaced():
    plan = ScriptedPlan([step()], valid=[False])
    controller = ScriptedController([plan, None], goals=[False, False])
    stream = FakeStream([still(1, 1.0), still(2, 11.0)])
    shows = {1: Screen.STORY_STAGE_LIST, 2: Screen.SORTIE_PREP}

    assert make_agent(stream, shows, controller).run() is RunResult.HALTED
    assert controller.reviewed == [plan]
    assert controller.thought[1][1] == (plan,)


def test_blocked_gesture_leaves_nothing_to_compare(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO, logger="ggge_ai_2.agent.loop")
    plan = ScriptedPlan([step(), step(LIST, "close_info"), step(LIST, "close_info")])
    controller = ScriptedController([plan], goals=[False, False, False, True])
    stream = FakeStream([still(1, 1.0), still(2, 11.0), still(3, 12.0), still(4, 13.0)])
    shows = {1: Screen.STORY_STAGE_LIST, 2: Screen.SORTIE_PREP, 3: Screen.SORTIE_PREP}
    actuator = FakeActuator(blocks=[False, True, True])

    assert make_agent(stream, shows, controller, actuator).run() is RunResult.DONE
    assert len(logged(caplog, "matches")) == 1
    assert stream.calls[2][0] == 11.0


def test_stop_request_ends_the_loop_between_cycles():
    stop = Event()
    stop.set()
    agent = make_agent(FakeStream([]), {}, ScriptedController([], goals=[]), stop=stop)

    assert agent.run() is RunResult.STOPPED


def seen(ui: UiState, at: float, camera: Alignment | None = None) -> Belief:
    return Belief(
        ui, UiBasis(UiSource.SEEN, 1), camera, KnownMap({}), FakeDomain(), still(1, at)[1]
    )


def predicted(camera: Alignment | None = None) -> Predicted:
    return Predicted(expected(INFO, camera), DISPATCHED.t1 + DEADLINE)


def compare(belief: Belief, predicted: Predicted) -> bool:
    return make_agent(FakeStream([]), {}, ScriptedController([], goals=[])).matches(
        belief, predicted
    )


def test_prediction_takes_the_expected_belief_and_the_deadline_from_the_step():
    agent = make_agent(FakeStream([]), {}, ScriptedController([], goals=[]))
    sent = step()

    assert agent.predict(sent, DISPATCHED) == Predicted(sent.expected, DISPATCHED.t1 + DEADLINE)


def test_belief_with_the_expected_ui_and_camera_in_time_matches():
    assert compare(seen(INFO, 11.0), predicted())


def test_belief_still_only_after_the_deadline_does_not_match():
    late = DISPATCHED.t1 + DEADLINE + 1.0

    assert not compare(seen(INFO, late), predicted())


def test_belief_with_another_ui_does_not_match():
    assert not compare(seen(LIST, 11.0), predicted())


def test_belief_with_another_camera_does_not_match():
    moved = seen(INFO, 11.0, Alignment((3, 0)))

    assert not compare(moved, predicted(Alignment((0, 0))))


def test_belief_still_locked_after_an_unlock_does_not_match():
    still_locked = replace(seen(INFO, 11.0), screen_lock=ScreenLock.ICON)

    assert not compare(still_locked, predicted())
