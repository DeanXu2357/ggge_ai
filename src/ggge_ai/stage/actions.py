"""行動詞彙：移動／攻擊／待機／應戰／主動離開。效果採保守下界。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..sandbox.advise import Guarantee, Pricing
from .state import Cell, Phase, StageState


class Action(ABC):
    """三個問句一組：現在能做嗎、做了保證變成什麼、畫面上算不算做到了。

    progressed 只讀觀測到的狀態，不看「我方才送出過操作」——佇列靠畫面
    證據推進的紀律就落在這個介面上。
    """

    @property
    @abstractmethod
    def label(self) -> str: ...

    @abstractmethod
    def applicable(self, state: StageState) -> bool: ...

    @abstractmethod
    def apply(self, state: StageState, pricing: Pricing) -> StageState: ...

    @abstractmethod
    def progressed(self, state: StageState, pricing: Pricing) -> bool: ...


@dataclass(frozen=True)
class Move(Action):
    unit: str
    destination: Cell

    @property
    def label(self) -> str:
        return f"move:{self.unit}->{self.destination[0]},{self.destination[1]}"

    def applicable(self, state: StageState) -> bool:
        return self.unit in state.actionable and (self.unit, self.destination) in state.reachable

    def apply(self, state: StageState, pricing: Pricing) -> StageState:
        return state.relocate(self.unit, self.destination).spend(self.unit)

    def progressed(self, state: StageState, pricing: Pricing) -> bool:
        return self.unit not in state.actionable and state.position_of(self.unit) == self.destination


@dataclass(frozen=True)
class Attack(Action):
    unit: str
    target: str

    @property
    def label(self) -> str:
        return f"attack:{self.unit}->{self.target}"

    def applicable(self, state: StageState) -> bool:
        return self.unit in state.actionable and self.target in state.enemies

    def apply(self, state: StageState, pricing: Pricing) -> StageState:
        spent = state.spend(self.unit)
        return spent.kill(self.target) if pricing.guarantee is Guarantee.KILL else spent

    def progressed(self, state: StageState, pricing: Pricing) -> bool:
        if self.unit in state.actionable:
            return False
        return pricing.guarantee is not Guarantee.KILL or self.target not in state.enemies


@dataclass(frozen=True)
class Standby(Action):
    unit: str

    @property
    def label(self) -> str:
        return f"standby:{self.unit}"

    def applicable(self, state: StageState) -> bool:
        return self.unit in state.actionable

    def apply(self, state: StageState, pricing: Pricing) -> StageState:
        return state.spend(self.unit)

    def progressed(self, state: StageState, pricing: Pricing) -> bool:
        return self.unit not in state.actionable


@dataclass(frozen=True)
class Brace(Action):
    """應戰：彈窗只保證姿態被送出去，交戰結果不在承諾內。"""

    unit: str
    attacker: str
    stance: str

    @property
    def label(self) -> str:
        return f"brace:{self.unit}<-{self.attacker}:{self.stance}"

    def applicable(self, state: StageState) -> bool:
        reaction = state.reaction
        if reaction is None:
            return False
        return (
            reaction.defender == self.unit
            and reaction.attacker == self.attacker
            and self.stance in reaction.stances
        )

    def apply(self, state: StageState, pricing: Pricing) -> StageState:
        return state.clear_reaction()

    def progressed(self, state: StageState, pricing: Pricing) -> bool:
        return state.reaction is None


@dataclass(frozen=True)
class Withdraw(Action):
    @property
    def label(self) -> str:
        return "withdraw"

    def applicable(self, state: StageState) -> bool:
        return not state.withdrawn

    def apply(self, state: StageState, pricing: Pricing) -> StageState:
        return state.leave()

    def progressed(self, state: StageState, pricing: Pricing) -> bool:
        return state.withdrawn


VOCABULARY: tuple[type[Action], ...] = (Move, Attack, Standby, Brace, Withdraw)


def candidates(state: StageState) -> tuple[Action, ...]:
    """機械展開所有合法候選，不排序不篩選——取捨全交給注入的 Advisor。"""
    reaction = state.reaction
    if reaction is not None:
        return tuple(
            Brace(reaction.defender, reaction.attacker, stance) for stance in reaction.stances
        )
    if state.phase is not Phase.PLAYER:
        return ()
    actions: list[Action] = []
    for unit in sorted(state.actionable):
        actions.append(Standby(unit))
        actions.extend(Attack(unit, enemy) for enemy in sorted(state.enemies))
        actions.extend(Move(unit, cell) for cell in state.reach_of(unit))
    if not state.withdrawn:
        actions.append(Withdraw())
    return tuple(actions)
