"""The mock action catalog.

Every `do()` here touches the mock device / mock board only; the one or two
comment lines above the mock body are the spec for what the real one does.
Preconditions carry as much weight as the bodies: a red line the loop must
never cross (never tap while a modal is up, never act outside our turn) is
expressed as a precondition, not as an `if` inside `do()`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .action import Action
from .state import UNKNOWN

if TYPE_CHECKING:
    from .bot import Bot


# --- 導航／修復：把畫面推回可操作的 hub，或把擋路的東西處理掉 ---


class ReachHub(Action):
    name = "ReachHub"
    cost = 2.0
    pre = {"in_stage": True, "obstruction": "none"}
    eff = {"view": "hub"}

    def do(self, bot: Bot) -> None:
        # 真做法：按一次返回鍵。還沒回到 hub 的話，下一 tick 的 sense 會看到
        # 還在別的畫面，規劃器自然會再選一次這個動作——不在 do() 裡迴圈。
        bot.device.tap(120, 980)
        bot.sensor.override(view="hub", panel="closed")


class ClearObstruction(Action):
    name = "ClearObstruction"
    cost = 1.0
    pre = {"obstruction": "popup"}
    eff = {"obstruction": "none"}

    def do(self, bot: Bot) -> None:
        # 真做法：用 vision 找出彈窗的關閉/確認鈕位置再點（座標會浮動，不寫死）。
        bot.device.tap(1170, 760)
        bot.sensor.override(obstruction="none")


class ExpandUnitList(Action):
    name = "ExpandUnitList"
    cost = 1.0
    pre = {"view": "hub", "unit_list": "collapsed"}
    eff = {"unit_list": "expanded"}

    def do(self, bot: Bot) -> None:
        # 真做法：點左側卡條把可操作單位列表展開，我方權威來源是這串卡條。
        bot.device.tap(90, 300)
        bot.sensor.override(unit_list="expanded")


class CollapseUnitList(Action):
    name = "CollapseUnitList"
    cost = 1.0
    pre = {"unit_list": "expanded"}
    eff = {"unit_list": "collapsed"}

    def do(self, bot: Bot) -> None:
        # 真做法：收起卡條，因為展開時它蓋住地圖左半，掃描會漏格。
        bot.device.tap(90, 300)
        bot.sensor.override(unit_list="collapsed")


class EnableGrid(Action):
    name = "EnableGrid"
    cost = 1.0
    pre = {"view": "hub", "grid": "off"}
    eff = {"grid": "on"}

    def do(self, bot: Bot) -> None:
        # 真做法：開格線顯示，讓像素座標能對回 cell 座標。
        bot.device.tap(2180, 140)
        bot.state.remember(grid="on")


class ZoomToMax(Action):
    name = "ZoomToMax"
    cost = 1.0
    pre = {"view": "hub"}
    eff = {"zoom": "max"}

    def do(self, bot: Bot) -> None:
        # 真做法：縮到最大比例尺——一格的像素夠大，模板比對才穩。
        bot.device.tap(2180, 420)
        bot.state.remember(zoom="max")


class WaitOut(Action):
    """The only legal way to spend a tick doing nothing.

    Cost is deliberately above `ClearObstruction`: if the obstruction can be
    identified and dismissed we do that; waiting is what is left when the
    screen is unreadable and we do not know what we would be tapping.
    """

    name = "WaitOut"
    cost = 4.0
    pre = {"view": UNKNOWN}
    eff = {"view": "hub", "obstruction": "none"}

    def do(self, bot: Bot) -> None:
        # 真做法：這個 tick 不碰裝置，讓劇情/轉場動畫自己跑；下一 tick 重新感知。
        # 不 sleep、不輪詢：它會一直待在隊頭，直到畫面重新讀得懂（eff 成立）。
        return


# --- 掃描：把地圖覆蓋起來，累積進 board ---


class ReAnchor(Action):
    name = "ReAnchor"
    cost = 1.5
    pre = {"view": "hub", "pose": "lost"}
    eff = {"pose": "anchored"}

    def do(self, bot: Bot) -> None:
        # 真做法：用地標模板重新定位，把螢幕座標系綁回 cell 座標系；
        # 對不上就維持 lost，讓 coverage 一直是 unknown（寧可重掃也不要錯位）。
        # 對位成功時當前視野的格子等於重新確認過一次，所以它也算一筆觀測進度——
        # 這讓「掉對位→修回來」的來回在流水帳的 progress 欄上看得出不是空轉。
        bot.board.pose = "anchored"
        bot.board.covered_cells += 1


class PanToFrontier(Action):
    """One swipe per tick, and it holds the head of the plan until the map is covered.

    `eff` is `coverage=complete`, which one swipe almost never achieves, so
    this is the plain case of a standing instruction: the plan does not move
    on until the board says the scan is done.
    """

    name = "PanToFrontier"
    cost = 1.0
    pre = {
        "view": "hub",
        "unit_list": "collapsed",
        "grid": "on",
        "zoom": "max",
        "pose": "anchored",
    }
    eff = {"coverage": "complete"}

    def do(self, bot: Bot) -> None:
        # 真做法：由 board 算出還沒覆蓋的方向，對地圖 swipe 一次；
        # 下一 tick 由 sense 重新定位，把新看到的格子併進 board。
        bot.device.swipe(1600, 540, 800, 540)
        bot.board.covered_cells += 1


# --- 逐台調查：打開單位面板讀數值，讀完退出來 ---


class TapUnit(Action):
    """Opens the unit info panel, and costs us the camera pose doing it."""

    name = "TapUnit"
    cost = 1.0
    pre = {"view": "hub", "coverage": "complete", "details": "partial"}
    eff = {"view": "panel", "panel": "ability_tab"}
    repeat_safe = False
    settle_ticks = 2

    _pose_loss_demoed = False

    def do(self, bot: Bot) -> None:
        # 真做法：點地圖上的單位圖示打開資訊面板。副作用是鏡頭會跳到該單位，
        # 掃描時建立的對位就失效了——所以退出面板後一定要重新 anchor。
        bot.device.tap(1180, 520)
        bot.sensor.override(view="panel", panel="ability_tab")
        if not self._pose_loss_demoed:
            # mock 只示範一次退化，真實情況是每次點都會掉。
            self._pose_loss_demoed = True
            bot.board.pose = "lost"


class ReadWeaponTab(Action):
    name = "ReadWeaponTab"
    cost = 1.0
    pre = {"view": "panel"}
    eff = {"panel": "weapon_tab", "details": "complete"}

    def do(self, bot: Bot) -> None:
        # 真做法：切到武裝分頁截一張，交給讀取器解析成結構化數值寫進 board。
        # 一次只解決一台，但 eff 寫的是 details=complete——所以它會留在隊頭
        # 一台一台讀下去，直到候選全部讀完為止。
        bot.device.tap(1520, 200)
        bot.sensor.override(panel="weapon_tab")
        bot.board.resolved_units += 1


class EscapePanel(Action):
    name = "EscapePanel"
    cost = 1.0
    pre = {"view": "panel"}
    eff = {"view": "hub", "panel": "closed"}

    def do(self, bot: Bot) -> None:
        # 真做法：點面板外或返回鍵關掉面板，回到地圖（鏡頭仍在跳走的位置）。
        bot.device.tap(120, 980)
        bot.sensor.override(view="hub", panel="closed")


# --- 思考／戰術：不碰裝置的動作，產出一樣進 state ---


class SyncSim(Action):
    """Pure computation. A think step is an action like any other."""

    name = "SyncSim"
    cost = 1.0
    pre = {"in_stage": True, "coverage": "complete", "details": "complete"}
    eff = {"sim_ready": True}

    def do(self, bot: Bot) -> None:
        # 真做法：把 board 的地形與單位快照灌進模擬器建 BattleState，不碰裝置。
        bot.state.remember(sim_ready=True)


class SolveTactics(Action):
    """Thinking as an action: it costs a tick, and its output is more plan.

    The second way a plan grows. `Bot.think` is the flow-level one (A* over
    this catalog); this is the tactical one, and it writes its result straight
    into the plan behind itself instead of returning it, so the steps it found
    are executed one per tick like anything else and stay interruptible.
    """

    name = "SolveTactics"
    cost = 1.0
    pre = {"in_stage": True, "phase": "our_turn", "sim_ready": True}
    eff = {"intent": "ready"}

    def do(self, bot: Bot) -> None:
        # 真做法：跑 expectiminimax 展開這回合的行動組合，產出 intent
        # （選誰、走哪一格、打誰），再把想出來的步驟接在自己後面。
        # 這裡的 mock 直接寫死一條三步序列當示範。
        bot.state.remember(intent="ready")
        bot.plan[1:1] = [SelectUnit(), MoveTo(), Attack()]


class SelectUnit(Action):
    name = "SelectUnit"
    cost = 1.0
    pre = {
        "in_stage": True,
        "phase": "our_turn",
        "cards": "present",
        "intent": "ready",
        "unit_state": "idle",
    }
    eff = {"unit_state": "selected"}

    def do(self, bot: Bot) -> None:
        # 真做法：點 intent 指定的那張單位卡（不是點地圖，卡條才是我方權威）。
        bot.device.tap(90, 260)


class MoveTo(Action):
    name = "MoveTo"
    cost = 1.0
    pre = {"unit_state": "selected", "intent": "ready"}
    eff = {"unit_state": "moved"}

    def do(self, bot: Bot) -> None:
        # 真做法：點 intent 指定的目標格；移動動畫由下一 tick 的 sense 收尾。
        bot.device.tap(1240, 560)


class Attack(Action):
    name = "Attack"
    cost = 1.0
    pre = {"unit_state": "moved", "intent": "ready"}
    eff = {"unit_state": "acted", "intent": "none"}

    def do(self, bot: Bot) -> None:
        # 真做法：開攻擊選單、選 intent 指定的武裝、確認出擊。
        # intent 用掉就作廢，下一台要打之前必須重新 SolveTactics。
        bot.device.tap(1700, 620)
        bot.state.remember(intent="none")


class EndTurn(Action):
    name = "EndTurn"
    cost = 3.0
    pre = {"in_stage": True, "phase": "our_turn", "cards": "absent"}
    eff = {"phase": "enemy_turn"}

    def do(self, bot: Bot) -> None:
        # 真做法：結束回合對話框永遠選左邊「待機並結束」再按執行。
        # 右邊是自動戰鬥（把單位交給內建 AI），架構紅線，絕不點。
        bot.device.tap(997, 562)
        bot.device.tap(1365, 850)


def default_catalog() -> list[Action]:
    return [
        ReachHub(),
        ClearObstruction(),
        ExpandUnitList(),
        CollapseUnitList(),
        EnableGrid(),
        ZoomToMax(),
        WaitOut(),
        ReAnchor(),
        PanToFrontier(),
        TapUnit(),
        ReadWeaponTab(),
        EscapePanel(),
        SyncSim(),
        SolveTactics(),
        SelectUnit(),
        MoveTo(),
        Attack(),
        EndTurn(),
    ]
