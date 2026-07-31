"""離線假件：腳本化假戰局、假分類器、假裝置、mock Advisor。

生產碼一條啟發式都不准有，所以每個決策點的內容都在這裡由測試腳本
指定：Advisor 給什麼價、畫面下一張長什麼樣，全部是資料不是邏輯。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from ggge_ai.contracts import Ending
from ggge_ai.runtime.perceive import Observation
from ggge_ai.sandbox.advise import Appraisal, Guarantee, Pricing, Verdict
from ggge_ai.stage.actions import (
    Action,
    Attack,
    Brace,
    CollapseRoster,
    Inspect,
    Move,
    ShowGrid,
    Standby,
    SurveyBoard,
    Withdraw,
)
from ggge_ai.stage.state import Cell, Phase, Reaction, StageState

Pricer = Callable[[StageState, Action], Pricing | None]


def battle(
    *,
    allies: Sequence[str],
    enemies: Sequence[str],
    actionable: Sequence[str] | None = None,
    phase: Phase = Phase.PLAYER,
    positions: dict[str, Cell] | None = None,
    reachable: dict[str, Sequence[Cell]] | None = None,
    known: Sequence[str] | None = None,
    reaction: Reaction | None = None,
    grid_on: bool = True,
    roster_collapsed: bool = True,
    board_synced: bool = True,
) -> StageState:
    """known 預設全知、格線已開、卡條已收、盤面已同步：不談情報與盤面的劇本才不會
    被 Inspect／ShowGrid／CollapseRoster／SurveyBoard 候選污染。"""
    return StageState(
        phase=phase,
        allies=frozenset(allies),
        actionable=frozenset(allies if actionable is None else actionable),
        enemies=frozenset(enemies),
        positions=frozenset((unit, cell) for unit, cell in (positions or {}).items()),
        reachable=frozenset(
            (unit, cell) for unit, cells in (reachable or {}).items() for cell in cells
        ),
        known=frozenset([*allies, *enemies] if known is None else known),
        reaction=reaction,
        grid_on=grid_on,
        roster_collapsed=roster_collapsed,
        board_synced=board_synced,
    )


def frame(
    state: StageState | None = None, screen: str = "battle_map", **evidence: Any
) -> Observation[StageState]:
    return Observation(screen=screen, state=state, evidence=evidence)


def result_screen(ending: Ending, screen: str = "battle_result") -> Observation[StageState]:
    return Observation(screen=screen, terminal=ending)


@dataclass
class ScriptedPerceiver:
    """預錄的畫面證據序列。跑完最後一張就停在那張——證據不會因為我方
    送出了操作而前進，這正是要拿來壓迴圈的性質。"""

    frames: list[Observation[StageState]]
    looks: int = 0

    def look(self) -> Observation[StageState]:
        index = min(self.looks, len(self.frames) - 1)
        self.looks += 1
        return self.frames[index]


@dataclass
class FakeDevice:
    taps: list[tuple[int, int]] = field(default_factory=list)
    swipes: list[tuple[int, int, int, int, float]] = field(default_factory=list)
    shots: int = 0

    def screenshot(self) -> Any:
        self.shots += 1
        return object()

    def tap(self, x: int, y: int) -> None:
        self.taps.append((x, y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_s: float) -> None:
        self.swipes.append((x1, y1, x2, y2, duration_s))


@dataclass
class FakeExecutor:
    device: FakeDevice = field(default_factory=FakeDevice)
    performed: list[Action] = field(default_factory=list)
    screens: list[str] = field(default_factory=list)

    def perform(self, action: Action, observation: Observation[StageState]) -> None:
        self.performed.append(action)
        self.screens.append(observation.screen)
        self.device.tap(len(self.performed), 0)

    @property
    def labels(self) -> list[str]:
        return [action.label for action in self.performed]


@dataclass(frozen=True)
class KindPricer:
    """按行動型別給價；None ＝ 不背書。要更細的區分就自己寫 callable。"""

    attack: Pricing | None = None
    move: Pricing | None = None
    inspect: Pricing | None = None
    standby: Pricing | None = None
    brace: Pricing | None = None
    withdraw: Pricing | None = None
    show_grid: Pricing | None = None
    collapse_roster: Pricing | None = None
    survey: Pricing | None = None

    def __call__(self, state: StageState, action: Action) -> Pricing | None:
        if isinstance(action, Attack):
            return self.attack
        if isinstance(action, Move):
            return self.move
        if isinstance(action, Inspect):
            return self.inspect
        if isinstance(action, Standby):
            return self.standby
        if isinstance(action, Brace):
            return self.brace
        if isinstance(action, Withdraw):
            return self.withdraw
        if isinstance(action, ShowGrid):
            return self.show_grid
        if isinstance(action, CollapseRoster):
            return self.collapse_roster
        if isinstance(action, SurveyBoard):
            return self.survey
        raise AssertionError(f"未知的行動型別：{type(action).__name__}")


def always_pursue(state: StageState) -> Appraisal:
    return Appraisal(Verdict.PURSUE)


def always_withdraw(state: StageState) -> Appraisal:
    return Appraisal(Verdict.WITHDRAW, "腳本指定")


@dataclass
class MockAdvisor:
    pricer: Pricer
    verdict: Callable[[StageState], Appraisal] = always_pursue
    appraisals: int = 0
    price_calls: int = 0

    def appraise(self, state: StageState) -> Appraisal:
        self.appraisals += 1
        return self.verdict(state)

    def price(self, state: StageState, candidates: Sequence[Action]) -> tuple[Pricing | None, ...]:
        self.price_calls += 1
        return tuple(self.pricer(state, action) for action in candidates)


def kills_everything(cost: float = 1.0) -> KindPricer:
    return KindPricer(
        attack=Pricing(cost, Guarantee.KILL),
        move=Pricing(cost),
        standby=Pricing(cost),
        brace=Pricing(cost),
    )


def never_kills(cost: float = 1.0) -> KindPricer:
    return KindPricer(attack=Pricing(cost), move=Pricing(cost), standby=Pricing(cost))


def exit_only(cost: float = 1.0) -> KindPricer:
    return KindPricer(withdraw=Pricing(cost))
