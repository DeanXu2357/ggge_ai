from __future__ import annotations

import logging
from dataclasses import dataclass, field
from threading import Event

import numpy as np
import pytest

from ggge_ai_2.actuator.contract import Dispatch, Gesture, GestureBlocked, Key, Rect, Tap
from ggge_ai_2.agent.loop import Agent, Belief, RunResult, ScreenSize, UiBasis, UiSource
from ggge_ai_2.interpreter.contract import MapMode, Screen, Situation
from ggge_ai_2.mapgeom.contract import Alignment, CellContent, KnownMap
from ggge_ai_2.mapparser.contract import CellReading, MapReading, ViewCell
from ggge_ai_2.planner.contract import (
    ActionResult,
    ActionStatus,
    Finish,
    Refused,
    State,
    Step,
    Wait,
)
from ggge_ai_2.stream.contract import NO_DISPLACEMENT, Frame, Observation, StillWindow
from ggge_ai_2.uisim.contract import (
    DangerBand,
    Operation,
    Outcome,
    RatioRect,
    UiMapMode,
    UiScreen,
    UiState,
    UiTap,
)
from tests.ggge_ai_2.fakes.domain import FakeDomain
from tests.ggge_ai_2.fakes.mapgeom import NoMapGeometry
from tests.ggge_ai_2.fakes.uisim import FakeUiSim

LIST = UiState(UiScreen.STAGE_LIST)
INFO = UiState(UiScreen.STAGE_INFO)
OPEN_INFO = Operation(
    name="open_info",
    precondition=LIST,
    gesture=UiTap((0.1, 0.2)),
    outcomes=(Outcome("info_open", INFO),),
    deadline=3.0,
    cost=1.0,
)
INFO_OPEN = OPEN_INFO.outcomes[0]
BANDS = {
    UiScreen.STAGE_LIST: DangerBand((RatioRect(0.0, 0.0, 0.05, 0.1),)),
    UiScreen.STAGE_INFO: DangerBand(),
}
LIST_BAND = (Rect(0, 0, 50, 50),)
SCREEN = ScreenSize(1000, 500)


def frame(seq: int, at: float) -> Frame:
    return Frame(np.zeros((1, 1, 3), np.uint8), at, seq)


Settle = tuple[Frame, StillWindow | None]


def still(seq: int, at: float) -> Settle:
    return frame(seq, at), StillWindow(at - 0.5, at, seq)


def moving(seq: int, at: float) -> Settle:
    return frame(seq, at), None


@dataclass
class FakeStream:
    settles: list[Settle]
    latest_frame: Frame = field(default_factory=lambda: frame(0, 0.0))
    calls: list[tuple[float, float]] = field(default_factory=list)

    def latest(self) -> Frame:
        return self.latest_frame

    def settled(self, after: float, deadline: float) -> Observation:
        self.calls.append((after, deadline))
        shown, window = self.settles.pop(0)
        return Observation(shown, after, window, 0.5, NO_DISPLACEMENT)


@dataclass
class FakeInterpreter:
    shows: dict[int, Situation]

    def interpret(self, frame: Frame) -> Situation | None:
        return self.shows.get(frame.seq)


def screens(**by_seq: str) -> dict[int, Situation]:
    return {int(k[1:]): Situation(int(k[1:]), Screen(v)) for k, v in by_seq.items()}


@dataclass
class FakeActuator:
    sent: list[tuple[Gesture, tuple[Rect, ...]]] = field(default_factory=list)
    blocks: bool = False

    def dispatch(self, gesture: Gesture, band: tuple[Rect, ...]) -> Dispatch:
        if self.blocks:
            raise GestureBlocked
        self.sent.append((gesture, band))
        return Dispatch(10.0, 10.1)


@dataclass
class Closures:
    gesture: Gesture | Refused = Tap((100, 100))
    outcome: Outcome | None = None
    stop: bool = False
    guarded: list[int] = field(default_factory=list)
    verified: list[int] = field(default_factory=list)
    judged: list[int] = field(default_factory=list)

    def guard(self, shown: Frame) -> Gesture | Refused:
        self.guarded.append(shown.seq)
        return self.gesture

    def verify(self, shown: Frame) -> Outcome | None:
        self.verified.append(shown.seq)
        return self.outcome

    def interrupt(self, shown: Frame) -> bool:
        self.judged.append(shown.seq)
        return self.stop

    def step(self, operation: Operation = OPEN_INFO, frame_after: float | None = None) -> Step:
        return Step("look", operation, self.guard, self.verify, self.interrupt, frame_after)


@dataclass
class ScriptedPlanner:
    steps: list[Step | Wait | Finish]
    seen: list[State] = field(default_factory=list)
    agendas: list[int] = field(default_factory=list)

    def plan(self, state: State, agenda: int) -> tuple[Step | Wait | Finish, int]:
        self.seen.append(state)
        self.agendas.append(agenda)
        return self.steps.pop(0), agenda + 1

    def acted(self, cycle: int) -> ActionResult:
        last = self.seen[cycle].last_action
        assert last is not None
        return last

    def absorbed(self, cycle: int) -> tuple[tuple[object, str | None], ...]:
        domain = self.seen[cycle].domain
        assert isinstance(domain, FakeDomain)
        return domain.absorbed


class NoMapParser:
    def parse(self, frame: Frame) -> MapReading | None:
        raise AssertionError("no map on these screens")

    def locate(self, frame: Frame, cell: ViewCell) -> tuple[int, int] | None:
        raise AssertionError("no map on these screens")


def initial_belief() -> Belief:
    return Belief(
        ui=UiState(UiScreen.LOGIN_BONUS),
        ui_basis=UiBasis(UiSource.ASSUMED),
        camera=None,
        known_map=KnownMap({}),
        domain=FakeDomain(),
        as_of=None,
    )


def make_agent(
    stream,
    interpreter,
    planner,
    actuator=None,
    *,
    mapparser=None,
    mapgeom=None,
    uisim=None,
    stop=None,
) -> Agent[int]:
    return Agent(
        stream=stream,
        interpreter=interpreter,
        mapparser=mapparser or NoMapParser(),
        mapgeom=mapgeom or NoMapGeometry(),
        uisim=uisim or FakeUiSim(BANDS),
        actuator=actuator or FakeActuator(),
        screen=SCREEN,
        planner=planner,
        belief=initial_belief(),
        agenda=0,
        idle_deadline=2.0,
        stop=stop or Event(),
    )


def run_one_step(
    closures: Closures,
    *,
    result: Settle = still(2, 11.0),
    latest: Frame = frame(1, 1.0),
    shows: dict[int, Situation] | None = None,
    frame_after: float | None = None,
    actuator: FakeActuator | None = None,
    then: Finish = Finish.DONE,
) -> tuple[RunResult, FakeStream, ScriptedPlanner]:
    stream = FakeStream([still(1, 1.0), result, still(3, result[0].captured_at + 1.0)])
    stream.latest_frame = latest
    planner = ScriptedPlanner([closures.step(frame_after=frame_after), then])
    interpreter = FakeInterpreter(
        shows or screens(f1="stage_list", f2="stage_info", f3="stage_info")
    )
    ran = make_agent(stream, interpreter, planner, actuator).run()
    return ran, stream, planner


def test_first_observation_interprets_the_frame_and_syncs_the_prediction():
    planner = ScriptedPlanner([Finish.DONE])
    agent = make_agent(
        FakeStream([still(1, 1.0)]), FakeInterpreter(screens(f1="stage_list")), planner
    )

    assert agent.run() is RunResult.DONE
    assert planner.seen[0].ui == LIST
    assert not planner.seen[0].ui_lost
    assert planner.seen[0].as_of == 1.0
    assert agent.belief.ui_basis == UiBasis(UiSource.SEEN, frame_seq=1)
    assert agent.belief.as_of == StillWindow(0.5, 1.0, 1)


def test_observation_waits_until_the_screen_is_still():
    stream = FakeStream([moving(1, 1.0), still(2, 1.5)])
    planner = ScriptedPlanner([Finish.DONE])
    make_agent(stream, FakeInterpreter(screens(f2="stage_list")), planner).run()

    assert [after for after, _ in stream.calls] == [0.0, 1.0]
    assert planner.seen[0].as_of == 1.5


def test_guard_closure_receives_the_latest_frame():
    closures = Closures(outcome=INFO_OPEN)
    run_one_step(closures, latest=frame(7, 1.2))

    assert closures.guarded == [7]


def test_refused_guard_sends_no_gesture_and_reports_the_refusal():
    refusal = Refused("a dialog covers the stage list")
    closures = Closures(gesture=refusal)
    actuator = FakeActuator()
    stream = FakeStream([still(1, 1.0), still(3, 2.0)])
    stream.latest_frame = frame(2, 1.2)
    planner = ScriptedPlanner([closures.step(), Finish.DONE])
    make_agent(stream, FakeInterpreter(screens(f1="stage_list")), planner, actuator).run()

    assert actuator.sent == []
    assert closures.verified == []
    assert planner.acted(1).status is ActionStatus.GUARD_FAILED
    assert planner.acted(1).refused == refusal
    assert stream.calls[1][0] == 1.2


def test_guard_gesture_reaches_the_actuator_unchanged():
    actuator = FakeActuator()
    run_one_step(Closures(gesture=Key("back"), outcome=INFO_OPEN), actuator=actuator)

    assert actuator.sent == [(Key("back"), LIST_BAND)]


def test_guard_frame_not_newer_than_the_step_requires_is_refused_unseen():
    closures = Closures(outcome=INFO_OPEN)
    actuator = FakeActuator()
    stream = FakeStream([still(1, 1.0), still(3, 2.0)])
    stream.latest_frame = frame(1, 1.0)
    planner = ScriptedPlanner([closures.step(frame_after=1.0), Finish.DONE])
    make_agent(stream, FakeInterpreter(screens(f1="stage_list")), planner, actuator).run()

    assert closures.guarded == []
    assert actuator.sent == []
    assert planner.acted(1).status is ActionStatus.GUARD_FAILED
    assert planner.acted(1).refused is not None


def test_guard_frame_newer_than_the_step_requires_reaches_the_guard_closure():
    closures = Closures(outcome=INFO_OPEN)
    run_one_step(closures, latest=frame(1, 1.0), frame_after=0.9)

    assert closures.guarded == [1]


def test_verification_closure_receives_the_still_result_frame():
    closures = Closures(outcome=INFO_OPEN)
    _, stream, _ = run_one_step(closures)

    assert closures.verified == [2]
    assert stream.calls[1] == (10.0, 10.1 + OPEN_INFO.deadline)


def test_verified_outcome_advances_the_prediction_and_reaches_the_domain():
    closures = Closures(outcome=INFO_OPEN)
    _, _, planner = run_one_step(closures, shows=screens(f1="stage_list"))

    assert planner.seen[1].ui == INFO
    assert planner.absorbed(1) == (("look", "info_open"),)
    assert planner.acted(1).status is ActionStatus.VERIFIED
    assert closures.judged == []


def test_failed_verification_asks_the_interrupt_closure_about_the_same_frame():
    closures = Closures(outcome=None)
    run_one_step(closures)

    assert closures.verified == [2]
    assert closures.judged == [2]


def test_interrupt_that_does_not_stop_lets_the_cycle_finish():
    closures = Closures(outcome=None, stop=False)
    ran, stream, planner = run_one_step(
        closures, shows=screens(f1="stage_list", f2="notice", f3="notice")
    )

    assert ran is RunResult.DONE
    assert planner.seen[1].ui == UiState(UiScreen.NOTICE)
    assert planner.absorbed(1) == (("look", None),)
    assert planner.acted(1).status is ActionStatus.UNVERIFIED
    assert stream.calls[2][0] == 11.0


def test_interrupt_that_stops_ends_the_run_as_halted():
    closures = Closures(outcome=None, stop=True)
    stream = FakeStream([still(1, 1.0), still(2, 11.0)])
    stream.latest_frame = frame(1, 1.0)
    planner = ScriptedPlanner([closures.step()])
    interpreter = FakeInterpreter(screens(f1="stage_list", f2="notice"))

    assert make_agent(stream, interpreter, planner).run() is RunResult.HALTED
    assert len(planner.seen) == 1
    assert len(stream.calls) == 2


def test_result_that_is_not_still_at_the_deadline_logs_an_error_and_calls_no_closure(
    caplog: pytest.LogCaptureFixture,
):
    caplog.set_level(logging.ERROR, logger="ggge_ai_2.agent.loop")
    closures = Closures(outcome=INFO_OPEN)
    _, stream, planner = run_one_step(closures, result=moving(2, 13.0))

    assert closures.verified == []
    assert closures.judged == []
    assert planner.absorbed(1) == (("look", None),)
    assert planner.acted(1).status is ActionStatus.UNVERIFIED
    assert [r.levelno for r in caplog.records] == [logging.ERROR]
    assert stream.calls[2][0] == 13.0


def test_blocked_gesture_is_reported_to_the_planner():
    closures = Closures(outcome=INFO_OPEN)
    stream = FakeStream([still(1, 1.0), still(2, 2.0)])
    stream.latest_frame = frame(1, 1.0)
    planner = ScriptedPlanner([closures.step(), Finish.HALTED])
    interpreter = FakeInterpreter(screens(f1="stage_list", f2="stage_list"))
    agent = make_agent(stream, interpreter, planner, FakeActuator(blocks=True))

    assert agent.run() is RunResult.HALTED
    assert planner.acted(1).status is ActionStatus.BLOCKED
    assert closures.verified == []
    assert stream.calls[1][0] == 1.0


def test_planner_gets_back_the_agenda_it_returned():
    _, _, planner = run_one_step(Closures(outcome=INFO_OPEN))

    assert planner.agendas == [0, 1]


def test_wait_goes_back_to_observation_without_a_gesture():
    stream = FakeStream([still(1, 1.0), still(2, 2.0)])
    actuator = FakeActuator()
    planner = ScriptedPlanner([Wait(), Finish.DONE])
    interpreter = FakeInterpreter(screens(f1="stage_list", f2="stage_list"))

    assert make_agent(stream, interpreter, planner, actuator).run() is RunResult.DONE
    assert actuator.sent == []
    assert [after for after, _ in stream.calls] == [0.0, 1.0]


def test_unreadable_screen_is_left_to_the_planner():
    planner = ScriptedPlanner([Finish.HALTED])
    agent = make_agent(FakeStream([still(1, 1.0)]), FakeInterpreter({}), planner)

    assert agent.run() is RunResult.HALTED
    assert planner.seen[0].ui_lost
    assert agent.belief.ui_basis == UiBasis(UiSource.LOST, frame_seq=1)


@dataclass
class GridParser:
    unreadable: frozenset[int] = frozenset()

    def parse(self, frame: Frame) -> MapReading | None:
        if frame.seq in self.unreadable:
            return None
        return MapReading({(2, 2): CellReading.EMPTY}, frozenset())

    def locate(self, frame: Frame, cell: ViewCell) -> tuple[int, int] | None:
        return (cell[0] * 100 + 50, cell[1] * 100 + 50)


@dataclass
class ScriptedGeometry:
    shifts: list[tuple[int, int] | None]
    priors: list[Alignment | None] = field(default_factory=list)

    def align(self, board, known, prior):
        self.priors.append(prior)
        shift = self.shifts.pop(0) if len(self.shifts) > 1 else self.shifts[0]
        return None if shift is None else Alignment(shift)

    def merge(self, known, board, alignment):
        dx, dy = alignment.shift
        seen = {(x + dx, y + dy): content for (x, y), content in board.cells.items()}
        return KnownMap({**known.cells, **seen})


ON_MAP = UiState(UiScreen.BATTLE_MAP, map_mode=UiMapMode.HUB)
TAP_CELL = Operation("tap_cell", ON_MAP, UiTap((0.25, 0.5)), (), 1.0, 1.0)


def run_on_map(settles, geometry, steps, latest=frame(2, 1.2), parser=None):
    stream = FakeStream(settles)
    stream.latest_frame = latest
    seqs = {shown.seq for shown, _ in settles} | {latest.seq}
    on_map = {n: Situation(n, Screen.BATTLE_MAP, map_mode=MapMode.HUB) for n in seqs}
    actuator = FakeActuator()
    planner = ScriptedPlanner(steps)
    make_agent(
        stream,
        FakeInterpreter(on_map),
        planner,
        actuator,
        mapparser=parser or GridParser(),
        mapgeom=geometry,
        uisim=FakeUiSim({UiScreen.BATTLE_MAP: DangerBand()}),
    ).run()
    return actuator, planner


def test_map_screen_puts_the_alignment_and_the_merged_map_into_the_belief():
    geometry = ScriptedGeometry([(10, 5)])
    _, planner = run_on_map([still(1, 1.0)], geometry, [Finish.DONE])

    assert geometry.priors == [None]
    assert planner.seen[0].camera == Alignment((10, 5))
    assert planner.seen[0].known_map == KnownMap({(12, 7): CellContent.EMPTY})


def test_unreadable_grid_keeps_the_camera():
    settles = [still(1, 1.0), still(2, 11.0), still(3, 12.0)]
    steps: list[Step | Wait | Finish] = [
        Closures(gesture=Tap((250, 250))).step(TAP_CELL),
        Finish.DONE,
    ]
    _, planner = run_on_map(
        settles,
        ScriptedGeometry([(10, 5)]),
        steps,
        latest=frame(1, 1.0),
        parser=GridParser(frozenset({3})),
    )

    assert planner.seen[1].camera == Alignment((10, 5))


def test_stop_request_ends_the_loop_between_cycles():
    stop = Event()
    stop.set()
    agent = make_agent(FakeStream([]), FakeInterpreter({}), ScriptedPlanner([]), stop=stop)

    assert agent.run() is RunResult.STOPPED
