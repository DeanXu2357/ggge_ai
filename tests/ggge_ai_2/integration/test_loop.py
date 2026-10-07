from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event

import numpy as np

from ggge_ai_2.actuator.contract import Dispatch, GestureBlocked, Rect, Tap
from ggge_ai_2.agent.contract import (
    ActionResult,
    ActionStatus,
    CellReads,
    Finish,
    Sensed,
    Step,
    Wait,
)
from ggge_ai_2.agent.loop import Agent, RunResult, ScreenSize
from ggge_ai_2.interpreter.contract import MapMode, Overlay, Screen, Situation
from ggge_ai_2.mapparser.contract import CellReading, MapReading, ScreenPoint, ViewCell
from ggge_ai_2.stream.contract import NO_DISPLACEMENT, Frame, Observation, StillWindow
from ggge_ai_2.uisim.contract import (
    DangerBand,
    Observed,
    Operation,
    Outcome,
    RatioRect,
    UiMapMode,
    UiScreen,
    UiState,
    UiTap,
)

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
BAND = DangerBand((RatioRect(0.0, 0.0, 0.05, 0.1),))
SCREEN = ScreenSize(1000, 500)
ON_MAP = UiState(UiScreen.BATTLE_MAP, map_mode=UiMapMode.HUB)
TAP_CELL = Operation("tap_cell", ON_MAP, UiTap((0.9, 0.9)), (), 1.0, 1.0)


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
    decisions: list[Step | Wait | Finish]
    seen: list[tuple[Sensed, ActionResult | None]] = field(default_factory=list)

    def plan(
        self, state: int, sensed: Sensed, acted: ActionResult | None
    ) -> tuple[Step | Wait | Finish, int]:
        self.seen.append((sensed, acted))
        return self.decisions.pop(0), state + 1


class NoMapParser:
    def parse(self, frame: Frame) -> MapReading | None:
        raise AssertionError("no map on these screens")

    def locate(self, frame: Frame, cell: ViewCell) -> ScreenPoint | None:
        raise AssertionError("no map on these screens")


@dataclass
class GridParser:
    unreadable: frozenset[int] = frozenset()

    def parse(self, frame: Frame) -> MapReading | None:
        if frame.seq in self.unreadable:
            return None
        return MapReading({(2, 2): CellReading.EMPTY}, frozenset())

    def locate(self, frame: Frame, cell: ViewCell) -> ScreenPoint | None:
        if cell[0] < 0:
            return None
        return (cell[0] * 100 + 50, cell[1] * 100 + 50)


def make_agent(stream, interpreter, planner, actuator=None, mapparser=None) -> Agent[int]:
    return Agent(
        stream=stream,
        interpreter=interpreter,
        mapparser=mapparser or NoMapParser(),
        actuator=actuator or FakeActuator(),
        screen=SCREEN,
        planner=planner,
        state=0,
        idle_deadline=2.0,
    )


def open_info() -> Step:
    return Step(OPEN_INFO, (), BAND)


def run_step(step: Step, shows: dict[int, Situation], latest: Frame, actuator=None):
    stream = FakeStream([still(1, 1.0), still(2, 11.0), still(3, 12.0)])
    stream.latest_frame = latest
    planner = ScriptedPlanner([step, Finish.DONE])
    make_agent(stream, FakeInterpreter(shows), planner, actuator).run()
    return stream, planner


def acted_after(planner: ScriptedPlanner) -> ActionResult:
    acted = planner.seen[1][1]
    assert acted is not None
    return acted


def test_first_observation_is_read_for_the_planner():
    planner = ScriptedPlanner([Finish.DONE])
    agent = make_agent(
        FakeStream([still(1, 1.0)]), FakeInterpreter(screens(f1="stage_list")), planner
    )

    assert agent.run() is RunResult.DONE
    sensed, acted = planner.seen[0]
    assert sensed.observed == Observed(UiScreen.STAGE_LIST)
    assert sensed.still == StillWindow(0.5, 1.0, 1)
    assert acted is None


def test_observation_waits_until_the_screen_is_still():
    stream = FakeStream([moving(1, 1.0), still(2, 1.5)])
    planner = ScriptedPlanner([Finish.DONE])
    make_agent(stream, FakeInterpreter(screens(f2="stage_list")), planner).run()

    assert [after for after, _ in stream.calls] == [0.0, 1.0]
    assert planner.seen[0][0].still.frame_seq == 2


def test_planner_gets_back_the_state_it_returned():
    planner = ScriptedPlanner([Wait(), Finish.DONE])
    stream = FakeStream([still(1, 1.0), still(2, 2.0)])
    agent = make_agent(stream, FakeInterpreter(screens(f1="stage_list", f2="stage_list")), planner)
    agent.run()

    assert agent.state == 2


def test_verified_outcome_reaches_the_planner_with_the_next_observation():
    actuator = FakeActuator()
    shows = screens(f1="stage_list", f2="stage_info", f3="stage_info")
    stream, planner = run_step(open_info(), shows, frame(1, 1.0), actuator)

    assert actuator.sent == [(Tap((100, 100)), (Rect(0, 0, 50, 50),))]
    assert stream.calls[1] == (10.0, 10.1 + OPEN_INFO.deadline)
    acted = acted_after(planner)
    assert acted.status is ActionStatus.VERIFIED
    assert acted.outcome == OPEN_INFO.outcomes[0]


def test_failed_ui_premise_sends_no_gesture():
    actuator = FakeActuator()
    shows = screens(f1="stage_list", f2="stage_info", f3="stage_info")
    stream, planner = run_step(open_info(), shows, frame(2, 1.2), actuator)

    assert actuator.sent == []
    assert stream.calls[1][0] == 1.2
    acted = acted_after(planner)
    assert acted.status is ActionStatus.GUARD_FAILED
    assert acted.failed_premise == LIST


def test_dialog_over_the_screen_fails_the_ui_premise():
    actuator = FakeActuator()
    covered = Situation(2, Screen.STAGE_LIST, frozenset({Overlay.DIALOG}))
    shows = {1: Situation(1, Screen.STAGE_LIST), 2: covered, 3: covered}
    _, planner = run_step(open_info(), shows, frame(2, 1.2), actuator)

    assert actuator.sent == []
    assert acted_after(planner).status is ActionStatus.GUARD_FAILED


def test_stale_guard_frame_sends_no_gesture():
    actuator = FakeActuator()
    step = Step(OPEN_INFO, (), BAND, frame_after=1.5)
    _, planner = run_step(step, screens(f1="stage_list", f3="stage_list"), frame(1, 1.0), actuator)

    assert actuator.sent == []
    assert acted_after(planner).status is ActionStatus.GUARD_FAILED


def test_blocked_gesture_is_reported_to_the_planner():
    shows = screens(f1="stage_list", f2="stage_list")
    stream, planner = run_step(open_info(), shows, frame(1, 1.0), FakeActuator(blocks=True))

    assert acted_after(planner).status is ActionStatus.BLOCKED
    assert stream.calls[1][0] == 1.0


def test_wait_goes_back_to_observation_without_a_gesture():
    actuator = FakeActuator()
    stream = FakeStream([still(1, 1.0), still(2, 2.0)])
    planner = ScriptedPlanner([Wait(), Finish.DONE])
    shows = screens(f1="stage_list", f2="stage_list")

    assert make_agent(stream, FakeInterpreter(shows), planner, actuator).run() is RunResult.DONE
    assert actuator.sent == []
    assert planner.seen[1][1] is None


def test_unexpected_result_is_unverified():
    shows = screens(f1="stage_list", f2="notice", f3="notice")
    _, planner = run_step(open_info(), shows, frame(1, 1.0))

    acted = acted_after(planner)
    assert acted.status is ActionStatus.UNVERIFIED
    assert acted.outcome is None


def test_result_that_is_not_still_at_the_deadline_is_unverified():
    stream = FakeStream([still(1, 1.0), moving(2, 13.0), still(3, 14.0)])
    stream.latest_frame = frame(1, 1.0)
    planner = ScriptedPlanner([open_info(), Finish.DONE])
    shows = screens(f1="stage_list", f2="stage_info", f3="stage_info")
    make_agent(stream, FakeInterpreter(shows), planner).run()

    assert acted_after(planner).status is ActionStatus.UNVERIFIED
    assert stream.calls[2][0] == 13.0


def test_unreadable_screen_is_left_to_the_planner():
    planner = ScriptedPlanner([Finish.HALTED])
    agent = make_agent(FakeStream([still(1, 1.0)]), FakeInterpreter({}), planner)

    assert agent.run() is RunResult.HALTED
    assert planner.seen[0][0].observed is None


def run_on_map(step: Step, parser: GridParser) -> tuple[FakeActuator, ScriptedPlanner]:
    stream = FakeStream([still(1, 1.0), still(3, 12.0), still(4, 13.0)])
    stream.latest_frame = frame(2, 1.2)
    on_map = {n: Situation(n, Screen.BATTLE_MAP, map_mode=MapMode.HUB) for n in (1, 2, 3, 4)}
    actuator = FakeActuator()
    planner = ScriptedPlanner([step, Finish.DONE])
    make_agent(stream, FakeInterpreter(on_map), planner, actuator, parser).run()
    return actuator, planner


def test_map_screen_is_read_for_the_planner():
    _, planner = run_on_map(Step(TAP_CELL, (), DangerBand(), target=(2, 2)), GridParser())

    assert planner.seen[0][0].map == MapReading({(2, 2): CellReading.EMPTY}, frozenset())


def test_target_cell_is_tapped_where_the_guard_frame_shows_it():
    premise = (CellReads((2, 2), CellReading.EMPTY),)
    step = Step(TAP_CELL, premise, DangerBand(), target=(2, 2))

    assert run_on_map(step, GridParser())[0].sent == [(Tap((250, 250)), ())]


def test_changed_cell_fails_the_map_premise():
    changed = CellReads((2, 2), CellReading.OCCUPIED)
    actuator, planner = run_on_map(
        Step(TAP_CELL, (changed,), DangerBand(), target=(2, 2)), GridParser()
    )

    assert actuator.sent == []
    assert acted_after(planner).failed_premise == changed


def test_unreadable_grid_fails_the_map_premise():
    premise = (CellReads((2, 2), CellReading.EMPTY),)
    step = Step(TAP_CELL, premise, DangerBand(), target=(2, 2))

    assert run_on_map(step, GridParser(frozenset({2})))[0].sent == []


def test_target_out_of_reach_sends_no_gesture():
    actuator, planner = run_on_map(Step(TAP_CELL, (), DangerBand(), target=(-1, 0)), GridParser())

    assert actuator.sent == []
    assert acted_after(planner).status is ActionStatus.GUARD_FAILED


def test_stop_request_ends_the_loop_between_cycles():
    stop = Event()
    stop.set()
    agent = make_agent(FakeStream([]), FakeInterpreter({}), ScriptedPlanner([]))
    agent.stop = stop

    assert agent.run() is RunResult.STOPPED
