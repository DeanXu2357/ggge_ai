"""一次攻略的生命週期：StageOrder 進、StageReport 出。"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ..contracts import Ending, IntelDelta, Objective, StageOrder, StageReport
from ..runtime.device import Executor
from ..runtime.journal import Journal
from ..runtime.perceive import Perceiver
from ..sandbox.advise import Advisor
from .actions import Action
from .goals import Goal
from .loop import LoopOutcome, Reflex, StageLoop
from .planner import PlannerConfig
from .state import StageState

JOURNAL_NAME = "stage.jsonl"


def stage_journal(run_dir: Path) -> Journal:
    return Journal(run_dir / JOURNAL_NAME)


def run_stage(
    order: StageOrder,
    *,
    perceiver: Perceiver[StageState],
    executor: Executor[Action],
    advisor: Advisor[StageState, Action],
    victory: Goal,
    journal: Journal,
    reflexes: Sequence[Reflex] = (),
    config: PlannerConfig = PlannerConfig(),
) -> StageReport:
    journal.record(
        "stage_start",
        stage=order.stage,
        objectives=sorted(item.value for item in order.objectives),
        hidden_policy=order.hidden_policy.value,
        max_ticks=order.max_ticks,
        victory=victory.name,
    )
    loop = StageLoop(
        order,
        perceiver=perceiver,
        executor=executor,
        advisor=advisor,
        victory=victory,
        journal=journal,
        reflexes=reflexes,
        config=config,
    )
    outcome = loop.run()
    journal.record(
        "stage_end",
        ending=outcome.ending.value,
        reason=outcome.reason,
        ticks=outcome.ticks,
    )
    return StageReport(
        stage=order.stage,
        ending=outcome.ending,
        achieved=_achieved(order, outcome),
        reason=outcome.reason,
        intel=IntelDelta(),
    )


def _achieved(order: StageOrder, outcome: LoopOutcome) -> dict[Objective, bool]:
    """只有過關判得出來：權威是遊戲自己的結算畫面，也就是終局種類。
    其餘目標項目的判定在關卡外（外層親讀），內層一律不宣稱達成。"""
    cleared = outcome.ending is Ending.VICTORY
    return {item: (item is Objective.CLEAR and cleared) for item in sorted_objectives(order)}


def sorted_objectives(order: StageOrder) -> tuple[Objective, ...]:
    return tuple(sorted(order.objectives, key=lambda item: item.value))
