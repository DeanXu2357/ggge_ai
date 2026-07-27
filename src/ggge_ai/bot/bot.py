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
from .state import UNKNOWN, BotState


class BotStuck(RuntimeError):
    """Honest abort: the loop stops and says where, it does not improvise.

    Raised only for immediate honest failures: the planner finds no route
    (an unprepared situation -- the vocabulary is missing a mid-state) or a
    fresh plan is somehow not applicable. Threshold judgements (too many
    replans, too long unreadable) belong to the deferred circuit breaker,
    which will derive them from the tick log; until then `run(max_ticks)`
    is the only coarse backstop. The real system turns this into a
    human-intervention request.
    """


@dataclass
class TickRecord:
    """One line per tick -- the single source of truth for every metric.

    No mutable counters anywhere else: replan rates, reflex streaks and
    progress stalls are all derived from this stream (the future circuit
    breaker reads it in-process; the jsonl export is analysis-only).
    """

    tick: int
    phase: str
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


class Bot:
    """sense -> reflex/wait -> bookkeeping -> plan -> one action.

    The queue is a persistent plan: it advances on evidence (a step is popped
    when its *effect* is observed, which may take many ticks or zero
    executions) and it dies whole (a stale head throws the entire queue away
    and replans from the current symbols -- there is no repair surgery).

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
        self._last_exec: tuple[str, tuple] | None = None

    def tick(self) -> None:
        """The whole lifecycle, inline: the spec diagram is this method, top to bottom.

        Deliberately not decomposed further -- the only extracted pieces are
        the ones with an identity of their own (reflex router, recorder,
        planner call). Everything else stays visible here so any drift from
        the spec diagram is immediately in view.
        """
        t0 = self.clock.now_ms()
        frame = self.screen.capture()
        reading = self.classifier.classify(frame)

        # 感知門開在拍首：符號表＋盤面摘要，一次性重算，走反射的拍也照做。
        perceived = self.symbol_table.translate(reading)
        perceived.update(self.board.summary_symbols())
        self.state.sense_update(perceived)

        handled = self.reflexes.route(self, reading)
        if handled is not None:
            self._record(reading, t0, handled)
            return

        if reading.phase == UNKNOWN:
            # 等待格只記帳、不裁決：連續 unknown 的超限是熔斷器的事（延後，
            # 從流水帳導出），v1 的粗保險只有 run() 的 max_ticks。
            self._record(reading, t0, "wait:unknown")
            return

        popped: list[str] = []
        while self.queue and self.state.satisfies(self.queue[0].eff):
            popped.append(self.queue.pop(0).name)

        replanned: str | None = None
        try:
            if not self.queue:
                self.queue = self.think()
                replanned = "refill"
            if self.queue and not self.state.satisfies(self.queue[0].pre):
                if replanned is not None:
                    raise BotStuck(
                        self._dump(f"fresh plan head {self.queue[0].name!r} not applicable")
                    )
                self.queue.clear()
                self.queue = self.think()
                replanned = "replan"
                if self.queue and not self.state.satisfies(self.queue[0].pre):
                    raise BotStuck(
                        self._dump(f"replanned head {self.queue[0].name!r} not applicable")
                    )
        except BotStuck:
            self._record(reading, t0, "panic", popped=popped, replanned=replanned)
            raise

        if not self.queue:
            # planner 回空計畫＝goal 已滿足。收工的唯一裁判是 A*，迴圈裡沒有
            # 第二個 goal 檢查點；代價是 goal 提早成立時會先把殘餘隊列走完。
            self.finished = True
            self._record(reading, t0, "done", popped=popped, replanned=replanned)
            return

        head = self.queue[0]
        if head.refire == "require_change" and self._last_exec == (head.name, reading.key()):
            # 幀沒變就不准重發：sleep 略短的轉場尾巴在這裡吸收，不會雙開面板。
            self._record(
                reading, t0, "wait:refire", head=head.name, popped=popped, replanned=replanned
            )
            return

        head.do(self)
        self._last_exec = (head.name, reading.key())
        self._record(reading, t0, "executed", head=head.name, popped=popped, replanned=replanned)

    def _record(
        self,
        reading: FrameReading,
        t0: int,
        outcome: str,
        head: str | None = None,
        popped: list[str] | None = None,
        replanned: str | None = None,
    ) -> None:
        """The only writer of the tick log."""
        self.log.append(
            TickRecord(
                tick=len(self.log),
                phase=reading.phase,
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
                slept_ms=self.clock.slept_ms() - t0,
            )
        )

    def think(self) -> list[Action]:
        """Refill the queue: one A* run over the catalog towards the outer goal.

        An empty result is not an error -- it is the done signal: A* returns
        no actions exactly when the current state already satisfies the goal
        (or there is no goal), and the planner is the loop's only judge of
        satisfaction. Flow-level thinking; the other kind is an action like
        `SolveTactics`, whose `do()` splices the tactical steps it produced
        in behind itself.
        """
        goal = self.state.goal
        if goal is None:
            return []
        try:
            result = plan(self.state.to_world_state(), goal, self.catalog)
        except PlanNotFound as exc:
            raise BotStuck(self._dump(f"no plan for goal {goal.name!r}: {exc}")) from exc
        return list(result.actions)

    def run(self, max_ticks: int = 60) -> list[TickRecord]:
        """Run until the goal is satisfied or `max_ticks` is spent.

        `max_ticks` plus BotStuck are the only v1 backstops; the circuit
        breaker (replans-without-progress over the log) comes later and reads
        the same records.
        """
        for _ in range(max_ticks):
            self.tick()
            if self.finished:
                break
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
