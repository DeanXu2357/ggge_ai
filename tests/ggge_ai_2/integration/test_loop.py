from __future__ import annotations

from dataclasses import dataclass, field, replace
from threading import Event

import numpy as np

from ggge_ai_2.actuator.contract import Dispatch, GestureBlocked, Rect, Tap
from ggge_ai_2.agent.loop import Agent, Belief, RunResult, ScreenSize, UiBasis, UiSource
from ggge_ai_2.interpreter.contract import MapMode, Overlay, Screen, Situation
from ggge_ai_2.mapgeom.contract import Alignment, CellAt, CellContent, CellHolds, KnownMap
from ggge_ai_2.mapparser.contract import CellReading, MapReading
from ggge_ai_2.planner.contract import ActionStatus, Finish, State, Step, Wait
from ggge_ai_2.stream.contract import NO_DISPLACEMENT, Frame, Observation, StillWindow
from ggge_ai_2.uisim.contract import (
    DangerBand,
    Operation,
    Outcome,
    RatioRect,
    UiMapMode,
    UiOverlay,
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
BANDS = {
    UiScreen.STAGE_LIST: DangerBand((RatioRect(0.0, 0.0, 0.05, 0.1),)),
    UiScreen.STAGE_INFO: DangerBand(),
}
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

    def interpret(self, f: Frame) -> Situation | None:
        return self.shows.get(f.seq)


def screens(**by_seq: str) -> dict[int, Situation]:
    return {int(k[1:]): Situation(int(k[1:]), Screen(v)) for k, v in by_seq.items()}


@dataclass
class FakeActuator:
    sent: list[tuple[object, tuple[Rect, ...]]] = field(default_factory=list)
    blocks: bool = False

    def dispatch(self, gesture, band: tuple[Rect, ...]) -> Dispatch:
        if self.blocks:
            raise GestureBlocked
        self.sent.append((gesture, band))
        return Dispatch(10.0, 10.1)


@dataclass
class ScriptedPlanner:
    steps: list[Step | Wait | Finish]
    seen: list[State] = field(default_factory=list)
    agendas: list[int] = field(default_factory=list)

    def plan(self, state: State, agenda: int) -> tuple[Step | Wait | Finish, int]:
        self.seen.append(state)
        self.agendas.append(agenda)
        step = self.steps.pop(0)
        if isinstance(step, Step):
            step = replace(step, based_on=state.as_of)
        return step, agenda + 1


class NoMapParser:
    def parse(self, f: Frame) -> MapReading | None:
        raise AssertionError("no map on these screens")

    def locate(self, f: Frame, cell):
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


def make_agent(stream, interpreter, planner, actuator=None, **overrides) -> Agent:
    mapgeom = overrides.pop("mapgeom", NoMapGeometry())
    kwargs = dict(
        stream=stream,
        interpreter=interpreter,
        mapparser=NoMapParser(),
        mapgeom=mapgeom,
        actuator=actuator or FakeActuator(),
        uisim=FakeUiSim(BANDS),
        screen=SCREEN,
        planner=planner,
        belief=initial_belief(),
        agenda=0,
        idle_deadline=2.0,
    )
    kwargs.update(overrides)
    return Agent(**kwargs)


def open_info_step() -> Step:
    return Step(intent="look", operation=OPEN_INFO, domain_premise=(), based_on=0.0)


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


def test_verified_outcome_advances_the_prediction_and_reaches_the_domain():
    stream = FakeStream([still(1, 1.0), still(2, 11.0), still(3, 12.0)])
    stream.latest_frame = frame(1, 1.0)
    actuator = FakeActuator()
    planner = ScriptedPlanner([open_info_step(), Finish.DONE])
    interpreter = FakeInterpreter(screens(f1="stage_list", f2="stage_info", f3="stage_info"))

    assert make_agent(stream, interpreter, planner, actuator).run() is RunResult.DONE
    assert actuator.sent == [(Tap((100, 100)), (Rect(0, 0, 50, 50),))]
    assert stream.calls[1] == (10.0, 10.1 + OPEN_INFO.deadline)
    assert stream.calls[2][0] == 11.0
    assert planner.seen[1].ui == INFO
    assert planner.seen[1].domain.absorbed == (("look", "info_open"),)
    assert planner.seen[1].last_action.status is ActionStatus.VERIFIED


def test_planner_gets_back_the_agenda_it_returned():
    stream = FakeStream([still(1, 1.0), still(2, 11.0), still(3, 12.0)])
    stream.latest_frame = frame(1, 1.0)
    planner = ScriptedPlanner([open_info_step(), Finish.DONE])
    interpreter = FakeInterpreter(screens(f1="stage_list", f2="stage_info", f3="stage_info"))
    make_agent(stream, interpreter, planner).run()

    assert planner.agendas == [0, 1]


def test_failed_guard_sends_no_gesture():
    stream = FakeStream([still(1, 1.0), still(3, 2.0)])
    stream.latest_frame = frame(2, 1.2)
    actuator = FakeActuator()
    planner = ScriptedPlanner([open_info_step(), Finish.DONE])
    interpreter = FakeInterpreter(screens(f1="stage_list", f2="stage_info", f3="stage_info"))
    make_agent(stream, interpreter, planner, actuator).run()

    assert actuator.sent == []
    assert stream.calls[1][0] == 1.2
    assert planner.seen[1].ui == INFO
    assert planner.seen[1].domain.absorbed == ()
    assert planner.seen[1].last_action.status is ActionStatus.GUARD_FAILED


def test_guard_sends_no_gesture_when_a_dialog_covers_the_screen():
    stream = FakeStream([still(1, 1.0), still(3, 2.0)])
    stream.latest_frame = frame(2, 1.2)
    actuator = FakeActuator()
    planner = ScriptedPlanner([open_info_step(), Finish.DONE])
    covered = Situation(2, Screen.STAGE_LIST, frozenset({Overlay.DIALOG}))
    interpreter = FakeInterpreter({1: Situation(1, Screen.STAGE_LIST), 2: covered, 3: covered})
    make_agent(stream, interpreter, planner, actuator).run()

    assert actuator.sent == []
    assert planner.seen[1].ui == UiState(UiScreen.STAGE_LIST, frozenset({UiOverlay.DIALOG}))


def test_blocked_gesture_is_reported_to_the_planner():
    stream = FakeStream([still(1, 1.0), still(2, 2.0)])
    stream.latest_frame = frame(1, 1.0)
    planner = ScriptedPlanner([open_info_step(), Finish.HALTED])
    interpreter = FakeInterpreter(screens(f1="stage_list", f2="stage_list"))
    agent = make_agent(stream, interpreter, planner, FakeActuator(blocks=True))

    assert agent.run() is RunResult.HALTED
    assert planner.seen[1].last_action.status is ActionStatus.BLOCKED
    assert stream.calls[1][0] == 1.0


def test_wait_goes_back_to_observation_without_a_gesture():
    stream = FakeStream([still(1, 1.0), still(2, 2.0)])
    actuator = FakeActuator()
    planner = ScriptedPlanner([Wait(), Finish.DONE])
    interpreter = FakeInterpreter(screens(f1="stage_list", f2="stage_list"))

    assert make_agent(stream, interpreter, planner, actuator).run() is RunResult.DONE
    assert actuator.sent == []
    assert [after for after, _ in stream.calls] == [0.0, 1.0]


@dataclass
class GridParser:
    unreadable: frozenset[int] = frozenset()

    def parse(self, f: Frame) -> MapReading | None:
        if f.seq in self.unreadable:
            return None
        return MapReading({(2, 2): CellReading.EMPTY}, frozenset())

    def locate(self, f: Frame, cell):
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


def run_map_tap(premise, guard_shift=(10, 5), unreadable=frozenset()) -> FakeActuator:
    geometry = ScriptedGeometry([(10, 5)] if unreadable else [(10, 5), guard_shift, (10, 5)])
    settles = [still(1, 1.0), still(3, 12.0), still(4, 13.0)]
    steps = [Step("probe", TAP_CELL, premise, 0.0), Finish.DONE]
    actuator, _ = run_on_map(settles, geometry, steps, parser=GridParser(unreadable))
    return actuator


def test_guard_sends_the_gesture_when_the_board_premise_holds():
    premise = (CellAt((250, 250), (12, 7)), CellHolds((12, 7), CellContent.EMPTY))

    assert run_map_tap(premise).sent == [(Tap((250, 250)), ())]


def test_guard_sends_no_gesture_when_the_camera_moved():
    assert run_map_tap((CellAt((250, 250), (12, 7)),), guard_shift=(11, 5)).sent == []


def test_guard_sends_no_gesture_when_the_grid_is_unreadable():
    assert run_map_tap((CellAt((250, 250), (12, 7)),), unreadable=frozenset({2})).sent == []


def test_guard_sends_no_gesture_when_the_board_has_no_place_on_the_known_map():
    assert run_map_tap((CellAt((250, 250), (12, 7)),), guard_shift=None).sent == []


def test_step_keeps_the_ui_and_the_domain_premise_apart():
    board_fact = CellAt((250, 250), (12, 7))
    premise = Step("probe", TAP_CELL, (board_fact,), 0.0).premise

    assert premise.ui == ON_MAP
    assert premise.domain == (board_fact,)


def test_unexpected_result_is_absorbed_as_none_and_corrected_by_the_next_observation():
    stream = FakeStream([still(1, 1.0), still(2, 11.0), still(3, 12.0)])
    stream.latest_frame = frame(1, 1.0)
    planner = ScriptedPlanner([open_info_step(), Finish.DONE])
    interpreter = FakeInterpreter(screens(f1="stage_list", f2="notice", f3="notice"))
    make_agent(stream, interpreter, planner).run()

    assert planner.seen[1].ui == UiState(UiScreen.NOTICE)
    assert planner.seen[1].domain.absorbed == (("look", None),)
    assert planner.seen[1].last_action.status is ActionStatus.UNVERIFIED


def test_result_that_is_not_still_at_the_deadline_is_not_verified():
    stream = FakeStream([still(1, 1.0), moving(2, 13.0), still(3, 14.0)])
    stream.latest_frame = frame(1, 1.0)
    planner = ScriptedPlanner([open_info_step(), Finish.DONE])
    interpreter = FakeInterpreter(screens(f1="stage_list", f2="stage_info", f3="stage_info"))
    make_agent(stream, interpreter, planner).run()

    assert planner.seen[1].domain.absorbed == (("look", None),)
    assert stream.calls[2][0] == 13.0


def test_unreadable_screen_is_left_to_the_planner():
    planner = ScriptedPlanner([Finish.HALTED])
    agent = make_agent(FakeStream([still(1, 1.0)]), FakeInterpreter({}), planner)

    assert agent.run() is RunResult.HALTED
    assert planner.seen[0].ui_lost
    assert agent.belief.ui_basis == UiBasis(UiSource.LOST, frame_seq=1)


def test_map_screen_puts_the_alignment_and_the_merged_map_into_the_belief():
    geometry = ScriptedGeometry([(10, 5)])
    _, planner = run_on_map([still(1, 1.0)], geometry, [Finish.DONE])

    assert geometry.priors == [None]
    assert planner.seen[0].camera == Alignment((10, 5))
    assert planner.seen[0].known_map == KnownMap({(12, 7): CellContent.EMPTY})


def test_unreadable_grid_keeps_the_camera():
    settles = [still(1, 1.0), still(2, 11.0), still(3, 12.0)]
    steps = [Step("probe", TAP_CELL, (), 0.0), Finish.DONE]
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
