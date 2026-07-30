"""反射組：把畫面收乾回穩態，不做行為決策。

反射只看畫面名與感知已經讀出來的小值——像素工作在 perceive 那裡發生過一次，
反射層再碰一次就是兩份真相。每個反射吐一個 ScreenFix（自帶手勢），迴圈交給
執行器重播，成敗照舊由下一張畫面裁決。

不在這裡的東西：跨 tick 的行為（由行動自身的符號流程承接，0727 裁決否決空轉
拍）、觸控鎖（在裝置通道的每段操作前，不是反射——反射也得先能點得動）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from . import screens
from .device import Gesture, Key, Settle, Tap

# 登入彈窗收乾路徑（0729 標定）：LOGIN BONUS 的 TAP TO NEXT → 公告「關閉」。
LOGIN_BONUS_TAP = (1150, 1000)
NOTICE_CLOSE_TAP = (1170, 993)
# 午夜跨日的系統對話框「將返回主畫面」＋前往主畫面鈕。
DATE_CHANGED_TAP = (1178, 850)
# 結束回合對話框：**永遠左邊「待機並結束」**，右邊是自動戰鬥（紅線）。
END_TURN_WAIT_TAP = (997, 562)
END_TURN_CONFIRM_TAP = (1365, 850)
# 地圖子模式（誤入單位移動／武裝選擇）退回穩態。
BATTLE_RETURN_TAP = (1802, 930)
UNIT_DETAIL_CLOSE_TAP = (1176, 992)
GAME_ICON_TAP = (355, 234)


@dataclass(frozen=True)
class ScreenFix:
    """一次收乾操作。label 進流水帳，gestures 給執行器重播。"""

    label: str
    gestures: tuple[Gesture, ...]


@dataclass(frozen=True)
class PopupReflex:
    """畫面名 → 固定收乾手勢。內容全是資料，沒有分支。"""

    name: str
    screen: str
    fix: ScreenFix

    def match(self, observation: Any) -> ScreenFix | None:
        return self.fix if observation.screen == self.screen else None


@dataclass
class StallWatchdog:
    """前景卡死看門狗（0729 實測的新故障模式）。

    症狀：遊戲仍是前景、adb 與 HOME 全活，只有 Unity 的幀泵與觸控處理停住——
    連續互動全無反應且畫面不動。復原＝HOME → 桌面點遊戲圖示回前景。

    判準是「連續 limit 張畫面指紋完全相同」。指紋來自感知（16x16／32 階降採樣），
    真動畫會改值。省電觸控鎖也會讓畫面凍住，但那是裝置通道每段操作前先處理掉
    的，走到這裡還在凍就不是鎖。
    """

    limit: int = 5
    name: ClassVar[str] = "stall"
    last: str | None = field(default=None, init=False)
    streak: int = field(default=0, init=False)

    def match(self, observation: Any) -> ScreenFix | None:
        signature = observation.evidence.get("frame_sig")
        if not signature:
            self.last, self.streak = None, 0
            return None
        if signature == self.last:
            self.streak += 1
        else:
            self.last, self.streak = signature, 1
        if self.streak < self.limit:
            return None
        self.streak = 0
        return ScreenFix(
            label="recover:foreground",
            gestures=(
                Key("KEYCODE_HOME", settle_s=2.0),
                Tap(*GAME_ICON_TAP, settle_s=6.0),
                Settle(2.0),
            ),
        )


LOGIN_BONUS_FIX = ScreenFix("skip:login_bonus", (Tap(*LOGIN_BONUS_TAP, settle_s=2.5),))
NOTICE_FIX = ScreenFix("skip:notice", (Tap(*NOTICE_CLOSE_TAP, settle_s=2.0),))
DATE_CHANGED_FIX = ScreenFix("dismiss:date_changed", (Tap(*DATE_CHANGED_TAP, settle_s=3.0),))
# 左選項＋執行：兩下之間留時間讓對話框重繪，否則第二下打在動畫上被吃掉。
END_TURN_FIX = ScreenFix(
    "end_turn:wait",
    (Tap(*END_TURN_WAIT_TAP, settle_s=1.0), Tap(*END_TURN_CONFIRM_TAP, settle_s=2.0)),
)
UNIT_MOVE_FIX = ScreenFix("leave:unit_move", (Tap(*BATTLE_RETURN_TAP, settle_s=1.2),))
UNIT_DETAIL_FIX = ScreenFix("close:unit_detail", (Tap(*UNIT_DETAIL_CLOSE_TAP, settle_s=1.2),))


def default_reflexes() -> tuple[Any, ...]:
    """收乾順序：對話框先於子模式，子模式先於看門狗——看門狗的復原最粗暴，
    只有沒別的東西可收時才輪到它。"""
    return (
        PopupReflex("login_bonus", screens.LOGIN_BONUS, LOGIN_BONUS_FIX),
        PopupReflex("notice", screens.NOTICE, NOTICE_FIX),
        PopupReflex("date_changed", screens.DATE_CHANGED, DATE_CHANGED_FIX),
        PopupReflex("end_turn", screens.END_TURN_DIALOG, END_TURN_FIX),
        PopupReflex("unit_detail", screens.UNIT_DETAIL, UNIT_DETAIL_FIX),
        PopupReflex("unit_move", screens.BATTLE_UNIT_MOVE, UNIT_MOVE_FIX),
        PopupReflex("weapon_select", screens.BATTLE_WEAPON_SELECT, UNIT_MOVE_FIX),
        StallWatchdog(),
    )
