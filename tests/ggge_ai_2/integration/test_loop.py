from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from threading import Event

import numpy as np
import pytest

from ggge_ai_2.actuator.contract import Dispatch, Gesture, GestureBlocked, Rect, Tap
from ggge_ai_2.agent.belief import Belief, Passing, ScreenLock, UiBasis, UiSource
from ggge_ai_2.agent.contract import Plan, Step
from ggge_ai_2.agent.loop import MISMATCH_LIMIT, Agent, Predicted, RunResult
from ggge_ai_2.agent.runlog import RunLog
from ggge_ai_2.interpreter.contract import Screen, Situation
from ggge_ai_2.mapgeom.contract import Alignment, KnownMap
from ggge_ai_2.mapparser.contract import MapReading, ViewCell
from ggge_ai_2.stream.contract import Frame, Observation, StillWindow
from ggge_ai_2.uisim.contract import Operation, Outcome, UiScreen, UiState
from tests.ggge_ai_2.fakes.domain import FakeDomain
from tests.ggge_ai_2.fakes.mapgeom import NoMapGeometry
from tests.ggge_ai_2.fakes.uisim import FakeUiSim

LIST = UiState(UiScreen.STORY_STAGE_LIST)
INFO = UiState(UiScreen.SORTIE_PREP)
DEADLINE = 3.0
BAND = (Rect(0, 0, 50, 50),)
TAP = Tap((100, 100))
DISPATCHED = Dispatch(10.0, 10.1)


def frame(seq: int, at: float, shade: int = 0) -> Frame:
    return Frame(np.full((1, 1, 3), shade, np.uint8), at, seq)


def window(seq: int, at: float) -> StillWindow:
    return StillWindow(at - 0.5, at, seq)


def still(seq: int, at: float) -> list[Frame]:
    return [frame(seq, at - 0.5), frame(seq, at)]


def expected(ui: UiState, camera: Alignment | None = None) -> Belief:
    return Belief(ui, UiBasis(UiSource.ASSUMED), camera, KnownMap({}), FakeDomain(), None)


def step(then: UiState = INFO, name: str = "open_info") -> Step:
    return Step(name, TAP, BAND, DEADLINE, (expected(then),))


@dataclass
class FakeStream:
    frames: list[Frame]

    def latest(self) -> Frame:
        return self.frames.pop(0)

    def settled(self, after: float, deadline: float) -> Observation:
        raise AssertionError("the loop settles on the interpretation, not on pixel stillness")


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
class StoppingStream(FakeStream):
    stop: Event

    def latest(self) -> Frame:
        shot = super().latest()
        if not self.frames:
            self.stop.set()
        return shot


@dataclass
class FakeInterpreter:
    shows: dict[int, Screen]
    autos: dict[int, bool] = field(default_factory=dict[int, bool])

    def interpret(self, frame: Frame, candidates: frozenset[Screen]) -> Situation | None:
        screen = self.shows.get(frame.seq)
        return None if screen is None else Situation(frame.seq, screen, self.autos.get(frame.seq))


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
    runlog: RunLog | None = None,
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
        stop=stop or Event(),
        runlog=runlog,
    )


def logged(caplog: pytest.LogCaptureFixture, message: str) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.getMessage() == message]


def test_animated_screen_settles_on_two_frames_with_the_same_interpretation():
    stream = FakeStream([frame(1, 1.0, shade=0), frame(2, 1.4, shade=200)])
    controller = ScriptedController([], goals=[True])
    shows = {1: Screen.STORY_STAGE_LIST, 2: Screen.STORY_STAGE_LIST}

    assert make_agent(stream, shows, controller).run() is RunResult.DONE
    assert controller.checked[0].ui == LIST
    assert controller.checked[0].as_of == StillWindow(1.0, 1.4, 2)


def test_sense_settles_on_the_second_of_two_equal_interpretations(
    caplog: pytest.LogCaptureFixture,
):
    caplog.set_level(logging.INFO, logger="ggge_ai_2.agent.loop")
    stream = FakeStream([frame(1, 1.0), frame(2, 1.4), frame(3, 1.8)])
    shows = {1: Screen.STORY_STAGE_LIST, 2: Screen.SORTIE_PREP, 3: Screen.SORTIE_PREP}

    sensed = make_agent(stream, shows, ScriptedController([], goals=[])).sense()

    assert sensed is not None
    assert sensed.still == StillWindow(1.4, 1.8, 3)
    assert sensed.observed is not None and sensed.observed.screen is UiScreen.SORTIE_PREP
    [unsettled] = logged(caplog, "sense unsettled")
    assert unsettled.__dict__["frame_seq"] == 2
    assert unsettled.__dict__["first"] == (Screen.STORY_STAGE_LIST, None)
    assert unsettled.__dict__["second"] == (Screen.SORTIE_PREP, None)


def test_different_auto_values_do_not_settle():
    stream = FakeStream([frame(1, 1.0), frame(2, 1.4), frame(3, 1.8)])
    shows = dict.fromkeys(range(1, 4), Screen.SORTIE_PREP)
    agent = make_agent(stream, shows, ScriptedController([], goals=[]))
    agent.interpreter = FakeInterpreter(shows, {1: False, 2: True, 3: True})

    sensed = agent.sense()

    assert sensed is not None
    assert sensed.still == StillWindow(1.4, 1.8, 3)
    assert sensed.observed is not None and sensed.observed.auto is True


def test_stop_request_during_unsettled_frames_ends_the_loop():
    stop = Event()
    stream = StoppingStream([frame(1, 1.0), frame(2, 1.4), frame(3, 1.8)], stop)
    shows = {1: Screen.STORY_STAGE_LIST, 2: Screen.SORTIE_PREP, 3: Screen.STORY_STAGE_LIST}
    controller = ScriptedController([], goals=[])

    assert make_agent(stream, shows, controller, stop=stop).run() is RunResult.STOPPED
    assert controller.checked == []


def test_frame_captured_before_the_gesture_fails_the_cutoff():
    controller = ScriptedController([ScriptedPlan([step()])], goals=[False])
    stream = FakeStream([*still(1, 1.0), *still(2, DISPATCHED.t0)])
    agent = make_agent(stream, {1: Screen.STORY_STAGE_LIST}, controller)

    with pytest.raises(AssertionError, match="older than the cutoff"):
        agent.run()


def test_lock_screen_reaches_the_belief_as_a_screen_lock():
    controller = ScriptedController([], goals=[True])
    agent = make_agent(FakeStream(still(1, 1.0)), {1: Screen.POWER_SAVE_LOCK}, controller)

    assert agent.run() is RunResult.DONE
    assert controller.checked[0] == replace(
        start(), screen_lock=ScreenLock.ICON, as_of=window(1, 1.0)
    )


def test_sense_reports_a_pass_through_frame_as_passing_and_not_as_a_screen():
    stream = FakeStream([*still(1, 1.0), *still(2, 2.0)])
    shows = {1: Screen.BATTLE_CLEAR_VIEW, 2: Screen.LOADING}
    agent = make_agent(stream, shows, ScriptedController([], goals=[]))

    clear, loading = agent.sense(), agent.sense()

    assert clear is not None and loading is not None
    assert (clear.passing, clear.observed) == (Passing.TAP_TO_CONTINUE, None)
    assert (loading.passing, loading.observed) == (Passing.WAIT, None)


def test_passing_cycle_keeps_the_earlier_prediction_for_the_next_screen(
    caplog: pytest.LogCaptureFixture,
):
    caplog.set_level(logging.INFO, logger="ggge_ai_2.agent.loop")
    plan = ScriptedPlan([step(), step(LIST, "tap_to_continue"), step()])
    controller = ScriptedController([plan], goals=[False, False, False, True])
    stream = FakeStream([*still(1, 1.0), *still(2, 11.0), *still(3, 12.0), *still(4, 13.0)])
    shows = {1: Screen.STORY_STAGE_LIST, 2: Screen.BATTLE_CLEAR_VIEW, 3: Screen.SORTIE_PREP}
    actuator = FakeActuator()

    assert make_agent(stream, shows, controller, actuator).run() is RunResult.DONE
    assert len(actuator.sent) == 3
    [compared] = logged(caplog, "matches")
    assert compared.__dict__["frame_seq"] == 3
    assert compared.__dict__["same"]
    assert compared.__dict__["in_time"]


def open_sortie_prep() -> Operation:
    outcomes = (
        Outcome("opened", INFO),
        Outcome("refused", UiState(UiScreen.AP_RECOVERY_OVERLAY)),
    )
    return Operation("open", LIST, None, outcomes, DEADLINE, 1.0)


def test_seen_belief_offers_the_successor_screens_and_the_anytime_screens():
    agent = make_agent(FakeStream([]), {}, ScriptedController([], goals=[]))
    agent.uisim = FakeUiSim(operations={UiScreen.STORY_STAGE_LIST: (open_sortie_prep(),)})

    assert agent.candidates(seen(LIST, 1.0)) == {
        Screen.STORY_STAGE_LIST,
        Screen.SORTIE_PREP,
        Screen.POWER_SAVE_LOCK,
        Screen.POWER_SAVE_DIM,
        Screen.LOADING,
        Screen.SIMPLIFY_WEAPON_ANIME,
        Screen.EX_WEAPON_ANIME,
        Screen.BATTLE_CLEAR_VIEW,
        Screen.MAP_PASSING,
    }


def test_lost_belief_offers_every_screen():
    agent = make_agent(FakeStream([]), {}, ScriptedController([], goals=[]))
    lost = replace(seen(LIST, 1.0), ui_basis=UiBasis(UiSource.LOST, 1))

    assert agent.candidates(lost) == frozenset(Screen)


def test_sense_logs_a_screen_outside_the_candidates(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.WARNING, logger="ggge_ai_2.agent.loop")
    shows = {1: Screen.BATTLE_SCORE_RESULT}
    agent = make_agent(FakeStream(still(1, 1.0)), shows, ScriptedController([], goals=[]))
    agent.belief = seen(LIST, 1.0)

    agent.sense()

    [record] = logged(caplog, "outside candidates")
    assert record.__dict__["frame_seq"] == 1
    assert record.__dict__["screen"] is Screen.BATTLE_SCORE_RESULT
    assert record.__dict__["candidates"] == sorted(
        screen.value for screen in agent.candidates(agent.belief)
    )


def test_controller_without_a_plan_halts_the_loop():
    controller = ScriptedController([None], goals=[False])
    actuator = FakeActuator()
    agent = make_agent(
        FakeStream(still(1, 1.0)), {1: Screen.STORY_STAGE_LIST}, controller, actuator
    )

    assert agent.run() is RunResult.HALTED
    assert controller.thought == [(controller.checked[0], ())]
    assert actuator.sent == []


def test_step_that_passes_the_guard_sends_its_gesture_and_band():
    plan = ScriptedPlan([step()])
    controller = ScriptedController([plan], goals=[False, True])
    stream = FakeStream([*still(1, 1.0), *still(2, 11.0)])
    actuator = FakeActuator()
    shows = {1: Screen.STORY_STAGE_LIST, 2: Screen.SORTIE_PREP}

    assert make_agent(stream, shows, controller, actuator).run() is RunResult.DONE
    assert actuator.sent == [(TAP, BAND)]
    assert controller.reviewed == [plan]


def test_guard_on_an_unreadable_screen_halts_and_logs_the_evidence(
    caplog: pytest.LogCaptureFixture,
):
    caplog.set_level(logging.ERROR, logger="ggge_ai_2.agent.loop")
    controller = ScriptedController([ScriptedPlan([step()])], goals=[False])
    actuator = FakeActuator()
    agent = make_agent(FakeStream(still(4, 1.0)), {}, controller, actuator)

    assert agent.run() is RunResult.HALTED
    assert actuator.sent == []
    [record] = logged(caplog, "guard on an unreadable screen")
    assert record.__dict__["unreadable_since_frame_seq"] == 4


def test_mismatches_up_to_the_limit_end_the_plan():
    plan = ScriptedPlan([step()] * MISMATCH_LIMIT)
    controller = ScriptedController([plan, None], goals=[False] * (MISMATCH_LIMIT + 1))
    unchanged = [shot for n in range(1, MISMATCH_LIMIT + 2) for shot in still(n, 10.0 + n)]
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
    frames = [shot for n in range(1, cycles + 1) for shot in still(n, 10.0 + n * 0.5)]
    shows = dict.fromkeys(range(1, cycles + 1), Screen.STORY_STAGE_LIST)

    assert make_agent(FakeStream(frames), shows, controller).run() is RunResult.DONE
    assert len(controller.thought) == 2


def test_match_between_mismatches_restarts_the_count():
    opens = [step()] * MISMATCH_LIMIT
    plan = ScriptedPlan([*opens, step(LIST, "close_info"), step(LIST, "close_info")])
    cycles = MISMATCH_LIMIT + 3
    controller = ScriptedController([plan, None], goals=[False] * (cycles - 1) + [True])
    frames = [shot for n in range(1, cycles + 1) for shot in still(n, 10.0 + n * 0.5)]
    shows = dict.fromkeys(range(1, MISMATCH_LIMIT + 1), Screen.STORY_STAGE_LIST)
    shows[MISMATCH_LIMIT + 1] = Screen.SORTIE_PREP
    shows[MISMATCH_LIMIT + 2] = Screen.SORTIE_PREP

    assert make_agent(FakeStream(frames), shows, controller).run() is RunResult.DONE
    assert len(controller.thought) == 1


def test_belief_equal_to_the_second_expected_belief_is_no_mismatch():
    either = Step("start_battle", TAP, BAND, DEADLINE, (expected(INFO), expected(LIST)))
    plan = ScriptedPlan([either] * MISMATCH_LIMIT)
    cycles = MISMATCH_LIMIT + 1
    controller = ScriptedController([plan, None], goals=[False] * (cycles - 1) + [True])
    frames = [shot for n in range(1, cycles + 1) for shot in still(n, 10.0 + n * 0.5)]
    shows = dict.fromkeys(range(1, cycles + 1), Screen.STORY_STAGE_LIST)

    assert make_agent(FakeStream(frames), shows, controller).run() is RunResult.DONE
    assert len(controller.thought) == 1


def test_wait_step_sends_no_gesture_and_is_compared_on_the_next_cycle(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
):
    caplog.set_level(logging.INFO, logger="ggge_ai_2.agent.loop")
    monkeypatch.setattr("ggge_ai_2.agent.loop.now", lambda: 5.0)
    wait = Step("enemy_turn", None, (), DEADLINE, (expected(INFO),))
    plan = ScriptedPlan([wait, wait])
    controller = ScriptedController([plan], goals=[False, False, True])
    stream = FakeStream([*still(1, 1.0), *still(2, 6.0), *still(3, 7.0)])
    shows = {1: Screen.STORY_STAGE_LIST, 2: Screen.SORTIE_PREP, 3: Screen.SORTIE_PREP}
    actuator = FakeActuator()

    assert make_agent(stream, shows, controller, actuator).run() is RunResult.DONE
    assert actuator.sent == []
    [first] = logged(caplog, "matches")
    assert first.__dict__["same"]
    assert first.__dict__["in_time"]
    assert len(logged(caplog, "wait")) == 2


def test_invalid_plan_is_reviewed_and_replaced():
    plan = ScriptedPlan([step()], valid=[False])
    controller = ScriptedController([plan, None], goals=[False, False])
    stream = FakeStream([*still(1, 1.0), *still(2, 11.0)])
    shows = {1: Screen.STORY_STAGE_LIST, 2: Screen.SORTIE_PREP}

    assert make_agent(stream, shows, controller).run() is RunResult.HALTED
    assert controller.reviewed == [plan]
    assert controller.thought[1][1] == (plan,)


def test_blocked_gesture_leaves_nothing_to_compare(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO, logger="ggge_ai_2.agent.loop")
    plan = ScriptedPlan([step(), step(LIST, "close_info"), step(LIST, "close_info")])
    controller = ScriptedController([plan], goals=[False, False, False, True])
    stream = FakeStream([*still(1, 1.0), *still(2, 11.0), *still(3, 12.0), *still(4, 13.0)])
    shows = {1: Screen.STORY_STAGE_LIST, 2: Screen.SORTIE_PREP, 3: Screen.SORTIE_PREP}
    actuator = FakeActuator(blocks=[False, True, True])

    assert make_agent(stream, shows, controller, actuator).run() is RunResult.DONE
    assert len(logged(caplog, "matches")) == 1


def test_stop_request_ends_the_loop_between_cycles():
    stop = Event()
    stop.set()
    agent = make_agent(FakeStream([]), {}, ScriptedController([], goals=[]), stop=stop)

    assert agent.run() is RunResult.STOPPED


def test_run_log_records_one_line_per_cycle_and_saves_only_the_mismatching_frame(
    tmp_path: Path,
):
    plan = ScriptedPlan([step(), step(LIST, "close_info"), step()])
    controller = ScriptedController([plan], goals=[False, False, False, True])
    stream = FakeStream([*still(1, 1.0), *still(2, 11.0), *still(3, 12.0), *still(4, 13.0)])
    shows = {
        1: Screen.STORY_STAGE_LIST,
        2: Screen.SORTIE_PREP,
        3: Screen.SORTIE_PREP,
        4: Screen.SORTIE_PREP,
    }
    run_dir = tmp_path / "run"

    agent = make_agent(stream, shows, controller, runlog=RunLog(run_dir))

    assert agent.run() is RunResult.DONE
    lines = (run_dir / "steps.jsonl").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert [
        (r["frame_seq"], r["interpreted"], r["expected"], r["matched"], r["step"]) for r in records
    ] == [
        (1, "story_stage_list", [], None, "open_info"),
        (2, "sortie_prep", ["sortie_prep"], True, "close_info"),
        (3, "sortie_prep", ["story_stage_list"], False, "open_info"),
        (4, "sortie_prep", ["sortie_prep"], None, None),
    ]
    assert sorted(path.name for path in (run_dir / "frames").iterdir()) == ["000003.png"]


def seen(ui: UiState, at: float, camera: Alignment | None = None) -> Belief:
    return Belief(ui, UiBasis(UiSource.SEEN, 1), camera, KnownMap({}), FakeDomain(), window(1, at))


def predicted(camera: Alignment | None = None) -> Predicted:
    return Predicted((expected(INFO, camera),), DISPATCHED.t1 + DEADLINE)


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
