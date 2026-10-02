from __future__ import annotations

from dataclasses import dataclass, field, replace
from threading import Event

import numpy as np

from ggge_ai_2.actuator.contract import Dispatch, GestureBlocked, Rect, Tap
from ggge_ai_2.agent.belief import ActionStatus, Belief, UiBasis, UiSource
from ggge_ai_2.agent.loop import Agent, RunResult, ScreenSize
from ggge_ai_2.agent.step import Finish, Step, Wait
from ggge_ai_2.interpreter.contract import Fact, Situation, Verdict
from ggge_ai_2.mapgeom.contract import CellAt, CellContent, CellHolds, LocalBoard
from ggge_ai_2.mapparser.contract import MapReading
from ggge_ai_2.stream.contract import NO_DISPLACEMENT, Frame, Observation, StillWindow
from ggge_ai_2.uisim.contract import (
    DangerBand,
    Operation,
    Outcome,
    RatioRect,
    UiState,
    UiTap,
)
from tests.ggge_ai_2.fakes.domain import FakeDomain
from tests.ggge_ai_2.fakes.mapgeom import NoMapGeometry
from tests.ggge_ai_2.fakes.uisim import FakeUiSim

HUB = UiState("hub")
MENU = UiState("menu")
OPEN_MENU = Operation(
    name="open_menu",
    precondition=HUB,
    gesture=UiTap((0.1, 0.2)),
    outcomes=(Outcome("menu_open", MENU),),
    deadline=3.0,
    cost=1.0,
)
BANDS = {"hub": DangerBand((RatioRect(0.0, 0.0, 0.05, 0.1),)), "menu": DangerBand()}
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
    interpreted: list[int] = field(default_factory=list)

    def interpret(self, f: Frame) -> Situation | None:
        self.interpreted.append(f.seq)
        return self.shows.get(f.seq)

    def verify(self, f: Frame, fact: Fact) -> Verdict:
        shown = self.shows.get(f.seq)
        if shown is None:
            return Verdict.UNREADABLE
        asked = (fact.params["screen"], fact.params["overlays"], fact.params["map_mode"])
        holds = (shown.screen, shown.overlays, shown.map_mode) == asked
        return Verdict.HOLDS if holds else Verdict.DOES_NOT_HOLD


def screens(**by_seq: str) -> dict[int, Situation]:
    return {int(k[1:]): Situation(int(k[1:]), v) for k, v in by_seq.items()}


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
    seen: list[Belief] = field(default_factory=list)
    agendas: list[int] = field(default_factory=list)

    def plan(self, belief: Belief, agenda: int) -> tuple[Step | Wait | Finish, int]:
        self.seen.append(belief)
        self.agendas.append(agenda)
        step = self.steps.pop(0)
        if isinstance(step, Step):
            step = replace(step, based_on=belief.as_of.until)
        return step, agenda + 1


class NoMapParser:
    def parse(self, f: Frame) -> MapReading:
        raise AssertionError("no map on these screens")


def initial_belief() -> Belief:
    return Belief(
        ui=UiState("unknown"),
        ui_basis=UiBasis(UiSource.ASSUMED),
        camera=None,
        drift=NO_DISPLACEMENT,
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


def open_menu_step() -> Step:
    return Step(intent="look", operation=OPEN_MENU, domain_premise=(), based_on=0.0)


def test_first_observation_interprets_the_frame_and_syncs_the_prediction():
    planner = ScriptedPlanner([Finish.DONE])
    agent = make_agent(FakeStream([still(1, 1.0)]), FakeInterpreter(screens(f1="hub")), planner)

    assert agent.run() is RunResult.DONE
    assert planner.seen[0].ui == HUB
    assert planner.seen[0].ui_basis == UiBasis(UiSource.SEEN, frame_seq=1)
    assert planner.seen[0].as_of == StillWindow(0.5, 1.0, 1)


def test_observation_waits_until_the_screen_is_still():
    stream = FakeStream([moving(1, 1.0), still(2, 1.5)])
    planner = ScriptedPlanner([Finish.DONE])
    make_agent(stream, FakeInterpreter(screens(f2="hub")), planner).run()

    assert [after for after, _ in stream.calls] == [0.0, 1.0]
    assert planner.seen[0].as_of.frame_seq == 2


def test_sensed_carries_the_cutoff_that_the_observation_started_from():
    stream = FakeStream([still(1, 1.0), moving(2, 1.5), still(3, 2.0)])
    interpreter = FakeInterpreter(screens(f1="hub", f3="hub"))
    agent = make_agent(stream, interpreter, ScriptedPlanner([]))

    first = agent.observe(agent.belief)
    second = agent.observe(agent.belief)

    assert first is not None and second is not None
    assert (first.after, second.after) == (0.0, 1.0)


def test_verified_outcome_advances_the_prediction_and_reaches_the_domain():
    stream = FakeStream([still(1, 1.0), still(2, 11.0), still(3, 12.0)])
    stream.latest_frame = frame(1, 1.0)
    actuator = FakeActuator()
    planner = ScriptedPlanner([open_menu_step(), Finish.DONE])
    interpreter = FakeInterpreter(screens(f1="hub", f2="menu", f3="menu"))

    assert make_agent(stream, interpreter, planner, actuator).run() is RunResult.DONE
    assert actuator.sent == [(Tap((100, 100)), (Rect(0, 0, 50, 50),))]
    assert stream.calls[1] == (10.0, 10.1 + OPEN_MENU.deadline)
    assert stream.calls[2][0] == 11.0
    assert planner.seen[1].ui == MENU
    assert planner.seen[1].domain.absorbed == (("look", "menu_open"),)
    assert planner.seen[1].last_action.status is ActionStatus.VERIFIED


def test_planner_gets_back_the_agenda_it_returned():
    stream = FakeStream([still(1, 1.0), still(2, 11.0), still(3, 12.0)])
    stream.latest_frame = frame(1, 1.0)
    planner = ScriptedPlanner([open_menu_step(), Finish.DONE])
    interpreter = FakeInterpreter(screens(f1="hub", f2="menu", f3="menu"))
    make_agent(stream, interpreter, planner).run()

    assert planner.agendas == [0, 1]


def test_failed_guard_sends_no_gesture():
    stream = FakeStream([still(1, 1.0), still(3, 2.0)])
    stream.latest_frame = frame(2, 1.2)
    actuator = FakeActuator()
    planner = ScriptedPlanner([open_menu_step(), Finish.DONE])
    interpreter = FakeInterpreter(screens(f1="hub", f2="menu", f3="menu"))
    make_agent(stream, interpreter, planner, actuator).run()

    assert actuator.sent == []
    assert stream.calls[1][0] == 1.2
    assert planner.seen[1].ui == MENU
    assert planner.seen[1].domain.absorbed == ()
    assert planner.seen[1].last_action.status is ActionStatus.GUARD_FAILED


def test_guard_sends_no_gesture_when_a_dialog_covers_the_screen():
    stream = FakeStream([still(1, 1.0), still(3, 2.0)])
    stream.latest_frame = frame(2, 1.2)
    actuator = FakeActuator()
    planner = ScriptedPlanner([open_menu_step(), Finish.DONE])
    dialog_over_hub = Situation(2, "hub", overlays=frozenset({"dialog"}))
    interpreter = FakeInterpreter({1: Situation(1, "hub"), 2: dialog_over_hub, 3: dialog_over_hub})
    make_agent(stream, interpreter, planner, actuator).run()

    assert actuator.sent == []
    assert planner.seen[1].ui == UiState("hub", frozenset({"dialog"}))


def test_blocked_gesture_is_reported_to_the_planner():
    stream = FakeStream([still(1, 1.0), still(2, 2.0)])
    stream.latest_frame = frame(1, 1.0)
    planner = ScriptedPlanner([open_menu_step(), Finish.HALTED])
    interpreter = FakeInterpreter(screens(f1="hub", f2="hub"))
    agent = make_agent(stream, interpreter, planner, FakeActuator(blocks=True))

    assert agent.run() is RunResult.HALTED
    assert planner.seen[1].last_action.status is ActionStatus.BLOCKED
    assert stream.calls[1][0] == 1.0


def test_wait_goes_back_to_observation_without_a_gesture():
    stream = FakeStream([still(1, 1.0), still(2, 2.0)])
    actuator = FakeActuator()
    planner = ScriptedPlanner([Wait(), Finish.DONE])
    interpreter = FakeInterpreter(screens(f1="hub", f2="hub"))

    assert make_agent(stream, interpreter, planner, actuator).run() is RunResult.DONE
    assert actuator.sent == []
    assert [after for after, _ in stream.calls] == [0.0, 1.0]


@dataclass(frozen=True)
class GridProjection:
    frame_seq: int
    shift: tuple[int, int]

    def to_view(self, point):
        return (point[0] // 100, point[1] // 100)

    def to_screen(self, cell):
        return ((cell[0] - self.shift[0]) * 100 + 50, (cell[1] - self.shift[1]) * 100 + 50)

    def to_world(self, cell):
        return (cell[0] + self.shift[0], cell[1] + self.shift[1])


@dataclass
class ScriptedGeometry:
    shifts: dict[int, tuple[int, int] | None]
    fits: list[tuple[int, object, tuple[float, float]]] = field(default_factory=list)

    def fit(self, reading, known, prior, displacement):
        self.fits.append((reading.frame_seq, prior, displacement))
        shift = self.shifts[reading.frame_seq]
        if shift is None:
            return None
        cells = {(12, 7): CellContent.EMPTY}
        return LocalBoard(GridProjection(reading.frame_seq, shift), cells)


class EchoParser:
    def parse(self, f: Frame) -> MapReading:
        return MapReading(f.seq, (), (), ())


ON_MAP = UiState("map", map_mode="hub")
TAP_CELL = Operation("tap_cell", ON_MAP, UiTap((0.25, 0.5)), (), 1.0, 1.0)


def run_on_map(settles, geometry, steps, latest=frame(2, 1.2)):
    stream = FakeStream(settles)
    stream.latest_frame = latest
    seqs = {shown.seq for shown, _ in settles} | {latest.seq}
    on_map = {n: Situation(n, "map", map_mode="hub") for n in seqs}
    actuator = FakeActuator()
    planner = ScriptedPlanner(steps)
    make_agent(
        stream,
        FakeInterpreter(on_map),
        planner,
        actuator,
        mapparser=EchoParser(),
        mapgeom=geometry,
        uisim=FakeUiSim({"map": DangerBand()}),
    ).run()
    return actuator, planner


def run_map_tap(guard_shift, premise) -> FakeActuator:
    geometry = ScriptedGeometry({1: (10, 5), 2: guard_shift, 3: (10, 5), 4: (10, 5)})
    settles = [still(1, 1.0), still(3, 12.0), still(4, 13.0)]
    actuator, _ = run_on_map(
        settles, geometry, [Step("probe", TAP_CELL, premise, 0.0), Finish.DONE]
    )
    return actuator


def test_guard_sends_the_gesture_when_the_board_premise_holds():
    premise = (CellAt((250, 250), (12, 7)), CellHolds((12, 7), CellContent.EMPTY))

    assert run_map_tap((10, 5), premise).sent == [(Tap((250, 250)), ())]


def test_guard_sends_no_gesture_when_the_camera_moved():
    assert run_map_tap((11, 5), (CellAt((250, 250), (12, 7)),)).sent == []


def test_guard_sends_no_gesture_when_the_grid_is_unreadable():
    assert run_map_tap(None, (CellAt((250, 250), (12, 7)),)).sent == []


def test_step_keeps_the_ui_and_the_domain_premise_apart():
    board_fact = CellAt((250, 250), (12, 7))
    premise = Step("probe", TAP_CELL, (board_fact,), 0.0).premise

    assert premise.ui == ON_MAP
    assert premise.domain == (board_fact,)


def test_unexpected_result_is_absorbed_as_none_and_corrected_by_the_next_observation():
    stream = FakeStream([still(1, 1.0), still(2, 11.0), still(3, 12.0)])
    stream.latest_frame = frame(1, 1.0)
    planner = ScriptedPlanner([open_menu_step(), Finish.DONE])
    interpreter = FakeInterpreter(screens(f1="hub", f2="dialog", f3="dialog"))
    make_agent(stream, interpreter, planner).run()

    assert planner.seen[1].ui == UiState("dialog")
    assert planner.seen[1].domain.absorbed == (("look", None),)
    assert planner.seen[1].last_action.status is ActionStatus.UNVERIFIED


def test_result_that_is_not_still_at_the_deadline_is_not_verified():
    stream = FakeStream([still(1, 1.0), moving(2, 13.0), still(3, 14.0)])
    stream.latest_frame = frame(1, 1.0)
    planner = ScriptedPlanner([open_menu_step(), Finish.DONE])
    interpreter = FakeInterpreter(screens(f1="hub", f2="menu", f3="menu"))
    make_agent(stream, interpreter, planner).run()

    assert planner.seen[1].domain.absorbed == (("look", None),)
    assert stream.calls[2][0] == 13.0


def test_unreadable_screen_is_left_to_the_planner():
    planner = ScriptedPlanner([Finish.HALTED])
    agent = make_agent(FakeStream([still(1, 1.0)]), FakeInterpreter({}), planner)

    assert agent.run() is RunResult.HALTED
    assert planner.seen[0].ui_basis == UiBasis(UiSource.LOST, frame_seq=1)


def test_observation_does_not_interpret_when_the_prediction_holds():
    stream = FakeStream([still(1, 1.0), still(2, 11.0), still(3, 12.0)])
    stream.latest_frame = frame(1, 1.0)
    interpreter = FakeInterpreter(screens(f1="hub", f2="menu", f3="menu"))
    make_agent(stream, interpreter, ScriptedPlanner([open_menu_step(), Finish.DONE])).run()

    assert interpreter.interpreted == [1]


def test_map_screen_puts_the_fitted_camera_into_the_belief():
    geometry = ScriptedGeometry({1: (10, 5)})
    _, planner = run_on_map([still(1, 1.0)], geometry, [Finish.DONE])

    assert geometry.fits == [(1, None, NO_DISPLACEMENT)]
    assert planner.seen[0].camera == GridProjection(1, (10, 5))
    assert planner.seen[0].domain.boards == 1


def test_unreadable_grid_keeps_the_camera():
    geometry = ScriptedGeometry({1: (10, 5), 3: None})
    settles = [still(1, 1.0), still(2, 11.0), still(3, 12.0)]
    _, planner = run_on_map(
        settles, geometry, [Step("probe", TAP_CELL, (), 0.0), Finish.DONE], latest=frame(1, 1.0)
    )

    assert planner.seen[1].camera == GridProjection(1, (10, 5))


def test_stop_request_ends_the_loop_between_cycles():
    stop = Event()
    stop.set()
    agent = make_agent(FakeStream([]), FakeInterpreter({}), ScriptedPlanner([]), stop=stop)

    assert agent.run() is RunResult.STOPPED
