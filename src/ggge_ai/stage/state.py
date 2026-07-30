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

    grid_on ＝ 輔助格線開著（畫面事實：地圖讀得出格網）。盤面全覽掃描以它
    為符號前置條件，所以開格線是一個行動、由規劃器排在掃描之前——掃描程序
    內部不偷偷翻開關，也沒有無格線降級掃這回事。

    board_synced ＝ 盤面全覽已收完並寫回，且還沒過期。swept ＝ 已掃完的分段，
    掃描行動跨 tick 重入時的恢復點。兩者都與 known 同族的程式內記憶（來源是
    stage/survey.py 的 SurveyPerceiver），但**必須在符號狀態上看得見**：完成
    判定走 progressed(state)，恢復點不能只活在執行器的內部變數裡。

    board_synced 過期＝敵方回合過完（敵人動過，站位全部作廢），所以回合交界
    會把它與 swept 一起打回原點（next_player_phase）。
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
    grid_on: bool = False
    board_synced: bool = False
    swept: frozenset[str] = frozenset()

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

    def show_grid(self) -> StageState:
        return replace(self, grid_on=True)

    def sync_board(self) -> StageState:
        """搜尋側的掃描是一步到底：分段進度是執行側的恢復點，不進搜尋鍵。"""
        return replace(self, board_synced=True)

    def kill(self, enemy: str) -> StageState:
        return replace(self, enemies=self.enemies - {enemy})

    def clear_reaction(self) -> StageState:
        return replace(self, reaction=None)

    def leave(self) -> StageState:
        return replace(self, withdrawn=True)


def next_player_phase(state: StageState) -> StageState:
    """回合交界的保守模型：敵方回合怎麼走不可預期，只承接必然成立的
    遊戲規則——存活我方單位下一個我方回合重新可行動。回合序號刻意不
    入狀態，讓沒有進展的交界自我重合，搜尋才會在原地打轉時收斂。

    盤面同步在交界一律過期：敵方回合裡每台敵人都可能動過，上一輪掃出來的站位
    不再是站位。格線不受影響（設定不會自己關掉）。"""
    return replace(
        state,
        phase=Phase.PLAYER,
        actionable=state.allies,
        reaction=None,
        board_synced=False,
        swept=frozenset(),
    )
