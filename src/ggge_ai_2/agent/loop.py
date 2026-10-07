from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from threading import Event

from ggge_ai_2.actuator.contract import (
    Actuator,
    Dispatch,
    Gesture,
    GestureBlocked,
    Key,
    Rect,
    ScreenPoint,
    Swipe,
    Tap,
)
from ggge_ai_2.agent.clock import Instant, now
from ggge_ai_2.agent.contract import (
    ActionResult,
    ActionStatus,
    AgentPlanner,
    CellReads,
    Finish,
    Sensed,
    Step,
    Wait,
)
from ggge_ai_2.interpreter.contract import Interpreter, Situation
from ggge_ai_2.mapparser.contract import MapParser
from ggge_ai_2.stream.contract import Frame, Observation, Stream
from ggge_ai_2.uisim.contract import (
    DangerBand,
    Observed,
    Outcome,
    RatioPoint,
    UiAuto,
    UiGesture,
    UiKey,
    UiMapMode,
    UiOverlay,
    UiScreen,
    UiState,
    UiSwipe,
    UiTap,
)

log = logging.getLogger(__name__)


class RunResult(StrEnum):
    DONE = "done"
    HALTED = "halted"
    STOPPED = "stopped"


@dataclass(frozen=True)
class ScreenSize:
    width: int
    height: int


@dataclass
class Agent[S]:
    stream: Stream
    interpreter: Interpreter
    mapparser: MapParser
    actuator: Actuator
    screen: ScreenSize
    planner: AgentPlanner[S]
    state: S
    idle_deadline: float
    stop: Event = field(default_factory=Event)
    _after: Instant = field(default=0.0, init=False)

    def run(self) -> RunResult:
        acted: ActionResult | None = None
        while not self.stop.is_set():
            sensed = self.observe()
            if sensed is None:
                break
            decision, self.state = self.planner.plan(self.state, sensed, acted)
            if isinstance(decision, Finish):
                return RunResult.DONE if decision is Finish.DONE else RunResult.HALTED
            acted = None if isinstance(decision, Wait) else self.execute(decision)
        return RunResult.STOPPED

    def observe(self) -> Sensed | None:
        obs = self._settle(self._after, now() + self.idle_deadline)
        waited = obs.waited
        while obs.still is None:
            if self.stop.is_set():
                return None
            obs = self._settle(obs.frame.captured_at, now() + self.idle_deadline)
            waited += obs.waited

        observed = _situation_to_observed(self.interpreter.interpret(obs.frame))
        on_map = observed is not None and observed.map_mode is not None
        reading = self.mapparser.parse(obs.frame) if on_map else None
        log.info(
            "observe",
            extra={
                "frame_seq": obs.frame.seq,
                "still_since": obs.still.since,
                "still_until": obs.still.until,
                "waited": waited,
                "recognized": observed is not None,
            },
        )
        return Sensed(obs.still, observed, reading)

    def execute(self, step: Step) -> ActionResult:
        guarded = self.guard(step)
        if isinstance(guarded, ActionResult):
            return guarded
        dispatch = self.dispatch(step, guarded)
        if dispatch is None:
            return ActionResult(step, ActionStatus.BLOCKED)
        outcome = self.verify(step, dispatch)
        status = ActionStatus.UNVERIFIED if outcome is None else ActionStatus.VERIFIED
        return ActionResult(step, status, outcome=outcome)

    def guard(self, step: Step) -> Gesture | ActionResult:
        frame = self.stream.latest()
        self._after = frame.captured_at
        fresh = step.frame_after is None or frame.captured_at > step.frame_after
        failed = self._failed_ui(frame, step.operation.precondition) or self._failed_map(
            frame, step.map_premise
        )
        gesture = self._gesture(frame, step) if fresh and failed is None else None
        log.info(
            "guard",
            extra={
                "frame_seq": frame.seq,
                "captured_at": frame.captured_at,
                "operation": step.operation.name,
                "fresh": fresh,
                "failed_premise": failed,
                "located": gesture is not None,
            },
        )
        if gesture is None:
            return ActionResult(step, ActionStatus.GUARD_FAILED, failed_premise=failed)
        return gesture

    def dispatch(self, step: Step, gesture: Gesture) -> Dispatch | None:
        name = step.operation.name
        band = _danger_band_to_rects(step.band, self.screen)
        try:
            dispatch = self.actuator.dispatch(gesture, band)
        except GestureBlocked:
            log.info("blocked", extra={"operation": name})
            return None
        log.info("dispatch", extra={"operation": name, "t0": dispatch.t0, "t1": dispatch.t1})
        return dispatch

    def verify(self, step: Step, dispatch: Dispatch) -> Outcome | None:
        op = step.operation
        obs = self._settle(dispatch.t0, dispatch.t1 + op.deadline)
        outcome = self._classify(obs.frame, op.outcomes) if obs.still else None
        log.info(
            "verify",
            extra={
                "frame_seq": obs.frame.seq,
                "captured_at": obs.frame.captured_at,
                "still": obs.still is not None,
                "waited": obs.waited,
                "outcome": outcome.name if outcome else None,
            },
        )
        return outcome

    def _settle(self, after: Instant, deadline: Instant) -> Observation:
        obs = self.stream.settled(after, deadline)
        assert obs.frame.captured_at > after, "stream returned a frame older than the cutoff"
        self._after = obs.frame.captured_at
        return obs

    def _failed_ui(self, frame: Frame, state: UiState) -> UiState | None:
        observed = _situation_to_observed(self.interpreter.interpret(frame))
        return None if observed == _ui_state_to_observed(state) else state

    def _failed_map(self, frame: Frame, premise: tuple[CellReads, ...]) -> CellReads | None:
        if not premise:
            return None
        reading = self.mapparser.parse(frame)
        for fact in premise:
            if reading is None or reading.cells.get(fact.cell) is not fact.reading:
                return fact
        return None

    def _gesture(self, frame: Frame, step: Step) -> Gesture | None:
        if step.target is None:
            return _ui_gesture_to_gesture(step.operation.gesture, self.screen)
        point = self.mapparser.locate(frame, step.target)
        return None if point is None else Tap(point)

    def _classify(self, frame: Frame, outcomes: tuple[Outcome, ...]) -> Outcome | None:
        observed = _situation_to_observed(self.interpreter.interpret(frame))
        for outcome in outcomes:
            if observed == _ui_state_to_observed(outcome.then):
                return outcome
        return None


def _ui_state_to_observed(state: UiState) -> Observed:
    return Observed(state.screen, state.overlays, state.map_mode, state.auto, state.grid_shown)


def _situation_to_observed(situation: Situation | None) -> Observed | None:
    if situation is None:
        return None
    return Observed(
        UiScreen(situation.screen.value),
        frozenset(UiOverlay(overlay.value) for overlay in situation.overlays),
        None if situation.map_mode is None else UiMapMode(situation.map_mode.value),
        None if situation.auto is None else UiAuto(situation.auto.value),
        situation.grid_shown,
    )


def _ratio_point_to_screen_point(point: RatioPoint, screen: ScreenSize) -> ScreenPoint:
    x, y = point
    return (round(x * screen.width), round(y * screen.height))


def _ui_gesture_to_gesture(gesture: UiGesture, screen: ScreenSize) -> Gesture:
    match gesture:
        case UiTap(point):
            return Tap(_ratio_point_to_screen_point(point, screen))
        case UiSwipe(start, end, duration):
            return Swipe(
                _ratio_point_to_screen_point(start, screen),
                _ratio_point_to_screen_point(end, screen),
                duration,
            )
        case UiKey(code):
            return Key(code)


def _danger_band_to_rects(band: DangerBand, screen: ScreenSize) -> tuple[Rect, ...]:
    return tuple(
        Rect(
            round(region.left * screen.width),
            round(region.top * screen.height),
            round(region.right * screen.width),
            round(region.bottom * screen.height),
        )
        for region in band.regions
    )
