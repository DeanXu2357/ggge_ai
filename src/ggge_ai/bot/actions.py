"""The mock catalog: actions, the symbol table, and the reflex table.

Every `do()` here touches the mock screen / board / device only; the
comment above each mock body is the spec for the real one. Actions read
symbols, never frames -- when a step needs a screen feature, the classifier
tags it and the symbol table below translates it.

Structural red line: choice dialogs (end-turn confirm and friends) are
identity tags driven by explicit actions; identity tags may never be
registered in the reflex table (`misrouted_identity_tags` enforces it), so no
generic dismiss logic can ever reach the auto-battle button.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .action import Action
from .frame import Tag
from .router import (
    ReflexRule,
    ReflexTable,
    SymbolTable,
    from_identity,
    identity_scope,
    tag_present,
    tag_value,
)
from .state import UNKNOWN

if TYPE_CHECKING:
    from .bot import Bot

# 記憶門符號的宣告——完備性測試用它對帳：pre/eff 出現的符號，
# 要嘛在符號表、要嘛在盤面摘要、要嘛在這裡。
MEMORY_SYMBOLS = frozenset({"intent", "sim_ready"})

# 畫面身分的封閉登記清單：identity tag 名 -> view 值。
IDENTITY_VIEWS = {"hub": "hub", "unit_panel": "panel"}


def default_symbol_table() -> SymbolTable:
    return SymbolTable(
        {
            "view": from_identity(IDENTITY_VIEWS),
            "turn": tag_value({"turn_ours": "our_turn", "turn_enemy": "enemy_turn"}),
            "cards": identity_scope({"hub"}, tag_present("unit_cards", "present", "absent")),
            "unit_list": identity_scope(
                {"hub"}, tag_present("unit_list_expanded", "expanded", "collapsed")
            ),
            "grid": identity_scope({"hub"}, tag_present("grid_on", "on", "off")),
            "zoom": identity_scope({"hub"}, tag_present("zoom_max", "max", "not_max")),
            "panel_tab": identity_scope(
                {"unit_panel"}, tag_value({"tab_weapon": "weapon", "tab_ability": "ability"})
            ),
            "unit_state": identity_scope(
                {"hub"},
                tag_value(
                    {"unit_selected": "selected", "unit_moved": "moved", "unit_acted": "acted"},
                    default="idle",
                ),
            ),
        },
        identities=IDENTITY_VIEWS,
    )


# --- 反射 handler：tap-through 類才進表；back 類 v1 由 replan＋導航動作承接 ---


def _tap_through(bot: Bot, tag: Tag) -> None:
    # 真做法：點分類器找到的位置（payload 座標），睡過跳轉；多頁劇情靠
    # 「tag 還在就每拍再被派發一次」連點推進。座標永遠來自本幀的 tag，
    # 不寫死。等待／重觸發判斷若有需要，寫在 handler 內容裡，不歸 router。
    assert tag.point is not None
    bot.device.tap(*tag.point)
    bot.clock.sleep(1.0)


def _dismiss_info_popup(bot: Bot, tag: Tag) -> None:
    # 真做法：單鈕資訊彈窗（獎勵通知等），點確認鈕。選擇型對話框永遠
    # 不會走到這裡——它們是 identity tag，靜態擋在反射表外。
    assert tag.point is not None
    bot.device.tap(*tag.point)
    bot.clock.sleep(0.5)


def default_reflex_table() -> ReflexTable:
    return ReflexTable(
        [
            ReflexRule(tag="skip_ui", handler=_tap_through),
            ReflexRule(tag="info_popup", handler=_dismiss_info_popup),
        ]
    )


# --- 觀察：不可讀的畫面是規劃的課題，不是迴圈的分支 ---


class Observe(Action):
    """The route out of an unreadable screen, expressed as an ordinary step.

    `view: unknown` is a state like any other, so the planner can be given a
    step that leaves it -- "look until the screen reads again, then carry on".
    It is a standing instruction with nothing to send: it holds the head while
    the screen stays unreadable, pops the moment the target screen is attested,
    and breaks its own `pre` if the screen comes back as something else, which
    replans from the now-known state.
    """

    name = "Observe"
    cost = 1.0
    pre = {"view": UNKNOWN}
    eff = {"view": IDENTITY_VIEWS["hub"]}

    def do(self, bot: Bot) -> None:
        # 真做法：不送任何輸入——下一拍的截圖就是唯一需要的新證據。
        pass


# --- 導航／畫面整備 ---


class ExpandUnitList(Action):
    """Ensure-style: pre binds the screen only, eff states the target value.

    The setup actions deliberately do not require the opposite value in
    `pre` -- identity scoping makes hub facts UNKNOWN while a panel is up, and
    a pre of `grid: off` would leave the planner no route from UNKNOWN. With
    ensure semantics the planner can schedule the step from an unknown
    state, and at runtime the evidence-pop discards it for free when the
    target already holds -- the toggle button is never blindly re-tapped.
    """

    name = "ExpandUnitList"
    cost = 1.0
    pre = {"view": "hub"}
    eff = {"unit_list": "expanded"}

    def do(self, bot: Bot) -> None:
        # 真做法：點左側卡條展開可操作單位列表（我方權威來源）。
        bot.device.tap(90, 300)
        bot.screen.retag_base(add=(Tag("unit_list_expanded"),))
        bot.clock.sleep(0.3)


class CollapseUnitList(Action):
    name = "CollapseUnitList"
    cost = 1.0
    pre = {"view": "hub"}
    eff = {"unit_list": "collapsed"}

    def do(self, bot: Bot) -> None:
        # 真做法：收起卡條——展開時蓋住地圖左半，掃描會漏格。
        bot.device.tap(90, 300)
        bot.screen.retag_base(remove=("unit_list_expanded",))
        bot.clock.sleep(0.3)


class EnableGrid(Action):
    name = "EnableGrid"
    cost = 1.0
    pre = {"view": "hub"}
    eff = {"grid": "on"}

    def do(self, bot: Bot) -> None:
        # 真做法：開格線顯示。格線開沒開是畫面能作證的事實，所以走
        # 感知門（分類器 grid_on tag），不用 remember——舊骨架在這裡
        # 用記憶門是界線模糊，已依規格改正。
        bot.device.tap(2180, 140)
        bot.screen.retag_base(add=(Tag("grid_on"),))
        bot.clock.sleep(0.3)


class ZoomToMax(Action):
    name = "ZoomToMax"
    cost = 1.0
    pre = {"view": "hub"}
    eff = {"zoom": "max"}

    def do(self, bot: Bot) -> None:
        # 真做法：縮到最大比例尺（pinch 冪等）；zoom 值域由格線 pitch
        # 推導，同樣是感知符號。
        bot.device.tap(2180, 420)
        bot.screen.retag_base(add=(Tag("zoom_max"),))
        bot.clock.sleep(0.3)


# --- 掃描 ---


class ReAnchor(Action):
    name = "ReAnchor"
    cost = 1.5
    pre = {"view": "hub", "pose": "lost"}
    eff = {"pose": "anchored"}

    def do(self, bot: Bot) -> None:
        # 真做法：地標模板重新定位，把螢幕座標綁回 cell 座標；對不上就
        # 維持 lost（coverage 一直 unknown，寧可重掃不要錯位）。對位成功
        # 等於重新確認當前視野，所以也算一筆觀測進度。
        bot.board.pose = "anchored"
        bot.board.covered_cells += 1


class PanToFrontier(Action):
    """One swipe per tick; holds the head until the board says the map is covered."""

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
        # 真做法：board 算出未覆蓋方向，對地圖 swipe 一次；新格子由
        # 下一拍的感知併進 board。
        bot.device.swipe(1600, 540, 800, 540)
        bot.board.covered_cells += 1
        bot.clock.sleep(0.2)


# --- 逐台調查 ---


class TapUnit(Action):
    """Opens the unit info panel, and costs us the camera pose doing it."""

    name = "TapUnit"
    cost = 1.0
    pre = {"view": "hub", "coverage": "complete", "details": "partial"}
    eff = {"view": "panel"}

    def do(self, bot: Bot) -> None:
        # 真做法：點地圖上的單位圖示。面板開在哪個 tab 由遊戲的黏性記憶
        # 決定——我們不建模，開了看一眼就知道（mock 固定開在能力分頁，
        # 最壞情況）。副作用：鏡頭跳到該單位，掃描對位失效。
        bot.device.tap(1180, 520)
        bot.screen.enter((Tag("unit_panel"), Tag("tab_ability")))
        bot.board.pose = "lost"
        bot.clock.sleep(1.0)


class ToWeaponTab(Action):
    """A step that may never fire: if the panel already shows the weapon tab it pops free."""

    name = "ToWeaponTab"
    cost = 1.0
    pre = {"view": "panel"}
    eff = {"panel_tab": "weapon"}

    def do(self, bot: Bot) -> None:
        # 真做法：點武裝分頁的頁籤。
        bot.device.tap(1520, 200)
        bot.screen.retag_overlay(add=(Tag("tab_weapon"),), remove=("tab_ability",))
        bot.clock.sleep(0.3)


class ReadWeaponData(Action):
    name = "ReadWeaponData"
    cost = 1.0
    pre = {"panel_tab": "weapon"}
    eff = {"details": "complete"}

    def do(self, bot: Bot) -> None:
        # 真做法：截武裝分頁交給讀取器解析成結構化數值寫進 board。
        # 一拍一台，eff 是 details=complete——留在隊頭直到候選讀完。
        bot.board.resolved_units += 1
        bot.clock.sleep(0.2)


class EscapePanel(Action):
    name = "EscapePanel"
    cost = 1.0
    pre = {"view": "panel"}
    eff = {"view": "hub"}

    def do(self, bot: Bot) -> None:
        # 真做法：返回鍵關面板回地圖（鏡頭仍在跳走的位置，pose 還是 lost）。
        bot.device.tap(120, 980)
        bot.screen.exit()
        bot.clock.sleep(0.5)


# --- 思考／戰術：不碰裝置的動作，產出一樣進符號空間或隊列 ---


class SyncSim(Action):
    """Pure computation. A think step is an action like any other."""

    name = "SyncSim"
    cost = 1.0
    pre = {"coverage": "complete", "details": "complete"}
    eff = {"sim_ready": True}

    def do(self, bot: Bot) -> None:
        # 真做法：把 board 的地形與單位快照灌進模擬器建 BattleState。
        # sim_ready 是畫面看不見的裁定——記憶門。
        bot.state.remember(sim_ready=True)


class SolveTactics(Action):
    """Thinking as an action: it costs a tick, and its output is more queue."""

    name = "SolveTactics"
    cost = 1.0
    pre = {"turn": "our_turn", "sim_ready": True}
    eff = {"intent": "ready"}

    def do(self, bot: Bot) -> None:
        # 真做法：expectiminimax 展開本回合行動組合，產出 intent 並把
        # 步驟接在自己後面（splice）——之後照樣一拍一步、可被中斷。
        bot.state.remember(intent="ready")
        bot.queue[1:1] = [SelectUnit(), MoveTo(), Attack()]


class SelectUnit(Action):
    name = "SelectUnit"
    cost = 1.0
    pre = {"turn": "our_turn", "cards": "present", "intent": "ready", "unit_state": "idle"}
    eff = {"unit_state": "selected"}

    def do(self, bot: Bot) -> None:
        # 真做法：點 intent 指定的單位卡（卡條才是我方權威，不點地圖）。
        bot.device.tap(90, 260)
        bot.screen.retag_base(add=(Tag("unit_selected"),))
        bot.clock.sleep(0.3)


class MoveTo(Action):
    name = "MoveTo"
    cost = 1.0
    pre = {"unit_state": "selected", "intent": "ready"}
    eff = {"unit_state": "moved"}

    def do(self, bot: Bot) -> None:
        # 真做法：點 intent 指定的目標格；移動動畫睡過去。
        bot.device.tap(1240, 560)
        bot.screen.retag_base(add=(Tag("unit_moved"),), remove=("unit_selected",))
        bot.clock.sleep(1.0)


class Attack(Action):
    name = "Attack"
    cost = 1.0
    pre = {"unit_state": "moved", "intent": "ready"}
    eff = {"intent": "none"}

    def do(self, bot: Bot) -> None:
        # 真做法：開攻擊選單、選 intent 指定的武裝、確認出擊。intent 用掉
        # 即作廢（記憶門）；下一台要打之前必須重新 SolveTactics。
        bot.device.tap(1700, 620)
        bot.state.remember(intent="none")
        bot.screen.retag_base(add=(Tag("unit_acted"),), remove=("unit_moved",))
        bot.clock.sleep(1.5)


class EndTurn(Action):
    name = "EndTurn"
    cost = 3.0
    pre = {"turn": "our_turn", "cards": "absent"}
    eff = {"turn": "enemy_turn"}

    def do(self, bot: Bot) -> None:
        # 真做法：結束回合對話框（identity tag，不進反射表）永遠選左邊「待機並結束」
        # 再按執行。右邊是自動戰鬥紅線，絕不點——本動作是唯一的擁有者。
        bot.device.tap(997, 562)
        bot.device.tap(1365, 850)
        bot.clock.sleep(1.0)


def default_catalog() -> list[Action]:
    return [
        Observe(),
        ExpandUnitList(),
        CollapseUnitList(),
        EnableGrid(),
        ZoomToMax(),
        ReAnchor(),
        PanToFrontier(),
        TapUnit(),
        ToWeaponTab(),
        ReadWeaponData(),
        EscapePanel(),
        SyncSim(),
        SolveTactics(),
        SelectUnit(),
        MoveTo(),
        Attack(),
        EndTurn(),
    ]
