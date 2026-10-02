from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from enum import StrEnum
from threading import Event
from typing import Protocol, Self

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
from ggge_ai_2.interpreter.contract import Interpreter, Situation
from ggge_ai_2.mapgeom.contract import (
    BoardFact,
    BoardVerdict,
    KnownMap,
    LocalBoard,
    MapGeometry,
    Projection,
)
from ggge_ai_2.mapparser.contract import MapParser, MapReading
from ggge_ai_2.planner.contract import (
    ActionResult,
    ActionStatus,
    Finish,
    Planner,
    State,
    Step,
    Wait,
)
from ggge_ai_2.stream.contract import Displacement, Frame, Observation, StillWindow, Stream
from ggge_ai_2.uisim.contract import (
    DangerBand,
    Observed,
    Outcome,
    RatioPoint,
    UiGesture,
    UiKey,
    UiMapMode,
    UiOverlay,
    UiScreen,
    UiSim,
    UiState,
    UiSwipe,
    UiTap,
)

log = logging.getLogger(__name__)


class DomainState(Protocol):
    def absorb(self, intent: object, outcome: Outcome | None) -> Self: ...

    def observe(self, board: LocalBoard) -> Self: ...

    def known_map(self) -> KnownMap: ...


class UiSource(StrEnum):
    ASSUMED = "assumed"
    SEEN = "seen"
    PREDICTED = "predicted"
    LOST = "lost"


@dataclass(frozen=True)
class UiBasis:
    source: UiSource
    frame_seq: int | None = None
    outcome: str | None = None


@dataclass(frozen=True)
class Belief:
    ui: UiState
    ui_basis: UiBasis
    camera: Projection | None
    drift: Displacement
    domain: DomainState
    as_of: StillWindow | None
    last_action: ActionResult | None = None

    def revise_when_sensed(
        self,
        still: StillWindow,
        observed: Observed | None,
        reading: MapReading | None,
        uisim: UiSim,
        mapgeom: MapGeometry,
    ) -> Belief:
        ui, basis = self._read_ui(still.frame_seq, observed, uisim)
        camera, domain = self.camera, self.domain
        if reading is not None:
            board = mapgeom.fit(reading, domain.known_map(), camera, self.drift)
            if board is not None:
                camera, domain = board.projection, domain.observe(board)
        return replace(self, ui=ui, ui_basis=basis, camera=camera, domain=domain, as_of=still)

    def revise_when_dispatched(self, step: Step, outcome: Outcome | None, uisim: UiSim) -> Belief:
        domain = self.domain.absorb(step.intent, outcome)
        if outcome is None:
            result = ActionResult(step.intent, step.operation.name, ActionStatus.UNVERIFIED)
            return replace(self, domain=domain, last_action=result)
        result = ActionResult(
            step.intent, step.operation.name, ActionStatus.VERIFIED, outcome=outcome.name
        )
        return replace(
            self,
            ui=uisim.advance(self.ui, outcome),
            ui_basis=UiBasis(UiSource.PREDICTED, outcome=outcome.name),
            domain=domain,
            last_action=result,
        )

    def revise_when_guard_failed(self, step: Step, premise: UiState | BoardFact) -> Belief:
        result = ActionResult(
            step.intent, step.operation.name, ActionStatus.GUARD_FAILED, failed_premise=premise
        )
        return replace(self, last_action=result)

    def revise_when_band_blocked(self, step: Step) -> Belief:
        result = ActionResult(step.intent, step.operation.name, ActionStatus.BLOCKED)
        return replace(self, last_action=result)

    def _read_ui(
        self, frame_seq: int, observed: Observed | None, uisim: UiSim
    ) -> tuple[UiState, UiBasis]:
        if observed is not None:
            return uisim.sync(self.ui, observed), UiBasis(UiSource.SEEN, frame_seq=frame_seq)
        if self.ui_basis.source is UiSource.LOST:
            return self.ui, self.ui_basis
        return self.ui, UiBasis(UiSource.LOST, frame_seq=frame_seq)


class RunResult(StrEnum):
    DONE = "done"
    HALTED = "halted"
    STOPPED = "stopped"


@dataclass(frozen=True)
class ScreenSize:
    width: int
    height: int


@dataclass(frozen=True)
class Sensed:
    still: StillWindow
    observed: Observed | None
    map: MapReading | None


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
            sensed = self.observe()
            if sensed is None:
                break
            self.belief = self.belief.revise_when_sensed(
                sensed.still, sensed.observed, sensed.map, self.uisim, self.mapgeom
            )
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
            return belief.revise_when_guard_failed(step, failed)

        band = _danger_band_to_rects(self.uisim.danger_band(belief.ui), self.screen)
        dispatch = self.dispatch(step, band)
        if dispatch is None:
            return belief.revise_when_band_blocked(step)

        return belief.revise_when_dispatched(step, self.verify(step, dispatch), self.uisim)

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

    def guard(self, step: Step, belief: Belief) -> UiState | BoardFact | None:
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
        return failed

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

    def _failed_domain(
        self, frame: Frame, facts: tuple[BoardFact, ...], belief: Belief
    ) -> BoardFact | None:
        if not facts:
            return None
        reading = self.mapparser.parse(frame)
        # The guard has one frame, so it has no displacement after the observed frame. The
        # fit then depends on the prior, and it can read a pan of exactly one cell as no pan.
        board = self.mapgeom.fit(reading, belief.domain.known_map(), belief.camera, belief.drift)
        if board is None:
            return facts[0]
        for fact in facts:
            if fact.holds_on(board) is not BoardVerdict.HOLDS:
                return fact
        return None

    def _classify(self, frame: Frame, outcomes: tuple[Outcome, ...]) -> Outcome | None:
        observed = _situation_to_observed(self.interpreter.interpret(frame))
        for outcome in outcomes:
            if observed == _ui_state_to_observed(outcome.then):
                return outcome
        return None


def _belief_to_state(belief: Belief) -> State:
    return State(
        ui=belief.ui,
        ui_lost=belief.ui_basis.source is UiSource.LOST,
        camera=belief.camera,
        domain=belief.domain,
        as_of=belief.as_of.until if belief.as_of else None,
        last_action=belief.last_action,
    )


def _ui_state_to_observed(state: UiState) -> Observed:
    return Observed(state.screen, state.overlays, state.map_mode)


def _situation_to_observed(situation: Situation | None) -> Observed | None:
    if situation is None:
        return None
    return Observed(
        UiScreen(situation.screen.value),
        frozenset(UiOverlay(overlay.value) for overlay in situation.overlays),
        None if situation.map_mode is None else UiMapMode(situation.map_mode.value),
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
