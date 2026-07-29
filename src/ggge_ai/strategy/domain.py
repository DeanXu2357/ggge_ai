"""外層領域方法：評估→出擊→刷資源→強化→再戰。"""

from __future__ import annotations

from collections.abc import Sequence

from ..contracts import GoalSpec
from .htn import Domain, Method, State, Task

ROOT_TASK = "achieve_goal"


def root_task(goal: GoalSpec) -> Task:
    return Task(ROOT_TASK, (goal,))


def goal_of(task: Task) -> GoalSpec:
    return task.args[0]


# 批 0 佔位：方法登記在案只為讓「無適用方法」報得出具名候選，
# 前置條件恆假、子任務未接線，批 3 才填。
def _not_wired(state: State, task: Task) -> bool:
    return False


def _unbuilt(state: State, task: Task) -> Sequence[Task]:
    raise NotImplementedError("批 3：外層骨架")


CLEAR_BY_SORTIE = Method(
    name="clear_by_sortie",
    task=ROOT_TASK,
    subtasks=_unbuilt,
    precondition=_not_wired,
)


def build_domain() -> Domain:
    domain = Domain()
    domain.add_method(CLEAR_BY_SORTIE)
    return domain
