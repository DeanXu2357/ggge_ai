"""tick 迴圈：感知→反射→簿記→規劃→至多一次操作。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar, Protocol

from ..contracts import Ending, StageOrder
from ..runtime.device import Executor
from ..runtime.journal import Journal
from ..runtime.perceive import Observation, Perceiver
from ..runtime.reflexes import ScreenFix
from ..sandbox.advise import Advisor, Verdict
from .actions import Action, Withdraw, candidates
from .goals import Goal, LeftStage
from .planner import NoPlan, PlannerConfig, Step, plan
from .state import Phase, StageState


class TickOutcome(Enum):
    TERMINAL = "terminal"
    REFLEX = "reflex"
    WAITING = "waiting"
    GOAL_MET = "goal_met"
    ACTED = "acted"
    NO_PLAN = "no_plan"


@dataclass(frozen=True)
class TickRecord:
    tick: int
    outcome: TickOutcome
    screen: str
    seen: dict[str, Any] | None
    terminal: Ending | None = None
    verdict: str | None = None
    reflex: str | None = None
    popped: tuple[str, ...] = ()
    discarded: str | None = None
    replanned: bool = False
    plan: tuple[str, ...] = ()
    did: str | None = None
    note: str = ""
    frame: str | None = None


@dataclass(frozen=True)
class LoopOutcome:
    ending: Ending
    reason: str
    ticks: int


class Reflex(Protocol):
    """彈窗反射：畫面直接指定一個操作，跳過規劃層。

    回傳可以是行動詞彙裡的行動（應戰要經 Advisor 計價），也可以是純收乾用的
    ScreenFix——後者不是符號行動，規劃層不該認識它，所以它自帶手勢。
    """

    name: str

    def match(self, observation: Observation[StageState]) -> Action | ScreenFix | None: ...


@dataclass(frozen=True)
class ReactionReflex:
    """應戰窗（敵方回合挨打時選反擊／閃避／防禦）沒有逾時——有 15 秒逾時的
    是隱藏關觸發彈窗與前次 AUTO 的關卡資訊頁，別搞混。走反射不走規劃器的
    理由是結構性的：敵方相位計畫佇列已作廢、選項只有畫面給的姿態，送
    Advisor 計價取最低價即可。這裡沒有戰術判斷，只是消費計價結果。"""

    advisor: Advisor[StageState, Action]
    name: ClassVar[str] = "reaction"

    def match(self, observation: Observation[StageState]) -> Action | None:
        state = observation.state
        if state is None or state.reaction is None:
            return None
        options = candidates(state)
        if not options:
            return None
        prices = self.advisor.price(state, options)
        priced = [
            (pricing.cost, index, action)
            for index, (action, pricing) in enumerate(zip(options, prices, strict=True))
            if pricing is not None
        ]
        if not priced:
            return None
        return min(priced)[2]


class StageLoop:
    """一張畫面→至多一次裝置操作。

    佇列只靠畫面證據推進：行動送出去不算數，下一張畫面上看到它的保證
    效果才彈出。頭部前置條件破了整條佇列作廢，不修補。
    """

    def __init__(
        self,
        order: StageOrder,
        *,
        perceiver: Perceiver[StageState],
        executor: Executor[Action],
        advisor: Advisor[StageState, Action],
        victory: Goal,
        journal: Journal,
        reflexes: Sequence[Reflex] = (),
        config: PlannerConfig = PlannerConfig(),
    ) -> None:
        self.order = order
        self.perceiver = perceiver
        self.executor = executor
        self.advisor = advisor
        self.goal = victory
        self.journal = journal
        self.reflexes = tuple(reflexes)
        self.config = config
        self.queue: list[Step] = []
        self.ticks = 0
        self.terminal: Ending | None = None
        self.withdrawn = False
        self.stop_reason = ""
        self._last_phase: Phase | None = None
        self._last_actionable: frozenset[str] = frozenset()

    def tick(self) -> TickRecord:
        self.ticks += 1
        observation = self.perceiver.look()

        if observation.terminal is not None:
            self.terminal = observation.terminal
            return self._record(observation, TickOutcome.TERMINAL)

        for reflex in self.reflexes:
            forced = reflex.match(observation)
            if forced is not None:
                self.executor.perform(forced, observation)
                return self._record(
                    observation, TickOutcome.REFLEX, reflex=reflex.name, did=forced.label
                )

        state = observation.state
        if state is None:
            return self._record(observation, TickOutcome.WAITING, note="no symbolic reading")

        popped, discarded = self._advance_queue(state)
        bookkeeping: dict[str, Any] = {"popped": popped, "discarded": discarded}

        if state.phase is not Phase.PLAYER:
            return self._record(
                observation, TickOutcome.WAITING, note="not our phase", **bookkeeping
            )

        appraisal = self.advisor.appraise(state)
        if appraisal.verdict is Verdict.WITHDRAW and not isinstance(self.goal, LeftStage):
            self.goal = LeftStage()
            self.queue.clear()
            bookkeeping["discarded"] = "goal switched to left_stage"
        bookkeeping["verdict"] = appraisal.verdict.value

        if self.goal.is_satisfied(state):
            return self._record(
                observation,
                TickOutcome.GOAL_MET,
                note="waiting for the result screen",
                **bookkeeping,
            )

        if not self.queue:
            bookkeeping["replanned"] = True
            result = plan(state, self.goal, self.advisor, self.config)
            if isinstance(result, NoPlan):
                self.stop_reason = f"{self.goal.name}: {result.reason} (expanded={result.expanded})"
                return self._record(
                    observation, TickOutcome.NO_PLAN, note=self.stop_reason, **bookkeeping
                )
            self.queue = list(result.steps)

        if not self.queue:
            return self._record(
                observation,
                TickOutcome.WAITING,
                note="plan stops at the phase boundary",
                **bookkeeping,
            )

        head = self.queue[0]
        self.executor.perform(head.action, observation)
        if isinstance(head.action, Withdraw):
            self.withdrawn = True
        return self._record(observation, TickOutcome.ACTED, did=head.action.label, **bookkeeping)

    def run(self) -> LoopOutcome:
        while self.ticks < self.order.max_ticks:
            record = self.tick()
            if record.outcome is TickOutcome.TERMINAL:
                return LoopOutcome(self._ending(), f"result screen: {record.screen}", self.ticks)
            if record.outcome is TickOutcome.NO_PLAN:
                return LoopOutcome(Ending.STUCK, self.stop_reason, self.ticks)
        return LoopOutcome(
            Ending.STUCK, f"tick budget exhausted ({self.order.max_ticks})", self.ticks
        )

    def _ending(self) -> Ending:
        # 主動離場的畫面跟戰敗長得一樣；是不是我方自己走的只有迴圈知道。
        if self.withdrawn:
            return Ending.WITHDREW
        return self.terminal or Ending.STUCK

    def _advance_queue(self, state: StageState) -> tuple[tuple[str, ...], str | None]:
        popped: list[str] = []
        discarded: str | None = None
        if self._turned_over(state):
            if self.queue:
                discarded = "phase turnover"
                self.queue.clear()
        else:
            while self.queue and self.queue[0].action.progressed(state, self.queue[0].pricing):
                popped.append(self.queue.pop(0).action.label)
            if self.queue and not self.queue[0].action.applicable(state):
                discarded = self.queue[0].action.label
                self.queue.clear()
        self._last_phase = state.phase
        self._last_actionable = state.actionable
        return tuple(popped), discarded

    def _turned_over(self, state: StageState) -> bool:
        """一個我方回合內可行動集合只會縮，長回來就是換過回合了——
        兩張畫面之間整個敵方回合過完沒被看見時，這是唯一的線索。"""
        if self._last_phase is None:
            return False
        return state.phase is not self._last_phase or not state.actionable <= self._last_actionable

    def _record(
        self,
        observation: Observation[StageState],
        outcome: TickOutcome,
        *,
        verdict: str | None = None,
        reflex: str | None = None,
        popped: tuple[str, ...] = (),
        discarded: str | None = None,
        replanned: bool = False,
        did: str | None = None,
        note: str = "",
    ) -> TickRecord:
        record = TickRecord(
            tick=self.ticks,
            outcome=outcome,
            screen=observation.screen,
            seen=_seen(observation.state),
            terminal=observation.terminal,
            verdict=verdict,
            reflex=reflex,
            popped=popped,
            discarded=discarded,
            replanned=replanned,
            plan=tuple(step.action.label for step in self.queue),
            did=did,
            note=note,
            frame=self.journal.save_frame(observation.frame, self.ticks),
        )
        stored_frame: dict[str, Any] = {} if record.frame is None else {"frame": record.frame}
        self.journal.record(
            "tick",
            tick=record.tick,
            outcome=record.outcome.value,
            screen=record.screen,
            seen=record.seen,
            evidence=observation.evidence,
            terminal=record.terminal.value if record.terminal else None,
            verdict=record.verdict,
            reflex=record.reflex,
            popped=list(record.popped),
            discarded=record.discarded,
            replanned=record.replanned,
            plan=list(record.plan),
            did=record.did,
            note=record.note,
            **stored_frame,
        )
        return record


def _seen(state: StageState | None) -> dict[str, Any] | None:
    if state is None:
        return None
    reaction = state.reaction
    return {
        "phase": state.phase.value,
        "allies": sorted(state.allies),
        "actionable": sorted(state.actionable),
        "enemies": sorted(state.enemies),
        "known": sorted(state.known),
        "grid_on": state.grid_on,
        "roster_collapsed": state.roster_collapsed,
        "board_synced": state.board_synced,
        "positions": {unit: list(cell) for unit, cell in sorted(state.positions)},
        "reaction": (
            None
            if reaction is None
            else {
                "defender": reaction.defender,
                "attacker": reaction.attacker,
                "stances": list(reaction.stances),
            }
        ),
    }
