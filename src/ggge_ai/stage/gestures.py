"""行動詞彙 → 手勢串。

住在 stage 而不是 runtime：手勢重播器不認識行動詞彙（型別住 stage），而「棄戰
要按哪三下」是關卡層的知識。plan 是純函式，吃行動與當下觀測、吐手勢，所以每個
接線點都能離線比對座標。

本批只接得動已標定完的流程。移動／攻擊／偵察要先有「單位 ↔ 螢幕點」的對位
（盤面掃描與身分解析的下一步），沒接的一律讓執行器拋 UnsupportedAction——無聲
空轉是這個專案最貴的失效模式。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from ..runtime.device import Gesture, Settle, Tap, UnsupportedAction
from ..runtime.entry import (
    ABANDON_CONFIRM_TAP,
    BATTLE_MENU_ABANDON_TAP,
    BATTLE_MENU_TAP,
)
from ..runtime.perceive import Observation
from .actions import Brace, Withdraw

# 應戰動作列是固定槽位格、右錨不動（0719 像素實證推翻「錨點隨武器數右移」）：
# 閃避最右，防禦左一格，反擊武器從防禦再往左 pitch=187 排。標定的兩個錨點實際
# 相距 188px，docs/battle-prep-ui.md 記的 pitch 是 187——差一像素，武器槽照文件
# 的 187 推。
STANCE_DODGE_TAP = (1540, 940)
STANCE_DEFEND_TAP = (1352, 940)
STANCE_PITCH = 187
STANCE_ROW_Y = 940
# 行動選擇：與出擊準備的自動編制共用同一塊右上區域，所以帶 intent 才點得下去。
REACTION_CONFIRM_TAP = (2042, 924)
CONFIRM_INTENT = "confirm"

# 結束回合對話框（0731 裁定自反射組遷出：選哪邊是行為選擇，歸按下結束
# 回合鈕的行動，反射不代答）。左「待機並結束」、右邊是自動戰鬥（紅線，
# 永不點）；兩下之間要留重繪時間，否則第二下打在動畫上被吃掉。結束回合
# 行動落地前先只保存標定。
END_TURN_WAIT_TAP = (997, 562)
END_TURN_CONFIRM_TAP = (1365, 850)

# 有盾機體的防禦鈕就是同一個槽位（換圖示、不換位置）。
STANCE_TAPS: dict[str, tuple[int, int]] = {
    "dodge": STANCE_DODGE_TAP,
    "defend": STANCE_DEFEND_TAP,
    "shield": STANCE_DEFEND_TAP,
}


def withdraw_gestures(action: Withdraw, observation: Observation[Any]) -> Sequence[Gesture]:
    """☰ → 放棄 → 確認。放棄鈕在危險帶內，只有這裡帶 intent。"""
    return (
        Tap(*BATTLE_MENU_TAP, settle_s=1.5),
        Tap(*BATTLE_MENU_ABANDON_TAP, settle_s=1.5, intent="abandon"),
        Tap(*ABANDON_CONFIRM_TAP, settle_s=3.0),
        Settle(1.0),
    )


def brace_gestures(action: Brace, observation: Observation[Any]) -> Sequence[Gesture]:
    """姿態鈕 → 行動選擇確認。

    counter:<武器> 需要武器在動作列的槽位，而槽位佔用要讀選單（EN 黃字）才知道
    ——那一段還沒接，所以直接拒絕而不是亂點一格。
    """
    point = STANCE_TAPS.get(action.stance)
    if point is None:
        raise UnsupportedAction(f"stance {action.stance!r} has no calibrated slot")
    return (
        Tap(*point, settle_s=1.2),
        Tap(*REACTION_CONFIRM_TAP, settle_s=2.0, intent=CONFIRM_INTENT),
    )


def battle_plans() -> dict[type, Callable[[Any, Observation[Any]], Sequence[Gesture]]]:
    return {Withdraw: withdraw_gestures, Brace: brace_gestures}
