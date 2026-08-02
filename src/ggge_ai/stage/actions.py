"""行動詞彙：移動／攻擊／偵察／待機／應戰／主動離開。效果採保守下界。"""

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
class Inspect(Action):
    """點單位讀詳情：只換到情報，不花任何單位的行動權。

    點單位會把可行動單位卡條彈回來（使用者實測），所以效果裡要把 roster_collapsed
    打回原點——否則規劃器會排出「收卡條→偵察→掃描」這種自己踩掉前置條件的計畫。
    """

    target: str

    @property
    def label(self) -> str:
        return f"inspect:{self.target}"

    def applicable(self, state: StageState) -> bool:
        return (
            state.phase is Phase.PLAYER
            and self.target in state.enemies
            and self.target not in state.known
        )

    def apply(self, state: StageState, pricing: Pricing) -> StageState:
        return state.learn(self.target).expand_roster()

    def progressed(self, state: StageState, pricing: Pricing) -> bool:
        return self.target in state.known


@dataclass(frozen=True)
class ShowGrid(Action):
    """開輔助格線。供給 grid_on，不花任何單位的行動權。

    翻開關的地方在戰鬥設定頁，所以這是一個會改遊戲狀態的行為——照 refire-gate
    同一精神，它是符號行動而不是藏在掃描程序裡的一步。驗不到格網＝沒進展，
    照既有行動失敗語意走（重送、換規劃、或誠實停止）。
    """

    @property
    def label(self) -> str:
        return "show_grid"

    def applicable(self, state: StageState) -> bool:
        return state.phase is Phase.PLAYER and not state.grid_on

    def apply(self, state: StageState, pricing: Pricing) -> StageState:
        return state.show_grid()

    def progressed(self, state: StageState, pricing: Pricing) -> bool:
        return state.grid_on


@dataclass(frozen=True)
class CollapseRoster(Action):
    """收可行動單位卡條（▽）。供給 roster_collapsed，不花任何單位的行動權。

    比照 ShowGrid：展開的卡條蓋住地圖下緣、掃描帶一路到 y1020，所以收卡條是一個
    符號行動而不是藏在掃描程序裡的一步（0730 使用者核可）。驗不到收合＝沒進展。
    """

    @property
    def label(self) -> str:
        return "collapse_roster"

    def applicable(self, state: StageState) -> bool:
        return state.phase is Phase.PLAYER and not state.roster_collapsed

    def apply(self, state: StageState, pricing: Pricing) -> StageState:
        return state.collapse_roster()

    def progressed(self, state: StageState, pricing: Pricing) -> bool:
        return state.roster_collapsed


@dataclass(frozen=True)
class SurveyBoard(Action):
    """盤面全覽掃描：最小縮放＋系統平移收全單位格座標。

    前置條件 grid_on 與 roster_collapsed 都是符號的——沒有格線就不掃，沒有降級版。
    像素→格的換算靠格線才穩，量不到格的座標進情報庫比沒有座標更糟；卡條沒收起來
    則下緣整帶量到的是卡條而不是地圖。

    **一個行動、跨 tick 重入**：它會留在計畫佇列頭被反覆 perform，執行器每次
    進來先感知複核再走一個微步驟（縮放→分段平移→逐幀量測吸附→邊界→合併
    寫回），所以反射可以在任何一個 tick 插進來收彈窗，之後接著掃。完成與否只
    看 board_synced——它的定義是沒有待掃格（四旗全定 ∧ 界內無缺口），不是推完
    幾把平移。
    """

    @property
    def label(self) -> str:
        return "survey_board"

    def applicable(self, state: StageState) -> bool:
        return (
            state.phase is Phase.PLAYER
            and state.grid_on
            and state.roster_collapsed
            and not state.board_synced
        )

    def apply(self, state: StageState, pricing: Pricing) -> StageState:
        return state.sync_board()

    def progressed(self, state: StageState, pricing: Pricing) -> bool:
        return state.board_synced


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


VOCABULARY: tuple[type[Action], ...] = (
    Move,
    Attack,
    Inspect,
    ShowGrid,
    CollapseRoster,
    SurveyBoard,
    Standby,
    Brace,
    Withdraw,
)


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
    actions.extend(Inspect(enemy) for enemy in sorted(state.enemies - state.known))
    for board_action in (ShowGrid(), CollapseRoster(), SurveyBoard()):
        if board_action.applicable(state):
            actions.append(board_action)
    if not state.withdrawn:
        actions.append(Withdraw())
    return tuple(actions)
