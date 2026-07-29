"""內層符號狀態：可行動我方單位集合＋敵方存活集合＋回合階段。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

Cell = tuple[int, int]


class Phase(Enum):
    PLAYER = "player"
    ENEMY = "enemy"


@dataclass(frozen=True)
class Reaction:
    """應戰彈窗的當下事實：誰被誰打、畫面給了哪些姿態。"""

    defender: str
    attacker: str
    stances: tuple[str, ...]


@dataclass(frozen=True)
class StageState:
    """符號層只留規劃推得動的事實；血量與武裝屬於沙盤，不進搜尋鍵。

    withdrawn 是規劃側的自標記——畫面永遠讀不到「我決定撤退」這件事，
    感知一律回 False，它只在搜尋內部讓離場目標可判定。

    known ＝ 已在本輪確認過詳情的單位。同樣不是畫面事實，來源是情報庫
    （stage/intel.py 的 IntelPerceiver 併入），因為 Inspect 的效果只有
    我們自己的記憶承接得住。
    """

    phase: Phase
    allies: frozenset[str]
    actionable: frozenset[str]
    enemies: frozenset[str]
    positions: frozenset[tuple[str, Cell]] = frozenset()
    reachable: frozenset[tuple[str, Cell]] = frozenset()
    known: frozenset[str] = frozenset()
    reaction: Reaction | None = None
    withdrawn: bool = False

    def __post_init__(self) -> None:
        strays = self.actionable - self.allies
        if strays:
            raise ValueError(f"可行動單位不在我方存活集合內：{sorted(strays)}")

    def position_of(self, unit: str) -> Cell | None:
        for uid, cell in self.positions:
            if uid == unit:
                return cell
        return None

    def reach_of(self, unit: str) -> tuple[Cell, ...]:
        return tuple(sorted(cell for uid, cell in self.reachable if uid == unit))

    def spend(self, unit: str) -> StageState:
        return replace(self, actionable=self.actionable - {unit})

    def relocate(self, unit: str, cell: Cell) -> StageState:
        kept = frozenset(pair for pair in self.positions if pair[0] != unit)
        return replace(self, positions=kept | {(unit, cell)})

    def learn(self, unit: str) -> StageState:
        return replace(self, known=self.known | {unit})

    def kill(self, enemy: str) -> StageState:
        return replace(self, enemies=self.enemies - {enemy})

    def clear_reaction(self) -> StageState:
        return replace(self, reaction=None)

    def leave(self) -> StageState:
        return replace(self, withdrawn=True)


def next_player_phase(state: StageState) -> StageState:
    """回合交界的保守模型：敵方回合怎麼走不可預期，只承接必然成立的
    遊戲規則——存活我方單位下一個我方回合重新可行動。回合序號刻意不
    入狀態，讓沒有進展的交界自我重合，搜尋才會在原地打轉時收斂。"""
    return replace(state, phase=Phase.PLAYER, actionable=state.allies, reaction=None)
