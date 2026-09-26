from __future__ import annotations

from dataclasses import dataclass, replace
from threading import Event
from unittest.mock import call, create_autospec

import pytest

from ggge_ai_2.actuator.contract import Actuator, DangerBand, Dispatch, Rect, Tap, TouchPoint
from ggge_ai_2.agent import Agent, Belief, Halt, Planner, RunResult, Step
from ggge_ai_2.mapgeom.contract import (
    CellAt,
    CellContent,
    CellHolds,
    KnownMap,
    LocalBoard,
    MapGeometry,
)
from ggge_ai_2.mapparser.contract import MapParser, MapReading
from ggge_ai_2.stream.contract import FramePoint, StillWindow
from ggge_ai_2.uisim.contract import (
    MapMode,
    Operation,
    Outcome,
    Overlay,
    Screen,
    ScreenIs,
    UiState,
)
from tests.ggge_ai_2.fakes.interpreter import LabeledInterpreter
from tests.ggge_ai_2.fakes.mapgeom import GridProjection
from tests.ggge_ai_2.fakes.stream import TimelineStream, flicker, frames, steady
from tests.ggge_ai_2.fakes.uisim import FrozenUiSim

HUB = UiState(Screen.STAGE_LIST)
MENU = UiState(Screen.STAGE_INFO)
DIALOG = UiState(Screen.NOTICE)
HUB_DIALOG = UiState(Screen.STAGE_LIST, frozenset({Overlay.DIALOG}))
ON_MAP = UiState(Screen.BATTLE_MAP, map_mode=MapMode.HUB)
UNMODELED = 9
LABELS = {1: HUB, 2: MENU, 3: DIALOG, 4: HUB_DIALOG, 5: ON_MAP}

OPEN_MENU = Operation(
    name="open_menu",
    precondition=(ScreenIs(Screen.STAGE_LIST),),
    gesture=Tap(TouchPoint(100, 100)),
    outcomes=(Outcome("menu_open", ScreenIs(Screen.STAGE_INFO), MENU),),
    deadline=3.0,
    cost=1.0,
)
MAP_SCREEN = ScreenIs(Screen.BATTLE_MAP)
TAP_CELL = Operation("tap_cell", (MAP_SCREEN,), Tap(TouchPoint(250, 250)), (), 1.0, 1.0)
BANDS = {
    Screen.STAGE_LIST: DangerBand((Rect(0, 0, 50, 50),)),
    Screen.STAGE_INFO: DangerBand(),
    Screen.BATTLE_MAP: DangerBand(),
}


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


def planner_of(*steps: Step | None):
    planner = create_autospec(Planner, instance=True)
    planner.plan.side_effect = list(steps)
    return planner


def beliefs(planner) -> list[Belief]:
    return [c.args[0] for c in planner.plan.call_args_list]


def actuator_on(stream: TimelineStream):
    actuator = create_autospec(Actuator, instance=True)

    def dispatch(gesture, band):
        t0 = stream.now
        stream.now = t0 + 0.05
        return Dispatch(t0, stream.now)

    actuator.dispatch.side_effect = dispatch
    return actuator


def no_map():
    parser = create_autospec(MapParser, instance=True)
    geometry = create_autospec(MapGeometry, instance=True)
    parser.parse.side_effect = AssertionError("no map on these screens")
    geometry.fit.side_effect = AssertionError("no map on these screens")
    return parser, geometry


def run(stream, planner, **overrides):
    parser, geometry = no_map()
    kwargs = dict(
        stream=stream,
        interpreter=LabeledInterpreter(LABELS),
        mapparser=parser,
        mapgeom=geometry,
        actuator=actuator_on(stream),
        planner=planner,
        bands=BANDS,
        initial_ui=FrozenUiSim(UiState(Screen.LOGIN_BONUS)),
        initial_domain=FakeDomain(),
        idle_deadline=2.0,
        clock=stream.clock,
    )
    kwargs.update(overrides)
    agent = Agent(**kwargs)
    return agent, agent.run()


def open_menu() -> Step:
    return Step(intent="look", operation=OPEN_MENU, domain_premise=(), based_on=0.0)


def test_first_observation_interprets_the_frame_and_syncs_the_prediction():
    planner = planner_of(None)
    _, result = run(TimelineStream(frames(*steady(1, 0.5, 1.0))), planner)

    assert result is RunResult.DONE
    assert beliefs(planner)[0].ui.state == HUB
    assert beliefs(planner)[0].still == StillWindow(0.5, 0.8, 4)


def test_observation_waits_again_when_the_screen_is_not_still_at_the_deadline():
    stream = TimelineStream(frames(*flicker((1, 2), 0.1, 1.0), *steady(1, 1.1, 1.6)))
    planner = planner_of(None)
    run(stream, planner, idle_deadline=1.0)

    assert [after for after, _ in stream.calls] == [0.0, 1.0]
    assert beliefs(planner)[0].still.until == 1.4


def test_verified_outcome_advances_the_prediction_and_reaches_the_domain():
    stream = TimelineStream(frames(*steady(1, 0.1, 0.5), *steady(2, 0.6, 1.3)))
    planner = planner_of(open_menu(), None)
    agent, result = run(stream, planner)

    assert result is RunResult.DONE
    assert agent.actuator.dispatch.call_args_list == [
        call(Tap(TouchPoint(100, 100)), BANDS[Screen.STAGE_LIST])
    ]
    assert stream.calls[1] == (0.5, 0.55 + OPEN_MENU.deadline)
    assert stream.calls[2][0] == 0.9
    assert beliefs(planner)[1].ui.state == MENU
    assert beliefs(planner)[1].domain.absorbed == (("look", "menu_open"),)


def test_failed_guard_sends_no_gesture():
    stream = TimelineStream(frames(*steady(1, 0.1, 0.4), *steady(2, 0.5, 0.9)))
    planner = planner_of(open_menu(), None)
    agent, _ = run(stream, planner)

    agent.actuator.dispatch.assert_not_called()
    assert stream.calls[1][0] == 0.5
    assert beliefs(planner)[1].ui.state == MENU
    assert beliefs(planner)[1].domain.absorbed == ()


def test_guard_sends_no_gesture_when_a_dialog_covers_the_screen():
    stream = TimelineStream(frames(*steady(1, 0.1, 0.4), *steady(4, 0.5, 0.9)))
    planner = planner_of(open_menu(), None)
    agent, _ = run(stream, planner)

    agent.actuator.dispatch.assert_not_called()
    assert beliefs(planner)[1].ui.state == HUB_DIALOG


def test_unexpected_result_is_absorbed_as_none_and_corrected_by_the_next_observation():
    stream = TimelineStream(frames(*steady(1, 0.1, 0.5), *steady(3, 0.6, 1.3)))
    planner = planner_of(open_menu(), None)
    run(stream, planner)

    assert beliefs(planner)[1].ui.state == DIALOG
    assert beliefs(planner)[1].domain.absorbed == (("look", None),)


def test_result_that_is_not_still_at_the_deadline_is_not_verified():
    timeline = frames(*steady(1, 0.1, 0.5), *flicker((2, 3), 0.6, 3.5), *steady(2, 3.6, 3.9))
    stream = TimelineStream(timeline)
    planner = planner_of(open_menu(), None)
    run(stream, planner)

    assert beliefs(planner)[1].domain.absorbed == (("look", None),)
    assert stream.calls[2][0] == 3.5


def test_unmodeled_screen_halts():
    with pytest.raises(Halt):
        run(TimelineStream(frames(*steady(UNMODELED, 0.1, 0.4))), planner_of(None))


def test_observation_does_not_interpret_when_the_prediction_holds():
    stream = TimelineStream(frames(*steady(1, 0.1, 0.5), *steady(2, 0.6, 1.3)))
    agent, _ = run(stream, planner_of(open_menu(), None))

    assert agent.interpreter.interpreted == [4]


def map_parts(fit):
    parser = create_autospec(MapParser, instance=True)
    parser.parse.side_effect = lambda frame: MapReading(frame.seq, (), (), ())
    geometry = create_autospec(MapGeometry, instance=True)
    geometry.fit.side_effect = fit
    return dict(mapparser=parser, mapgeom=geometry)


def run_map_tap(guard_shift, premise):
    guard_seq = 5

    def fit(reading, known, prior, displacement):
        shift = guard_shift if reading.frame_seq == guard_seq else (10, 5)
        if shift is None:
            return None
        cells = {(12, 7): CellContent.EMPTY}
        return LocalBoard(GridProjection(reading.frame_seq, shift), frozenset(cells), cells)

    stream = TimelineStream(frames(*steady(5, 0.1, 0.5), *steady(5, 0.6, 1.3)))
    planner = planner_of(Step("probe", TAP_CELL, premise, 0.0), None)
    agent, _ = run(stream, planner, **map_parts(fit))
    return agent.actuator.dispatch


def test_guard_sends_the_gesture_when_the_board_premise_holds():
    premise = (CellAt(FramePoint(250, 250), (12, 7)), CellHolds((12, 7), CellContent.EMPTY))

    assert run_map_tap((10, 5), premise).call_args_list == [
        call(Tap(TouchPoint(250, 250)), DangerBand())
    ]


def test_guard_sends_no_gesture_when_the_camera_moved():
    run_map_tap((11, 5), (CellAt(FramePoint(250, 250), (12, 7)),)).assert_not_called()


def test_guard_sends_no_gesture_when_the_grid_is_unreadable():
    run_map_tap(None, (CellAt(FramePoint(250, 250), (12, 7)),)).assert_not_called()


def test_step_keeps_the_ui_and_the_domain_premise_apart():
    board_fact = CellAt(FramePoint(250, 250), (12, 7))
    premise = Step("probe", TAP_CELL, (board_fact,), 0.0).premise

    assert premise.ui == (MAP_SCREEN,)
    assert premise.domain == (board_fact,)


def test_map_screen_builds_the_local_board_into_the_belief():
    cells = {(3, 4): CellContent.EMPTY}
    board = LocalBoard(GridProjection(4, (0, 0)), frozenset(cells), cells)
    parts = map_parts(lambda reading, known, prior, displacement: board)
    planner = planner_of(None)
    run(TimelineStream(frames(*steady(5, 0.1, 0.4))), planner, **parts)

    reading, _, prior, _ = parts["mapgeom"].fit.call_args.args
    assert (reading.frame_seq, prior) == (4, None)
    assert beliefs(planner)[0].board is board
    assert beliefs(planner)[0].domain.boards == 1


def test_next_map_fit_takes_the_last_projection_as_its_prior():
    projection = GridProjection(4, (0, 0))
    parts = map_parts(
        lambda reading, known, prior, displacement: LocalBoard(projection, frozenset(), {})
    )
    pan = replace(OPEN_MENU, precondition=(MAP_SCREEN,), outcomes=())
    stream = TimelineStream(frames(*steady(5, 0.1, 0.5), *steady(5, 0.6, 1.3)))
    run(stream, planner_of(Step("pan", pan, (), 0.0), None), **parts)

    priors = [c.args[2] for c in parts["mapgeom"].fit.call_args_list]
    assert priors == [None, projection]


def test_stop_request_ends_the_loop_between_cycles():
    stop = Event()
    stop.set()
    _, result = run(TimelineStream(frames(*steady(1, 0.1, 0.4))), planner_of(), stop=stop)

    assert result is RunResult.STOPPED
