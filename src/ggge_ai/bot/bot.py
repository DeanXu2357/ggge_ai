"""The loop: sense, decide, act -- over a plan that outlives the tick."""

from __future__ import annotations

from dataclasses import dataclass, field

from ggge_ai.goap.planner import PlanNotFound, plan
from ggge_ai.goap.state import Value

from .action import Action, Goal
from .board import MockBoard
from .mocks import MockDevice, MockSensor
from .state import BotState


class BotStuck(RuntimeError):
    """Honest abort. The loop stops and says where, it does not improvise.

    Exactly two things raise it: `think` cannot find a plan for the goal, and
    `on_blocked` has already tried repair and reset and still has nothing.
    Anything else that goes wrong is supposed to show up in the log, not in an
    exception -- reading the log is how this skeleton is meant to be judged.
    """


@dataclass
class TickRecord:
    """One line per tick, and the whole point of this skeleton.

    `head` is the action the tick was about (the one executed, or the one that
    was found blocked, or the one now at the front after popping) and
    `outcome` is what happened to it. `plan` is what is left afterwards, so
    two consecutive lines show whether a repair kept the tail or a reset threw
    it away, and a run of identical `head` values shows an action holding the
    front of the plan until its effect finally comes true.
    """

    tick: int
    goal: str | None
    head: str | None
    outcome: str
    plan_len: int
    plan: list[str] = field(default_factory=list)
    progress: tuple[int, int] = (0, 0)
    symbols: dict[str, Value] = field(default_factory=dict)


class Bot:
    """Two things per tick: read the screen once, take one step.

    One goal, and it is the outer one. The staging that used to live in a goal
    array now lives in `plan`, an ordered list of actions that survives across
    ticks: the planner said "collapse the list, then scan, then read the
    panels, then sync", and that sentence is kept instead of being re-derived
    every tick from a goal that only says "sync".

    The plan advances on evidence, not on execution -- see `decide`. Nothing
    else in this class is allowed to pop it.
    """

    def __init__(
        self,
        state: BotState,
        board: MockBoard,
        sensor: MockSensor,
        device: MockDevice,
        catalog: list[Action],
        repair_max_cost: float = 6.0,
    ) -> None:
        self.state = state
        self.board = board
        self.sensor = sensor
        self.device = device
        self.catalog = list(catalog)
        self.repair_max_cost = repair_max_cost
        self.plan: list[Action] = []
        self.log: list[TickRecord] = []
        self.finished = False
        # decide 決定這個 tick 的 head 與 outcome，act 只有在真的動手時才把
        # outcome 改成 executed/settled——兩者合起來才是一筆完整的流水帳。
        self._outcome = "done"
        self._head: str | None = None
        self._last_action: str | None = None
        self._settle_left = 0

    def tick(self) -> None:
        self.sense()
        action = self.decide()
        self.act(action)

    def sense(self) -> None:
        self.state.sense_update(**self.sensor.read())
        self.state.sense_update(**self.board.summary_symbols())

    def decide(self) -> Action | None:
        """Advance the plan by one step, or hand back the step to run.

        The rule that everything else follows from: the head is popped when
        its *effect* is true, not when it has been executed. An action is a
        standing instruction -- "pan until the map is covered", "wait until
        the screen is readable" -- and it keeps the front of the plan for as
        many ticks as that takes. Repetition needs no counter and no
        intermediate goal, and an action that ran but achieved nothing simply
        runs again.

        A tick that pops does not also execute: popping is a claim about the
        world ("that step is done"), and the next step deserves to be judged
        against a fresh reading rather than against the one that just changed
        under it. Same for a blocked head -- `on_blocked` rewrites the plan
        and lets the next tick run it.
        """
        goal = self.state.goal
        if goal is None or goal.satisfied(self.state):
            self.finished = True
            self._outcome, self._head = "done", None
            return None

        if not self.plan:
            self.plan = self.think()

        advanced = False
        while self.plan and self.state.satisfies(self.plan[0].eff):
            self.plan.pop(0)
            advanced = True
        if advanced:
            if not self.plan:
                self.plan = self.think()
            self._outcome = "popped"
            self._head = self.plan[0].name if self.plan else None
            return None

        head = self.plan[0]
        self._head = head.name
        if not self.state.satisfies(head.pre):
            return self.on_blocked(head)
        self._outcome = "executed"
        return head

    def think(self) -> list[Action]:
        """Refill the plan. Two kinds of thinking coexist, on purpose.

        This one is the flow-level kind: a single A* run over the catalog
        towards the outer goal, and the entire `actions` list is kept, not
        just its first step. Keeping it is what makes the plan a commitment --
        re-deriving the route every tick would let it flip between equal-cost
        alternatives and would throw away work the search already did.

        The other kind is `SolveTactics`: an action whose `do()` splices the
        steps it just produced in behind itself. Thinking is then an action
        like any other -- it occupies one tick, it appears in the log with its
        own line, and it can be interrupted before its output is executed. The
        mock body writes a fixed sequence; the real one runs expectiminimax
        over the battle state and splices what it found.
        """
        goal = self.state.goal
        if goal is None:
            return []
        try:
            result = plan(self.state.to_world_state(), goal, self.catalog)
        except PlanNotFound as exc:
            raise BotStuck(self._dump(f"no plan for goal {goal.name!r}: {exc}")) from exc
        if not result.actions:
            raise BotStuck(self._dump(f"empty plan for unsatisfied goal {goal.name!r}"))
        return list(result.actions)

    def on_blocked(self, head: Action) -> Action | None:
        """The head cannot run from here. Decide what the rest of the plan is worth.

        Three answers, and choosing between them is one question: how
        expensive is the tail?

        - repair: plan a detour from the current state to `head.pre` and
          splice it in *front*, keeping the tail. For tails that were costly
          to produce -- a tactical sequence out of expectiminimax is not worth
          throwing away because a popup covered the screen for two ticks.
        - reset: drop the whole plan and think again next tick. For cheap
          tails -- flow-level A* over this catalog costs microseconds, and a
          plan derived from the screen as it is now is more honest than one
          patched to look like the screen we expected.
        - abandon: the head itself stopped meaning anything, so drop it and
          continue with the tail. Here it is only `Action.still_relevant`,
          which defaults to True; the real use is inside tactical sequences,
          where the target of a planned attack is already dead or the unit has
          already acted.

        v1 policy: abandon if the head says so, otherwise repair while the
        detour stays under `repair_max_cost` -- past that it is not a detour,
        it is a different plan -- otherwise reset. If the think() that follows
        a reset also finds nothing, `BotStuck`: the loop stops and says so.

        Override this one method to change the policy. The choice is a
        judgement about the price of a plan, and a judgement that small does
        not need a framework built around it. Returning an action here runs it
        this tick; v1 always returns None and lets the next tick run the
        rewritten plan.
        """
        if not head.still_relevant(self.state):
            self.plan.pop(0)
            self._outcome = "blocked:abandon"
            return None

        detour = self._repair(head)
        if detour is not None:
            self.plan[0:0] = detour
            self._outcome = "blocked:repair"
            return None

        self.plan.clear()
        self._outcome = "blocked:reset"
        return None

    def _repair(self, head: Action) -> list[Action] | None:
        goal = Goal(f"repair:{head.name}", dict(head.pre))
        try:
            result = plan(self.state.to_world_state(), goal, self.catalog)
        except PlanNotFound:
            return None
        if not result.actions or result.total_cost > self.repair_max_cost:
            return None
        return list(result.actions)

    def act(self, action: Action | None) -> None:
        outcome = self._outcome
        if action is not None:
            if (
                not action.repeat_safe
                and self._last_action == action.name
                and self._settle_left > 0
            ):
                # 上一 tick 才點過同一顆，畫面還沒定下來：這個 tick 只記帳不動手。
                self._settle_left -= 1
                outcome = "settled"
            else:
                action.do(self)
                self._last_action = action.name
                self._settle_left = 0 if action.repeat_safe else action.settle_ticks
        self.log.append(
            TickRecord(
                tick=len(self.log),
                goal=self.state.goal.name if self.state.goal else None,
                head=self._head,
                outcome=outcome,
                plan_len=len(self.plan),
                plan=[step.name for step in self.plan],
                progress=self.board.progress_key(),
                symbols=self.state.symbols(),
            )
        )

    def run(self, max_ticks: int = 60) -> list[TickRecord]:
        """Run until the goal is satisfied or `max_ticks` is spent.

        `max_ticks` is the only termination guarantee there is. This version
        has no loop detection at all: an action whose effect never becomes
        true holds the front of the plan and is fired every tick until the
        budget runs out, and nothing will interrupt it. That is a deliberate
        simplification for this round -- the log is the only instrument for
        judging whether the behaviour was sane, so read `trace()` and do not
        read "it finished" as "it was right".
        """
        for _ in range(max_ticks):
            self.tick()
            if self.finished:
                break
        return self.log

    def trace(self) -> str:
        """The log as aligned text: one line per tick, plan remainder on the right."""
        goal = self.state.goal.name if self.state.goal else "-"
        lines = [
            f"goal={goal}",
            f"{'tick':>4}  {'outcome':<16}{'head':<18}{'left':<5}{'progress':<10}plan",
        ]
        for record in self.log:
            remaining = " -> ".join(record.plan) or "-"
            lines.append(
                f"{record.tick:>4}  {record.outcome:<16}{record.head or '-':<18}"
                f"{record.plan_len:<5}{str(record.progress):<10}{remaining}"
            )
        return "\n".join(lines)

    def _dump(self, reason: str) -> str:
        facts = ", ".join(f"{k}={v!r}" for k, v in sorted(self.state.symbols().items()))
        trail = " -> ".join(f"{r.head or '-'}[{r.outcome}]" for r in self.log[-6:])
        return (
            f"{reason}\n"
            f"  symbols={{{facts}}}\n"
            f"  board={self.board}\n"
            f"  plan={[step.name for step in self.plan]}\n"
            f"  last ticks: {trail}"
        )
