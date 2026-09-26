from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from threading import Event
from typing import Protocol, Self

from ggge_ai_2.actuator.contract import Actuator, DangerBand
from ggge_ai_2.clock import Instant, now
from ggge_ai_2.interpreter.contract import Interpreter
from ggge_ai_2.mapgeom.contract import BoardFact, KnownMap, LocalBoard, MapGeometry
from ggge_ai_2.mapparser.contract import MapParser
from ggge_ai_2.stream.contract import Frame, FrameVector, Observation, StillWindow, Stream
from ggge_ai_2.uisim.contract import Operation, Outcome, Screen, UiFact, UiSim
from ggge_ai_2.verdict import Verdict

log = logging.getLogger(__name__)

DangerBands = Mapping[Screen, DangerBand]


class DomainState(Protocol):
    def absorb(self, intent: object, outcome: Outcome | None) -> Self: ...

    def observe(self, board: LocalBoard) -> Self: ...

    def known_map(self) -> KnownMap: ...


@dataclass(frozen=True)
class Belief:
    ui: UiSim
    domain: DomainState
    board: LocalBoard | None
    still: StillWindow


@dataclass(frozen=True)
class Premise:
    ui: tuple[UiFact, ...]
    domain: tuple[BoardFact, ...]


@dataclass(frozen=True)
class Step:
    intent: object
    operation: Operation
    domain_premise: tuple[BoardFact, ...]
    based_on: Instant

    @property
    def premise(self) -> Premise:
        return Premise(ui=self.operation.precondition, domain=self.domain_premise)


class Planner(Protocol):
    def plan(self, belief: Belief) -> Step | None: ...


class RunResult(StrEnum):
    DONE = "done"
    STOPPED = "stopped"


class Halt(Exception):
    def __init__(self, observation: Observation) -> None:
        super().__init__(f"unreadable screen at frame {observation.frame.seq}")
        self.observation = observation


@dataclass
class Agent:
    stream: Stream
    interpreter: Interpreter
    mapparser: MapParser
    mapgeom: MapGeometry
    actuator: Actuator
    planner: Planner
    bands: DangerBands
    initial_ui: UiSim
    initial_domain: DomainState
    idle_deadline: float
    stop: Event = field(default_factory=Event)
    clock: Callable[[], Instant] = now
    belief: Belief | None = field(default=None, init=False)
    _after: Instant = field(default=0.0, init=False)

    def run(self) -> RunResult:
        while not self.stop.is_set():
            if not self.observe():
                break
            step = self.planner.plan(self.belief)
            if step is None:
                return RunResult.DONE
            self.execute(step)
        return RunResult.STOPPED

    def observe(self) -> bool:
        obs = self._settle(self._after, self.clock() + self.idle_deadline)
        while obs.still is None:
            if self.stop.is_set():
                return False
            obs = self._settle(obs.frame.captured_at, self.clock() + self.idle_deadline)

        prior = self.belief
        ui = prior.ui if prior else self.initial_ui
        domain = prior.domain if prior else self.initial_domain
        if prior is None or self._failed_ui(obs.frame, ui.state.facts()) is not None:
            observed = self.interpreter.interpret(obs.frame)
            if observed is None:
                raise Halt(obs)
            ui = ui.sync(observed)

        board = None
        if ui.state.map_mode is not None:
            reading = self.mapparser.parse(obs.frame)
            last = prior.board.projection if prior and prior.board else None
            board = self.mapgeom.fit(reading, domain.known_map(), last, obs.displacement)
            if board is not None:
                domain = domain.observe(board)

        self.belief = Belief(ui=ui, domain=domain, board=board, still=obs.still)
        log.info(
            "observe",
            extra={
                "frame_seq": obs.frame.seq,
                "still_since": obs.still.since,
                "still_until": obs.still.until,
                "waited": obs.waited,
                "screen": ui.state.screen,
            },
        )
        return True

    def execute(self, step: Step) -> None:
        belief = self.belief
        op = step.operation
        guard = self.stream.latest()
        assert guard.captured_at >= step.based_on, "guard frame is older than the plan"
        failed = self._failed_ui(guard, step.premise.ui) or self._failed_domain(
            guard, step.premise.domain, belief
        )
        log.info(
            "guard",
            extra={
                "frame_seq": guard.seq,
                "captured_at": guard.captured_at,
                "operation": op.name,
                "failed_premise": failed,
            },
        )
        if failed is not None:
            self._after = guard.captured_at
            return

        dispatch = self.actuator.dispatch(op.gesture, self.bands[belief.ui.state.screen])
        log.info("dispatch", extra={"operation": op.name, "t0": dispatch.t0, "t1": dispatch.t1})

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
        self.belief = replace(
            belief,
            ui=belief.ui.advance(outcome) if outcome else belief.ui,
            domain=belief.domain.absorb(step.intent, outcome),
            still=obs.still if outcome else belief.still,
        )

    def _settle(self, after: Instant, deadline: Instant) -> Observation:
        obs = self.stream.settled(after, deadline)
        assert obs.frame.captured_at > after, "stream returned a frame older than the cutoff"
        self._after = obs.frame.captured_at
        return obs

    def _failed_ui(self, frame: Frame, facts: tuple[UiFact, ...]) -> tuple[UiFact, Verdict] | None:
        for fact in facts:
            verdict = self.interpreter.verify(frame, fact)
            if verdict is not Verdict.HOLDS:
                return fact, verdict
        return None

    def _failed_domain(
        self, frame: Frame, facts: tuple[BoardFact, ...], belief: Belief
    ) -> tuple[BoardFact, Verdict] | None:
        if not facts:
            return None
        reading = self.mapparser.parse(frame)
        prior = belief.board.projection if belief.board else None
        # The guard has one frame, so it has no pan displacement. The fit then depends on
        # the prior alone, and it can read a pan of exactly one cell as no pan.
        board = self.mapgeom.fit(reading, belief.domain.known_map(), prior, FrameVector(0.0, 0.0))
        if board is None:
            return facts[0], Verdict.UNREADABLE
        for fact in facts:
            verdict = fact.holds_on(board)
            if verdict is not Verdict.HOLDS:
                return fact, verdict
        return None

    def _classify(self, frame: Frame, outcomes: tuple[Outcome, ...]) -> Outcome | None:
        for outcome in outcomes:
            if self.interpreter.verify(frame, outcome.fact) is Verdict.HOLDS:
                return outcome
        return None
