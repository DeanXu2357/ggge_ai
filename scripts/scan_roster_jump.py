"""名冊跳轉掃描：用「部隊資訊」的名冊逐台跳鏡頭，每一台都靠定位點掛回世界座標。

不推鏡找單位——名冊是完整的（我軍 10、敵軍 18），每一台都點得開、跳得到，剩下的
問題只是「跳過去那一台在世界的哪一格」。兩條路，都不含無標記的圖片比對：

- **constellation**：把整個窗掛回世界。幀內**點擊確認過有單位**的格（點下去出卡或進行動
  模式＝存在，卡面內容一律不讀）與已解單位的世界格做平移配對，唯一解才採信；窗位一鎖住，
  目標的幀格就落出世界座標。目標的幀格讀的是遊戲自己畫的範圍：敵方＝攻擊範圍紅菱形中心、
  我方＝移動範圍菱形中心（跳轉直接進單位移動模式）。
- **march**：自力。在目標旁種標記，往西推到 FrameGrid 讀到西界，逐把靠標記重認累計
  格數；往北同理（先跳回同一台重置鏡頭）。

`board.find_unit_screen_hints` 的峰只拿來**避開單位**（挑乾淨格種標記／挑空白格解除），
不進任何座標計算，也不拿來主動探測身分——身分只來自種標偶然點到單位時的摘要反查。

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
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from ggge_ai.battle import vision
from ggge_ai.battle.map_grid import FrameGrid, GridUnreadable, read_frame_grid, snap_cell
from ggge_ai.runtime import board, entry, jumpscan, marchkit, roster, screens, sweep
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

# 路徑 A：最多點幾格確認「有單位」——確認 ≥2 格才配得起來，點太多只是浪費。
CONFIRM_PROBES = 4
# 落地鄰居反查：最多問幾格。一趟一兩次點擊就要換掉整段推鏡，問太多就不划算了。
NEIGHBOR_PROBES = 2
# 路徑 B：一軸最多推幾把（一把約一格半，地圖再大也用不到這麼多）。
MARCH_LEGS = 40
MARCH_SEED_ATTEMPTS = 3
# 標記連兩把認不回來就放棄該軸——重種一次是自癒，兩次是這一帶認不出填色。
MARCH_LOST_LIMIT = 2

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
# adb exec-out screencap 偶發逾時（0805 一例、0806 run 20260806-121910 一例），通道旋即
# 恢復——實測 2.5 秒就通了。截圖是唯讀且冪等的，重試一次不會多按到任何東西。
CAPTURE_RETRY_WAIT_S = 2.0

# 巡迴順序預設敵方優先：敵 18 台是驗收大頭，先把它們的世界格解出來，後面的窗才有足夠的
# 參考集可以做平移配對。
TOUR_ORDERS: dict[str, tuple[str, ...]] = {
    roster.ENEMY: (roster.ENEMY, roster.ALLY),
    roster.ALLY: (roster.ALLY, roster.ENEMY),
}

# 地圖點擊前的狀態閘：不是 battle_map 就先 escape 收乾淨，最多三輪。
MAP_TAP_ATTEMPTS = 3

MARCH_AXES: tuple[tuple[int, str], ...] = ((0, "west"), (1, "north"))
# 前緣種標的排序：往西推內容往東走，所以種在螢幕最西邊的格撐最久。
FRONTIER_SORT: dict[str, tuple[int, int]] = {"west": (0, 1), "north": (1, 1)}


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


def same_view(a: FrameGrid, b: FrameGrid) -> bool:
    """兩張格網的格號對不對得起來——只問**原點相位**，不要求兩邊裁出一樣多條線。

    比較的目的只是「鏡頭沒被拉走」，格號一律以先讀到的那張為準（擬合是在那張上做的）。
    逐線全等太嚴：0806 run 20260806-121910 三次 range_fit 成功全被作廢，實際上只是格線
    偵測在邊緣多裁／少裁一條。相位差半格以內就是同一個鏡位。
    """
    pitch_a, pitch_b = grid_pitch(a), grid_pitch(b)
    return (
        abs(a.cols[0] - b.cols[0]) < 0.5 * min(pitch_a[0], pitch_b[0])
        and abs(a.rows[0] - b.rows[0]) < 0.5 * min(pitch_a[1], pitch_b[1])
    )


def bounded(grid: FrameGrid, side: str) -> bool:
    return bool(grid.bounds()[side])


def at_border(view: "View", side: str) -> tuple[bool, dict[str, bool]]:
    """這一幀有沒有真的推到 `side` 的界，以及兩個訊號各說了什麼。

    北界不能只信 `FrameGrid.north_bound`：頂帶 HUD 蓋掉格線時，HUD 下緣的脊會被當成
    北界（0806 run 20260806-173300 的 enemy#3 就是假北界＋travel=0 互鎖出一個看起來很
    自洽的錯答案）。北界改以 `sweep.read_borders`（舊 sweep 十二輪驗證過的終止邊特徵）
    為權威，格網的 `north_bound` 只當佐證記帳。其餘三側維持格網判定。
    """
    grid_says = bounded(view.grid, side)
    if side != "north":
        return (grid_says, {"grid": grid_says})
    edge_says = "north" in sweep.read_borders(view.frame)
    return (edge_says, {"grid": grid_says, "edge": edge_says})


def card_present(frame: np.ndarray) -> bool:
    """卡開了沒——只問「有沒有這張卡」，**不讀卡面內容**。

    卡面的 `name_sig` 完全退出定位：同型量產機的卡面不可分，拿它認身分等於在毒帳上簽名
    （0806 使用者裁決）。這裡要的只是「這一格有東西」這個 bit。
    """
    return vision.read_enemy_summary(frame) is not None


class Halt(RuntimeError):
    """停在原地：印出原因與當下截圖，不再點任何東西。"""


@dataclass
class Camera:
    """唯一幀源：段界與失敗點存的就是當下判定用的那一張。"""

    device: LiveDevice
    journal: Journal
    sleep: Callable[[float], None] = time.sleep
    raw: bytes | None = field(default=None, init=False)
    shots: int = field(default=0, init=False)

    def screenshot(self) -> bytes:
        """截圖並重試一次：通道暫態逾時不該滅團。

        重試只給 `TimeoutExpired`——那是「這一下沒回來」，不是「裝置不見了」；掉線是
        RuntimeError，照樣往上拋。截圖唯讀且冪等，重試不會多按到任何東西。
        """
        try:
            self.raw = self.device.screenshot()
        except subprocess.TimeoutExpired:
            self.journal.record("capture_retry", wait=CAPTURE_RETRY_WAIT_S)
            self.sleep(CAPTURE_RETRY_WAIT_S)
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


@dataclass(frozen=True)
class AxisResult:
    """一軸推鏡的結果：推到界拿到的該軸世界格，或順路結帳直接拿到的整格。"""

    world: int | None = None
    met: Cell | None = None


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
    # 推鏡與種標記的執行者：機制全在 runtime.marchkit（搬自 sweep_scan），這支只留
    # 「里程帳＋出帳守門」那層業務邏輯。
    marcher: marchkit.Marcher = None  # type: ignore[assignment]
    # march 種下的選取填色：色簽與它現在在哪一格。
    signature: board.MarkerSignature | None = None
    marker: Cell | None = None
    # 本輪所有「非預期進入地圖子模式」事件，供驗收判準的零誤觸機器檢查。
    mistaps: list[dict] = field(default_factory=list)
    # 種標記那一下偶然點到單位：（幀格, 摘要窗讀到的數值），由 march_axis 取走反查。
    encounter: tuple[Cell, tuple[int | None, ...]] | None = None
    # 最後一把推鏡真正送出的行程（像素）。不進帳，只當每一把標記位移的合理性對照。
    stroke: float = 0.0

    # ---------- 流程 ----------

    def __post_init__(self) -> None:
        if self.marcher is None:
            self.marcher = marchkit.Marcher(
                device=self.device, camera=self.camera, journal=self.journal, sleep=self.sleep
            )

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
            self.visit(key)
            if self.ledger.resolved(key):
                continue
            # 失敗即棄：把面板收乾淨再換下一台，不在原地重試。
            self.close_panels()
            count = self.ledger.fail(key)
            self.journal.record("jump_failed", key=list(key), failures=count)
            if count >= JUMP_ATTEMPTS:
                self.ledger.retire(key)
        if not self.ledger.cells:
            raise Halt("整份名冊都跳過了仍然一台都定位不了，帳面沒有任何絕對座標")

    def visit(self, key: jumpscan.Key) -> bool:
        """一台的一趟，固定節奏、失敗即棄：跳轉 → 定格 → march（順路結帳）→ 收尾。

        中間不做 escape 重試迴圈（0806 run 20260806-141615 就是在原地空轉燒掉一整輪）：
        任何一步不成就交回 `tour()`，那裡會把面板收乾淨換下一台。星座配對（`constellation`）
        0806 使用者裁決下架，不再擋在 march 前面。
        """
        view, target = self.land(key, label="jump")
        if view is None or target is None:
            return False
        cell = self.neighbor(key, view, target)
        if cell is not None:
            self.ledger.anchor(key, cell, jumpscan.SOURCE_NEIGHBOR)
            self.journal.record("neighbor_anchor", key=list(key), cell=list(cell))
            return True
        return self.march(key, view, target)

    def neighbor(self, key: jumpscan.Key, view: View, target: Cell) -> Cell | None:
        """落地就先問鄰居：離目標最近的一兩格點下去讀摘要，反查名冊唯一且已解就出帳。

        這條路一趟只花一兩次點擊，省掉整段推鏡（0806 run 20260806-173300 每台 march
        要 5-9 把推鏡）。與「不用 hint 猜位置」不衝突：hint 只決定**去哪問**，身分由點下去
        讀到的數值回答，位置由**同幀格差**算——三件事各有各的證據。
        """
        if not self.ledger.cells:
            return None
        hints = {snap_cell(view.grid, peak) for peak in board.find_unit_screen_hints(view.frame)}
        window = (0, 0, len(view.grid.cols) - 2, len(view.grid.rows) - 2)
        cells = jumpscan.probe_cells(
            (cell for cell in hints if cell is not None),
            target,
            window=window,
            limit=NEIGHBOR_PROBES,
        )
        for cell in cells:
            values = self.probe_identity(view, cell)
            match = jumpscan.roster_lookup(
                values or (), self.roster_table(), self.ledger.cells
            )
            self.journal.record(
                "neighbor_probe",
                key=list(key),
                cell=list(cell),
                values=None if values is None else list(values),
                reason=match.reason,
                via=None if match.key is None else list(match.key),
            )
            anchor = None if match.reason != jumpscan.MEET_UNIQUE else self.ledger.cells[match.key]
            if anchor is not None:
                return jumpscan.meet_cell(anchor, cell, target)
        return None

    def probe_identity(self, view: View, cell: Cell) -> tuple[int | None, ...] | None:
        """點一格問身分：讀摘要（敵在左上、我在右上，塢位由畫面狀態分派）再收拾乾淨。

        收拾照既有路徑：出卡就點一個空白格收掉，進了行動模式就按返回鈕——那顆鈕在行動
        模式下才真的存在（0806 run 20260806-141615 的盲點教訓）。
        """
        point = view.centres.get(cell)
        if point is None or not self.ready_for_map_tap():
            return None
        self.device.tap(int(point[0]), int(point[1]))
        self.sleep(TAP_SETTLE_S)
        after = self.camera.grab()
        seen = screens.classify(after)
        self.note_encounter(cell, after, seen)
        met = self.encounter
        self.encounter = None
        if seen in screens.MAP_SUBSTATES:
            self.leave_action_mode()
        elif card_present(after):
            self.clear_card(view)
        return None if met is None else met[1]

    def land(
        self, key: jumpscan.Key, *, label: str
    ) -> tuple[View | None, Cell | None]:
        """跳轉 → 落點幀（帶指定標示）→ 解除 → 乾淨幀。回傳乾淨鏡位與目標格。

        目標格讀的是**遊戲自己畫在落點幀上的範圍**：敵方的攻擊範圍紅菱形、我方的移動
        範圍菱形。解除不移動鏡頭，所以乾淨幀與落點幀共用同一張格網。
        """
        faction, index = key
        self.open_troop_info(faction)
        if self.open_detail(roster.cell_taps(faction)[index]) is None:
            raise Halt(f"{faction}#{index} 點不開詳情頁——名冊順序與跳轉對不上")
        self.device.tap(*roster.DETAIL_SELECT_TAP, intent=ROSTER_JUMP_INTENT)
        if not self.await_map():
            # 詳情頁沒收＝「選擇」那一下沒生效（0806 run 20260806-103335 的 ally#4
            # 第二趟：該台的詳情頁只有一顆置中的「關閉」，(1372,995) 點在空處）。
            self.journal.record("jump_not_taken", key=list(key))
            self.close_panels()
            return (None, None)
        # 跳轉不是瞬間到位：固定 1.5 秒的落點幀常常還是**跳轉前**的鏡位（同一輪 run 的
        # ally#0 落點幀與乾淨幀根本不是同一個鏡頭），兩幀不同鏡位時指定標示的比對整個
        # 沒有意義。改成等畫面自己停下來。
        landing = self.steady()
        self.camera.keep(f"{label}:{faction}:{index}:landing")
        if faction == roster.ALLY:
            return self.land_ally(key, landing, label)
        marked = self.view(landing)
        if marked is None:
            marked = self.look()
            self.journal.record("land_reread", key=list(key), ok=marked is not None)
        if marked is None:
            self.journal.record("land_failed", key=list(key), reason="grid_unreadable")
            return (None, None)
        # 紅範圍只在解除**之前**的那一幀上，所以目標格在這裡就要讀完。
        target = self.attack_cell(key, marked)
        self.dismiss(faction, marked)
        clean = self.camera.settled(JUMP_SETTLE_S, self.sleep)
        self.camera.keep(f"{label}:{faction}:{index}:clean")
        view = self.view(clean)
        if view is None:
            # 解除只是把紅範圍收掉，鏡頭沒動：沿用落點幀的格網，不作廢已經讀到的格。
            self.journal.record("grid_reused", key=list(key), where="enemy_clean")
            view = View(clean, marked.grid, marked.centres)
        elif not same_view(marked.grid, view.grid):
            self.journal.record("land_grid_shifted", key=list(key))
            return (view, None)
        self.journal.record(
            "landed",
            key=list(key),
            target=None if target is None else list(target),
            bounds=view.grid.bounds(),
        )
        if target is None:
            return (view, None)
        return (view, target)

    def land_ally(
        self, key: jumpscan.Key, landing: np.ndarray, label: str
    ) -> tuple[View | None, Cell | None]:
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
            return (None, None)
        moving = self.view(landing)
        target = None if moving is None else self.range_cell(key, moving)
        self.device.tap(*jumpscan.ALLY_DISMISS_TAP, intent=jumpscan.ALLY_DISMISS_INTENT)
        self.sleep(TAP_SETTLE_S)
        if not self.await_map():
            self.journal.record("ally_stuck_in_move", key=list(key))
            self.close_panels()
            return (None, None)
        clean = self.steady()
        self.camera.keep(f"{label}:{faction}:{index}:clean")
        if moving is None:
            self.journal.record("land_failed", key=list(key), reason="grid_unreadable")
            return (None, None)
        view = self.view(clean)
        if view is None:
            # 乾淨幀讀不出格網（我方那一叢圖示很密，seed spacing implausible 高發），
            # 但鏡頭沒動——沿用移動模式幀的格網，別把已經擬合好的格丟掉。
            self.journal.record("grid_reused", key=list(key), where="ally_clean")
            return (View(clean, moving.grid, moving.centres), target)
        if not same_view(moving.grid, view.grid):
            # 退出移動模式之後相位對不上＝鏡頭動過，菱形算出來的格號不能跨鏡位用。
            self.journal.record("ally_grid_shifted", key=list(key))
            return (view, None)
        self.journal.record(
            "landed",
            key=list(key),
            target=None if target is None else list(target),
            bounds=view.grid.bounds(),
        )
        return (view, target)

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

    def ready_for_map_tap(self) -> bool:
        """地圖上要點下去之前的硬閘：畫面是 `battle_map`，而且卡條是收合的。

        兩件事都要問。狀態：0806 run 20260806-130539 的 ally#2 在移動模式殘留下繼續點，
        下一下開了武裝選單（誤攻擊前哨）。卡條：0806 run 20260806-141615 卡條被展開之後
        `classify` 照樣回 `battle_map`，但地圖下緣被蓋住、格網從此讀不出來——「畫面對」
        不等於「盤面可用」。

        不在這裡做 escape 重試迴圈（那是上一輪空轉的來源）：問一次，不對就交給呼叫端
        收尾換下一台。
        """
        if screens.classify(self.camera.grab()) != screens.BATTLE_MAP:
            self.journal.record("map_tap_blocked", reason="not_map")
            return False
        strip = screens.read_roster_strip(self.camera.grab())
        if strip == screens.ROSTER_COLLAPSED:
            return True
        self.journal.record("map_tap_blocked", reason="strip", strip=strip)
        if strip is None:
            return False
        # 卡條讀得出來是展開的：這是先讀再點，不是盲點。
        self.device.tap(*screens.ROSTER_TOGGLE_TAP)
        self.sleep(ROSTER_SETTLE_S)
        return screens.read_roster_strip(self.camera.grab()) == screens.ROSTER_COLLAPSED

    def note_state(self, seen: str, *, expect: str | None, where: str) -> str:
        """點完之後畫面在哪：進了非預期的地圖子模式就是誤觸，記進 run 級帳。

        「零誤觸」要機器查得到，不能靠人翻幀（0806 run 20260806-103335 誤下了一次移動
        指令，事後只能從詳情頁少一顆鈕反推）。
        """
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

    def attack_cell(self, key: jumpscan.Key, marked: View) -> Cell | None:
        """敵方的目標格：攻擊範圍紅菱形的中心（最小包覆半徑，唯一才收）。"""
        cells = jumpscan.attack_cells(
            marked.frame, marked.centres, half=min(marked.pitch) / 3.0
        )
        found = jumpscan.attack_centre(
            cells,
            window=(0, 0, len(marked.grid.cols) - 2, len(marked.grid.rows) - 2),
            prefer=snap_cell(marked.grid, jumpscan.SCREEN_CENTRE),
        )
        self.journal.record(
            "attack_fit",
            key=list(key),
            cells=len(cells),
            cell=None if found is None else list(found),
        )
        return found

    def view(self, frame: np.ndarray) -> View | None:
        grid = frame_grid(frame)
        return None if grid is None else View(frame, grid, grid_centres(grid))

    # ---------- 路徑 A：星座鎖窗 ----------

    def constellation(self, key: jumpscan.Key, view: View, target: Cell) -> Cell | None:
        """把整個窗掛回世界：幀內**點擊確認有單位**的格 × 已解單位的世界格，平移唯一配對。

        身分靠位置認，不靠圖案認——點擊只取「這一格有東西」這個 bit，卡面內容一律不讀
        （同型量產機的卡面不可分，認錯一台就是毒帳）。窗位一鎖住，目標的幀格自然落出
        世界座標。
        """
        references = self.ledger.references()
        if len(references) < jumpscan.CONSTELLATION_MIN_MATCH:
            return None
        peaks = board.find_unit_screen_hints(view.frame)
        occupied: list[Cell] = []
        for peak in jumpscan.probe_order(peaks, view.centres[target], limit=CONFIRM_PROBES):
            cell = snap_cell(view.grid, peak)
            point = None if cell is None else view.centres.get(cell)
            if cell is None or cell == target or point is None or cell in occupied:
                continue
            if not self.confirm_occupied(view, point):
                continue
            occupied.append(cell)
        fix = jumpscan.window_offset(references, occupied)
        self.journal.record(
            "window_fix",
            key=list(key),
            occupied=[list(cell) for cell in occupied],
            matched=fix.matched,
            reason=fix.reason,
            delta=None if fix.delta is None else list(fix.delta),
        )
        if fix.delta is None:
            return None
        return (target[0] + fix.delta[0], target[1] + fix.delta[1])

    def confirm_occupied(self, view: View, point: Point) -> bool:
        """點一格問「這裡有沒有單位」：出卡或進行動模式都算有，讀完立刻收掉。

        只取存在這個 bit。點擊座標本身就是格子的證明——點 (x,y) 落在格 c、有反應，
        記的就是格 c 有東西。
        """
        if not self.ready_for_map_tap():
            return False
        before = self.camera.grab()
        self.device.tap(int(point[0]), int(point[1]))
        self.sleep(TAP_SETTLE_S)
        after = self.camera.grab()
        seen = screens.classify(after)
        if seen in screens.MAP_SUBSTATES:
            # 點到我方＝進了行動模式：返回鈕在這個模式下才是真的存在，按它退出。
            self.note_state(seen, expect=screens.BATTLE_UNIT_MOVE, where="confirm_occupied")
            self.leave_action_mode()
            return True
        if card_present(after):
            self.clear_card(view)
            return True
        outcome = sweep.classify_tap(
            before, after, point, card=card_present, pitch=view.pitch
        )
        if outcome.verdict == sweep.TAP_EMPTY:
            # 填色出現在被點的那一格＝那是空格，這一格不算證人。
            return False
        self.note_state(screens.classify(after), expect=None, where="confirm_occupied")
        return False

    def clear_card(self, view: View) -> None:
        """卡是疊在地圖上的浮層，點一個乾淨的空白格就收掉，鏡頭不動。"""
        blank = self.blank_point(view, board.find_unit_screen_hints(view.frame))
        if blank is None:
            self.journal.record("card_stuck")
            return
        self.device.tap(*blank)
        self.sleep(TAP_SETTLE_S)

    # ---------- 路徑 B：標記接力平移 ----------

    def march(self, key: jumpscan.Key, view: View, target: Cell) -> bool:
        """兩軸各推到界：西界定 x、北界定 y。兩軸之間跳回同一台重置鏡頭（O(1)）。

        推的途中撞見已解單位就地結帳（`march_meet`）：那一路兩軸同時入帳，界只是兜底。
        """
        fresh = True
        for axis, direction in MARCH_AXES:
            if self.ledger.axis_of(key, axis) is not None:
                # 這一軸上一趟就量到了：軸級帳是持久的，回訪只補缺的那一軸。
                self.journal.record("axis_reused", key=list(key), axis=jumpscan.AXIS_NAMES[axis])
                continue
            if not fresh:
                view, target = self.land(key, label="march")
                if view is None or target is None:
                    self.journal.record("march_failed", key=list(key), axis=axis, reason="reland")
                    return self.ledger.resolved(key)
            result = self.march_axis(key, view, target, axis, direction)
            fresh = False
            if result.met is not None:
                self.ledger.anchor(key, result.met, jumpscan.SOURCE_MARCH_MEET)
                self.journal.record("march_meet_anchor", key=list(key), cell=list(result.met))
                return True
            if result.world is None:
                return self.ledger.resolved(key)
            self.book_axis(key, axis, result.world)
        if self.ledger.resolved(key):
            self.journal.record("march", key=list(key), cell=list(self.ledger.cells[key]))
            return True
        return False

    def book_axis(self, key: jumpscan.Key, axis: int, world: int) -> None:
        """一軸量到就立刻入帳。同台同軸兩次量測不一致記矛盾、**不覆寫**。"""
        verdict = self.ledger.record_axis(key, axis, world, jumpscan.SOURCE_MARCH)
        name = jumpscan.AXIS_NAMES[axis]
        if verdict == jumpscan.AXIS_CONFLICT:
            self.journal.record(
                "axis_conflict",
                key=list(key),
                axis=name,
                booked=self.ledger.axis_of(key, axis),
                measured=world,
            )
            return
        self.journal.record("axis_booked", key=list(key), axis=name, world=world, verdict=verdict)

    def march_axis(
        self, key: jumpscan.Key, view: View, target: Cell, axis: int, direction: str
    ) -> AxisResult:
        """往 direction 推到界，逐把靠標記重認算累計格數，回傳目標在該軸的世界格。

        每一把都在**推進方向的前緣**重種標記（往西推就種在畫面西側），不是等它快被推出
        視野才補——這是 sweep_scan `carry_marker` 用了十二輪的紀律：不要求一顆標記活過
        好幾把推鏡。0806 run 20260806-130539 的 65 筆 march_lost 有 48 筆倒在第 2 把、
        16 筆倒在第 1 把，正是「一顆標記撐到底」撐不住的形狀。

        重種發生在同一幀內（鏡位沒變），所以計格帳不受影響：下一把的 `before` 用新標記
        在**這一幀**的格就好。

        種標記的點擊偶然落在單位上時順勢認人（`Scan.meet`）：反查得出唯一且已解的那台，
        幀內格差就是世界格差，兩軸同時收工，不必推到界。這不多點任何一下。
        """
        name = jumpscan.AXIS_NAMES[axis]
        seeded = self.seed_marker(view, avoid=target, toward=direction)
        if seeded is None:
            self.journal.record("march_lost", key=list(key), axis=name, reason="no_seed")
            return AxisResult()
        signature, marker, spot = seeded
        odometer: jumpscan.MarkerOdometer | None = jumpscan.MarkerOdometer.seeded(marker, target)
        met = self.meet(key, target, name, 0)
        if met is not None:
            return AxisResult(met=met)
        legs: list[jumpscan.MarchLeg] = []
        pans = 0
        suspect = 0
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
                odometer = None
            view = current
            hit, signals = at_border(view, direction)
            if hit:
                audit = jumpscan.audit_march(legs, pans, suspect=suspect)
                world = jumpscan.march_world(target[axis], legs, border_cell=0)
                self.journal.record(
                    "march_axis",
                    key=list(key),
                    axis=name,
                    legs=len(legs),
                    world=world if audit.ok else None,
                    travel=audit.travel,
                    pans=audit.pans,
                    suspect=suspect,
                    reason=audit.reason,
                    border=signals,
                )
                if not audit.ok:
                    # 見界但帳不自洽（假界／缺一把的位移／存疑的腿）：寧可 unresolved。
                    self.journal.record("march_inconsistent", key=list(key), axis=name,
                                        reason=audit.reason)
                    return AxisResult()
                return AxisResult(world=world)
            carried = self.carry_marker(view, signature, direction)
            if odometer is not None:
                # 重種那一輪點到的單位要用**這一幀**的目標格結帳，而且要在里程計被新標記
                # 更新之前算——同一幀內兩者等價，但混用就是錯一個重種位移。
                met = self.meet(key, odometer.target_frame(marker), name, len(legs))
                if met is not None:
                    return AxisResult(met=met)
            if carried is None:
                lost += 1
                self.journal.record(
                    "march_lost", key=list(key), axis=name, legs=len(legs), reason="no_carry"
                )
                if lost >= MARCH_LOST_LIMIT:
                    break
                continue
            signature, fresh_marker, spot, fresh = carried
            if fresh and odometer is not None:
                odometer = odometer.reseeded(marker, fresh_marker)
            marker = fresh_marker
            before = marker[axis]
            pitch = view.pitch[axis]
            stride = self.marcher.stride(spot, direction, pitch, board.PAN_MAX_REACH)
            result = self.marcher.pan(direction, view.frame, reach=stride)
            pans += 1
            if result.verdict in (marchkit.PAN_BORDER, sweep.PAN_PINNED):
                # 推不動不等於有界線：界由呼叫端自己的證據說了算（`at_border`），這裡
                # 只是這一把沒走——沒有位移就沒有這一腿，帳不記。
                pans -= 1
                current = self.reread(key, name, result.frame)
                if current is None:
                    break
                view = current
                continue
            if result.verdict != sweep.PAN_LANDED:
                self.journal.record("pan_eaten", key=list(key), axis=name)
                break
            self.stroke = result.stroke
            current = self.reread(key, name, result.frame)
            if current is None:
                lost += 1
                # 鏡頭動了而這一把沒有標記帳：里程計失去接力點，順路結帳停用（推到界的
                # 那條路本來就只認界，見 march_world）。
                odometer = None
                if lost >= MARCH_LOST_LIMIT:
                    break
                continue
            view = current
            spot = self.marcher.marker_point(view.frame)
            cell = None if spot is None else snap_cell(view.grid, spot)
            if cell is None:
                lost += 1
                odometer = None
                self.journal.record("march_lost", key=list(key), axis=name, legs=len(legs))
                if lost >= MARCH_LOST_LIMIT:
                    break
                continue
            if jumpscan.leg_suspect(cell[axis] - before, self.stroke, pitch):
                # 名義行程與標記位移對不上：先當成 snap 抖了一格，重拍重認一次。
                again = self.look()
                spot = None if again is None else self.marcher.marker_point(again.frame)
                recell = None if spot is None or again is None else snap_cell(again.grid, spot)
                if recell is not None:
                    view, current, cell = again, again, recell
                if recell is None or jumpscan.leg_suspect(
                    cell[axis] - before, self.stroke, pitch
                ):
                    suspect += 1
                    self.journal.record(
                        "leg_suspect",
                        key=list(key),
                        axis=name,
                        legs=len(legs),
                        moved=cell[axis] - before,
                        stroke=round(self.stroke, 1),
                        pitch=round(pitch, 1),
                    )
            lost = 0
            legs.append(jumpscan.MarchLeg(before, cell[axis]))
            marker = cell
        self.journal.record("march_failed", key=list(key), axis=name, legs=len(legs))
        return AxisResult()

    def reread(self, key: jumpscan.Key, axis: str, frame: np.ndarray) -> View | None:
        """驗收幀讀不出格網就重拍重讀一次。**沒有「沿用推鏡前那張」這個選項**——鏡頭已經
        動了，舊視圖的格號全部作廢（0806 第九輪的 CRASH 就是拿 None.grid 炸的）。"""
        view = self.view(frame)
        if view is not None:
            return view
        view = self.look()
        self.journal.record("march_reread", key=list(key), axis=axis, ok=view is not None)
        return view

    def meet(self, key: jumpscan.Key, target_frame: Cell, axis: str, legs: int) -> Cell | None:
        """順路結帳：種標記時**偶然點到單位**的那一下，順勢認人。

        零額外點擊——march 本來就一路在點格種標記，這裡只是把「點到單位」這條原本的失敗
        路徑翻轉成免費的辨識機會：讀簡化資訊窗的 HP／EN 去名冊反查，唯一且已解就用幀內
        格差兩軸同時出帳。撞名（同型雜魚整批同數值）或反查到的那台還沒解，就什麼都不做，
        照舊換一格種標繼續推。
        """
        met = self.encounter
        self.encounter = None
        if met is None or not self.ledger.cells:
            return None
        cell, values = met
        match = jumpscan.roster_lookup(values, self.roster_table(), self.ledger.cells)
        anchor = None if match.key is None else self.ledger.cells.get(match.key)
        world = None if anchor is None else jumpscan.meet_cell(anchor, cell, target_frame)
        self.journal.record(
            "march_meet",
            key=list(key),
            axis=axis,
            legs=legs,
            met=list(cell),
            values=list(values),
            reason=match.reason,
            via=None if match.key is None else list(match.key),
            cell=None if world is None else list(world),
        )
        return world

    def roster_table(self) -> dict[jumpscan.Key, tuple[int | None, ...]]:
        """名冊的反查表。摘要窗只有 HP／EN 兩個數字可讀（0806 實幀 run 20260806-130539
        的 frames/00109 敵方卡、assets/screenshots/20260806-013500.png 我方卡：一邊是機體名
        ＋HP＋EN，另一邊是駕駛員與 MP，沒有移動力也沒有 LV），所以反查鍵只能是這兩欄。"""
        return {(unit.faction, unit.index): (unit.hp, unit.en) for unit in self.entries}

    def carry_marker(
        self, view: View, signature: board.MarkerSignature, direction: str
    ) -> tuple[board.MarkerSignature, Cell, Point, bool] | None:
        """推之前把標記搬到前緣。搬不動就沿用舊的——但舊的必須在這一幀上找得到。

        「找得到」是硬條件：記著的格看不到填色，代表那顆標記已經沒了，再拿它當證人會讓
        下一次重認拿舊填色配新格號（sweep_scan 的 `drop_stale_marker` 同一條）。

        末項 `fresh` 說的是「這是不是新種的一顆」：新的一顆才要把兩顆的幀格差記進里程計，
        沿用舊的那一顆是同一個實體，世界格差不變。
        """
        seeded = self.seed_marker(view, signature=signature, toward=direction)
        if seeded is not None:
            return (*seeded, True)
        found = self.marcher.marker_point(view.frame)
        cell = None if found is None else snap_cell(view.grid, found)
        if cell is None:
            return None
        return (signature, cell, found, False)

    def seed_marker(
        self,
        view: View,
        *,
        avoid: Cell | None = None,
        signature: board.MarkerSignature | None = None,
        toward: str | None = None,
    ) -> tuple[board.MarkerSignature, Cell, Point] | None:
        """在一個乾淨空白格種標記：點下去、驗收填色真的出現在被點的那一格才算數。

        沒驗收就記 `marker` 會讓下一把重認拿舊填色配新格號，整幀寫進差一格距整數倍的
        世界位置——這條紀律照抄 sweep_scan 的 `carry_marker`。
        """
        if not self.ready_for_map_tap():
            return None
        peaks = board.find_unit_screen_hints(view.frame)
        points = jumpscan.clean_points(
            view.frame,
            view.centres.values(),
            peaks,
            keep_out=jumpscan.PEAK_KEEP_OUT_PITCH * max(view.pitch),
            red_half=min(view.pitch) / 3.0,
            # 填色的 learn／find 只看 MAP_REGION，區外種下去的標記哪一幀都找不到。
            inside=board.MAP_REGION,
            # 界外的格點下去是虛空，而前緣排序專挑最外側的格——0806 run 20260806-210825
            # 的 enemy#0 就是這樣在 col 0 連環 none 到整台退場。
            borders=sweep.read_borders(view.frame),
        )
        if toward is None:
            points.sort(
                key=lambda point: float(
                    np.hypot(
                        point[0] - jumpscan.SCREEN_CENTRE[0],
                        point[1] - jumpscan.SCREEN_CENTRE[1],
                    )
                )
            )
        else:
            axis, sign = FRONTIER_SORT[toward]
            points.sort(key=lambda point: sign * point[axis])
        for point in points[:MARCH_SEED_ATTEMPTS]:
            cell = snap_cell(view.grid, point)
            if cell is None or cell == avoid:
                continue
            placed = self.marcher.place_marker(
                point,
                self.camera.grab(),
                pitch=view.pitch,
                card=card_present,
                signature=signature,
                settle=TAP_SETTLE_S,
            )
            after = self.camera.grab()
            self.journal.record("seed_marker", cell=list(cell), verdict=placed.verdict)
            if not placed.ok:
                seen = screens.classify(after)
                self.note_encounter(cell, after, seen)
                self.note_state(seen, expect=None, where="seed_marker")
                # 說不出結果的那一下可能已經把畫面帶進選擇／移動態，而移動態下的下一次
                # 格點擊就是真的下移動指令（0806 run 20260806-103335 的 ally#4：連四下
                # verdict=none，之後那台的詳情頁只剩「關閉」＝它已經行動過了）。
                # 已經在地圖上就不必逃：0806 run 20260806-173300 的 192 筆 escape_map
                # 清一色 was=battle_map，每筆燒掉 4.8 秒卻什麼都沒做。
                if seen != screens.BATTLE_MAP:
                    self.leave_action_mode()
                continue
            self.signature = placed.signature
            self.marker = cell

            return (placed.signature, cell, placed.point or point)
        return None

    def note_encounter(self, cell: Cell, frame: np.ndarray, seen: str) -> None:
        """種標記那一下點到單位了：把簡化資訊窗的數值記下來給 `meet()` 反查。

        這是免費的——那一下本來就要點，本來也只會被記成一筆失敗。兩個陣營都有卡，只是
        塢位不同：敵方在左，我方（點下去進單位移動模式）在右，同一張版面平移 818px
        （實幀 assets/screenshots/20260806-013500.png：右塢錨 0.980、讀出 38311/148）。

        **哪一塢由畫面狀態決定，不是兩邊都試**：battle-prep／選擇武裝的右面板長得一樣，
        在那些畫面上讀到的是攻擊目標的數值，記進來就是毒帳。
        """
        if seen == screens.BATTLE_UNIT_MOVE:
            summary = vision.read_ally_summary(frame)
        elif seen in screens.MAP_SUBSTATES:
            return
        else:
            summary = vision.read_enemy_summary(frame)
        if summary is None:
            return
        self.encounter = (cell, (summary.hp, summary.en))
        self.journal.record(
            "met_unit", cell=list(cell), values=[summary.hp, summary.en], dock=seen
        )

    def leave_action_mode(self) -> bool:
        """把畫面帶回地圖 hub。**不盲點**：返回鈕只有在行動模式下才存在。

        0806 run 20260806-141615 的教訓：(1798,971) 在純地圖上是「單位列表」鈕
        （它就落在 `jumpscan.UI_EXCLUSION_ZONES` 的那個矩形裡），盲點下去把卡條展開，
        之後每一張幀的 `read_frame_grid` 都讀不出格網——整輪 38 個 attack_fit 掉到 1。
        """
        seen = screens.classify(self.camera.grab())
        if seen in screens.MAP_SUBSTATES:
            self.device.tap(*jumpscan.ALLY_DISMISS_TAP, intent=jumpscan.ALLY_DISMISS_INTENT)
            self.sleep(TAP_SETTLE_S)
        elif seen in PANEL_CLOSERS:
            self.close_panels()
        elif seen != screens.BATTLE_MAP:
            self.journal.record("escape_unknown", seen=seen)
            return False
        ok = screens.classify(self.camera.grab()) == screens.BATTLE_MAP
        self.journal.record("escape_map", was=seen, on_map=ok)
        return ok

    def look(self) -> View | None:
        """重拍重讀一張視圖。讀不出格網就是 None——沒有「沿用上一張」這個選項。"""
        return self.view(self.camera.settled(board.PAN_SETTLE_S, self.sleep))

    # ---------- 解除 ----------

    def dismiss(self, faction: str, view: View) -> None:
        """敵方的解除：點一個空白格。我方走 `land_ally`，這裡不該收到我方。"""
        if not self.ready_for_map_tap():
            self.journal.record("dismiss_blocked", faction=faction)
            return
        blank = self.blank_point(view, board.find_unit_screen_hints(view.frame))
        if blank is None:
            self.journal.record("no_blank_cell", faction=faction)
            raise Halt("落點幀找不到任何空白格可以解除敵方指定")
        self.device.tap(*blank)

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
        units = jumpscan.ledger_report(self.ledger, self.keys())
        sources: dict[str, int] = {}
        for source in self.ledger.sources.values():
            sources[source] = sources.get(source, 0) + 1
        partial = sum(
            1 for unit in units if unit["cell"] is None and unit["axes"]
        )
        self.journal.record(
            "settle",
            partial=partial,
            axis_conflicts=len(self.ledger.axis_conflicts),
            clean_run=not self.mistaps,
            mistaps=len(self.mistaps),
            resolved=len(self.ledger.cells),
            sources=sources,
        )
        self.write_json(
            "coords.json",
            {
                # 驗收判準「零誤觸」的機器可讀答案：本輪有沒有任何一下把畫面帶進
                # 非預期的地圖子模式（移動／武裝選擇／技能）。
                "clean_run": not self.mistaps,
                "mistaps": self.mistaps,
                "sources": sources,
                # 單軸帳照實出：只解出 x 的那台，下一輪回訪只要補 y。
                "partial": partial,
                "axis_conflicts": [
                    {"key": list(key), "axis": jumpscan.AXIS_NAMES[axis],
                     "booked": booked, "measured": measured}
                    for key, axis, booked, measured in self.ledger.axis_conflicts
                ],
                "units": units,
            },
        )
        log.info(
            "%d/%d resolved %s", len(self.ledger.cells), len(self.keys()), sources
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
