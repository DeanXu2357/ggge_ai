"""任務／方法分解與回溯引擎：領域無關，不認識任何遊戲概念。"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

State = Mapping[str, Any]


@dataclass(frozen=True)
class Task:
    name: str
    args: tuple[Any, ...] = ()


def always(state: State, task: Task) -> bool:
    return True


def unchanged(state: State, task: Task) -> State:
    return state


@dataclass(frozen=True)
class Operator:
    name: str
    precondition: Callable[[State, Task], bool] = always
    effect: Callable[[State, Task], State] = unchanged


@dataclass(frozen=True)
class Method:
    name: str
    task: str
    subtasks: Callable[[State, Task], Sequence[Task]]
    precondition: Callable[[State, Task], bool] = always


@dataclass
class Domain:
    operators: dict[str, Operator] = field(default_factory=dict)
    methods: dict[str, list[Method]] = field(default_factory=dict)

    def add_operator(self, operator: Operator) -> None:
        if operator.name in self.methods:
            raise ValueError(f"{operator.name} 已是複合任務，不能同時是 operator")
        self.operators[operator.name] = operator

    def add_method(self, method: Method) -> None:
        if method.task in self.operators:
            raise ValueError(f"{method.task} 已是 operator，不能同時是複合任務")
        self.methods.setdefault(method.task, []).append(method)


@dataclass(frozen=True)
class Decomposition:
    plan: tuple[Task, ...]
    state: State


@dataclass(frozen=True)
class NoApplicableMethod:
    """分解失敗的一級結果——誠實停止的觸發，不是例外流。"""

    task: Task
    reason: str
    tried: tuple[str, ...] = ()
    cause: NoApplicableMethod | None = None

    def describe(self) -> str:
        text = f"{self.task.name}: {self.reason}"
        if self.tried:
            text += f" (tried: {', '.join(self.tried)})"
        if self.cause is not None:
            text += f" <- {self.cause.describe()}"
        return text


def decompose(
    domain: Domain, state: State, tasks: Iterable[Task]
) -> Decomposition | NoApplicableMethod:
    remaining = list(tasks)
    plan: list[Task] = []
    while remaining:
        head = remaining.pop(0)
        operator = domain.operators.get(head.name)
        if operator is not None:
            if not operator.precondition(state, head):
                return NoApplicableMethod(head, "operator precondition unmet")
            state = operator.effect(state, head)
            plan.append(head)
            continue

        methods = domain.methods.get(head.name)
        if not methods:
            return NoApplicableMethod(head, "no method declared")

        tried: list[str] = []
        cause: NoApplicableMethod | None = None
        for method in methods:
            tried.append(method.name)
            if not method.precondition(state, head):
                continue
            # 後續任務一起帶進遞迴：方法選擇要為它造成的後果負責，
            # 光子任務成功但害後面卡住的分支必須回溯掉。
            branch = decompose(domain, state, [*method.subtasks(state, head), *remaining])
            if isinstance(branch, Decomposition):
                return Decomposition(tuple(plan) + branch.plan, branch.state)
            cause = branch
        return NoApplicableMethod(head, "no applicable method", tuple(tried), cause)

    return Decomposition(tuple(plan), state)
