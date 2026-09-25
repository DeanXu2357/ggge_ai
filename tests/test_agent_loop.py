from __future__ import annotations

from dataclasses import dataclass, field, replace
from threading import Event

import numpy as np
import pytest

from ggge_ai_2.actuator.contract import DangerBand, Dispatch, Rect, Tap
from ggge_ai_2.agent import Agent, Belief, Halt, RunResult, Step
from ggge_ai_2.interpreter.contract import Fact, Situation, Verdict
from ggge_ai_2.mapgeom.contract import CellAt, CellContent, CellHolds, KnownMap, LocalBoard
from ggge_ai_2.mapparser.contract import MapReading
from ggge_ai_2.stream.contract import Frame, Observation, StillWindow
from ggge_ai_2.uisim.contract import Operation, Outcome, UiState

HUB = UiState("hub")
MENU = UiState("menu")
OPEN_MENU = Operation(
    name="open_menu",
    precondition=(Fact("screen_is", {"screen": "hub", "overlays": frozenset()}),),
    gesture=Tap((100, 100)),
    outcomes=(Outcome("menu_open", Fact("screen_is", {"screen": "menu"}), MENU),),
    deadline=3.0,
    cost=1.0,
)
BANDS = {"hub": DangerBand((Rect(0, 0, 50, 50),)), "menu": DangerBand()}


def frame(seq: int, at: float) -> Frame:
    return Frame(np.zeros((1, 1, 3), np.uint8), at, seq)


def still(seq: int, at: float) -> Observation:
    return Observation(frame(seq, at), StillWindow(at - 0.5, at, seq), 0.5, (0.0, 0.0))


def moving(seq: int, at: float) -> Observation:
    return Observation(frame(seq, at), None, 0.5, (0.0, 0.0))


@dataclass
class FakeStream:
    settles: list[Observation]
    latest_frame: Frame = field(default_factory=lambda: frame(0, 0.0))
    calls: list[tuple[float, float]] = field(default_factory=list)

    def latest(self) -> Frame:
        return self.latest_frame

    def settled(self, after: float, deadline: float) -> Observation:
        self.calls.append((after, deadline))
        return self.settles.pop(0)


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
        overlays = fact.params.get("overlays", shown.overlays)
        holds = shown.screen == fact.params["screen"] and shown.overlays == overlays
        return Verdict.HOLDS if holds else Verdict.DOES_NOT_HOLD


def screens(**by_seq: str) -> dict[int, Situation]:
    return {int(k[1:]): Situation(int(k[1:]), v) for k, v in by_seq.items()}


@dataclass(frozen=True)
class FakeUiSim:
    state: UiState

    def fact(self) -> Fact:
        return Fact("state_is", {"screen": self.state.screen, "overlays": self.state.overlays})

    def successors(self):
        return ()

    def predecessors(self):
        return ()

    def advance(self, outcome: Outcome) -> FakeUiSim:
        return replace(self, state=outcome.then)

    def sync(self, observed: Situation) -> FakeUiSim:
        return replace(self, state=UiState(observed.screen, observed.overlays, observed.map_mode))


@dataclass(frozen=True)
class FakeDomain:
    absorbed: tuple[tuple[object, str | None], ...] = ()
    boards: int = 0

    def absorb(self, intent: object, outcome: Outcome | None) -> FakeDomain:
        name = outcome.name if outcome else None
        return replace(self, absorbed=(*self.absorbed, (intent, name)))

    def observe(self, board: LocalBoard) -> FakeDomain:
        return replace(self, boards=self.boards + 1)

    def known_map(self) -> KnownMap:
        return KnownMap({})


@dataclass
class FakeActuator:
    sent: list[tuple[object, DangerBand]] = field(default_factory=list)

    def dispatch(self, gesture, band: DangerBand) -> Dispatch:
        self.sent.append((gesture, band))
        return Dispatch(10.0, 10.1)


@dataclass
class ScriptedPlanner:
    steps: list[Step | None]
    seen: list[Belief] = field(default_factory=list)

    def plan(self, belief: Belief) -> Step | None:
        self.seen.append(belief)
        step = self.steps.pop(0)
        return step and replace(step, based_on=belief.still.until)


class NoMapParser:
    def parse(self, f: Frame) -> MapReading:
        raise AssertionError("no map on these screens")


class NoMapGeometry:
    def fit(self, *args) -> LocalBoard | None:
        raise AssertionError("no map on these screens")


def make_agent(stream, interpreter, planner, actuator=None, **overrides) -> Agent:
    kwargs = dict(
        stream=stream,
        interpreter=interpreter,
        mapparser=NoMapParser(),
        mapgeom=NoMapGeometry(),
        actuator=actuator or FakeActuator(),
        planner=planner,
        bands=BANDS,
        initial_ui=FakeUiSim(UiState("unknown")),
        initial_domain=FakeDomain(),
        idle_deadline=2.0,
    )
    kwargs.update(overrides)
    return Agent(**kwargs)


def open_menu_step() -> Step:
    return Step(intent="look", operation=OPEN_MENU, domain_premise=(), based_on=0.0)


def test_first_observation_interprets_the_frame_and_syncs_the_prediction():
    planner = ScriptedPlanner([None])
    agent = make_agent(FakeStream([still(1, 1.0)]), FakeInterpreter(screens(f1="hub")), planner)

    assert agent.run() is RunResult.DONE
    assert planner.seen[0].ui.state == HUB
    assert planner.seen[0].still == StillWindow(0.5, 1.0, 1)


def test_observation_waits_until_the_screen_is_still():
    stream = FakeStream([moving(1, 1.0), still(2, 1.5)])
    planner = ScriptedPlanner([None])
    make_agent(stream, FakeInterpreter(screens(f2="hub")), planner).run()

    assert [after for after, _ in stream.calls] == [0.0, 1.0]
    assert planner.seen[0].still.frame_seq == 2


def test_verified_outcome_advances_the_prediction_and_reaches_the_domain():
    stream = FakeStream([still(1, 1.0), still(2, 11.0), still(3, 12.0)])
    stream.latest_frame = frame(1, 1.0)
    actuator = FakeActuator()
    planner = ScriptedPlanner([open_menu_step(), None])
    interpreter = FakeInterpreter(screens(f1="hub", f2="menu", f3="menu"))

    assert make_agent(stream, interpreter, planner, actuator).run() is RunResult.DONE
    assert actuator.sent == [(Tap((100, 100)), BANDS["hub"])]
    assert stream.calls[1] == (10.0, 10.1 + OPEN_MENU.deadline)
    assert stream.calls[2][0] == 11.0
    assert planner.seen[1].ui.state == MENU
    assert planner.seen[1].domain.absorbed == (("look", "menu_open"),)


def test_failed_guard_sends_no_gesture():
    stream = FakeStream([still(1, 1.0), still(3, 2.0)])
    stream.latest_frame = frame(2, 1.2)
    actuator = FakeActuator()
    planner = ScriptedPlanner([open_menu_step(), None])
    interpreter = FakeInterpreter(screens(f1="hub", f2="menu", f3="menu"))
    make_agent(stream, interpreter, planner, actuator).run()

    assert actuator.sent == []
    assert stream.calls[1][0] == 1.2
    assert planner.seen[1].ui.state == MENU
    assert planner.seen[1].domain.absorbed == ()


def test_guard_sends_no_gesture_when_a_dialog_covers_the_screen():
    stream = FakeStream([still(1, 1.0), still(3, 2.0)])
    stream.latest_frame = frame(2, 1.2)
    actuator = FakeActuator()
    planner = ScriptedPlanner([open_menu_step(), None])
    dialog_over_hub = Situation(2, "hub", overlays=frozenset({"dialog"}))
    interpreter = FakeInterpreter({1: Situation(1, "hub"), 2: dialog_over_hub, 3: dialog_over_hub})
    make_agent(stream, interpreter, planner, actuator).run()

    assert actuator.sent == []
    assert planner.seen[1].ui.state == UiState("hub", frozenset({"dialog"}))


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

    def fit(self, reading, known, prior, displacement):
        shift = self.shifts[reading.frame_seq]
        if shift is None:
            return None
        cells = {(12, 7): CellContent.EMPTY}
        return LocalBoard(GridProjection(reading.frame_seq, shift), cells)


class EchoParser:
    def parse(self, f: Frame) -> MapReading:
        return MapReading(f.seq, (), (), ())


MAP_SCREEN = Fact("screen_is", {"screen": "map", "overlays": frozenset()})
TAP_CELL = Operation("tap_cell", (MAP_SCREEN,), Tap((250, 250)), (), 1.0, 1.0)


def run_map_tap(guard_shift, premise) -> FakeActuator:
    stream = FakeStream([still(1, 1.0), still(3, 12.0), still(4, 13.0)])
    stream.latest_frame = frame(2, 1.2)
    on_map = {n: Situation(n, "map", map_mode="hub") for n in (1, 2, 3, 4)}
    geometry = ScriptedGeometry({1: (10, 5), 2: guard_shift, 3: (10, 5), 4: (10, 5)})
    actuator = FakeActuator()
    planner = ScriptedPlanner([Step("probe", TAP_CELL, premise, 0.0), None])
    make_agent(
        stream,
        FakeInterpreter(on_map),
        planner,
        actuator,
        mapparser=EchoParser(),
        mapgeom=geometry,
        bands={"map": DangerBand()},
    ).run()
    return actuator


def test_guard_sends_the_gesture_when_the_board_premise_holds():
    premise = (CellAt((250, 250), (12, 7)), CellHolds((12, 7), CellContent.EMPTY))

    assert run_map_tap((10, 5), premise).sent == [(Tap((250, 250)), DangerBand())]


def test_guard_sends_no_gesture_when_the_camera_moved():
    assert run_map_tap((11, 5), (CellAt((250, 250), (12, 7)),)).sent == []


def test_guard_sends_no_gesture_when_the_grid_is_unreadable():
    assert run_map_tap(None, (CellAt((250, 250), (12, 7)),)).sent == []


def test_step_keeps_the_ui_and_the_domain_premise_apart():
    board_fact = CellAt((250, 250), (12, 7))
    premise = Step("probe", TAP_CELL, (board_fact,), 0.0).premise

    assert premise.ui == (MAP_SCREEN,)
    assert premise.domain == (board_fact,)


def test_unexpected_result_is_absorbed_as_none_and_corrected_by_the_next_observation():
    stream = FakeStream([still(1, 1.0), still(2, 11.0), still(3, 12.0)])
    stream.latest_frame = frame(1, 1.0)
    planner = ScriptedPlanner([open_menu_step(), None])
    interpreter = FakeInterpreter(screens(f1="hub", f2="dialog", f3="dialog"))
    make_agent(stream, interpreter, planner).run()

    assert planner.seen[1].ui.state == UiState("dialog")
    assert planner.seen[1].domain.absorbed == (("look", None),)


def test_result_that_is_not_still_at_the_deadline_is_not_verified():
    stream = FakeStream([still(1, 1.0), moving(2, 13.0), still(3, 14.0)])
    stream.latest_frame = frame(1, 1.0)
    planner = ScriptedPlanner([open_menu_step(), None])
    interpreter = FakeInterpreter(screens(f1="hub", f2="menu", f3="menu"))
    make_agent(stream, interpreter, planner).run()

    assert planner.seen[1].domain.absorbed == (("look", None),)
    assert stream.calls[2][0] == 13.0


def test_unreadable_screen_halts():
    with pytest.raises(Halt):
        make_agent(FakeStream([still(1, 1.0)]), FakeInterpreter({}), ScriptedPlanner([None])).run()


def test_observation_does_not_interpret_when_the_prediction_holds():
    stream = FakeStream([still(1, 1.0), still(2, 11.0), still(3, 12.0)])
    stream.latest_frame = frame(1, 1.0)
    interpreter = FakeInterpreter(screens(f1="hub", f2="menu", f3="menu"))
    make_agent(stream, interpreter, ScriptedPlanner([open_menu_step(), None])).run()

    assert interpreter.interpreted == [1]


def test_map_screen_builds_the_local_board_into_the_belief():
    board = LocalBoard(projection=object(), cells={(3, 4): CellContent.EMPTY})
    fits = []

    class Parser:
        def parse(self, f: Frame) -> MapReading:
            return MapReading(f.seq, (), (), ())

    class Geometry:
        def fit(self, reading, known, prior, displacement):
            fits.append((reading.frame_seq, prior))
            return board

    interpreter = FakeInterpreter({1: Situation(1, "map", map_mode="hub")})
    planner = ScriptedPlanner([None])
    stream = FakeStream([still(1, 1.0)])
    make_agent(stream, interpreter, planner, mapparser=Parser(), mapgeom=Geometry()).run()

    assert fits == [(1, None)]
    assert planner.seen[0].board is board
    assert planner.seen[0].domain.boards == 1


def test_next_map_fit_takes_the_last_projection_as_its_prior():
    projection = object()
    fits = []

    class Parser:
        def parse(self, f: Frame) -> MapReading:
            return MapReading(f.seq, (), (), ())

    class Geometry:
        def fit(self, reading, known, prior, displacement):
            fits.append(prior)
            return LocalBoard(projection=projection, cells={})

    on_map = Situation(0, "map", map_mode="hub")
    interpreter = FakeInterpreter({1: on_map, 2: on_map, 3: on_map})
    stream = FakeStream([still(1, 1.0), still(2, 11.0), still(3, 12.0)])
    stream.latest_frame = frame(1, 1.0)
    map_screen = Fact("screen_is", {"screen": "map", "overlays": frozenset()})
    pan = replace(OPEN_MENU, precondition=(map_screen,), outcomes=())
    planner = ScriptedPlanner([Step("pan", pan, (), 0.0), None])
    make_agent(
        stream,
        interpreter,
        planner,
        mapparser=Parser(),
        mapgeom=Geometry(),
        bands={"map": DangerBand()},
    ).run()

    assert fits == [None, projection]


def test_stop_request_ends_the_loop_between_cycles():
    stop = Event()
    stop.set()
    agent = make_agent(FakeStream([]), FakeInterpreter({}), ScriptedPlanner([]), stop=stop)

    assert agent.run() is RunResult.STOPPED
