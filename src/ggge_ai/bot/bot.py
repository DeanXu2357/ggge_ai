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
    """Escalation raised only by `run`: a tick returns its verdict, never throws.

    Files nothing of its own -- the tick behind the escalation is already
    recorded. The real system turns this into a human-intervention request.
    """

    def __init__(self, message: str, kind: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass
class TickRecord:
    """One line per tick: a collector, never a channel -- no machinery reads it back.

    Which is why `plan_ms` has to live here: it is the one column that cannot
    be reconstructed from the others afterwards.
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

    The queue advances on evidence, not on execution, and it dies whole: a
    stale head throws the entire queue away rather than being repaired.

    No unknown check belongs anywhere in the loop. A frame that cannot say
    which screen it is breaks the head's `view` precondition like any other
    stale head, and the planner routes out of it through an observation
    action.

    Bookkeeping never ends a tick: pops, refill and replan are pure
    computation over the frame captured at the top, so the interaction that
    follows is still authorized by that same fresh frame.
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
        """The whole lifecycle, kept inline: the spec diagram is this method.

        A failing sense must not take the unreadable-frame route: no action in
        any catalog fixes a dead adb, so an `Observe` plan would spin to
        `max_ticks` and report a timeout in place of the real cause. It dies
        here instead, after one record (symbols are the previous tick's
        leftovers -- nothing was sensed), re-raising untouched so the
        traceback still names the transport, the decoder or the classifier.
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

        Called only when the tick has already judged the goal unsatisfied, so
        a plan of zero steps is the planner contradicting that judgement over
        the same symbols -- `or None` folds it into `stuck:no_plan`, because a
        split view has to stop the run loudly instead of refilling with
        nothing and spinning.

        `PlanNotFound` becomes a value here because this is the seam with the
        GOAP library.
        """
        try:
            result = plan(self.state.to_world_state(), self.state.goal, self.catalog)
        except PlanNotFound:
            return None
        return list(result.actions) or None

    def run(self, max_ticks: int = 60) -> list[TickRecord]:
        """The only judge of when the loop stops: finished, stuck, breaker, budget.

        A tick a reflex ended is neutral -- it neither counts nor clears. The
        arc returns without ever reaching the queue, so it is evidence about
        neither side, and clearing on it would let a popup burst launder
        exactly the flip-popup-flip interleaving the breaker exists to catch.

        `REPLAN_STORM_TICKS = 10` is a placeholder from the offline mock. It
        must be re-judged against real-device jsonl before this loop drives
        the phone: how long a legitimate replan streak runs during an enemy
        turn is unknown.
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
