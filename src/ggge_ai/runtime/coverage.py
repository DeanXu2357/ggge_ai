"""世界空間的四態知識圖：逐格認知狀態、邊界旗、缺口導向補掃與五層量測防禦。

取代方向腿數制的覆蓋簿記（0730 使用者定案，docs/survey-coverage-v2.md）。立場是
**掃描成功不依賴縮小**——縮小只減少截圖次數，掃得完與否由資料結構保證：

- **知識圖**：每一格四態可分。EMPTY（掃過沒單位）與 UNKNOWN（沒掃）是兩件不同的
  事實，STALE（前代有單位、這代還沒重掃）是第三件。混在一起就沒有缺口可言。
- **邊界旗**：四個方向各自「未發現／已定於某一格線」。地圖幾何不衰效（邊界旗與
  charted 跨代保留），只有單位知識衰效。
- **前緣**：界內、與已測繪區相鄰、還不是現況的格。前緣空且四旗全定＝完成。
  未定的方向旗本身是強制前緣——沒有邊界就一定還有地方沒去過。

量測的五層防禦（順序即防線順序）：

1. 主里程計＝`board.measure_pan`：有指令的水平腿走格線相位通道（小數部分看格線、
   整數欄數由證人裁決），其餘一律相位相關，量測窗 ≥2× 最大位移。
2. 指令包絡閘（`board.envelope`）：同軸同號、倍率有上界，擋繞回混疊的自信錯值。
3. 格線相位交叉驗證：混疊差一個窗寬、窗寬 mod 格距 ≠ 0，相位對不上即拒收；
   對得上就順手吸附，讓漂移只能整格跳。全幀帶讀不出格線就退象限窗
   （`board.find_lattice`）——邊緣區地圖只佔一角，整段沒有相位閘比量錯更貴。
4. 星座匹配（`board.relocalise`）＝全域重定位器，斷鏈後重錨用，不是主里程計。
5. 撞邊重錨＝絕對參考：島嶼在已知邊界上撞邊就把那一軸釘死。

島嶼合併另有兩道閘（`Survey._admits`）：指令包絡（合併偏移不能大過斷鏈期間沒入帳
的指令位移）與影像複驗（合併偏移隱含的螢幕位移要在畫面上勝過「鏡頭沒動」）。

兩條安全網不變式：**無「量錯寫入」路徑**（雙閘沒過就斷鏈，該幀的觀測進側緩衝
不進權威圖）、**無「無聲丟失」路徑**（沒觀測到的界內格永遠是 UNKNOWN，前緣一定
把它排回補掃）。
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum

import numpy as np

from . import board
from .board import Cell, Lattice, Point, Region, Shift, Sighting

log = logging.getLogger(__name__)


class Knowledge(Enum):
    UNKNOWN = "unknown"
    EMPTY = "empty"
    UNIT = "unit"
    STALE = "stale"


# 還不是現況的兩態：完成判準要求界內一格都不剩，前緣也只挑這兩態。
GAPS = (Knowledge.UNKNOWN, Knowledge.STALE)
COMPASS: tuple[str, ...] = ("west", "east", "north", "south")

ACCEPTED = "accepted"
STALLED = "stalled"
BROKEN = "broken"
# 目視終止邊與已定旗對不上的斷鏈理由（帶方向後綴進遙測）。
EDGE_MISMATCH = "edge_mismatch"
# 目視邊與旗容許的落差（格距的比例）。半格＝格座標還指得到同一格。
EDGE_TOLERANCE = 0.5

# 單腿的內容位移上限（世界像素）＝該軸無歧義量測範圍的一半。相位相關的無歧義範圍
# 是 ±窗長/2，量測窗 1600x620 → x 400／y 155；x 收到 350 留餘裕（0719 教訓：1050px
# 窗量 600px 位移量出 −505 反號）。**橫軸的窗只有 620，所以縱向腿本來就得走小步。**
LEG_LIMIT: dict[str, float] = {
    "x": board.MAP_REGION[2] / 4.57,
    "y": board.MAP_REGION[3] / 4.0,
}
MIN_LEG = 120.0
# 手指行程 → 內容位移的增益。0730 實測 250px 手勢推出約 570-600px 位移，起手值只
# 是為了第一腿不超出無歧義範圍，之後逐腿用量到的值修正。
GAIN_DEFAULT = 2.3
GAIN_RANGE = (0.5, 8.0)
GAIN_BLEND = 0.5
# 一次停滯不算邊界：起手點落在單位精靈上會被遊戲吃掉，畫面同樣不動。連兩次（起手
# 點已逐腿重挑）才把邊界旗釘下去——邊界旗跨代保留，寫錯的代價是永久的。
STALL_CONFIRM = 2
# 島嶼重錨的耐心。用完就整批丟棄並重開世界：誠實重掃的成本有界，帶著不知道位置的
# 觀測繼續走沒有上界。
ISLAND_BUDGET = 6
# 島嶼目擊去重的半徑（格距的比例）。兩台不同實體至少隔一格，同一台在重疊 view 之間
# 只差里程計的量測小數，半格把兩者分得很開。
DUPLICATE_SPAN = 0.5
# 前緣選目標時 STALE 聚類的距離折扣（含 STALE ＝ 單位大概率在附近，威脅評估最需要）。
STALE_WEIGHT = 0.5
# 腿數保險絲：只防**單一回合**內的失控，不是整場戰鬥的額度，也不是完成判準。
# 跨回合累積的話十幾回合就燒斷，之後 fused 恆真、掃描永遠完不成＝整關卡死。
LEG_BUDGET = 200

_STILL = Shift(0.0, 0.0, 1.0, "still")


@dataclass(frozen=True)
class WorldGrid:
    """世界格網：錨定幀的格線相位＋格距。世界像素 ÷ 格距 ＝ 格座標（可為負）。

    row_pitch 是近似值——橫線間距隨 y 遞增（縱向透視），所以列座標與 2b-2 人工普查
    同級（±1 行），權威仍是世界像素。
    """

    phase: Point
    col_pitch: float
    row_pitch: float

    @classmethod
    def anchor(cls, lattice: Lattice, offset: Point = (0.0, 0.0)) -> WorldGrid | None:
        if lattice.col_pitch <= 0 or lattice.row_pitch <= 0:
            return None
        return cls(
            (lattice.cols[0] + offset[0], lattice.rows[0] + offset[1]),
            lattice.col_pitch,
            lattice.row_pitch,
        )

    def cell_of(self, point: Point) -> Cell:
        return (
            math.floor((point[0] - self.phase[0]) / self.col_pitch),
            math.floor((point[1] - self.phase[1]) / self.row_pitch),
        )

    def box_of(self, cell: Cell) -> tuple[float, float, float, float]:
        x = self.phase[0] + cell[0] * self.col_pitch
        y = self.phase[1] + cell[1] * self.row_pitch
        return (x, y, x + self.col_pitch, y + self.row_pitch)

    def centre_of(self, cell: Cell) -> Point:
        x0, y0, x1, y1 = self.box_of(cell)
        return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)


@dataclass(frozen=True)
class FrameView:
    """一幀的觀測連同它的座標系（世界 ＝ 螢幕 ＋ offset）。

    島嶼緩衝存的就是這個：重錨解出偏移之後整批 `shifted()` 再併進權威圖，所以
    「先觀測、後知道自己在哪」不必重截圖。
    """

    offset: Point
    units: tuple[Sighting, ...] = ()
    region: Region = board.UNIT_DENSITY_REGION
    holes: tuple[Region, ...] = board.UNIT_DENSITY_HUD_HOLES
    # 這一幀格線覆蓋的**螢幕**矩形（所以 shifted() 不必動它）與看到終止邊的側。
    # None ＝ 這一幀讀不出格線：幾何上「整格在帶內」照樣成立，但沒有格線背書就
    # 不敢說那裡有格子——EMPTY 毯一格都不鋪。
    lattice: Region | None = None
    edges: frozenset[str] = frozenset()

    def shifted(self, delta: Point) -> FrameView:
        return replace(self, offset=(self.offset[0] + delta[0], self.offset[1] + delta[1]))

    def world(self, point: Point) -> Point:
        return (point[0] + self.offset[0], point[1] + self.offset[1])


@dataclass(frozen=True)
class Reading:
    """一次位移量測的裁決。BROKEN ＝ 雙閘沒過，呼叫端要把這一幀隔離。"""

    verdict: str
    shift: Shift
    offset: Point
    reason: str = ""


@dataclass(frozen=True)
class Leg:
    """一步平移：手指行程＋預期的內容位移（世界像素，帶號；內容與鏡頭反向）。"""

    direction: str
    reach: float
    expected: Point
    target: Cell | None = None


@dataclass
class KnowledgeMap:
    """世界空間的四態圖。charted 是幾何（看過的格），衰效只動單位知識。"""

    grid: WorldGrid
    state: dict[Cell, Knowledge] = field(default_factory=dict)
    charted: set[Cell] = field(default_factory=set)
    boundary: dict[str, int] = field(default_factory=dict)
    # 界內但**從任何推得到的鏡頭位置都看不清楚**的格：地圖角落壓在回合橫幅底下
    # 的那幾格就是這樣（鏡頭夾在邊界上，橫幅在螢幕座標固定不動）。它們不是被
    # 忘掉——退休是明寫的事實，逐 tick 進流水帳，只是不再要求前緣去補。
    unreachable: set[Cell] = field(default_factory=set)
    # 目擊的**世界像素**座標，不是格心：重定位器要拿它跟當下的密度峰配對投票，
    # 量化到格心會讓靜態單位的票散進不同的桶、眾數湊不出來。
    marks: dict[Cell, Sighting] = field(default_factory=dict)

    def knowledge(self, cell: Cell) -> Knowledge:
        return self.state.get(cell, Knowledge.UNKNOWN)

    @property
    def bounded(self) -> bool:
        return all(direction in self.boundary for direction in COMPASS)

    @property
    def complete(self) -> bool:
        """建構性判準：四旗全定 ∧ 界內沒有 UNKNOWN／STALE。"""
        return self.bounded and not self.gaps()

    def in_bounds(self, cell: Cell) -> bool:
        col, row = cell
        limits = (
            ("west", col, 1),
            ("east", col, -1),
            ("north", row, 1),
            ("south", row, -1),
        )
        for direction, value, sign in limits:
            line = self.boundary.get(direction)
            if line is not None and sign * (value - line) < 0:
                return False
        return True

    def absorb(self, view: FrameView) -> tuple[Cell, ...]:
        """把一幀寫進圖：整格看得清楚的先記 EMPTY，落在其中的目擊再蓋成 UNIT。

        **同一代裡已是 UNIT 的格不因為這一幀沒目擊就降級。** 掃描發生在我方回合，
        敵單位在這段時間不會移動，所以「這一格看得清楚卻沒目擊」是偵測漏（弧被
        精靈或特效遮住、密度峰沒過門檻、斷鏈期的座標誤差把目擊算到隔壁格），不是
        單位離開的證據。無條件先鋪 EMPTY 的話，一次漏檢就抹掉先前記下的 UNIT，
        整輪掃完只剩最後一次看到的那幾台。

        單位離開的合法證據只有跨代：`expire()` 把 UNIT 降成 STALE 之後，同款的
        view 照常把它蓋成 EMPTY——那一代的敵人真的動過。

        **EMPTY 毯與目擊兩條口徑不同**：毯子要格線背書（`covered`），目擊只要讀得
        清楚（`readable`）。密度峰不依賴格線，一幀讀不出格線不代表看不見機體——
        那時該做的是不蓋章，不是連看到的單位都丟掉。
        """
        seen = covered(self.grid, view)
        fresh = tuple(cell for cell in seen if self.knowledge(cell) in GAPS)
        for cell in seen:
            self.charted.add(cell)
            if self.knowledge(cell) is Knowledge.UNIT:
                continue
            self.state[cell] = Knowledge.EMPTY
            self.marks.pop(cell, None)
        inside = set(readable(self.grid, view))
        for sighting in view.units:
            point = view.world(sighting.point)
            cell = self.grid.cell_of(point)
            if cell not in inside:
                continue
            self.state[cell] = Knowledge.UNIT
            self.marks[cell] = Sighting(point, sighting.hint)
        return fresh

    def fix_boundary(self, direction: str, view: FrameView) -> int | None:
        """撞邊事件：這個方向再也推不動，界線就是這一幀該側最外一格看得清楚的格。

        用觀測得到的極值而不是地圖美術的邊：看不全的半格永遠補不完，把它畫進界內
        會讓前緣永遠不空。

        定線之後把線外的每一筆知識裁掉（`state`／`marks`／`charted`／`unreachable`）：
        **邊界＝該側最外一格看得清楚的格，線外沒有地圖。** 線外還留著紀錄就是舊
        座標系的殘留——那些格是定案前寫下的，島嶼重錨把整個世界的座標挪過之後它們
        落到線外，從此不會有任何一幀去覆蓋，變成永久鬼影混進單位帳（0801 第 4 輪：
        journal 的 84 筆單位格裡有 29 筆的欄座標整段落在最終東界之外）。同方向第二
        次定案（改判）走同一條裁剪。
        """
        line = edge_cell(self.grid, view, direction)
        if line is None:
            return None
        return self.set_boundary(direction, line)

    def set_boundary(self, direction: str, line: int) -> int:
        """定旗＋裁掉線外的每一筆知識。撞邊（`fix_boundary`）與目視終止邊
        （`Survey._sight_edges`）走同一條路——裁剪的理由與來源無關。"""
        self.boundary[direction] = line
        self._trim()
        return line

    def _trim(self) -> None:
        self.state = {cell: known for cell, known in self.state.items() if self.in_bounds(cell)}
        self.marks = {cell: mark for cell, mark in self.marks.items() if self.in_bounds(cell)}
        self.charted = {cell for cell in self.charted if self.in_bounds(cell)}
        self.unreachable = {cell for cell in self.unreachable if self.in_bounds(cell)}

    def frontier(self) -> tuple[Cell, ...]:
        """界內、與已測繪區相鄰（或本身已測繪過）、還不是現況的格。

        限制在測繪區周邊是為了讓未定邊界的方向有界可推——真正的無限外擴由邊界旗
        另外處理，不然界內在四旗全定之前是無限大。
        """
        out: set[Cell] = set()
        for cell in self.charted:
            for candidate in (cell, *_neighbours(cell)):
                if candidate in out or candidate in self.unreachable:
                    continue
                if not self.in_bounds(candidate):
                    continue
                if self.knowledge(candidate) in GAPS:
                    out.add(candidate)
        return tuple(sorted(out))

    def gaps(self) -> tuple[Cell, ...]:
        """四旗全定之後界內每一格的缺口。未定邊界時界內無限大，退回前緣。"""
        if not self.bounded:
            return self.frontier()
        return tuple(
            (col, row)
            for col in range(self.boundary["west"], self.boundary["east"] + 1)
            for row in range(self.boundary["north"], self.boundary["south"] + 1)
            if self.knowledge((col, row)) in GAPS and (col, row) not in self.unreachable
        )

    def targets(self) -> tuple[Cell, ...]:
        return self.frontier() or self.gaps()

    def choose(self, viewport: Point) -> tuple[Cell, ...] | None:
        """挑一個前緣聚類：近者優先，含 STALE 的聚類加權優先。"""
        pockets = clusters(self.targets())
        if not pockets:
            return None
        return min(pockets, key=lambda pocket: self._priority(pocket, viewport))

    def _priority(self, pocket: tuple[Cell, ...], viewport: Point) -> float:
        centre = self.grid.centre_of(_centroid(pocket))
        distance = math.hypot(centre[0] - viewport[0], centre[1] - viewport[1])
        stale = any(self.knowledge(cell) is Knowledge.STALE for cell in pocket)
        return distance * (STALE_WEIGHT if stale else 1.0)

    def expire(self) -> None:
        """敵回合過完：單位知識降級，地圖幾何原封不動。

        UNIT→STALE（不是抹除，站位還有威脅評估的價值）、EMPTY→UNKNOWN（敵可能
        移進來）。charted 與邊界旗保留——它們是地圖的幾何，不隨誰站哪裡改變。
        """
        for cell, known in list(self.state.items()):
            if known is Knowledge.UNIT:
                self.state[cell] = Knowledge.STALE
            elif known is Knowledge.EMPTY:
                self.state[cell] = Knowledge.UNKNOWN

    def units(self) -> tuple[tuple[Cell, str | None], ...]:
        """現況的單位格。**STALE 不出現**——前代的站位永遠不能當現況。

        四旗全定之後只回界內，跟 `census()` 同一個口徑：流水帳的單位清單與普查
        本來就該對得起來，界外的 mark 是錯座標，算進台數就是憑空多出來的鬼影。
        """
        return tuple(
            (cell, mark.hint)
            for cell, mark in sorted(self.marks.items())
            if self.knowledge(cell) is Knowledge.UNIT and self._inside(cell)
        )

    def sightings(self) -> tuple[Point, ...]:
        """已記目擊的世界像素座標（含 STALE）——重定位器的比對標的。

        同樣只回界內：界外 mark 的世界像素本身就是錯的（線外沒有地圖），拿它當
        星座錨只會把 `relocalise` 解出來的偏移帶歪，整批島嶼再以錯格吸收。
        """
        return tuple(
            mark.point
            for cell, mark in sorted(self.marks.items())
            if self.knowledge(cell) in (Knowledge.UNIT, Knowledge.STALE) and self._inside(cell)
        )

    def _inside(self, cell: Cell) -> bool:
        """四旗全定才談界內：只定了一兩面旗時界內仍是無限大，濾了等於憑半套邊界
        丟掉真的觀測。"""
        return not self.bounded or self.in_bounds(cell)

    def census(self) -> dict[str, int]:
        counts = {known.value: 0 for known in Knowledge}
        for cell in self._scope():
            counts[self.knowledge(cell).value] += 1
        return counts

    def _scope(self) -> Iterable[Cell]:
        if not self.bounded:
            return sorted(self.charted)
        return (
            (col, row)
            for col in range(self.boundary["west"], self.boundary["east"] + 1)
            for row in range(self.boundary["north"], self.boundary["south"] + 1)
        )


@dataclass
class Odometer:
    """世界錨定與逐幀位移。offset 的定義是「世界 ＝ 螢幕 ＋ offset」。

    量測不過雙閘就回 BROKEN 且**什麼都不改**——斷鏈的處置（隔離、重錨、丟棄）是
    呼叫端的事，里程計只負責誠實。
    """

    grid: WorldGrid | None = None
    offset: Point = (0.0, 0.0)
    previous: np.ndarray | None = None

    def feed(self, frame: np.ndarray, expected: Point | None = None) -> Reading:
        if self.previous is None:
            self.previous = frame
            return Reading(ACCEPTED, _STILL, self.offset, "anchor")
        shift = board.measure_pan(self.previous, frame, expected)
        # 兩幀幾乎同一張＝畫面真的沒動，位移取準確的 0。相位相關對零位移有半像素
        # 的系統偏差（實測 identical frames 回 dy=+0.5），停滯一多就會累成整格漂移。
        if shift.magnitude < board.EDGE_SHIFT_PX or not shift.known:
            if board.frame_difference(self.previous, frame) < board.EDGE_FRAME_DIFF:
                shift = _STILL
            elif not shift.known:
                return Reading(BROKEN, shift, self.offset, "unmeasurable")
        gate = board.envelope(shift, expected)
        if gate == board.ENVELOPE_REFUSED:
            return Reading(BROKEN, shift, self.offset, "envelope")
        candidate = (self.offset[0] - shift.dx, self.offset[1] - shift.dy)
        snapped = self._snap(frame, candidate)
        if snapped is None:
            return Reading(BROKEN, shift, self.offset, "phase")
        self.offset = snapped
        self.previous = frame
        stalled = shift.magnitude < board.EDGE_SHIFT_PX and _commanded(expected)
        return Reading(STALLED if stalled else ACCEPTED, shift, snapped, gate)

    def rephase(self, frame: np.ndarray) -> None:
        """把 offset 對齊到這一幀的格線相位（不設容差）。

        島嶼開局用：局部原點本來就是隨便挑的，挑一個與世界格網同相位的，島與世界
        之間的偏移才必然是整數格——不然往後每一幀的相位閘都會拒收，島嶼連累積
        觀測的機會都沒有（實測：偏半格的島會逐幀重開，永遠等不到重錨）。
        """
        if self.grid is None:
            return
        lattice = board.find_lattice(frame)
        if lattice is None:
            return
        residual = board.median_residual(
            [col + self.offset[0] for col in lattice.cols],
            self.grid.col_pitch,
            self.grid.phase[0],
        )
        self.offset = (self.offset[0] - residual, self.offset[1])

    def _snap(self, frame: np.ndarray, candidate: Point) -> Point | None:
        """格線相位交叉驗證＋吸附。對不上就回 None（拒收），對得上就把小數吃掉，
        讓累積漂移只能整格跳。

        只驗直線軸：橫線間距隨 y 遞增（縱向透視），對它取模的相位不是不變量。縱向
        的保護落在腿長規則（單腿 ≤ 窗高/4）與包絡閘。

        殘差取**全線中位數**而不是單線：單線抖動 ±10px 實測在案，容差只有 0.25 pitch。

        格線走 `board.find_lattice`（全幀帶讀不出來就退象限窗）：讀不到格線這一支是
        **無條件放行**，邊緣區整段停擺等於整段沒有相位閘。
        """
        if self.grid is None:
            return candidate
        lattice = board.find_lattice(frame)
        if lattice is None:
            return candidate
        pitch = self.grid.col_pitch
        residual = board.median_residual(
            [col + candidate[0] for col in lattice.cols], pitch, self.grid.phase[0]
        )
        if abs(residual) > board.PHASE_TOLERANCE * pitch:
            return None
        return (candidate[0] - residual, candidate[1])


@dataclass
class Island:
    """斷鏈之後的側緩衝：局部座標系的觀測，重錨成功才併進權威圖。

    局部原點刻意沿用斷鏈當下的 offset 估計並對齊格線相位（`rephase`），所以島與
    世界的**欄**偏移必然是整數格（相位同一族），吸附到整欄不會撕裂格網。**列不然**
    ——橫軸沒有相位閘，島與世界的列偏移可以是任意值（見 `_whole_columns`）。
    """

    reason: str
    odometer: Odometer
    views: list[FrameView] = field(default_factory=list)
    pins: dict[str, float] = field(default_factory=dict)
    # 島嶼模式的停滯計數（方向別）。掛在島上而不是 Survey 上：島一丟棄就跟著滅，
    # 上一座島的停滯不能拿來釘下一座島的軸。
    stalls: dict[str, int] = field(default_factory=dict)
    # 島嶼存活期間發出過的指令位移（軸別絕對值和）＝合併偏移的物理上界來源。斷鏈
    # 那一腿與島內每一腿都算進來：島內的腿即使被判 STALLED 也可能是量錯（相關器
    # 鎖靜態峰），那段位移一樣要靠合併偏移補回來。跨島嶼累加——島內再斷鏈會換一座島
    # 但**沿用同一個局部原點**，前一次的帳還掛在這個原點上。None ＝ 沒有指令可當
    # 包絡（回合交界鏡頭被遊戲拉走）。
    lost: dict[str, float] | None = None

    @property
    def sightings(self) -> tuple[Point, ...]:
        """島內的目擊，**同一台實體在重疊 view 的重複目擊只算一票**。

        重錨的支持數門檻要的是「這麼多台實體真的對上位置」；不去重的話一台單位
        出現在 N 個重疊 view 就自己湊滿門檻，星座複驗形同虛設。
        """
        radius = self._merge_radius()
        seen = sorted(view.world(unit.point) for view in self.views for unit in view.units)
        kept: list[Point] = []
        for point in seen:
            if any(math.hypot(point[0] - x, point[1] - y) < radius for x, y in kept):
                continue
            kept.append(point)
        return tuple(kept)

    def _merge_radius(self) -> float:
        grid = self.odometer.grid
        if grid is None:
            return float(board.CONSTELLATION_TOLERANCE)
        return DUPLICATE_SPAN * min(grid.col_pitch, grid.row_pitch)


@dataclass
class Survey:
    """一次盤面全覽的世界模型：里程計＋知識圖＋島嶼緩衝。

    只吃幀與指令，回報這一幀被怎麼收下。行動語意（微步驟名、符號狀態）在 stage
    層——這裡不認識行動詞彙。
    """

    region: Region = board.UNIT_DENSITY_REGION
    holes: tuple[Region, ...] = board.UNIT_DENSITY_HUD_HOLES
    budget: int = LEG_BUDGET
    chart: KnowledgeMap | None = None
    odometer: Odometer = field(default_factory=Odometer)
    island: Island | None = None
    gain: dict[str, float] = field(default_factory=lambda: {"x": GAIN_DEFAULT, "y": GAIN_DEFAULT})
    stalls: dict[str, int] = field(default_factory=dict)
    # 撞邊當下的世界座標（軸別）：鏡頭離開就不再是夾住的狀態，見 _clamped。
    clamps: dict[str, float] = field(default_factory=dict)
    # 最近一次收下的 view 目視到終止邊的那幾側＝該方向的天然夾點（見 _clamped）。
    # 存側名不存座標：終止邊在不在畫面上是螢幕事實，與里程計解出什麼偏移無關，所以
    # 島嶼期的 view 一樣算數（那正是旗還沒定、最需要它的時候）。
    sighted: frozenset[str] = frozenset()
    islands: dict[str, int] = field(
        default_factory=lambda: {
            "isolated": 0,
            "merged": 0,
            "discarded": 0,
            "reset": 0,
            "refused": 0,
        }
    )
    unlocalised: int = 0
    legs: int = 0
    generation: int = 0
    adrift: bool = False
    # 大陸最後一張收下的幀與它的 offset。島嶼合併前拿它跟島當下幀對質（影像複驗
    # 閘）——量測層要自己留一份：driver 的 previous 是 stage 層的取幀紀錄，而
    # `Odometer.previous` 在斷鏈時刻意不推進，兩者都不是「大陸最後的權威幀」。
    mainland: tuple[np.ndarray, Point] | None = None
    # 這一次 observe 有沒有合併島嶼，合併在哪個偏移、併進幾個 view。每次 observe
    # 開頭清成 None：它是「這一幀發生了什麼」的遙測，留著跨 tick 會讓同一次合併
    # 重複入帳。delta 寫錯時整批島 view 以錯格吸收，事後光看 islands 的累計次數
    # 分不出是哪一次錯、錯多少。
    last_merge: tuple[Point, int] | None = None

    @property
    def anchored(self) -> bool:
        return self.chart is not None

    @property
    def complete(self) -> bool:
        return self.chart is not None and self.chart.complete

    @property
    def fused(self) -> bool:
        return self.legs >= self.budget

    def observe(self, frame: np.ndarray, leg: Leg | None = None) -> Reading:
        """吃一幀：量位移、過雙閘，寫進權威圖或側緩衝。"""
        self.last_merge = None
        if self.chart is None:
            return self._anchor(frame)
        if self.adrift:
            self.adrift = False
            reading = Reading(BROKEN, _STILL, self.odometer.offset, "generation")
            self._isolate(frame, reading, self.odometer, None, counted=False, metered=False)
            return reading
        odometer = self.island.odometer if self.island is not None else self.odometer
        expected = None if leg is None else leg.expected
        reading = odometer.feed(frame, expected)
        if reading.verdict == BROKEN:
            self._isolate(frame, reading, odometer, expected)
            return reading
        if leg is not None:
            self._learn_gain(leg, reading)
        view = self._view(frame, reading.offset)
        self.sighted = view.edges
        if self.island is not None:
            self.island.views.append(view)
            self._reanchor(leg, reading, view, frame)
        else:
            clash = self._edge_clash(view)
            if clash is not None:
                reading = Reading(BROKEN, reading.shift, reading.offset, clash)
                self._isolate(frame, reading, odometer, expected)
                return reading
            self.chart.absorb(view)
            self._sight_edges(view)
            if leg is not None:
                self._boundary(leg, reading, view)
        if self.island is None:
            self.mainland = (frame, self.odometer.offset)
        return reading

    def plan_leg(self) -> Leg | None:
        """下一步往哪推。None ＝ 沒得推了（完成或保險絲燒斷）。

        還沒錨定（讀不到格網）時照樣給一腿：地圖邊緣的半幅虛空會讓格網讀不出來，
        待在原地只會永遠讀不到，推一步換個視野才有機會錨上。
        """
        if self.fused:
            if not self.complete:
                log.warning("survey leg budget %d spent before the frontier emptied", self.budget)
            return None
        if self.chart is None:
            return self._probe()
        if self.complete:
            return None
        for _ in range(len(self.chart.targets()) + 1):
            leg = self._aim()
            if leg is not None:
                return leg
            if self.complete:
                return None
        return self._probe()

    def _aim(self) -> Leg | None:
        """挑一個前緣聚類推一步。推不動（兩軸都夾在邊界上）就把目標退休——
        那一格從任何到得了的鏡頭位置都看不清楚，硬要它只會原地空轉。

        退休的一定是**聚類成員**：L 形聚類的質心根本不在聚類裡，退休它既不會讓
        目標清單變短（plan_leg 的迴圈永遠挑到同一團＝活鎖），又把一格可能是 EMPTY
        的格子跨代排除掉＝無聲丟失。一次退休一格，迴圈才保證嚴格縮小。
        """
        chart = self.chart
        if chart is None:
            return None
        viewport = self.viewport()
        pocket = chart.choose(viewport)
        if pocket is None:
            return None
        target = _centroid(pocket)
        centre = chart.grid.centre_of(target)
        delta = (centre[0] - viewport[0], centre[1] - viewport[1])
        axes = sorted(("x", "y"), key=lambda axis: -abs(delta[0] if axis == "x" else delta[1]))
        for axis in axes:
            wanted = delta[0] if axis == "x" else delta[1]
            if abs(wanted) < 1.0:
                continue
            direction = _bearing(axis, wanted)
            if self._clamped(direction):
                continue
            return self._leg(direction, min(abs(wanted), LEG_LIMIT[axis]), target)
        retired = _nearest(pocket, target)
        chart.unreachable.add(retired)
        log.warning("cell %s is unreachable from every camera position we can hold", retired)
        return None

    def viewport(self) -> Point:
        x, y, w, h = self.region
        offset = self.island.odometer.offset if self.island else self.odometer.offset
        return (x + w / 2.0 + offset[0], y + h / 2.0 + offset[1])

    def expire(self) -> None:
        """回合交界：單位知識降級，地圖幾何留著，里程計斷鏈。

        敵方回合鏡頭會被遊戲拉去演出，兩個回合之間的位移量不出來，所以世界錨點
        一律當作斷了——下一幀進島嶼，重錨成功才接回同一套世界座標；重錨不成就
        誠實重開世界（邊界旗一起重來，但不會有一格是錯的）。

        腿數保險絲跟著歸零：衰效之後整張圖都要重掃，這一回合的腿數不該由上一回合
        預付。不歸零的話十幾回合就燒斷，之後每一回合都直接判掃不完。
        """
        self.generation += 1
        self.legs = 0
        if self.chart is None:
            return
        self.chart.expire()
        if self.island is not None:
            self.islands["discarded"] += 1
            self.island = None
        self.stalls.clear()
        self.adrift = True

    def units(self) -> tuple[tuple[Cell, str | None], ...]:
        return () if self.chart is None else self.chart.units()

    def summary(self) -> dict[str, object]:
        """逐 tick 進流水帳的覆蓋自述：覆蓋率、前緣聚類、斷鏈與島嶼事件。"""
        chart = self.chart
        census = chart.census() if chart is not None else {known.value: 0 for known in Knowledge}
        scope = sum(census.values())
        observed = census[Knowledge.EMPTY.value] + census[Knowledge.UNIT.value]
        pockets = clusters(chart.targets()) if chart is not None else ()
        return {
            "generation": self.generation,
            "anchored": chart is not None,
            "bounded": sorted(chart.boundary) if chart is not None else [],
            "boundary": dict(chart.boundary) if chart is not None else {},
            "sighted": sorted(self.sighted),
            "cells": census,
            "coverage": round(observed / scope, 3) if scope else 0.0,
            "frontier": len(chart.targets()) if chart is not None else 0,
            "clusters": len(pockets),
            "unreachable": len(chart.unreachable) if chart is not None else 0,
            "unlocalised": self.unlocalised,
            "islands": {**self.islands, "open": self.island is not None},
            "legs": self.legs,
            "units": len(self.units()),
            "complete": self.complete,
        }

    def _anchor(self, frame: np.ndarray) -> Reading:
        lattice = board.read_lattice(frame)
        grid = None if lattice is None else WorldGrid.anchor(lattice)
        if grid is None:
            log.warning("no lattice on the anchor frame; the world stays unanchored")
            return Reading(BROKEN, _STILL, (0.0, 0.0), "no lattice")
        self.chart = KnowledgeMap(grid=grid)
        self.odometer = Odometer(grid=grid, offset=(0.0, 0.0), previous=frame)
        view = self._view(frame, (0.0, 0.0))
        self.sighted = view.edges
        self.chart.absorb(view)
        self._sight_edges(view)
        self.mainland = (frame, (0.0, 0.0))
        return Reading(ACCEPTED, _STILL, (0.0, 0.0), "anchor")

    def _view(self, frame: np.ndarray, offset: Point) -> FrameView:
        span = board.read_span(frame)
        return FrameView(
            offset=offset,
            units=board.find_sightings(frame, self.region),
            region=self.region,
            holes=self.holes,
            lattice=None if span is None else span.box,
            edges=frozenset() if span is None else span.edges,
        )

    def _sight_edges(self, view: FrameView) -> None:
        """目視終止邊定旗：格網在畫面上就到這裡，那一側的邊界是**看到的**，不是從
        「推不動了」推論出來的（0723 定則：邊界只目視、永不推論）。撞邊那條路
        （`_boundary`）保留當第二來源——手勢被吃掉與到邊在畫面上分不開，但格網終止
        邊分得出來。

        旗已定就不再動它，見 `_edge_clash`。
        """
        chart = self.chart
        if chart is None:
            return
        for direction in sorted(view.edges):
            if direction in chart.boundary:
                continue
            border = sighted_border(view, direction)
            if border is None:
                continue
            line = _border_cell(chart.grid, direction, border)
            chart.set_boundary(direction, line)
            log.info("boundary %s sighted at cell %s (no stall needed)", direction, line)

    def _edge_clash(self, view: FrameView) -> str | None:
        """已定的旗與這一幀目視的終止邊差超過半格＝旗與 offset 至少有一個錯了。

        當場裁不出是哪一個（旗跨代保留、offset 是這一幀的量測），所以**兩個都不改**
        ——誠實把這一幀隔離，讓影像複驗閘與重定位器在島嶼那條路上裁。自動改旗的
        代價是跨代永久的，自動改 offset 就是「量錯寫入」。
        """
        chart = self.chart
        if chart is None:
            return None
        for direction in sorted(view.edges):
            line = chart.boundary.get(direction)
            if line is None:
                continue
            border = sighted_border(view, direction)
            if border is None:
                continue
            pitch = _pitch_of(chart.grid, direction)
            drift = border - _flag_border(chart.grid, direction, line)
            if abs(drift) > EDGE_TOLERANCE * pitch:
                log.warning(
                    "sighted %s edge sits %.1fpx from the flag; isolating the frame", direction, drift
                )
                return f"{EDGE_MISMATCH}:{direction}"
        return None

    def _leg(self, direction: str, wanted: float, target: Cell | None = None) -> Leg:
        axis = "x" if direction in ("east", "west") else "y"
        reach = min(
            max(max(wanted, MIN_LEG) / self.gain[axis], board.PAN_MIN_REACH), board.PAN_MAX_REACH
        )
        travel = min(reach * self.gain[axis], LEG_LIMIT[axis])
        dx, dy = board.DIRECTIONS[direction]
        self.legs += 1
        return Leg(direction, reach, (-dx * travel, -dy * travel), target)

    def _clamped(self, direction: str) -> bool:
        """往這個方向再推收不到覆蓋。兩個來源並列，任一成立即成立：

        1. **目視終止邊**（`sighted`）：最近一次收下的畫面看得到那一側的格網終止邊，
           邊外是虛空、邊內整段已經在偵測帶裡，所以再推只是把虛空推進畫面。鏡頭移開
           之後那一側自然讀不到終止邊，下一幀就解除——它是逐幀的證言，不是旗子。
        2. **撞邊當下的世界座標**（`clamps`）：手勢推不動的那一點。同樣不記成旗子，
           離開之後同一個方向當然又推得動，拿旗子當狀態會讓地圖中央的格也被當成推不到。
           一次停滯不算數——起手點被單位精靈吃掉的手勢，畫面同樣不動。

        兩者互不覆蓋：目視邊管「那邊沒有地圖」，撞邊線管「這邊推不動」，前者連旗還
        沒定的島嶼期都成立（`_sight_edges` 只在大陸那條路上跑），後者連讀不到格線的
        幀都成立。這是**規劃層**的節流——量測與簿記一概不看它。
        """
        if direction in self.sighted:
            return True
        line = self.clamps.get(direction)
        if line is None:
            return False
        offset = self.island.odometer.offset if self.island else self.odometer.offset
        return abs(offset[0 if _axis_of(direction) == "x" else 1] - line) < board.EDGE_SHIFT_PX

    def _probe(self) -> Leg | None:
        """沒有前緣格可挑（或還沒錨定）時，未定的方向旗自己就是強制前緣——往那邊
        推去找邊。方向輪流換，免得夾在同一條邊上原地空轉。"""
        fixed = self.chart.boundary if self.chart is not None else {}
        open_flags = [
            direction
            for direction in COMPASS
            if direction not in fixed and not self._clamped(direction)
        ]
        if not open_flags:
            return None
        direction = open_flags[self.legs % len(open_flags)]
        return self._leg(direction, LEG_LIMIT[_axis_of(direction)])

    def _learn_gain(self, leg: Leg, reading: Reading) -> None:
        """手指行程對內容位移的增益逐腿修正：**真的動了就入帳**。

        舊條件是「量到的不足預期的一半就不入帳」，本意是擋撞邊那一腿。但預設增益
        高估三倍時 measured/expected 恆在 0.5 以下（0801 遙測：南向 9 腿全是 0.33，
        51.5px 對 155px），這條保護就恆真——增益永遠學不到，每一腿都照著錯的增益
        超推。撞邊的污染改由三件事自癒：真撞邊時位移 < EDGE_SHIFT_PX 已經被判
        STALLED，而 STALLED 進不了這裡；GAIN_BLEND 的指數混合讓半推半就的一腿只
        帶走一半權重；GAIN_RANGE 夾住極端值。
        """
        if reading.verdict != ACCEPTED or leg.reach <= 0:
            return
        measured = math.hypot(reading.shift.dx, reading.shift.dy)
        if measured < board.EDGE_SHIFT_PX:
            return
        blended = (1 - GAIN_BLEND) * self.gain[_axis_of(leg.direction)] + GAIN_BLEND * (
            measured / leg.reach
        )
        self.gain[_axis_of(leg.direction)] = min(max(blended, GAIN_RANGE[0]), GAIN_RANGE[1])

    def _boundary(self, leg: Leg, reading: Reading, view: FrameView) -> None:
        if self.chart is None:
            return
        if reading.verdict != STALLED:
            self.stalls.pop(leg.direction, None)
            return
        hits = self.stalls.get(leg.direction, 0) + 1
        self.stalls[leg.direction] = hits
        if hits < STALL_CONFIRM:
            return
        self.clamps[leg.direction] = view.offset[0 if _axis_of(leg.direction) == "x" else 1]
        line = self.chart.fix_boundary(leg.direction, view)
        log.info("boundary %s fixed at %s after %d stalls", leg.direction, line, hits)

    def _isolate(
        self,
        frame: np.ndarray,
        reading: Reading,
        odometer: Odometer,
        expected: Point | None,
        *,
        counted: bool = True,
        metered: bool = True,
    ) -> None:
        """斷鏈：這一幀之後的觀測進側緩衝，不進權威圖。島內再斷鏈就把舊島丟掉
        （那一區留 UNKNOWN，前緣會回來補）。

        counted=False 是回合交界的預期斷鏈——那不是量測失敗，不該算進 unlocalised。
        metered=False 是同一件事的另一面：鏡頭被遊戲拉走，沒有指令可以當合併偏移的
        上界，`lost` 於是留 None（不設包絡）。
        """
        if counted:
            self.unlocalised += 1
        carried = (
            None
            if not metered
            else (self.island.lost if self.island is not None else {"x": 0.0, "y": 0.0})
        )
        if self.island is not None:
            self.islands["discarded"] += 1
        log.warning("odometry chain broke (%s); isolating the frame", reading.reason)
        seed = Odometer(grid=odometer.grid, offset=odometer.offset, previous=frame)
        seed.rephase(frame)
        self.island = Island(reason=reading.reason, odometer=seed, lost=_lost(carried, expected))
        self.island.views.append(self._view(frame, seed.offset))
        self.islands["isolated"] += 1

    def _reanchor(
        self, leg: Leg | None, reading: Reading, view: FrameView, frame: np.ndarray
    ) -> None:
        island = self.island
        if island is None or self.chart is None:
            return
        if leg is not None:
            island.lost = _lost(island.lost, leg.expected)
            self._pin(leg, reading, view)
        delta = self._solve()
        if delta is not None and not self._admits(island, delta, view, frame):
            self.islands["refused"] += 1
            delta = None
        if delta is not None:
            for buffered in island.views:
                self.chart.absorb(buffered.shifted(delta))
            self.odometer = Odometer(
                grid=self.chart.grid,
                offset=(island.odometer.offset[0] + delta[0], island.odometer.offset[1] + delta[1]),
                previous=island.odometer.previous,
            )
            self.island = None
            self.islands["merged"] += 1
            self.last_merge = (delta, len(island.views))
            log.info("island of %d frames re-anchored at %s", len(island.views), delta)
            return
        if len(island.views) >= ISLAND_BUDGET:
            self._abandon(island)

    def _admits(
        self, island: Island, delta: Point, view: FrameView, frame: np.ndarray
    ) -> bool:
        """合併偏移的兩道複驗：指令包絡與影像複驗。過不了就不併（島照舊攢或丟棄）。

        重錨解錯一次，整批島 view 就以錯格吸收，而 UNIT 滯後（v2.3）會把那些鬼影
        保到跨代——0801 第 5 輪台數 80 對真值 28 就是這樣長出來的。兩道閘都只否決、
        不修正偏移：改寫偏移等於再造一條「量錯寫入」的路。
        """
        if not self._metered(island, delta):
            log.warning("merge offset %s exceeds what the commanded legs could have moved", delta)
            return False
        if self.mainland is None:
            return True
        anchor, offset = self.mainland
        implied = (
            offset[0] - view.offset[0] - delta[0],
            offset[1] - view.offset[1] - delta[1],
        )
        verdict = board.null_check(
            anchor, frame, implied, [sighting.point for sighting in view.units]
        )
        if verdict == board.NULL_STILL:
            log.warning("merge offset %s lands where the picture says the camera never moved", delta)
            return False
        return True

    def _metered(self, island: Island, delta: Point) -> bool:
        """合併偏移的每軸絕對值上界＝該軸的指令位移和 ×1.5 ＋一格裕度。

        1.5 與包絡閘的單次上限同一個數（`board.ENVELOPE_SINGLE`）：增益學不準時一腿
        推得比預期遠，但推不到兩倍。一格裕度給重錨本來就該有的整格吸附餘裕。
        0801 t22 的 (546, −670)：島只發過一條東向腿（expected (−342, 0)），y 軸沒有
        任何指令位移可言，上界就是一格，670 當場出局。
        """
        lost = island.lost
        if lost is None or self.chart is None:
            return True
        grid = self.chart.grid
        return (
            abs(delta[0]) <= board.ENVELOPE_SINGLE * lost["x"] + grid.col_pitch
            and abs(delta[1]) <= board.ENVELOPE_SINGLE * lost["y"] + grid.row_pitch
        )

    def _pin(self, leg: Leg, reading: Reading, view: FrameView) -> None:
        """撞邊重錨：島嶼在一條已知的邊界線上停住，那一軸的偏移就被絕對釘死。

        停滯要連續 STALL_CONFIRM 次才算撞邊，跟主圖釘邊界旗同一條規則：起手點落在
        單位精靈上的手勢會被遊戲吃掉，畫面同樣不動，一次停滯分不出是哪一種。釘錯
        軸的代價是整批島嶼寫進錯的世界座標。
        """
        island = self.island
        if island is None or self.chart is None:
            return
        if reading.verdict != STALLED:
            island.stalls.pop(leg.direction, None)
            return
        hits = island.stalls.get(leg.direction, 0) + 1
        island.stalls[leg.direction] = hits
        if hits < STALL_CONFIRM:
            return
        line = self.chart.boundary.get(leg.direction)
        if line is None:
            return
        local = edge_cell(self.chart.grid, view, leg.direction)
        if local is None:
            return
        axis = _axis_of(leg.direction)
        pitch = self.chart.grid.col_pitch if axis == "x" else self.chart.grid.row_pitch
        island.pins[axis] = (line - local) * pitch

    def _solve(self) -> Point | None:
        island = self.island
        if island is None or self.chart is None:
            return None
        if "x" in island.pins and "y" in island.pins:
            pinned = (island.pins["x"], island.pins["y"])
            if self._agrees(pinned):
                return pinned
            log.warning("pinned offset %s contradicts the recorded sightings", pinned)
        drift = board.relocalise(self.chart.sightings(), island.sightings)
        if drift is None:
            return None
        return self._whole_columns((-drift[0], -drift[1]))

    def _agrees(self, delta: Point) -> bool:
        """撞邊釘出來的偏移過不過 relocalise 那一關的支持數複驗。

        兩軸都釘住不代表釘對：邊界旗與邊緣格任一量錯，整批島嶼就寫進錯的世界座標
        ——「量錯寫入」那條路徑不准存在，所以釘軸也要回頭跟已記目擊對答案。島上
        零目擊（或權威圖零目擊）時沒有可矛盾之物，釘軸單獨成立。
        """
        island = self.island
        chart = self.chart
        if island is None or chart is None:
            return False
        seen = island.sightings
        marks = chart.sightings()
        if not seen or not marks:
            return True
        span = (chart.grid.col_pitch / 2.0, chart.grid.row_pitch / 2.0)
        support = sum(
            any(
                abs(sx + delta[0] - kx) <= span[0] and abs(sy + delta[1] - ky) <= span[1]
                for kx, ky in marks
            )
            for sx, sy in seen
        )
        return support >= board.RELOCATE_MIN_SUPPORT

    def _whole_columns(self, delta: Point) -> Point:
        """只把**欄**吸附整格，列保留重定位器解出來的原值。

        島嶼開局的 `rephase` 只驗直線軸的相位，所以島與世界的欄偏移必然是整數格，
        吸附只是把量測小數吃掉。列方向沒有相位閘（橫線間距隨 y 遞增，取模不是
        不變量），敵回合演出常把鏡頭拉走半列——硬吸附整列會把半列誤差當成 0 寫進
        整批合併，重錨後的里程計還會一路繼承那個誤差。
        """
        grid = self.chart.grid if self.chart is not None else None
        if grid is None:
            return delta
        return (round(delta[0] / grid.col_pitch) * grid.col_pitch, delta[1])

    def _abandon(self, island: Island) -> None:
        """島嶼重錨失敗：整批丟棄（那一區留 UNKNOWN），世界重開在當下這一幀。

        規格的「開到最近已知邊歸零」是更好的復原，但那需要一套朝已知邊界轉向的
        steering；本批取有界的誠實重來——舊圖作廢、重新錨定，成本是一次全掃。

        撞邊線跟著舊世界一起作廢（新世界的原點是當下這一幀，舊座標值沒有意義）；
        腿數**不**歸零——同一回合內島嶼反覆丟棄重開仍受同一條保險絲約束，不然
        回合內就沒有上界了。
        """
        log.warning("island of %d frames never re-anchored; resetting the world", len(island.views))
        self.islands["discarded"] += 1
        self.islands["reset"] += 1
        frame = island.odometer.previous
        self.island = None
        self.chart = None
        self.odometer = Odometer()
        self.mainland = None
        self.stalls.clear()
        self.clamps.clear()
        if frame is not None:
            self._anchor(frame)

    def reset(self) -> None:
        """鏡頭的比例被動過（縮放）：舊世界的像素座標全部作廢，重新錨定。

        撞邊線帶的是舊世界的座標值，新世界走到同一個數字並不代表頂在邊上，所以
        一起清掉；腿數也重開，縮放後這是新的一輪掃描。

        目視邊也清：縮放換的是整個畫面內容，縮小之後同一側可能露出更多地圖，留著
        舊證言會讓那個方向被誤判成推不動——`_aim` 兩軸都被誤夾就把目標格退休掉，
        那是跨代生效的。**丟棄世界（`_abandon`）不清**：那裡的畫面沒變，側名照樣
        成立，而且下一次錨定馬上會覆蓋它。
        """
        self.chart = None
        self.odometer = Odometer()
        self.island = None
        self.mainland = None
        self.adrift = False
        self.stalls.clear()
        self.clamps.clear()
        self.sighted = frozenset()
        self.legs = 0


def readable(grid: WorldGrid, view: FrameView) -> tuple[Cell, ...]:
    """這一幀讀得清楚的格：整格框都在偵測帶內、且不碰 HUD 挖洞。

    被螢幕邊切一半、或壓在回合橫幅底下的格一律留 UNKNOWN——那裡漏看一台單位是
    沉默的錯，比多走一腿貴得多。**這是幾何，不是「掃過」**：見 `covered`。
    """
    x, y, w, h = view.region
    ox, oy = view.offset
    first = grid.cell_of((x + ox, y + oy))
    last = grid.cell_of((x + w + ox, y + h + oy))
    out: list[Cell] = []
    for col in range(first[0], last[0] + 1):
        for row in range(first[1], last[1] + 1):
            bx0, by0, bx1, by1 = grid.box_of((col, row))
            box = (bx0 - ox, by0 - oy, bx1 - ox, by1 - oy)
            if not _within(box, view.region):
                continue
            if any(_overlaps(box, hole) for hole in view.holes):
                continue
            out.append((col, row))
    return tuple(out)


def covered(grid: WorldGrid, view: FrameView) -> tuple[Cell, ...]:
    """這一幀敢說「掃過」的格：讀得清楚**而且沒有越過看得見的格網終止邊**。

    四態知識全是單位知識，每一態都預設「這裡有一格」——但那個前提要有人背書。
    幾何框完整不代表那裡是棋盤：地圖邊緣外是星空虛空，鏡頭帶把它框得再完整也
    不該蓋 EMPTY 章（EMPTY 的語意是「掃過、沒單位」，不是「那裡什麼都沒有」）。

    切的是**有目擊的那幾側**，不是整個線位矩形：`GRID_REGION` 是取樣帶不是格網的
    邊界，拿帶緣當界會把帶外明明有格線的地方一起判成沒格子（實測那會讓單幀的
    EMPTY 毯縮到四成，掃描腿數跟著翻倍）。同一條原則在 `board._terminal_edges`
    ——貼著帶緣的線分不出「格網到此為止」與「帶就到這裡」，那種側不出證言。

    整幀讀不出格線（全幀帶與象限窗都 None）＝零遮罩，這一幀一格都不蓋——單位目擊
    照收（密度峰不依賴格線，見 `KnowledgeMap.absorb`）。
    """
    if view.lattice is None:
        return ()
    x, y, w, h = view.lattice
    ox, oy = view.offset
    out: list[Cell] = []
    for cell in readable(grid, view):
        box = _screen_box(grid, cell, (ox, oy))
        if "west" in view.edges and box[0] < x:
            continue
        if "east" in view.edges and box[2] > x + w:
            continue
        if "north" in view.edges and box[1] < y:
            continue
        if "south" in view.edges and box[3] > y + h:
            continue
        out.append(cell)
    return tuple(out)


def _screen_box(grid: WorldGrid, cell: Cell, offset: Point) -> tuple[float, float, float, float]:
    bx0, by0, bx1, by1 = grid.box_of(cell)
    return (bx0 - offset[0], by0 - offset[1], bx1 - offset[0], by1 - offset[1])


def sighted_border(view: FrameView, direction: str) -> float | None:
    """目視終止邊在**世界像素**上的位置（該側地圖的外緣）。沒有目擊就 None。"""
    if view.lattice is None or direction not in view.edges:
        return None
    x, y, w, h = view.lattice
    ox, oy = view.offset
    return {
        "west": x + ox,
        "east": x + w + ox,
        "north": y + oy,
        "south": y + h + oy,
    }[direction]


def _flag_border(grid: WorldGrid, direction: str, line: int) -> float:
    """已定的旗換算成該側地圖外緣的世界像素。"""
    if _axis_of(direction) == "x":
        edge = grid.phase[0] + line * grid.col_pitch
        return edge if direction == "west" else edge + grid.col_pitch
    edge = grid.phase[1] + line * grid.row_pitch
    return edge if direction == "north" else edge + grid.row_pitch


def _border_cell(grid: WorldGrid, direction: str, border: float) -> int:
    """外緣往界內半格＝該側最外一格的格座標。"""
    pitch = _pitch_of(grid, direction)
    inward = pitch / 2.0 if direction in ("west", "north") else -pitch / 2.0
    if _axis_of(direction) == "x":
        return grid.cell_of((border + inward, grid.phase[1]))[0]
    return grid.cell_of((grid.phase[0], border + inward))[1]


def _pitch_of(grid: WorldGrid, direction: str) -> float:
    return grid.col_pitch if _axis_of(direction) == "x" else grid.row_pitch


def edge_cell(grid: WorldGrid, view: FrameView, direction: str) -> int | None:
    """這一幀在 direction 那一側最外一格看得清楚的格座標。"""
    seen = covered(grid, view)
    if not seen:
        return None
    axis = 0 if direction in ("west", "east") else 1
    pick = min if direction in ("west", "north") else max
    return pick(cell[axis] for cell in seen)


def clusters(cells: Sequence[Cell]) -> tuple[tuple[Cell, ...], ...]:
    """四鄰接的連通分量。前緣要成塊處理才不會在兩個缺口之間來回跑。"""
    remaining = set(cells)
    out: list[tuple[Cell, ...]] = []
    while remaining:
        seed = min(remaining)
        pocket: list[Cell] = []
        queue = [seed]
        remaining.discard(seed)
        while queue:
            cell = queue.pop()
            pocket.append(cell)
            for neighbour in _neighbours(cell):
                if neighbour in remaining:
                    remaining.discard(neighbour)
                    queue.append(neighbour)
        out.append(tuple(sorted(pocket)))
    return tuple(out)


def _neighbours(cell: Cell) -> tuple[Cell, ...]:
    col, row = cell
    return ((col - 1, row), (col + 1, row), (col, row - 1), (col, row + 1))


def _centroid(cells: Sequence[Cell]) -> Cell:
    return (
        round(sum(cell[0] for cell in cells) / len(cells)),
        round(sum(cell[1] for cell in cells) / len(cells)),
    )


def _nearest(cells: Sequence[Cell], target: Cell) -> Cell:
    """離 target 最近的成員格。平手時取字典序最小的——退休是跨代生效的事實，
    同一個盤面每次都要退休同一格。"""
    return min(
        cells,
        key=lambda cell: ((cell[0] - target[0]) ** 2 + (cell[1] - target[1]) ** 2, cell),
    )


def _bearing(axis: str, wanted: float) -> str:
    if axis == "x":
        return "east" if wanted > 0 else "west"
    return "south" if wanted > 0 else "north"


def _axis_of(direction: str) -> str:
    return "x" if direction in ("east", "west") else "y"


def _commanded(expected: Point | None) -> bool:
    return expected is not None and math.hypot(*expected) >= board.EDGE_SHIFT_PX


def _lost(carried: dict[str, float] | None, expected: Point | None) -> dict[str, float] | None:
    """島嶼沒入帳的指令位移。None 一路傳染：沒有指令可當包絡的島，往後也沒有。"""
    if carried is None:
        return None
    if expected is None:
        return dict(carried)
    return {"x": carried["x"] + abs(expected[0]), "y": carried["y"] + abs(expected[1])}


def _within(box: tuple[float, float, float, float], region: Region) -> bool:
    x, y, w, h = region
    return box[0] >= x and box[1] >= y and box[2] <= x + w and box[3] <= y + h


def _overlaps(box: tuple[float, float, float, float], region: Region) -> bool:
    x, y, w, h = region
    return box[0] < x + w and box[2] > x and box[1] < y + h and box[3] > y
