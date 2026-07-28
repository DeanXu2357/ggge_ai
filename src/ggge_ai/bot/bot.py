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
    """Honest abort: the loop stops and says where, it does not improvise.

    Raised for immediate honest failures, and `kind` says which: `no_plan`
    (the planner finds no route -- an unprepared situation, the vocabulary
    is missing a mid-state), `stale_plan` (a fresh plan is somehow not
    applicable) or `replan_storm` (the breaker in `run`).

    The first two are tick-level: the tick catches them, leaves one final
    `panic:<kind>` record -- the same literal family as `panic:sense` -- and
    re-raises. The third is a threshold judgement, and those live in `run`,
    outside the tick: `run` supervises from the record each tick hands back,
    counting in a local of its own rather than reading the log. It writes no
    record -- the tick that completed the streak is already recorded like
    any other, so the trip point is reconstructible from the log without the
    breaker ever having written to it.
    `max_ticks` stays the coarse backstop for every stall no breaker names.
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
    tick hands it). Reading these lines is analysis -- replan rates, reflex
    streaks, progress stalls -- and it happens after the fact, in a test or
    over the jsonl export. A column that no other column can reconstruct --
    `plan_ms` -- therefore has to be written here.
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
        planner call). Everything else stays visible here so any drift from
        the spec diagram is immediately in view.

        The return value is this tick's report to whoever called it -- the
        same record the log just collected, handed over directly so that a
        supervisor like `run` never has to read the log back. The two panic
        exits report by raising instead: they file their record and let the
        exception carry the news.

        A sense that raises is an infrastructure failure, not a game
        situation: no action in any catalog fixes a dead adb, so routing it
        through the unreadable-frame path would spin the loop on `Observe`
        until `max_ticks` and report a timeout instead of the real cause.
        The tick therefore dies at the top -- but never silently: it leaves
        one `panic:sense` record (no tags, and the symbols are the previous
        tick's leftovers, since nothing was sensed) and re-raises the
        original exception untouched. Not BotStuck: that type is scoped to
        planning failures, and only the real traceback says whether it was
        the transport, the decoder, or the classifier.
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

        replanned: str | None = None
        plan_ms: int | None = None
        try:
            if not self.queue:
                # 先賦值再進 think()：think 死在裡面時，panic 記錄也要如實說出死前在做哪一種規劃。
                replanned = "refill"
                started = self.clock.now_ms()
                try:
                    self.queue = self.think()
                finally:
                    plan_ms = self.clock.now_ms() - started
            if self.queue and not self.state.satisfies(self.queue[0].pre):
                if replanned is not None:
                    raise BotStuck(
                        self._dump(f"fresh plan head {self.queue[0].name!r} not applicable"),
                        kind="stale_plan",
                    )
                self.queue.clear()
                replanned = "replan"
                started = self.clock.now_ms()
                try:
                    self.queue = self.think()
                finally:
                    plan_ms = self.clock.now_ms() - started
                if self.queue and not self.state.satisfies(self.queue[0].pre):
                    raise BotStuck(
                        self._dump(f"replanned head {self.queue[0].name!r} not applicable"),
                        kind="stale_plan",
                    )
        except BotStuck as exc:
            self._record(
                reading,
                t0,
                slept0,
                f"panic:{exc.kind}",
                popped=popped,
                replanned=replanned,
                plan_ms=plan_ms,
            )
            raise

        if not self.queue:
            self.finished = True
            return self._record(
                reading, t0, slept0, "done", popped=popped, replanned=replanned, plan_ms=plan_ms
            )

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

    def think(self) -> list[Action]:
        """Refill the queue: one A* run over the catalog towards the outer goal.

        An empty result is not an error -- it is the done signal: A* returns
        no actions exactly when the current state already satisfies the goal
        (or there is no goal), and the planner is the loop's only judge of
        satisfaction. Flow-level thinking; the other kind is an action like
        `SolveTactics`, whose `do()` splices the tactical steps it produced
        in behind itself.

        The caller times this call and puts the cost in the record's
        `plan_ms`; nothing is counted here.
        """
        goal = self.state.goal
        if goal is None:
            return []
        try:
            result = plan(self.state.to_world_state(), goal, self.catalog)
        except PlanNotFound as exc:
            raise BotStuck(
                self._dump(f"no plan for goal {goal.name!r}: {exc}"), kind="no_plan"
            ) from exc
        return list(result.actions)

    def run(self, max_ticks: int = 60) -> list[TickRecord]:
        """The only judge of when the loop stops: finished, breaker, budget.

        A supervisor with a memory of its own: every tick reports what it did
        and the streak lives in a local here, so the loop never reads the log
        back to decide anything -- the log stays a collector.

        The breaker names a plan-flipping cycle: every tick the head's `pre`
        has stopped holding, the queue dies whole and is rebuilt, and nothing
        decided survives long enough to be spent. Consecutive replans imply
        the symbols keep moving -- a head that still applies is never
        replanned -- so behind them is perception jitter, or a world changing
        faster than a plan can be executed.

        A tick a reflex ended is neutral: it neither counts nor clears. The
        reflex arc dismisses what sits in front of the plan and returns
        without ever reaching the queue, so it is evidence about neither
        side; clearing on it would let a popup burst launder exactly the
        flip-popup-flip interleaving this exists to catch. Only a tick that
        ran the bookkeeping through without throwing the queue away -- a
        refill, an ordinary execution -- shows a plan surviving, and that is
        what resets the count.

        `finished` wins over the breaker: a run whose very last tick happens
        to be a replan has still reached its goal. `max_ticks` is unchanged,
        the coarse budget behind every stall no breaker names -- a head
        spinning without progress, an observation loop on a screen that never
        reads, a reflex chain: all stalls, none of them replans.

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
