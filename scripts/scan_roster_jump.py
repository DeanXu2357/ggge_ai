"""名冊跳轉掃描：用「部隊資訊」的名冊逐台跳鏡頭，每一台都靠定位點掛回世界座標。

不推鏡找單位——名冊是完整的（我軍 10、敵軍 18），每一台都點得開、跳得到，剩下的
問題只是「跳過去那一台在世界的哪一格」。兩條路，都不含無標記的圖片比對：

- **relay**：同幀接力。目標端敵方＝跳轉指定標示所在格（落點幀與乾淨幀的變化指出來的，
  不是密度峰猜的）、我方＝移動範圍菱形的中心（跳轉直接進單位移動模式，**一下地圖都不
  點**）；鄰居端＝我們點下去而且真的出卡的那一格。兩端都是驗證過的格，幀內格差由同一張
  FrameGrid 算。鄰居的身分還沒有座標就先記帳，`settle` 回填。
- **march**：自力。在目標旁種標記，往西推到 FrameGrid 讀到西界，逐把靠標記重認累計
  格數；往北同理（先跳回同一台重置鏡頭）。

`board.find_unit_screen_hints` 的峰只拿來挑「要點哪一格問身分」，不進任何座標計算。

usage:
  uv run python scripts/scan_roster_jump.py --serial R5CRC37JBYJ --stage-node 544,667 \
      --stop-after prepare
  # 分段停點：prepare / roster / jump / settle
  uv run python scripts/scan_roster_jump.py … --no-abandon

前提：手機已經停在目標系列的關卡列表（選擇關卡頁）。--stage-node 必填，理由同
dry_run_entry（棄戰回來游標會飄）。

證據：data/runs/<時間戳>/roster_jump.jsonl＋frames/。名冊 JSON 出在 roster.json，
最終座標帳與矛盾清單出在 coords.json。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from ggge_ai.battle import vision
from ggge_ai.battle.map_grid import FrameGrid, GridUnreadable, read_frame_grid, snap_cell
from ggge_ai.runtime import board, entry, jumpscan, roster, screens, sweep
from ggge_ai.runtime.device import (
    ROSTER_CELL_INTENT,
    ROSTER_JUMP_INTENT,
    Adb,
    LiveDevice,
)
from ggge_ai.runtime.journal import Journal, rotate_runs
from ggge_ai.runtime.keyguard import Keyguard
from ggge_ai.runtime.perceive import decode

log = logging.getLogger("scan_roster_jump")

Cell = tuple[int, int]
Point = tuple[float, float]

RUNS_ROOT = Path("data/runs")
JOURNAL_NAME = "roster_jump.jsonl"
STAGES = ("prepare", "roster", "jump", "settle")
IN_BATTLE_STAGES = (None, "prepare", "roster", "jump", "settle")

PANEL_SETTLE_S = 1.2
JUMP_SETTLE_S = 1.5
TAP_SETTLE_S = 0.8
CARD_SETTLE_S = 1.0
# 迷路重試：連兩敗就退場記 unresolved，換下一台（與 jumpscan.next_target 對齊）。
JUMP_ATTEMPTS = 2
ROSTER_ATTEMPTS = 3
ROSTER_SETTLE_S = 1.0
# 面板判定一律輪詢：詳情頁開場有轉場動畫，單發 classify 會在動畫中途讀到底下的
# 部隊資訊（0806 run 20260806-024307 就是這樣把第一格誤判成列表盡頭）。
SCREEN_ATTEMPTS = 5
END_OF_LIST_CONFIRMATIONS = 2

# 路徑 A：最多問兩台鄰居的身分，都問不到就走自力。
RELAY_PROBES = 2
# 路徑 B：一軸最多推幾把（一把約一格半，地圖再大也用不到這麼多）。
MARCH_LEGS = 40
MARCH_SEED_ATTEMPTS = 3
# 標記連兩把認不回來就放棄該軸——重種一次是自癒，兩次是這一帶認不出填色。
MARCH_LOST_LIMIT = 2
# 標記離推進方向的出界邊剩不到這麼多格就先重種，別等它被推出視野。
MARCH_RESEED_PITCH = 1.5

# 路徑 A 的三種下場：接上一筆帳／這一窗問不出身分／點到我方被拉走鏡頭（整幀作廢）。
RELAY_LINKED = "linked"
RELAY_NONE = "none"
RELAY_ADRIFT = "adrift"

# 面板逐層關閉：詳情頁→部隊資訊→戰鬥選單。開選單前一律先跑一遍。
PANEL_LAYERS = 3
PANEL_CLOSERS: dict[str, tuple[int, int]] = {
    screens.UNIT_DETAIL: roster.DETAIL_CLOSE_TAP,
    screens.TROOP_INFO: roster.TROOP_INFO_CLOSE_TAP,
    screens.BATTLE_MENU: entry.BATTLE_MENU_CLOSE_TAP,
}

# 詳情頁的讀值區（陣營帶＋數值欄都在裡面）。淡入轉場中整張泛白，字模形狀過得了
# classify、顏色與筆畫卻全被稀釋（0806 run 20260806-120326 的 enemy#16：陣營帶紅色佔比
# 0.000、HP/EN/移動力三個欄位一起讀成 None），所以讀值之前要先確認這一塊停下來了。
DETAIL_REGION = (1100, 120, 700, 320)
DETAIL_READ_ATTEMPTS = 3

# 鏡頭落定的判準（0806 run 20260806-103335 量：同鏡位兩張 0.007-0.04，跳轉途中 0.15-0.37）。
CAMERA_STEADY_FRACTION = 0.06
CAMERA_STEADY_ATTEMPTS = 6
CAMERA_STEADY_WAIT_S = 0.6

# 巡迴順序預設敵方優先：敵 18 台是驗收大頭，而敵方那條路（紅圈指定→點出卡→name_sig）
# 才是接力鏈的證人來源；我方只出得了驗證格、出不了身分，排後面。
TOUR_ORDERS: dict[str, tuple[str, ...]] = {
    roster.ENEMY: (roster.ENEMY, roster.ALLY),
    roster.ALLY: (roster.ALLY, roster.ENEMY),
}

MARCH_AXES: tuple[tuple[int, str], ...] = ((0, "west"), (1, "north"))
LEAVING_EDGE = {"west": "east", "north": "south"}


def frame_grid(frame: np.ndarray) -> FrameGrid | None:
    """逐線對格（battle.map_grid）：慢，但不會被縱向透視咬掉一列。"""
    try:
        return read_frame_grid(frame)
    except GridUnreadable as exc:
        log.warning("frame grid unreadable: %s", exc)
        return None


def grid_pitch(grid: FrameGrid) -> tuple[float, float]:
    cols, rows = grid.cols, grid.rows
    return (
        (cols[-1] - cols[0]) / (len(cols) - 1),
        (rows[-1] - rows[0]) / (len(rows) - 1),
    )


def grid_centres(grid: FrameGrid) -> dict[Cell, Point]:
    return {
        (col, row): ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        for col, (x0, x1) in enumerate(zip(grid.cols, grid.cols[1:]))
        for row, (y0, y1) in enumerate(zip(grid.rows, grid.rows[1:]))
    }


def bounded(grid: FrameGrid, side: str) -> bool:
    return bool(grid.bounds()[side])


def card_present(frame: np.ndarray) -> bool:
    return vision.read_enemy_summary(frame) is not None


def read_signature(frame: np.ndarray) -> str | None:
    summary = vision.read_enemy_summary(frame)
    return None if summary is None else summary.name_sig


class Halt(RuntimeError):
    """停在原地：印出原因與當下截圖，不再點任何東西。"""


@dataclass
class Camera:
    """唯一幀源：段界與失敗點存的就是當下判定用的那一張。"""

    device: LiveDevice
    journal: Journal
    raw: bytes | None = field(default=None, init=False)
    shots: int = field(default=0, init=False)

    def screenshot(self) -> bytes:
        self.raw = self.device.screenshot()
        self.shots += 1
        return self.raw

    def grab(self) -> np.ndarray:
        return decode(self.screenshot())

    def settled(self, wait: float, sleep: Callable[[float], None]) -> np.ndarray:
        sleep(wait)
        return self.grab()

    def keep(self, label: str) -> str | None:
        path = self.journal.save_frame(self.raw, self.shots)
        self.journal.record("frame", label=label, frame=path)
        return path


@dataclass
class View:
    """一個鏡位：幀、它自己的格網、格心表。跳轉是硬切，所以每次落點都是新的一個。"""

    frame: np.ndarray
    grid: FrameGrid
    centres: dict[Cell, Point]

    @property
    def pitch(self) -> tuple[float, float]:
        return grid_pitch(self.grid)


@dataclass
class Scan:
    device: LiveDevice
    camera: Camera
    journal: Journal
    stop_after: str | None = None
    node: tuple[int, int] | None = None
    expect_title: str | None = entry.DEFAULT_EXPECTED_TITLE
    tour_first: str = roster.ENEMY
    sleep: Callable[[float], None] = time.sleep
    ledger: jumpscan.JumpLedger = field(default_factory=jumpscan.JumpLedger)
    entries: list[roster.RosterEntry] = field(default_factory=list)
    # 我們自己留在畫面上的東西：選取填色的色簽與格、以及最後一次解除點的格。
    signature: board.MarkerSignature | None = None
    marker: Cell | None = None
    dismissed: Cell | None = None
    # 本輪所有「非預期進入地圖子模式」事件，供驗收判準的零誤觸機器檢查。
    mistaps: list[dict] = field(default_factory=list)

    # ---------- 流程 ----------

    def run(self) -> None:
        capture, tap, nap = self.camera.grab, self.device.tap, self.sleep

        self.begin("prepare")
        self.gate(
            "select",
            entry.select_stage(
                capture, tap, node=self.node, expect_title=self.expect_title, sleep=nap
            ),
        )
        self.gate("prep", entry.open_sortie_prep(capture, tap, entry.GateReport(), sleep=nap))
        self.gate("enter", entry.enter_stage(capture, tap, sleep=nap))
        self.prepare_board()
        if self.end("prepare"):
            return

        self.begin("roster")
        self.read_roster()
        if self.end("roster"):
            return

        self.begin("jump")
        self.tour()
        if self.end("jump"):
            return

        self.begin("settle")
        self.settle()
        self.end("settle")

    # ---------- 掃描前置條件 ----------

    def prepare_board(self) -> None:
        """格線 ON ＋卡條收合。兩個都是這一支後面每一步的前置條件，不是可選項。

        格線設定沿用上一輪，OFF 的時候 `read_frame_grid` 讀不出任何一條線，定位鏈整條
        垮掉；展開的卡條蓋住地圖下緣，單位候選點與空白格挑選都會被污染。
        """
        report = entry.GateReport()
        entry.confirm_grid(self.camera.grab, self.device.tap, report, sleep=self.sleep)
        self.journal.record("gate", name="grid", trail=list(report.trail))
        self.camera.keep("prepare:grid")
        if not report.ok:
            raise Halt(f"格線閘門未過：{report.trail}")
        self.collapse_roster()
        self.camera.keep("prepare:roster_collapsed")

    def collapse_roster(self) -> None:
        """先讀再點：切換鈕是同一顆的兩個位置，讀不出來盲點一下會把收好的又展開。"""
        for _ in range(ROSTER_ATTEMPTS):
            strip = screens.read_roster_strip(self.camera.grab())
            self.journal.record("roster_strip", state=strip)
            if strip == screens.ROSTER_COLLAPSED:
                return
            if strip is None:
                raise Halt("卡條狀態讀不出來，不對著它盲點")
            self.device.tap(*screens.ROSTER_TOGGLE_TAP)
            self.sleep(ROSTER_SETTLE_S)
        raise Halt("卡條收不起來，掃描的前置條件不成立")

    # ---------- 名冊 ----------

    def read_roster(self) -> None:
        for faction in (roster.ALLY, roster.ENEMY):
            self.open_troop_info(faction)
            for index, point in enumerate(roster.cell_taps(faction)):
                frame = self.open_detail(point)
                if frame is None:
                    self.journal.record("roster_end", faction=faction, index=index)
                    break
                found = self.read_entry(faction, index)
                self.camera.keep(f"roster:{faction}:{index}")
                if found is None:
                    raise Halt(f"{faction}#{index} 的詳情頁讀不出陣營帶")
                self.entries.append(found)
                self.journal.record("roster_entry", **asdict(found))
                self.tap(roster.DETAIL_CLOSE_TAP, expect=screens.TROOP_INFO)
            self.close_panel()
        self.write_json("roster.json", [asdict(found) for found in self.entries])

    def read_entry(self, faction: str, index: int) -> roster.RosterEntry | None:
        """讀一台的詳情：先等這一頁畫完，讀不齊就重拍重讀。

        `classify` 過了不代表畫完——淡入轉場中的半透明幀字模形狀還在，顏色與筆畫卻被
        稀釋掉（0806 run 20260806-120326 的 enemy#16 就這樣把陣營帶與三個數值一起讀成
        None，整輪 Halt 在第 16 台）。
        """
        best: roster.RosterEntry | None = None
        for attempt in range(DETAIL_READ_ATTEMPTS):
            found = roster.read_detail(self.steady(DETAIL_REGION), index)
            if found is not None and found.complete:
                return found
            best = best or found
            self.journal.record(
                "detail_retry",
                faction=faction,
                index=index,
                attempt=attempt + 1,
                faction_band=found is not None,
            )
        return best

    def open_troop_info(self, faction: str) -> None:
        if not self.close_panels():
            raise Halt("面板收不回地圖，不對著不明畫面點選單")
        self.tap(entry.BATTLE_MENU_TAP, expect=screens.BATTLE_MENU)
        self.tap(roster.BATTLE_MENU_TROOP_INFO_TAP, expect=screens.TROOP_INFO)
        self.tap(roster.TAB_TAPS[faction], expect=screens.TROOP_INFO)

    def open_detail(self, point: tuple[int, int]) -> np.ndarray | None:
        """點一格開詳情。開不出來（畫面還是部隊資訊）＝列表盡頭，不是錯誤。

        盡頭要連續兩輪讀到部隊資訊才算數：一輪可能只是詳情頁的轉場還沒蓋滿。
        """
        self.device.tap(*point, intent=ROSTER_CELL_INTENT)
        seen = screens.UNKNOWN
        settled = 0
        for _ in range(SCREEN_ATTEMPTS):
            frame = self.camera.settled(PANEL_SETTLE_S, self.sleep)
            seen = screens.classify(frame)
            if seen == screens.UNIT_DETAIL:
                return frame
            settled = settled + 1 if seen == screens.TROOP_INFO else 0
            if settled >= END_OF_LIST_CONFIRMATIONS:
                return None
        raise Halt(f"點 {point} 之後畫面停在 {seen}，既不是詳情頁也不是名冊盡頭")

    def close_panel(self) -> None:
        self.tap(roster.TROOP_INFO_CLOSE_TAP, expect=screens.BATTLE_MENU)
        self.tap(entry.BATTLE_MENU_CLOSE_TAP, expect=None)

    def close_panels(self) -> bool:
        """逐層關閉：詳情頁→部隊資訊→戰鬥選單，最多三層，回到地圖才算數。

        0806 run 20260806-103335 的收尾 halt「點 ☰ 之後畫面是 troop_info」就是失敗路徑
        沒把面板收乾淨：`land()` 在詳情頁點不動「選擇」之後直接回報失敗，下一台開選單
        時整疊面板還開著。開選單前一律先跑這支，不要假設自己在地圖上。
        """
        for _ in range(PANEL_LAYERS):
            seen = screens.classify(self.camera.grab())
            closer = PANEL_CLOSERS.get(seen)
            if closer is None:
                return True
            self.journal.record("panel_recover", seen=seen)
            self.device.tap(*closer, intent=ROSTER_CELL_INTENT)
            self.sleep(PANEL_SETTLE_S)
        return screens.classify(self.camera.grab()) not in PANEL_CLOSERS

    def on_map(self) -> bool:
        return screens.classify(self.camera.grab()) not in PANEL_CLOSERS

    # ---------- 跳轉巡迴 ----------

    def keys(self) -> list[jumpscan.Key]:
        """巡迴序（也是排程的「名冊相鄰」定義）：先跑 `tour_first` 那一方。"""
        order = TOUR_ORDERS[self.tour_first]
        found = [(unit.faction, unit.index) for unit in self.entries]
        return sorted(found, key=lambda key: (order.index(key[0]), key[1]))

    def tour(self) -> None:
        roster_keys = self.keys()
        while True:
            key = jumpscan.next_target(self.ledger, roster_keys, give_up_after=JUMP_ATTEMPTS)
            if key is None:
                break
            visited = self.visit(key)
            self.ledger.settle()
            if self.ledger.resolved(key):
                continue
            # 記到一筆等回填的接力帳也算跑過一趟：不記次數會讓排程一直挑同一台。
            count = self.ledger.fail(key)
            self.journal.record(
                "jump_failed", key=list(key), failures=count, pending=visited
            )
            if count >= JUMP_ATTEMPTS:
                self.ledger.retire(key)
        if not self.ledger.cells:
            raise Halt("整份名冊都跳過了仍然一台都定位不了，帳面沒有任何絕對座標")

    def visit(self, key: jumpscan.Key) -> bool:
        """一台的一趟：跳轉 → 解除 → 讀指定格 → 路徑 A（接力）→ 路徑 B（自力）。"""
        view, target, sig = self.land(key, label="jump")
        if view is None or target is None:
            return False
        if sig is not None:
            self.ledger.identify(key, sig)
            self.journal.record("identity", key=list(key), sig=sig)
        # 第一趟才試便宜的接力：帳上一台都還沒定位就沒有可接的對象（第一台必然自力），
        # 而重來一趟的那一台上次已經接過了——再接一次多半又是同一筆等不到的線索。
        if self.ledger.cells and not self.ledger.failures.get(key):
            found = self.relay(key, view, target)
            if found == RELAY_LINKED:
                return True
            if found == RELAY_ADRIFT:
                # 鏡頭被拉走了，這一幀的格號全部作廢——march 只能從新的落點重來。
                return False
        return self.march(key, view, target)

    def land(
        self, key: jumpscan.Key, *, label: str
    ) -> tuple[View | None, Cell | None, str | None]:
        """跳轉 → 落點幀（帶指定標示）→ 解除 → 乾淨幀。回傳乾淨鏡位與目標格。

        目標格由**兩幀的變化**指出來（指定標示只在落點幀上），不是拿密度峰猜的；解除
        不移動鏡頭，所以兩幀共用同一張格網。
        """
        faction, index = key
        self.dismissed = None
        self.open_troop_info(faction)
        if self.open_detail(roster.cell_taps(faction)[index]) is None:
            raise Halt(f"{faction}#{index} 點不開詳情頁——名冊順序與跳轉對不上")
        self.device.tap(*roster.DETAIL_SELECT_TAP, intent=ROSTER_JUMP_INTENT)
        if not self.await_map():
            # 詳情頁沒收＝「選擇」那一下沒生效（0806 run 20260806-103335 的 ally#4
            # 第二趟：該台的詳情頁只有一顆置中的「關閉」，(1372,995) 點在空處）。
            self.journal.record("jump_not_taken", key=list(key))
            self.close_panels()
            return (None, None, None)
        # 跳轉不是瞬間到位：固定 1.5 秒的落點幀常常還是**跳轉前**的鏡位（同一輪 run 的
        # ally#0 落點幀與乾淨幀根本不是同一個鏡頭），兩幀不同鏡位時指定標示的比對整個
        # 沒有意義。改成等畫面自己停下來。
        landing = self.steady()
        self.camera.keep(f"{label}:{faction}:{index}:landing")
        sig = read_signature(landing)
        if faction == roster.ALLY:
            return self.land_ally(key, landing, sig, label)
        self.dismiss(faction, landing)
        clean = self.camera.settled(JUMP_SETTLE_S, self.sleep)
        self.camera.keep(f"{label}:{faction}:{index}:clean")
        view = self.view(clean)
        if view is None:
            view = self.look()
            self.journal.record("land_reread", key=list(key), ok=view is not None)
        if view is None:
            self.journal.record("land_failed", key=list(key), reason="grid_unreadable")
            return (None, None, sig)
        # 指定標示的比對一定要用**這張視圖自己的幀**：重讀過的話 clean 已經換人了。
        target = jumpscan.designation_cell(
            landing,
            view.frame,
            view.centres,
            half=min(view.pitch) / 3.0,
            exclude=self.own_marks(view, landing),
        )
        self.journal.record(
            "landed",
            key=list(key),
            target=None if target is None else list(target),
            sig=sig,
            bounds=view.grid.bounds(),
        )
        if target is None:
            return (view, None, sig)
        return (view, target, sig)

    def land_ally(
        self, key: jumpscan.Key, landing: np.ndarray, sig: str | None, label: str
    ) -> tuple[View | None, Cell | None, str | None]:
        """我方：跳轉本來就直接進「單位移動」，所以**一下地圖都不點**。

        目標格從高亮的移動範圍讀出來——那是遊戲自己以該台為中心、以移動力為半徑畫的
        菱形，中心就是它站的格。讀完按返回鈕回地圖。
        """
        faction, index = key
        seen = screens.classify(landing)
        self.journal.record("ally_landing_state", key=list(key), seen=seen)
        if seen != screens.BATTLE_UNIT_MOVE:
            # 已行動的單位跳不進移動模式（詳情頁連「選擇」鈕都沒有）。不猜、不點地圖。
            self.journal.record("jump_not_taken", key=list(key), reason=seen)
            self.close_panels()
            return (None, None, sig)
        moving = self.view(landing)
        target = None if moving is None else self.range_cell(key, moving)
        self.device.tap(*jumpscan.ALLY_DISMISS_TAP, intent=jumpscan.ALLY_DISMISS_INTENT)
        self.sleep(TAP_SETTLE_S)
        if not self.await_map():
            self.journal.record("ally_stuck_in_move", key=list(key))
            self.close_panels()
            return (None, None, sig)
        clean = self.steady()
        self.camera.keep(f"{label}:{faction}:{index}:clean")
        view = self.view(clean)
        if view is None or moving is None:
            self.journal.record("land_failed", key=list(key), reason="grid_unreadable")
            return (None, None, sig)
        if (view.grid.cols, view.grid.rows) != (moving.grid.cols, moving.grid.rows):
            # 退出移動模式之後格線對不上＝鏡頭動過，菱形算出來的格號不能跨鏡位用。
            self.journal.record("ally_grid_shifted", key=list(key))
            return (view, None, sig)
        self.journal.record(
            "landed",
            key=list(key),
            target=None if target is None else list(target),
            sig=sig,
            bounds=view.grid.bounds(),
        )
        return (view, target, sig)

    def range_cell(self, key: jumpscan.Key, moving: View) -> Cell | None:
        """移動範圍的菱形中心＝那台單位站的格。半徑用名冊讀到的移動力。"""
        reach = self.reach(key)
        if reach is None:
            self.journal.record("range_fit", key=list(key), reason="no_mobility")
            return None
        marks = jumpscan.range_marks(moving.frame, moving.pitch)
        cells = {snap_cell(moving.grid, point) for point in marks}
        seen = sorted(cell for cell in cells if cell is not None)
        window = (0, 0, len(moving.grid.cols) - 2, len(moving.grid.rows) - 2)
        found = jumpscan.diamond_centre(
            seen,
            reach,
            window=window,
            prefer=snap_cell(moving.grid, jumpscan.SCREEN_CENTRE),
        )
        self.journal.record(
            "range_fit",
            key=list(key),
            reach=reach,
            marks=len(seen),
            cell=None if found is None else list(found),
        )
        return found

    def reach(self, key: jumpscan.Key) -> int | None:
        for unit in self.entries:
            if (unit.faction, unit.index) == key:
                return unit.mobility
        return None

    def note_state(self, frame: np.ndarray, *, expect: str | None, where: str) -> str:
        """點完之後畫面在哪：進了非預期的地圖子模式就是誤觸，記進 run 級帳。

        「零誤觸」要機器查得到，不能靠人翻幀（0806 run 20260806-103335 誤下了一次移動
        指令，事後只能從詳情頁少一顆鈕反推）。
        """
        seen = screens.classify(frame)
        if seen in screens.MAP_SUBSTATES and seen != expect:
            self.mistaps.append({"where": where, "seen": seen})
            self.journal.record("mistap", where=where, seen=seen, expected=expect)
        return seen

    def await_map(self) -> bool:
        """跳轉之後面板要收乾淨才算數；一直停在面板上就是那一下沒生效。"""
        for _ in range(SCREEN_ATTEMPTS):
            if self.on_map():
                return True
            self.sleep(PANEL_SETTLE_S)
        return False

    def steady(self, region: tuple[int, int, int, int] = board.UNIT_DENSITY_REGION) -> np.ndarray:
        """等畫面停下來再拍：連兩張在 `region` 內的變化夠小才算落定。

        地圖用它等跳轉的鏡頭，面板用它等淡入轉場——同一個問題（發出≠畫完），同一把尺。
        """
        frame = self.camera.grab()
        moved = 1.0
        for _ in range(CAMERA_STEADY_ATTEMPTS):
            self.sleep(CAMERA_STEADY_WAIT_S)
            later = self.camera.grab()
            moved = jumpscan.changed_fraction(frame, later, region)
            frame = later
            if moved < CAMERA_STEADY_FRACTION:
                return frame
        self.journal.record("camera_unsteady", moved=round(moved, 3), region=list(region))
        return frame

    def own_marks(self, view: View, landing: np.ndarray) -> tuple[Cell, ...]:
        """我們自己在畫面上留下的填色：上一台的選取標記、這一台解除時點的那一格。

        兩張幀都要找——標記在落點幀與乾淨幀之間會被我們自己搬走，那個「消失」比任何
        指定標示都大聲。

        只收**這個鏡位**算得出來的格：`dismissed` 是剛剛在這一幀上點的，色簽是就地重找
        的；上一台記的格號屬於別的鏡位，一律不採用。
        """
        cells: list[Cell] = []
        if self.dismissed is not None:
            cells.append(self.dismissed)
        if self.signature is not None:
            for frame in (landing, view.frame):
                found = board.find_marker(
                    frame, self.signature, holes=board.UNIT_DENSITY_HUD_HOLES
                )
                cell = None if found is None else snap_cell(view.grid, found)
                if cell is not None:
                    cells.append(cell)
        return tuple(dict.fromkeys(cells))

    def view(self, frame: np.ndarray) -> View | None:
        grid = frame_grid(frame)
        return None if grid is None else View(frame, grid, grid_centres(grid))

    # ---------- 路徑 A：同幀接力 ----------

    def relay(self, key: jumpscan.Key, view: View, target: Cell) -> str:
        """點鄰居出卡讀身分：兩端都是驗證過的格，幀內格差直接記帳。

        身分還沒有座標一樣記——`settle` 會反覆回填到不動點。
        """
        peaks = board.find_unit_screen_hints(view.frame)
        probes = jumpscan.probe_order(peaks, view.centres[target], limit=RELAY_PROBES)
        for peak in probes:
            cell = snap_cell(view.grid, peak)
            point = None if cell is None else view.centres.get(cell)
            if cell is None or cell == target or point is None:
                continue
            verdict, sig = self.ask_identity(view, point)
            self.journal.record(
                "relay_probe", key=list(key), cell=list(cell), verdict=verdict, sig=sig
            )
            if verdict != sweep.TAP_CARD:
                # 卡沒開就當「可能點到我方、可能已經進了移動態」處理：先按返回，
                # 再決定要不要問下一格。verdict=none 與 shifted 在這裡沒有分別——
                # 我方單位的身分本來就讀不到（`read_enemy_summary` 只讀敵方卡）。
                self.escape_map()
                if verdict in sweep.TAP_SHIFTS:
                    # 鏡頭被拉走了，這一幀的格號全部作廢。
                    return RELAY_ADRIFT
                continue
            if sig is None:
                continue
            delta = (target[0] - cell[0], target[1] - cell[1])
            self.ledger.relay(key, sig, delta)
            self.journal.record("relay", key=list(key), via=sig, delta=list(delta))
            return RELAY_LINKED
        return RELAY_NONE

    def ask_identity(self, view: View, point: Point) -> tuple[str, str | None]:
        """點一格問身分：出卡才算數，卡沒開這一格就不算（換一格）。

        點擊座標本身就是格子的證明——點 (x,y) 落在格 c、卡開了，記的就是格 c。
        """
        before = self.camera.grab()
        self.device.tap(int(point[0]), int(point[1]))
        self.sleep(TAP_SETTLE_S)
        after = self.camera.grab()
        outcome = sweep.classify_tap(
            before, after, point, card=card_present, pitch=view.pitch
        )
        if outcome.verdict != sweep.TAP_CARD:
            self.note_state(after, expect=None, where="relay_probe")
            return (outcome.verdict, None)
        self.sleep(CARD_SETTLE_S)
        card = self.camera.grab()
        self.camera.keep("relay:card")
        sig = read_signature(card)
        self.clear_card(view)
        return (outcome.verdict, sig)

    def clear_card(self, view: View) -> None:
        """卡是疊在地圖上的浮層，點一個乾淨的空白格就收掉，鏡頭不動。"""
        blank = self.blank_point(view, board.find_unit_screen_hints(view.frame))
        if blank is None:
            raise Halt("收不掉單位卡：這一幀找不到任何乾淨空白格")
        self.device.tap(*blank)
        self.sleep(TAP_SETTLE_S)

    # ---------- 路徑 B：標記接力平移 ----------

    def march(self, key: jumpscan.Key, view: View, target: Cell) -> bool:
        """兩軸各推到界：西界定 x、北界定 y。兩軸之間跳回同一台重置鏡頭（O(1)）。"""
        found: dict[int, int] = {}
        for axis, direction in MARCH_AXES:
            if axis > 0:
                view, target, _ = self.land(key, label="march")
                if view is None or target is None:
                    self.journal.record("march_failed", key=list(key), axis=axis, reason="reland")
                    return False
            value = self.march_axis(key, view, target, axis, direction)
            if value is None:
                return False
            found[axis] = value
        cell = (found[0], found[1])
        self.ledger.anchor(key, cell, jumpscan.SOURCE_MARCH)
        self.journal.record("march", key=list(key), cell=list(cell))
        return True

    def march_axis(
        self, key: jumpscan.Key, view: View, target: Cell, axis: int, direction: str
    ) -> int | None:
        """往 direction 推到界，逐把靠標記重認算累計格數，回傳目標在該軸的世界格。"""
        name = jumpscan.AXIS_NAMES[axis]
        seeded = self.seed_marker(view, avoid=target)
        if seeded is None:
            self.journal.record("march_lost", key=list(key), axis=name, reason="no_seed")
            return None
        signature, marker = seeded
        legs: list[jumpscan.MarchLeg] = []
        lost = 0
        current: View | None = view
        for _ in range(MARCH_LEGS):
            if current is None:
                # 推鏡之後讀不出格網：鏡頭已經動了，**不准沿用推鏡前的舊視圖**假裝沒動。
                # 重拍重讀一次，還是讀不出來才計 lost。
                current = self.look()
                self.journal.record(
                    "march_reread", key=list(key), axis=name, ok=current is not None
                )
                if current is None:
                    lost += 1
                    if lost >= MARCH_LOST_LIMIT:
                        break
                    continue
            view = current
            if bounded(view.grid, direction):
                world = jumpscan.march_world(target[axis], legs, border_cell=0)
                self.journal.record(
                    "march_axis", key=list(key), axis=name, legs=len(legs), world=world
                )
                return world
            before = marker[axis]
            current = self.pan(direction)
            if current is None:
                lost += 1
                if lost >= MARCH_LOST_LIMIT:
                    break
                continue
            view = current
            point = board.find_marker(
                view.frame, signature, holes=board.UNIT_DENSITY_HUD_HOLES
            )
            cell = None if point is None else snap_cell(view.grid, point)
            if cell is None:
                lost += 1
                self.journal.record("march_lost", key=list(key), axis=name, legs=len(legs))
                if lost >= MARCH_LOST_LIMIT:
                    break
                continue
            lost = 0
            legs.append(jumpscan.MarchLeg(before, cell[axis]))
            marker = cell
            if self.leaving(view, point, direction):
                reseeded = self.seed_marker(view, signature=signature)
                if reseeded is None:
                    lost += 1
                    if lost >= MARCH_LOST_LIMIT:
                        break
                    continue
                signature, marker = reseeded
        self.journal.record("march_failed", key=list(key), axis=name, legs=len(legs))
        return None

    def leaving(self, view: View, point: Point, direction: str) -> bool:
        """標記快被推出視野了嗎——推西時它往東走，推北時它往南走。"""
        side = LEAVING_EDGE[direction]
        x, y, w, h = board.UNIT_DENSITY_REGION
        pitch = view.pitch
        if side == "east":
            return point[0] > x + w - MARCH_RESEED_PITCH * pitch[0]
        return point[1] > y + h - MARCH_RESEED_PITCH * pitch[1]

    def seed_marker(
        self,
        view: View,
        *,
        avoid: Cell | None = None,
        signature: board.MarkerSignature | None = None,
    ) -> tuple[board.MarkerSignature, Cell] | None:
        """在一個乾淨空白格種標記：點下去、驗收填色真的出現在被點的那一格才算數。

        沒驗收就記 `marker` 會讓下一把重認拿舊填色配新格號，整幀寫進差一格距整數倍的
        世界位置——這條紀律照抄 sweep_scan 的 `carry_marker`。
        """
        peaks = board.find_unit_screen_hints(view.frame)
        points = jumpscan.clean_points(
            view.frame,
            view.centres.values(),
            peaks,
            keep_out=jumpscan.PEAK_KEEP_OUT_PITCH * max(view.pitch),
            red_half=min(view.pitch) / 3.0,
        )
        points.sort(
            key=lambda point: float(
                np.hypot(point[0] - jumpscan.SCREEN_CENTRE[0], point[1] - jumpscan.SCREEN_CENTRE[1])
            )
        )
        for point in points[:MARCH_SEED_ATTEMPTS]:
            cell = snap_cell(view.grid, point)
            if cell is None or cell == avoid:
                continue
            before = self.camera.grab()
            self.device.tap(int(point[0]), int(point[1]))
            self.sleep(TAP_SETTLE_S)
            after = self.camera.grab()
            outcome = sweep.classify_tap(
                before, after, point, signature=signature, card=card_present, pitch=view.pitch
            )
            self.journal.record("seed_marker", cell=list(cell), verdict=outcome.verdict)
            if outcome.verdict != sweep.TAP_EMPTY:
                self.note_state(after, expect=None, where="seed_marker")
                # 說不出結果的那一下可能已經把畫面帶進選擇／移動態，而移動態下的下一次
                # 格點擊就是真的下移動指令（0806 run 20260806-103335 的 ally#4：連四下
                # verdict=none，之後那台的詳情頁只剩「關閉」＝它已經行動過了）。
                self.escape_map()
                continue
            learned = outcome.learned or signature
            if learned is None:
                continue
            self.signature = learned
            self.marker = cell
            return (learned, cell)
        return None

    def escape_map(self) -> None:
        """把畫面帶回地圖 hub：先按返回鈕（選擇／移動態唯一安全的一下），再驗面板。

        地圖上連點兩下之前一定要先跑這支——沒有 `selected=` 背書的 `classify_tap` 分不出
        「點到我方進了移動態」與「什麼都沒發生」，而那兩者的下一下差別是會不會誤下移動
        指令。
        """
        self.device.tap(*jumpscan.ALLY_DISMISS_TAP, intent=jumpscan.ALLY_DISMISS_INTENT)
        self.sleep(TAP_SETTLE_S)
        self.journal.record("escape_map", on_map=self.close_panels())

    def pan(self, direction: str) -> View | None:
        """一把推鏡。行程量不參與定位——世界座標只由標記重認的格數與界線決定。"""
        frame = self.camera.grab()
        origin, stroke = board.pan_stroke(
            direction, board.PAN_MAX_REACH, board.find_sightings(frame)
        )
        x1, y1, x2, y2 = board.pan_gesture(direction, origin, stroke)
        self.device.swipe(x1, y1, x2, y2, board.PAN_DURATION_S)
        self.journal.record("pan", direction=direction, reach=round(stroke, 1))
        return self.look()

    def look(self) -> View | None:
        """重拍重讀一張視圖。讀不出格網就是 None——沒有「沿用上一張」這個選項。"""
        return self.view(self.camera.settled(board.PAN_SETTLE_S, self.sleep))

    # ---------- 解除 ----------

    def dismiss(self, faction: str, frame: np.ndarray) -> None:
        """敵方的解除：點一個空白格。我方走 `land_ally`，這裡不該收到我方。"""
        view = self.view(frame)
        if view is None:
            # 落點幀讀不出格網可能只是轉場沒停穩：鏡頭沒動，重拍一張再試一次。
            view = self.look()
            self.journal.record("dismiss_reread", ok=view is not None)
        if view is None:
            raise Halt("落點幀讀不出格網，挑不出解除用的空白格")
        blank = self.blank_point(view, board.find_unit_screen_hints(view.frame))
        if blank is None:
            self.journal.record("no_blank_cell", faction=faction)
            raise Halt("落點幀找不到任何空白格可以解除敵方指定")
        self.device.tap(*blank)
        # 這一下自己會留下選取填色：記下來，指定標示的比對要把它排除。
        self.dismissed = snap_cell(view.grid, (float(blank[0]), float(blank[1])))

    def blank_point(self, view: View, peaks: Sequence[Point]) -> tuple[int, int] | None:
        return jumpscan.blank_cell_tap(
            view.frame,
            view.centres.values(),
            peaks,
            keep_out=jumpscan.PEAK_KEEP_OUT_PITCH * max(view.pitch),
            red_half=min(view.pitch) / 3.0,
        )

    # ---------- 收尾 ----------

    def settle(self) -> None:
        report = self.ledger.settle()
        flags = jumpscan.audit(self.ledger)
        units = jumpscan.ledger_report(self.ledger, self.keys())
        self.journal.record(
            "settle",
            clean_run=not self.mistaps,
            mistaps=len(self.mistaps),
            resolved=len(self.ledger.cells),
            filled=[list(key) for key in report.filled],
            relays=len(self.ledger.relays),
            identities=len(self.ledger.identities),
            conflicts=len(flags),
        )
        self.write_json(
            "coords.json",
            {
                # 驗收判準「零誤觸」的機器可讀答案：本輪有沒有任何一下把畫面帶進
                # 非預期的地圖子模式（移動／武裝選擇／技能）。
                "clean_run": not self.mistaps,
                "mistaps": self.mistaps,
                "units": units,
                "conflicts": [
                    {
                        "key": list(flag.key),
                        "known": list(flag.known),
                        "saw": list(flag.saw),
                        "via": flag.via,
                    }
                    for flag in flags
                ],
            },
        )
        log.info(
            "%d/%d resolved, %d relays, %d conflicts",
            len(self.ledger.cells),
            len(self.keys()),
            len(self.ledger.relays),
            len(flags),
        )

    def abandon(self) -> None:
        self.begin("abandon")
        self.gate(
            "abandon", entry.abandon_battle(self.camera.grab, self.device.tap, sleep=self.sleep)
        )
        self.end("abandon")

    # ---------- 通用 ----------

    def tap(self, point: tuple[int, int], *, expect: str | None, intent: str = "") -> np.ndarray:
        self.device.tap(*point, intent=intent)
        if expect is None:
            return self.camera.settled(PANEL_SETTLE_S, self.sleep)
        seen = screens.UNKNOWN
        for _ in range(SCREEN_ATTEMPTS):
            frame = self.camera.settled(PANEL_SETTLE_S, self.sleep)
            seen = screens.classify(frame)
            if seen == expect:
                return frame
        raise Halt(f"點 {point} 之後畫面是 {seen}，期望 {expect}")

    def write_json(self, name: str, payload: object) -> None:
        path = self.journal.path.parent / name
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.journal.record("wrote", file=name)

    def begin(self, name: str) -> None:
        self.device.ensure_unlocked(force=True)
        self.journal.record("stage", name=name)
        self.camera.grab()
        self.camera.keep(f"{name}:start")

    def end(self, name: str) -> bool:
        log.info("stage %s done (frame %s)", name, self.camera.keep(f"{name}:end"))
        return self.stop_after == name

    def gate(self, name: str, report: entry.GateReport) -> None:
        self.journal.record("gate", name=name, trail=list(report.trail))
        if report.ok:
            return
        raise Halt(f"{name} 閘門未過：{report.trail} {[s.detail for s in report.failures]}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", default=None)
    parser.add_argument("--stop-after", choices=STAGES, default=None)
    parser.add_argument("--stage-node", required=True, help="X,Y：要打的關卡節點（必填）")
    parser.add_argument("--expect-title", default=entry.DEFAULT_EXPECTED_TITLE)
    parser.add_argument("--tour-first", choices=sorted(TOUR_ORDERS), default=roster.ENEMY)
    parser.add_argument("--abandon", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--run-dir", type=Path, default=None)
    return parser.parse_args()


def point(text: str) -> tuple[int, int]:
    x, y = (int(value) for value in text.split(","))
    return x, y


def title(text: str | None) -> str | None:
    return None if text is None or text.lower() == "none" else text


def open_run(run_dir: Path | None) -> Journal:
    if run_dir is None:
        rotate_runs(RUNS_ROOT)
        run_dir = RUNS_ROOT / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    return Journal(run_dir / JOURNAL_NAME)


def soft_capture(camera: Camera) -> Callable[[], np.ndarray | None]:
    def capture() -> np.ndarray | None:
        try:
            return camera.grab()
        except Exception:
            log.warning("keyguard capture failed", exc_info=True)
            return None

    return capture


def build(args: argparse.Namespace, journal: Journal) -> Scan:
    adb = Adb(serial=args.serial)
    device = LiveDevice(adb=adb)
    camera = Camera(device=device, journal=journal)
    device.keyguard = Keyguard(shell=adb.shell, capture=soft_capture(camera))
    return Scan(
        device=device,
        camera=camera,
        journal=journal,
        stop_after=args.stop_after,
        node=point(args.stage_node),
        expect_title=title(args.expect_title),
        tour_first=args.tour_first,
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args()
    journal = open_run(args.run_dir)
    run_dir = journal.path.parent
    print(f"run dir: {run_dir}")
    scan = build(args, journal)
    journal.record("scan_start", stop_after=args.stop_after, stage_node=args.stage_node)
    try:
        scan.run()
        if args.abandon and args.stop_after in IN_BATTLE_STAGES:
            scan.abandon()
    except Halt as stop:
        frame = scan.camera.keep("halt")
        journal.record("halt", reason=str(stop), frame=frame)
        print(f"HALT: {stop}")
        print(f"當下截圖: {run_dir / frame if frame else '(無)'}")
        return 1
    except Exception as boom:
        frame = scan.camera.keep("crash")
        journal.record("crash", reason=repr(boom), frame=frame)
        print(f"CRASH: {boom!r}")
        raise
    journal.record("scan_end")
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
