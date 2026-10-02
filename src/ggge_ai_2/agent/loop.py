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
from ggge_ai_2.agent.belief import Belief, UiSource
from ggge_ai_2.agent.clock import Instant, now
from ggge_ai_2.agent.evidence import Dispatched, GuardFailed, Sensed
from ggge_ai_2.interpreter.contract import Fact, Interpreter, Situation, Verdict
from ggge_ai_2.mapgeom.contract import BoardFact, BoardVerdict, MapGeometry
from ggge_ai_2.mapparser.contract import MapParser
from ggge_ai_2.planner.contract import Finish, Planner, State, Step, Wait
from ggge_ai_2.stream.contract import Frame, Observation, Stream, add_displacement
from ggge_ai_2.uisim.contract import (
    DangerBand,
    Observed,
    Outcome,
    RatioPoint,
    UiGesture,
    UiKey,
    UiSim,
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
class Agent[A]:
    stream: Stream
    interpreter: Interpreter
    mapparser: MapParser
    mapgeom: MapGeometry
    uisim: UiSim
    actuator: Actuator
    screen: ScreenSize
    planner: Planner[A]
    belief: Belief
    agenda: A
    idle_deadline: float
    stop: Event = field(default_factory=Event)
    _after: Instant = field(default=0.0, init=False)

    def run(self) -> RunResult:
        while not self.stop.is_set():
            sensed = self.observe(self.belief)
            if sensed is None:
                break
            self.belief = self.belief.sensed(sensed, self.uisim, self.mapgeom)
            decision, self.agenda = self.planner.plan(_belief_to_state(self.belief), self.agenda)
            if isinstance(decision, Finish):
                return RunResult.DONE if decision is Finish.DONE else RunResult.HALTED
            if isinstance(decision, Wait):
                continue
            self.belief = self._execute(decision, self.belief)
        return RunResult.STOPPED

    def _execute(self, step: Step, belief: Belief) -> Belief:
        failed = self.guard(step, belief)
        if failed is not None:
            return belief.guard_failed(failed)

        band = _danger_band_to_rects(self.uisim.danger_band(belief.ui), self.screen)
        dispatch = self.dispatch(step, band)
        if dispatch is None:
            return belief.band_blocked(step)

        return belief.dispatched(self.verify(step, dispatch), self.uisim)

    def observe(self, belief: Belief) -> Sensed | None:
        obs = self._settle(self._after, now() + self.idle_deadline)
        after, waited, displacement = obs.after, obs.waited, obs.displacement
        while obs.still is None:
            if self.stop.is_set():
                return None
            obs = self._settle(obs.frame.captured_at, now() + self.idle_deadline)
            waited += obs.waited
            displacement = add_displacement(displacement, obs.displacement)

        holds = self._prediction_holds(obs.frame, belief)
        observed = None if holds else _situation_to_observed(self.interpreter.interpret(obs.frame))
        on_map = _map_mode(holds, observed, belief) is not None
        reading = self.mapparser.parse(obs.frame) if on_map else None
        log.info(
            "observe",
            extra={
                "frame_seq": obs.frame.seq,
                "still_since": obs.still.since,
                "still_until": obs.still.until,
                "waited": waited,
                "prediction_holds": holds,
                "recognized": observed is not None,
            },
        )
        return Sensed(
            obs.frame.seq, after, obs.still, waited, holds, observed, reading, displacement
        )

    def guard(self, step: Step, belief: Belief) -> GuardFailed | None:
        frame = self.stream.latest()
        assert frame.captured_at >= step.based_on, "guard frame is older than the plan"
        self._after = frame.captured_at
        failed = self._failed_ui(frame, step.premise.ui) or self._failed_domain(
            frame, step.premise.domain, belief
        )
        log.info(
            "guard",
            extra={
                "frame_seq": frame.seq,
                "captured_at": frame.captured_at,
                "operation": step.operation.name,
                "failed_premise": failed,
            },
        )
        if failed is None:
            return None
        premise, verdict = failed
        return GuardFailed(step, premise, verdict, frame.seq)

    def dispatch(self, step: Step, band: tuple[Rect, ...]) -> Dispatch | None:
        op = step.operation
        gesture = _ui_gesture_to_gesture(op.gesture, self.screen)
        try:
            dispatch = self.actuator.dispatch(gesture, band)
        except GestureBlocked:
            log.info("blocked", extra={"operation": op.name})
            return None
        log.info("dispatch", extra={"operation": op.name, "t0": dispatch.t0, "t1": dispatch.t1})
        return dispatch

    def verify(self, step: Step, dispatch: Dispatch) -> Dispatched:
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
        return Dispatched(step, dispatch, obs.frame.seq, obs.still, outcome, obs.displacement)

    def _settle(self, after: Instant, deadline: Instant) -> Observation:
        obs = self.stream.settled(after, deadline)
        assert obs.frame.captured_at > after, "stream returned a frame older than the cutoff"
        self._after = obs.frame.captured_at
        return obs

    def _prediction_holds(self, frame: Frame, belief: Belief) -> bool:
        if belief.ui_basis.source is UiSource.ASSUMED:
            return False
        return self.interpreter.verify(frame, _ui_state_to_fact(belief.ui)) is Verdict.HOLDS

    def _failed_ui(self, frame: Frame, state: UiState) -> tuple[UiState, Verdict] | None:
        verdict = self.interpreter.verify(frame, _ui_state_to_fact(state))
        return None if verdict is Verdict.HOLDS else (state, verdict)

    def _failed_domain(
        self, frame: Frame, facts: tuple[BoardFact, ...], belief: Belief
    ) -> tuple[BoardFact, BoardVerdict] | None:
        if not facts:
            return None
        reading = self.mapparser.parse(frame)
        # The guard has one frame, so it has no displacement after the observed frame. The
        # fit then depends on the prior, and it can read a pan of exactly one cell as no pan.
        board = self.mapgeom.fit(reading, belief.domain.known_map(), belief.camera, belief.drift)
        if board is None:
            return facts[0], BoardVerdict.UNREADABLE
        for fact in facts:
            verdict = fact.holds_on(board)
            if verdict is not BoardVerdict.HOLDS:
                return fact, verdict
        return None

    def _classify(self, frame: Frame, outcomes: tuple[Outcome, ...]) -> Outcome | None:
        for outcome in outcomes:
            if self.interpreter.verify(frame, _ui_state_to_fact(outcome.then)) is Verdict.HOLDS:
                return outcome
        return None


def _map_mode(holds: bool, observed: Observed | None, belief: Belief) -> str | None:
    if holds:
        return belief.ui.map_mode
    if observed is None:
        return None
    return observed.map_mode


def _belief_to_state(belief: Belief) -> State:
    return State(
        ui=belief.ui,
        ui_lost=belief.ui_basis.source is UiSource.LOST,
        camera=belief.camera,
        domain=belief.domain,
        as_of=belief.as_of.until if belief.as_of else None,
        last_action=belief.last_action,
    )


def _ui_state_to_fact(state: UiState) -> Fact:
    return Fact(
        "state_is",
        {"screen": state.screen, "overlays": state.overlays, "map_mode": state.map_mode},
    )


def _situation_to_observed(situation: Situation | None) -> Observed | None:
    if situation is None:
        return None
    return Observed(situation.screen, situation.overlays, situation.map_mode)


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
