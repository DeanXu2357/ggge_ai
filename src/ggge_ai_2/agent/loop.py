from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from enum import StrEnum
from threading import Event
from typing import Protocol, Self

from ggge_ai_2.actuator.contract import Actuator, Dispatch, Gesture, GestureBlocked, Rect
from ggge_ai_2.agent.clock import Instant, now
from ggge_ai_2.interpreter.contract import Interpreter, Situation
from ggge_ai_2.mapgeom.contract import (
    Alignment,
    BoardEdge,
    CellContent,
    KnownMap,
    LocalBoard,
    MapGeometry,
)
from ggge_ai_2.mapparser.contract import MapParser, MapReading
from ggge_ai_2.planner.contract import (
    ActionResult,
    ActionStatus,
    Finish,
    Planner,
    Refused,
    State,
    Step,
    Wait,
)
from ggge_ai_2.stream.contract import Frame, Observation, StillWindow, Stream
from ggge_ai_2.uisim.contract import (
    DangerBand,
    Observed,
    Outcome,
    UiMapMode,
    UiOverlay,
    UiScreen,
    UiSim,
    UiState,
)

log = logging.getLogger(__name__)


class DomainState(Protocol):
    def absorb(self, intent: object, outcome: Outcome | None) -> Self: ...


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
    camera: Alignment | None
    known_map: KnownMap
    domain: DomainState
    as_of: StillWindow | None
    last_action: ActionResult | None = None

    def revise_when_sensed(
        self,
        still: StillWindow,
        observed: Observed | None,
        board: LocalBoard | None,
        uisim: UiSim,
        mapgeom: MapGeometry,
    ) -> Belief:
        ui, basis = self._read_ui(still.frame_seq, observed, uisim)
        camera, known_map = self.camera, self.known_map
        if board is not None:
            alignment = mapgeom.align(board, known_map, camera)
            if alignment is not None:
                camera, known_map = alignment, mapgeom.merge(known_map, board, alignment)
        return replace(self, ui=ui, ui_basis=basis, camera=camera, known_map=known_map, as_of=still)

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

    def revise_when_guard_failed(self, step: Step, refused: Refused) -> Belief:
        result = ActionResult(
            step.intent, step.operation.name, ActionStatus.GUARD_FAILED, refused=refused
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
                sensed.still,
                sensed.observed,
                _map_reading_to_local_board(sensed.map),
                self.uisim,
                self.mapgeom,
            )
            decision, self.agenda = self.planner.plan(_belief_to_state(self.belief), self.agenda)
            if isinstance(decision, Finish):
                return RunResult.DONE if decision is Finish.DONE else RunResult.HALTED
            if isinstance(decision, Wait):
                continue
            stopped = self._execute(decision)
            if stopped:
                return RunResult.HALTED
        return RunResult.STOPPED

    def _execute(self, step: Step) -> bool:
        gesture = self.guard(step)
        if isinstance(gesture, Refused):
            self.belief = self.belief.revise_when_guard_failed(step, gesture)
            return False

        band = _danger_band_to_rects(self.uisim.danger_band(self.belief.ui), self.screen)
        dispatch = self.dispatch(step, gesture, band)
        if dispatch is None:
            self.belief = self.belief.revise_when_band_blocked(step)
            return False

        result = self._settle(dispatch.t0, dispatch.t1 + step.operation.deadline)
        if result.still is None:
            log.error(
                "result not still at the deadline",
                extra={
                    "frame_seq": result.frame.seq,
                    "waited": result.waited,
                    "operation": step.operation.name,
                },
            )
            outcome = None
        else:
            outcome = self.verify(step, result)
            if outcome is None and self.judge_interrupt(step, result.frame):
                return True
        self.belief = self.belief.revise_when_dispatched(step, outcome, self.uisim)
        return False

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

    def guard(self, step: Step) -> Gesture | Refused:
        frame = self.stream.latest()
        self._after = frame.captured_at
        if step.frame_after is not None and frame.captured_at <= step.frame_after:
            answer: Gesture | Refused = Refused("guard frame is not newer than the step requires")
        else:
            answer = step.guard(frame)
        log.info(
            "guard",
            extra={
                "frame_seq": frame.seq,
                "captured_at": frame.captured_at,
                "operation": step.operation.name,
                "refused": answer.reason if isinstance(answer, Refused) else None,
            },
        )
        return answer

    def dispatch(self, step: Step, gesture: Gesture, band: tuple[Rect, ...]) -> Dispatch | None:
        name = step.operation.name
        try:
            dispatch = self.actuator.dispatch(gesture, band)
        except GestureBlocked:
            log.info("blocked", extra={"operation": name})
            return None
        log.info("dispatch", extra={"operation": name, "t0": dispatch.t0, "t1": dispatch.t1})
        return dispatch

    def verify(self, step: Step, result: Observation) -> Outcome | None:
        outcome = step.verify(result.frame)
        log.info(
            "verify",
            extra={
                "frame_seq": result.frame.seq,
                "captured_at": result.frame.captured_at,
                "waited": result.waited,
                "outcome": outcome.name if outcome else None,
            },
        )
        return outcome

    def judge_interrupt(self, step: Step, frame: Frame) -> bool:
        stop = step.interrupt(frame)
        log.info(
            "interrupt",
            extra={"frame_seq": frame.seq, "operation": step.operation.name, "stop": stop},
        )
        return stop

    def _settle(self, after: Instant, deadline: Instant) -> Observation:
        obs = self.stream.settled(after, deadline)
        assert obs.frame.captured_at > after, "stream returned a frame older than the cutoff"
        self._after = obs.frame.captured_at
        return obs


def _belief_to_state(belief: Belief) -> State:
    return State(
        ui=belief.ui,
        ui_lost=belief.ui_basis.source is UiSource.LOST,
        camera=belief.camera,
        known_map=belief.known_map,
        domain=belief.domain,
        as_of=belief.as_of.until if belief.as_of else None,
        last_action=belief.last_action,
    )


def _situation_to_observed(situation: Situation | None) -> Observed | None:
    if situation is None:
        return None
    return Observed(
        UiScreen(situation.screen.value),
        frozenset(UiOverlay(overlay.value) for overlay in situation.overlays),
        None if situation.map_mode is None else UiMapMode(situation.map_mode.value),
    )


def _map_reading_to_local_board(reading: MapReading | None) -> LocalBoard | None:
    if reading is None:
        return None
    return LocalBoard(
        {cell: CellContent(seen.value) for cell, seen in reading.cells.items()},
        frozenset(BoardEdge(edge.value) for edge in reading.borders),
    )


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
