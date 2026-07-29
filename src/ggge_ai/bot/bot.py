"""The tick loop: one screenshot, at most one device interaction, no idle ticks."""

from __future__ import annotations

from dataclasses import dataclass, field

from ggge_ai.goap.planner import PlanNotFound, plan
from ggge_ai.goap.state import Value

from .action import Action
from .board import MockBoard
from .frame import FrameReading
from .mocks import IdentityClassifier, MockClock, MockDevice, MockScreen
from .router import ReflexRouter, ReflexTable, SymbolTable
from .state import BotState


class BotStuck(RuntimeError):
    """The supervisor escalating: the loop stops and asks for a human.

    Raised by `run` and nowhere else. A tick never throws this -- a tick that
    cannot proceed says so in its record and returns it, and `run` is the one
    that decides an honest stop is warranted. `kind` says what it saw:
    `no_plan` (the planner found no route -- an unprepared situation, the
    vocabulary is missing a mid-state) or `replan_storm` (its own threshold
    judgement over the reports, counted in a local rather than read out of
    the log).

    Nothing here writes to the log. The tick behind an escalation is already
    recorded like any other, so where and why it stopped is reconstructible
    from the records without the supervisor ever having filed one.
    `max_ticks` stays the coarse backstop for every stall no kind names.
    The real system turns this into a human-intervention request.
    """

    def __init__(self, message: str, kind: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass
class TickRecord:
    """One line per tick -- everything that happened, filed as it happens.

    The log is a collector, not a channel: nothing in the loop's machinery
    reads it back to decide anything (`run` supervises from the record each
    tick hands it). Reading these lines is after-the-fact analysis, which is
    why a column no other column can reconstruct -- `plan_ms` -- lives here.
    """

    tick: int
    tags: list[str]
    outcome: str
    head: str | None
    popped: list[str]
    replanned: str | None
    plan_len: int
    plan: list[str] = field(default_factory=list)
    progress: tuple[int, int] = (0, 0)
    symbols: dict[str, Value] = field(default_factory=dict)
    duration_ms: int = 0
    slept_ms: int = 0
    plan_ms: int | None = None


REPLAN_STORM_TICKS = 10


class Bot:
    """sense -> reflex/wait -> bookkeeping -> plan -> one action.

    The queue is a persistent plan: it advances on evidence (a step is popped
    when its *effect* is observed, which may take many ticks or zero
    executions) and it dies whole (a stale head throws the entire queue away
    and replans from the current symbols -- there is no repair surgery).

    There is no unknown check anywhere in the loop: a frame that cannot say
    which screen it is breaks the head's `view` precondition like any other
    stale head, and the planner routes out of it through an observation
    action that holds the head until the screen reads again.

    Same-tick continuation: pops, refill and replan are bookkeeping and pure
    computation over the frame captured at the top of this tick, so they do
    not end the tick -- the one device interaction that follows is authorized
    by that same fresh frame. What never happens is two device interactions
    on one reading.
    """

    def __init__(
        self,
        state: BotState,
        board: MockBoard,
        screen: MockScreen,
        classifier: IdentityClassifier,
        device: MockDevice,
        clock: MockClock,
        catalog: list[Action],
        symbol_table: SymbolTable,
        reflex_table: ReflexTable,
    ) -> None:
        self.state = state
        self.board = board
        self.screen = screen
        self.classifier = classifier
        self.device = device
        self.clock = clock
        self.catalog = list(catalog)
        self.symbol_table = symbol_table
        self.reflexes = ReflexRouter(reflex_table)
        self.queue: list[Action] = []
        self.log: list[TickRecord] = []
        self.finished = False

    def tick(self) -> TickRecord:
        """The whole lifecycle, inline: the spec diagram is this method, top to bottom.

        Deliberately not decomposed further -- the only extracted pieces are
        the ones with an identity of their own (reflex router, recorder,
        planner call).

        The record goes back to the caller directly, so a supervisor like
        `run` never has to read the log. Four outcomes return one:
        `reflex:<tag>`, `done`, `executed`, `stuck:no_plan` -- running out of
        road is a verdict this loop returns, not an exception it throws.
        `done` is judged here, right after the pops: an empty queue plus a
        goal the symbols satisfy, checked against the state itself and never
        inferred from what the planner answered.

        The one raise is `panic:sense`: a sense that fails is an
        infrastructure failure no action in any catalog can fix, so the tick
        dies at the top after filing one record (no tags, symbols left over
        from the previous tick) and re-raises the original exception
        untouched -- only the real traceback says whether it was the
        transport, the decoder, or the classifier.
        """
        t0 = self.clock.now_ms()
        slept0 = self.clock.slept_ms()
        try:
            frame = self.screen.capture()
            reading = self.classifier.classify(frame)
        except Exception:
            self._record(FrameReading(), t0, slept0, "panic:sense")
            raise

        perceived = self.symbol_table.translate(reading)
        perceived.update(self.board.summary_symbols())
        self.state.sense_update(perceived)

        handled = self.reflexes.route(self, reading)
        if handled is not None:
            return self._record(reading, t0, slept0, handled)

        popped: list[str] = []
        while self.queue and self.state.satisfies(self.queue[0].eff):
            popped.append(self.queue.pop(0).name)

        goal = self.state.goal
        if not self.queue and (goal is None or self.state.satisfies(goal.conditions)):
            self.finished = True
            return self._record(reading, t0, slept0, "done", popped=popped)

        if not self.queue:
            replanned = "refill"
            started = self.clock.now_ms()
            try:
                plans = self.think()
            finally:
                plan_ms = self.clock.now_ms() - started
            if plans is None:
                return self._record(
                    reading,
                    t0,
                    slept0,
                    "stuck:no_plan",
                    popped=popped,
                    replanned=replanned,
                    plan_ms=plan_ms,
                )
            self.queue = plans
        elif not self.state.satisfies(self.queue[0].pre):
            self.queue.clear()
            replanned = "replan"
            started = self.clock.now_ms()
            try:
                plans = self.think()
            finally:
                plan_ms = self.clock.now_ms() - started
            if plans is None:
                return self._record(
                    reading,
                    t0,
                    slept0,
                    "stuck:no_plan",
                    popped=popped,
                    replanned=replanned,
                    plan_ms=plan_ms,
                )
            self.queue = plans
        else:
            replanned = None
            plan_ms = None

        head = self.queue[0]
        head.do(self)
        return self._record(
            reading,
            t0,
            slept0,
            "executed",
            head=head.name,
            popped=popped,
            replanned=replanned,
            plan_ms=plan_ms,
        )

    def _record(
        self,
        reading: FrameReading,
        t0: int,
        slept0: int,
        outcome: str,
        head: str | None = None,
        popped: list[str] | None = None,
        replanned: str | None = None,
        plan_ms: int | None = None,
    ) -> TickRecord:
        """The only writer of the tick log; hands the filed record back to the tick."""
        record = TickRecord(
            tick=len(self.log),
            tags=[tag.name for tag in reading.tags],
            outcome=outcome,
            head=head,
            popped=popped or [],
            replanned=replanned,
            plan_len=len(self.queue),
            plan=[step.name for step in self.queue],
            progress=self.board.progress_key(),
            symbols=self.state.symbols(),
            duration_ms=self.clock.now_ms() - t0,
            slept_ms=self.clock.slept_ms() - slept0,
            plan_ms=plan_ms,
        )
        self.log.append(record)
        return record

    def think(self) -> list[Action] | None:
        """One A* run towards the outer goal: steps to take, or `None` for no route.

        Two answers only, and the tick reads them as such: a non-empty queue
        refill, or `stuck:no_plan`. It is called exactly when the tick has
        already judged the goal unsatisfied, so a plan of zero steps is the
        planner contradicting that judgement over the same symbols -- `or
        None` folds it into the stuck verdict, because a view that split has
        to stop the run loudly rather than refill with nothing and spin.

        `PlanNotFound` turns into a value here because here is the seam with
        the GOAP library: raising is how that library says it, a value is how
        this loop carries it.
        """
        try:
            result = plan(self.state.to_world_state(), self.state.goal, self.catalog)
        except PlanNotFound:
            return None
        return list(result.actions) or None

    def run(self, max_ticks: int = 60) -> list[TickRecord]:
        """The only judge of when the loop stops: finished, stuck, breaker, budget.

        `finished` is read first and there is nothing for it to outrank: a
        done tick returns before the fork, so it carries no replan the
        breaker could have counted.

        A tick a reflex ended is neutral: it neither counts nor clears. The
        reflex arc dismisses what sits in front of the plan and returns
        without ever reaching the queue, so it is evidence about neither
        side; clearing on it would let a popup burst launder exactly the
        flip-popup-flip interleaving the breaker exists to catch.

        `REPLAN_STORM_TICKS = 10` is a placeholder from the offline mock era.
        It must be re-judged against real-device jsonl before this loop
        drives the phone: how long a legitimate replan streak runs during an
        enemy turn is unknown.
        """
        streak = 0
        for _ in range(max_ticks):
            record = self.tick()
            if self.finished:
                break
            if record.outcome == "stuck:no_plan":
                raise BotStuck(
                    self._dump(f"no plan for goal {self.state.goal.name!r}"), kind="no_plan"
                )
            if record.outcome.startswith("reflex:"):
                continue
            streak = streak + 1 if record.replanned == "replan" else 0
            if streak >= REPLAN_STORM_TICKS:
                raise BotStuck(
                    self._dump(f"replan storm: {REPLAN_STORM_TICKS} consecutive replans"),
                    kind="replan_storm",
                )
        return self.log

    def trace(self) -> str:
        """The log as aligned text: one line per tick, queue remainder on the right."""
        goal = self.state.goal.name if self.state.goal else "-"
        lines = [
            f"goal={goal}",
            f"{'tick':>4}  {'outcome':<18}{'head':<18}{'pops':<5}"
            f"{'left':<5}{'progress':<10}plan",
        ]
        for r in self.log:
            outcome = f"replan>{r.outcome}" if r.replanned == "replan" else r.outcome
            lines.append(
                f"{r.tick:>4}  {outcome:<18}{r.head or '-':<18}{len(r.popped):<5}"
                f"{r.plan_len:<5}{str(r.progress):<10}{' -> '.join(r.plan) or '-'}"
            )
        return "\n".join(lines)

    def _dump(self, reason: str) -> str:
        facts = ", ".join(f"{k}={v!r}" for k, v in sorted(self.state.symbols().items()))
        trail = " -> ".join(f"{r.head or '-'}[{r.outcome}]" for r in self.log[-6:])
        return (
            f"{reason}\n"
            f"  symbols={{{facts}}}\n"
            f"  board={self.board}\n"
            f"  queue={[step.name for step in self.queue]}\n"
            f"  last ticks: {trail}"
        )
