from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from enum import StrEnum
from threading import Event

from ggge_ai_2.actuator.contract import Actuator, Dispatch, GestureBlocked
from ggge_ai_2.agent.belief import Belief, Passing, ScreenLock, Sensed, UiSource
from ggge_ai_2.agent.clock import Instant, now
from ggge_ai_2.agent.contract import Plan, PlanController, Step
from ggge_ai_2.interpreter.contract import Interpreter, Screen, Situation
from ggge_ai_2.mapgeom.contract import BoardEdge, CellContent, LocalBoard, MapGeometry
from ggge_ai_2.mapparser.contract import MapParser, MapReading
from ggge_ai_2.stream.contract import Observation, Stream
from ggge_ai_2.uisim.contract import (
    Observed,
    UiScreen,
    UiSim,
)

log = logging.getLogger(__name__)

MISMATCH_LIMIT = 3
MAP_SCREENS = frozenset(
    {
        UiScreen.PLAYER_PHASE_OVERVIEW,
        UiScreen.SELECT_ACTION_IN_BATTLE,
        UiScreen.SELECT_SKILL_IN_BATTLE,
        UiScreen.SELECT_WEAPON_IN_BATTLE,
        UiScreen.NON_PLAYER_PHASE_BATTLE_VIEW,
    }
)
PASSING_SCREENS = {
    Screen.LOADING: Passing.WAIT,
    Screen.SIMPLIFY_WEAPON_ANIME: Passing.WAIT,
    Screen.EX_WEAPON_ANIME: Passing.WAIT,
    Screen.MAP_PASSING: Passing.WAIT,
    Screen.BATTLE_CLEAR_VIEW: Passing.TAP_TO_CONTINUE,
}


class RunResult(StrEnum):
    DONE = "done"
    HALTED = "halted"
    STOPPED = "stopped"


class UnreadableScreen(Exception):
    def __init__(self, step: Step, belief: Belief) -> None:
        super().__init__(step.name)
        self.step = step
        self.belief = belief


@dataclass(frozen=True)
class Predicted:
    beliefs: tuple[Belief, ...]
    deadline: Instant


@dataclass
class Agent:
    stream: Stream
    actuator: Actuator
    interpreter: Interpreter
    mapparser: MapParser
    mapgeom: MapGeometry
    uisim: UiSim
    plan_controller: PlanController
    belief: Belief
    idle_deadline: float
    stop: Event = field(default_factory=Event)
    _after: Instant = field(default=0.0, init=False)

    def run(self) -> RunResult:
        plan: Plan | None = None
        predicted: Predicted | None = None
        mismatches = 0
        history: list[object] = []
        while not self.stop.is_set():
            sensed = self.sense()
            if sensed is None:
                break
            self.belief = self.belief.update(sensed, self.uisim, self.mapgeom)

            if self.plan_controller.goal_reached(self.belief):
                if plan is not None:
                    history.append(self.plan_controller.review(plan, self.belief))
                return RunResult.DONE

            passing = self.belief.passing is not None
            if not passing:
                if predicted is not None and not self.matches(self.belief, predicted):
                    mismatches += 1
                else:
                    mismatches = 0
            effect_failed = mismatches >= MISMATCH_LIMIT

            plan_invalid = plan is not None and not plan.still_valid(self.belief)

            if plan is None or effect_failed or plan_invalid:
                if plan is not None:
                    history.append(self.plan_controller.review(plan, self.belief))
                plan = self.plan_controller.think(self.belief, history)
                mismatches = 0
                if plan is None:
                    return RunResult.HALTED

            step = plan.next(self.belief)
            try:
                self.guard(step, self.belief)
            except UnreadableScreen as unreadable:
                log.error(
                    "guard on an unreadable screen",
                    extra={
                        "step": unreadable.step.name,
                        "believed_ui": unreadable.belief.ui,
                        "unreadable_since_frame_seq": unreadable.belief.ui_basis.frame_seq,
                    },
                )
                return RunResult.HALTED
            dispatch = self.act(step)
            if not passing:
                predicted = None if dispatch is None else self.predict(step, dispatch)
        return RunResult.STOPPED

    def sense(self) -> Sensed | None:
        obs = self._settle(self._after, now() + self.idle_deadline)
        waited = obs.waited
        while obs.still is None:
            if self.stop.is_set():
                return None
            obs = self._settle(obs.frame.captured_at, now() + self.idle_deadline)
            waited += obs.waited

        situation = self.interpreter.interpret(obs.frame)
        locks = {Screen.POWER_SAVE_LOCK: ScreenLock.ICON, Screen.POWER_SAVE_DIM: ScreenLock.DIM}
        screen_lock = None if situation is None else locks.get(situation.screen)
        passing = None if situation is None else PASSING_SCREENS.get(situation.screen)
        readable = screen_lock is None and passing is None
        observed = _situation_to_observed(situation) if readable else None
        on_map = observed is not None and observed.screen in MAP_SCREENS
        reading = self.mapparser.parse(obs.frame) if on_map else None
        log.info(
            "sense",
            extra={
                "frame_seq": obs.frame.seq,
                "still_since": obs.still.since,
                "still_until": obs.still.until,
                "waited": waited,
                "recognized": situation is not None,
            },
        )
        board = _map_reading_to_local_board(reading)
        return Sensed(obs.still, observed, board, screen_lock, passing)

    def matches(self, belief: Belief, predicted: Predicted) -> bool:
        still = belief.as_of
        in_time = still is not None and still.since <= predicted.deadline
        same = any(
            replace(expected, as_of=belief.as_of, ui_basis=belief.ui_basis) == belief
            for expected in predicted.beliefs
        )
        log.info(
            "matches",
            extra={
                "frame_seq": None if still is None else still.frame_seq,
                "in_time": in_time,
                "same": same,
            },
        )
        return in_time and same

    def guard(self, step: Step, belief: Belief) -> None:
        if belief.ui_basis.source is UiSource.LOST:
            raise UnreadableScreen(step, belief)

    def act(self, step: Step) -> Dispatch | None:
        name = step.name
        if step.gesture is None:
            at = now()
            self._after = at
            log.info("wait", extra={"step": name})
            return Dispatch(at, at)
        try:
            dispatch = self.actuator.dispatch(step.gesture, step.band)
        except GestureBlocked:
            log.info("blocked", extra={"step": name})
            return None
        self._after = dispatch.t0
        log.info("act", extra={"step": name, "t0": dispatch.t0, "t1": dispatch.t1})
        return dispatch

    def predict(self, step: Step, dispatch: Dispatch) -> Predicted:
        return Predicted(step.expected, dispatch.t1 + step.deadline)

    def _settle(self, after: Instant, deadline: Instant) -> Observation:
        obs = self.stream.settled(after, deadline)
        assert obs.frame.captured_at > after, "stream returned a frame older than the cutoff"
        self._after = obs.frame.captured_at
        return obs


def _situation_to_observed(situation: Situation | None) -> Observed | None:
    if situation is None:
        return None
    return Observed(UiScreen(situation.screen.value), situation.auto)


def _map_reading_to_local_board(reading: MapReading | None) -> LocalBoard | None:
    if reading is None:
        return None
    return LocalBoard(
        {cell: CellContent(seen.value) for cell, seen in reading.cells.items()},
        frozenset(BoardEdge(edge.value) for edge in reading.borders),
    )
