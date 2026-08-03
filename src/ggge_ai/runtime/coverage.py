"""世界空間的四態知識圖：位置一律解自畫面內容，永不由上一張位置加上移動量累加。

覆蓋模型 v3（0802 使用者核可，docs/survey-anchor-v3-proposal.md）。第 1 到第 7 輪
實機驗證修掉的問題——量測凍值、靜態畫面誤判成移動、拼接錯位、單位數膨脹到真實
數量的三倍——全部是累加骨架的病：位置靠累加，每一次量測都是單點故障。v3 把位置
的來源換成畫面裡看得見的東西：

- **歸零**：往西北連續用力推，直到畫面連續兩次不再變化（被地圖邊卡住）＝西北角。
  以那一幀錨定世界原點。角落是可重現的絕對位置，所以跨回合重新歸零會回到同一套
  座標，地圖幾何（格網、界線、地標）不必重學。
- **地標**：定位成功的幀看到哪一側的地圖終止邊，就把那一側的世界像素記下來。往後
  任何一幀只要看得到同一側，那一軸的座標直接讀出來——單側可見鎖一軸、角落可見
  鎖兩軸。
- **對回已知地圖**：兩軸都讀不到地標時（中央帶），拿畫面裡的單位排列對回已記目擊
  （`board.relocalise`），影像複驗消掉整數格歧義。**背景圖案不當位置證據**（0803
  第 10 輪定讞）：不隨鏡頭動的星空層在整區量測裡面積佔優，它給的是「畫面沒動」
  的高信心錯答，會把唯一正確的候選否掉。
- **每一個候選各自複驗**：候選座標套上去之後，這一幀的機體要落回知識圖已記的目擊
  （佔位一致性）。複驗**絕不與產生候選的那一次量測同源**——拿量測回頭替自己背書是
  恆等式不是複驗。一個候選過不了就換下一個，全部過不了才丟整幀。
- **對不回來就丟棄**：定位不出來的幀整張丟掉，不進緩衝、不重錨、不累積。連續丟到
  沒耐心就推回角落重新歸零，成本有上限（地圖就這麼大）。

- **知識圖**：每一格四態可分。EMPTY（掃過沒單位）與 UNKNOWN（沒掃）是兩件不同的
  事實，STALE（前代有單位、這代還沒重掃）是第三件。混在一起就沒有缺口可言。
- **界線**：四個方向各自「未發現／已定於某一格線」，一律目視（看到地圖終止邊），
  不從「推不動了」推論。地圖幾何不衰效，只有單位知識衰效。
- **待掃格**：界內、與已測繪區相鄰、還不是現況的格。沒有待掃格且四面界線都定＝完成。

兩條安全網不變式原樣保留：**無「量錯寫入」路徑**（定位不出來、或與已記地標矛盾的
幀整張丟棄，一格都不寫）、**無「無聲丟失」路徑**（沒觀測到的界內格永遠是 UNKNOWN，
待掃格一定把它排回補掃）。
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


# 還不是現況的兩態：完成判準要求界內一格都不剩，待掃格也只挑這兩態。
GAPS = (Knowledge.UNKNOWN, Knowledge.STALE)
COMPASS: tuple[str, ...] = ("west", "east", "north", "south")

# 一幀的處置。ZEROING ＝ 還在往角落推、本來就不談座標，與「試著定位但定不出來」
# （BROKEN）分開記，流水帳才看得出這一幀是沒必要定位還是定位失敗。
ACCEPTED = "accepted"
STALLED = "stalled"
BROKEN = "broken"
ZEROING = "zeroing"

# 掃描的三個階段：推去角落歸零 → 沿邊繞一圈 → 補中央的缺口。
ZERO = "zero"
TOUR = "tour"
FILL = "fill"

# 歸零推去的角落（兩個方向都推到卡住才算到角），與繞邊的順序。
ZERO_CORNER: tuple[str, ...] = ("west", "north")
TOUR_ROUTE: tuple[str, ...] = ("east", "south", "west")

# 這一幀的座標是怎麼來的（進遙測的 shift.source）。
SOURCE_EDGE = "edge"
SOURCE_MATCH = "match"
SOURCE_STILL = "still"
SOURCE_ANCHOR = "anchor"

# 丟棄的理由。
EDGE_MISMATCH = "edge_mismatch"
UNMATCHED = "unmatched"
PICTURE_REFUSED = "picture"
OCCUPANCY_REFUSED = "occupancy"
# 複驗是誰放行的（進遙測，流水帳才看得出這一幀憑什麼被收下）。
BY_OCCUPANCY = "occupancy"
BY_EDGES = "edges"
BY_PICTURE = "picture"
BY_LANDMARK = "landmark"
# 目視終止邊與已記地標容許的落差（格距的比例）。半格＝格座標還指得到同一格。
EDGE_TOLERANCE = 0.5
# 佔位一致性要幾台機體才裁得動「這個候選差了一整格」。一台配得上可能只是巧合
# （盤面上二十幾台，隔壁格剛好也站著一台的機率不低）；兩台一起指向同一格才是證據。
OCCUPANCY_QUORUM = 2
# 逐窗影像複驗給兩個假設的對位餘裕（像素）。問的是「差一整格的兩個位置哪個對」，
# 而候選本身帶著幾個像素的量測誤差——逐像素硬比會連正確的假設一起判否。
PICTURE_SLACK = 3

# 一次推移手勢的內容位移上限（世界像素）。前後幀要留得下八成以上的重疊，中央帶
# 才對得回已知地圖。
LEG_LIMIT: dict[str, float] = {"x": board.MAP_REGION[2] / 4.0, "y": board.MAP_REGION[3] / 4.0}
# 手指行程換算內容位移的固定比例（0730 實測 250px 手勢推出約 570-600px）。v3 不再
# 逐次修正它——推移只需要「往那個方向推一把」，距離準不準不影響座標。
NOMINAL_GAIN = 2.3
# 一次畫面沒動不算卡住：起手點落在單位精靈上會被遊戲吃掉，畫面同樣不動。連兩次
# 才算數（提案第二節的「連續兩次畫面不再變化」）。
STALL_CONFIRM = 2
# 連續丟掉這麼多幀就推回角落重新歸零：帶著不知道位置的鏡頭繼續走沒有上界。
LOST_PATIENCE = 3
# 角落讀不出格網時退一步再回來的次數上限。用完就誠實停在沒掃完。
ZERO_TRIES = 3
# 挑待掃格目標時 STALE 聚類的距離折扣（含 STALE ＝ 單位大概率在附近，威脅評估最需要）。
STALE_WEIGHT = 0.5
# 推移次數的保險絲：只防**單一回合**內的失控，不是整場戰鬥的額度，也不是完成判準。
# 跨回合累積的話十幾回合就燒斷，之後 fused 恆真、掃描永遠完不成＝整關卡死。
LEG_BUDGET = 200

_STILL = Shift(0.0, 0.0, 1.0, "still")
_SIDES: dict[str, tuple[str, str]] = {"x": ("west", "east"), "y": ("north", "south")}


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

    定位在先、寫圖在後：`Survey` 先用 offset=(0,0) 生一張 view 讀它的螢幕事實（格線
    框、終止邊、單位位置），解出座標之後才 `shifted()` 到世界座標寫進知識圖。
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
    # 目擊到的那幾側終止邊在**螢幕**上的位置（所以 shifted() 同樣不必動它）。它與
    # lattice 框各說各話：框是取樣帶讀到的線位，邊界來自全幀掃描，看得到框外。
    borders: tuple[tuple[str, float], ...] = ()
    # 生這張 view 的那一次 observe 的序號，與流水帳同一列，join 得回 tick／probe。
    sequence: int = 0

    def shifted(self, delta: Point) -> FrameView:
        return replace(self, offset=(self.offset[0] + delta[0], self.offset[1] + delta[1]))

    def world(self, point: Point) -> Point:
        return (point[0] + self.offset[0], point[1] + self.offset[1])


@dataclass(frozen=True)
class Reading:
    """一幀的裁決。BROKEN ＝ 定位不出來或與地標矛盾，呼叫端要知道那一幀被丟了。"""

    verdict: str
    shift: Shift
    offset: Point
    reason: str = ""
    # 定位的逐步驟自述（讀到哪幾側的地標、單位排列對上沒、影像複驗怎麼說）。純
    # 觀察者：沒有任何判斷讀它，流水帳讀它。
    detail: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Leg:
    """一次推移手勢：手指行程＋預期的內容位移（世界像素，帶號；內容與鏡頭反向）。

    expected 只進流水帳與「畫面到底有沒有動」的影像複驗，**不進座標計算**——手勢的
    量在 v3 完全退出定位。
    """

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
    # 的那幾格就是這樣（鏡頭夾在界線上，橫幅在螢幕座標固定不動）。它們不是被
    # 忘掉——退休是明寫的事實，逐 tick 進流水帳，只是不再要求待掃格去補。
    unreachable: set[Cell] = field(default_factory=set)
    # 目擊的**世界像素**座標，不是格心：對回已知地圖那一步要拿它跟當下的密度峰
    # 配對投票，量化到格心會讓靜態單位的票散進不同的桶、眾數湊不出來。
    marks: dict[Cell, Sighting] = field(default_factory=dict)

    def knowledge(self, cell: Cell) -> Knowledge:
        return self.state.get(cell, Knowledge.UNKNOWN)

    @property
    def bounded(self) -> bool:
        return all(direction in self.boundary for direction in COMPASS)

    @property
    def complete(self) -> bool:
        """建構性判準：四面界線都定 ∧ 界內沒有 UNKNOWN／STALE。"""
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
        精靈或特效遮住、密度峰沒過門檻），不是單位離開的證據。無條件先鋪 EMPTY
        的話，一次漏檢就抹掉先前記下的 UNIT，整輪掃完只剩最後一次看到的那幾台。

        單位離開的合法證據只有跨代：`expire()` 把 UNIT 降成 STALE 之後，同款的
        view 照常把它蓋成 EMPTY——那一代的敵人真的動過。

        **EMPTY 毯與目擊兩條口徑不同**：毯子要格線背書（`covered`），目擊只要讀得
        清楚（`readable`）。密度峰不依賴格線，一幀讀不出格線不代表看不見機體。
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

    def set_boundary(self, direction: str, line: int) -> int:
        """定界線＋裁掉線外的每一筆知識。

        **界線＝該側最外一格看得清楚的格，線外沒有地圖。** 線外還留著紀錄就是舊
        座標系的殘留，從此不會有任何一幀去覆蓋，變成永久鬼影混進單位帳（0801 第 4
        輪：journal 的 84 筆單位格裡有 29 筆的欄座標整段落在最終東界之外）。同方向
        第二次定案（改判）走同一條裁剪。
        """
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

        限制在測繪區周邊是為了讓還沒定界線的方向有界可推——真正的無限外擴由界線
        另外處理，不然界內在四面都定之前是無限大。
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
        """四面界線都定之後界內每一格的缺口。還沒定滿時界內無限大，退回待掃格。"""
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
        """挑一個待掃格聚類：近者優先，含 STALE 的聚類加權優先。"""
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
        移進來）。charted 與界線保留——它們是地圖的幾何，不隨誰站哪裡改變。
        """
        for cell, known in list(self.state.items()):
            if known is Knowledge.UNIT:
                self.state[cell] = Knowledge.STALE
            elif known is Knowledge.EMPTY:
                self.state[cell] = Knowledge.UNKNOWN

    def units(self) -> tuple[tuple[Cell, str | None], ...]:
        """現況的單位格。**STALE 不出現**——前代的站位永遠不能當現況。

        四面界線都定之後只回界內，跟 `census()` 同一個口徑：流水帳的單位清單與普查
        本來就該對得起來，界外的 mark 是錯座標，算進台數就是憑空多出來的鬼影。
        """
        return tuple(
            (cell, mark.hint)
            for cell, mark in sorted(self.marks.items())
            if self.knowledge(cell) is Knowledge.UNIT and self._inside(cell)
        )

    def sightings(self) -> tuple[Point, ...]:
        """**這一代**已記目擊的世界像素座標——把新幀對回已知地圖的比對標的。

        只給 UNIT 不給 STALE：STALE 是敵方回合之前的站位，那些機體早就動過了，拿它
        當比對標的等於用過期的星圖定位。同樣只回界內：界外 mark 的世界像素本身就是
        錯的（線外沒有地圖），拿它比對只會把解出來的座標帶歪。
        """
        return tuple(
            mark.point
            for cell, mark in sorted(self.marks.items())
            if self.knowledge(cell) is Knowledge.UNIT and self._inside(cell)
        )

    def _inside(self, cell: Cell) -> bool:
        """四面界線都定才談界內：只定了一兩面時界內仍是無限大，濾了等於憑半套界線
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
class Survey:
    """一次盤面全覽的世界模型：歸零、沿邊繞圈、補中央，外加四態知識圖。

    只吃幀與推移指令，回報這一幀被怎麼收下。行動語意（微步驟名、符號狀態）在 stage
    層——這裡不認識行動詞彙。
    """

    region: Region = board.UNIT_DENSITY_REGION
    holes: tuple[Region, ...] = board.UNIT_DENSITY_HUD_HOLES
    budget: int = LEG_BUDGET
    chart: KnowledgeMap | None = None
    # 四側地圖終止邊的世界像素。定位成功的幀看到哪一側就記哪一側，從此那一側就是
    # 那一軸的絕對讀數。地圖幾何不衰效，所以它跨回合保留——角落可重現，重新歸零
    # 回到的是同一套座標。
    landmarks: dict[str, float] = field(default_factory=dict)
    stance: str = ZERO
    route: list[str] = field(default_factory=lambda: list(TOUR_ROUTE))
    # 最近一張收下的幀（判「畫面有沒有動」用）。
    previous: np.ndarray | None = None
    # 最近一張**定位成功**的幀連同它的座標：對回已知地圖與影像複驗的對手。定位
    # 失敗的幀不會動它——丟棄就是丟棄，不留半套狀態。
    located: tuple[np.ndarray, Point] | None = None
    # 那一幀讀到的螢幕事實（終止邊在螢幕上的位置）。複驗要拿它跟這一幀的同一側
    # 相減，量出一個與像素位移量測互相獨立的內容位移。
    located_view: FrameView | None = None
    stalls: dict[str, int] = field(default_factory=dict)
    # 推不動當下的世界座標（軸別）：鏡頭離開就不再是夾住的狀態，見 `_clamped`。
    clamps: dict[str, float] = field(default_factory=dict)
    # 那個方向被確認推不動幾輪。退休格子是跨代生效的，所以要兩輪才算數。
    bumped: dict[str, int] = field(default_factory=dict)
    # 最近一張 view 目視到終止邊的那幾側。存側名不存座標：終止邊在不在畫面上是
    # 螢幕事實，與解出什麼座標無關。
    sighted: frozenset[str] = frozenset()
    lost: int = 0
    tries: int = 0
    retreat: bool = False
    # 地標算出來的座標與已記目擊對不上的連續次數，見 `_contest`。
    contested: int = 0
    unlocalised: int = 0
    zeroings: int = 0
    legs: int = 0
    generation: int = 0
    # observe 的呼叫序號（從 1 起）。純識別用：每一張 view 帶著它出生的序號。
    observes: int = 0
    last_view: FrameView | None = None

    @property
    def offset(self) -> Point | None:
        return None if self.located is None else self.located[1]

    @property
    def anchored(self) -> bool:
        """世界有原點，而且我們知道鏡頭現在在哪。"""
        return self.located is not None

    @property
    def complete(self) -> bool:
        return self.chart is not None and self.chart.complete

    @property
    def fused(self) -> bool:
        return self.legs >= self.budget

    def observe(self, frame: np.ndarray, leg: Leg | None = None) -> Reading:
        """吃一幀：解它的座標，解得出來就寫進知識圖，解不出來就丟掉。"""
        self.observes += 1
        still = self.previous is not None and self._unchanged(self.previous, frame, leg)
        if leg is not None:
            self._tally(leg.direction, still)
        reading = self._zeroing(frame) if self.stance == ZERO else self._place(frame, still)
        self.previous = frame
        return reading

    def plan_leg(self) -> Leg | None:
        """下一把往哪推。None ＝ 沒得推了（掃完、保險絲燒斷，或角落讀不出格網）。"""
        if self.fused:
            if not self.complete:
                log.warning("survey spent %d pans before the frontier emptied", self.budget)
            return None
        if self.stance == ZERO:
            return self._zero_leg()
        if self.complete:
            return None
        if self.stance == TOUR:
            leg = self._tour_leg()
            if leg is not None:
                return leg
            self.stance = FILL
        assert self.chart is not None
        for _ in range(len(self.chart.targets()) + 1):
            leg = self._aim()
            if leg is not None:
                return leg
            if self.complete:
                return None
        return self._probe()

    def viewport(self) -> Point:
        x, y, w, h = self.region
        offset = self.offset or (0.0, 0.0)
        return (x + w / 2.0 + offset[0], y + h / 2.0 + offset[1])

    def expire(self) -> None:
        """回合交界：單位知識降級，地圖幾何留著，鏡頭當作不知道在哪。

        敵方回合鏡頭會被遊戲拉去演出，兩個回合之間的位移量不出來，所以 v3 不再嘗試
        跨回合接回去——直接推回西北角重新歸零。角落是可重現的絕對位置，歸零回到的
        是同一套世界座標，所以界線與地標一格都不必重學。

        推移次數的保險絲跟著歸零：衰效之後整張圖都要重掃，這一回合不該由上一回合
        預付。不歸零的話十幾回合就燒斷，之後每一回合都直接判掃不完。
        """
        self.generation += 1
        self.legs = 0
        if self.chart is None:
            return
        self.chart.expire()
        self._rezero("the enemy phase moved the camera")

    def units(self) -> tuple[tuple[Cell, str | None], ...]:
        return () if self.chart is None else self.chart.units()

    def summary(self) -> dict[str, object]:
        """逐 tick 進流水帳的覆蓋自述：覆蓋率、待掃格聚類、階段、丟棄與歸零次數。"""
        chart = self.chart
        census = chart.census() if chart is not None else {known.value: 0 for known in Knowledge}
        scope = sum(census.values())
        observed = census[Knowledge.EMPTY.value] + census[Knowledge.UNIT.value]
        pockets = clusters(chart.targets()) if chart is not None else ()
        return {
            "generation": self.generation,
            "anchored": self.anchored,
            "stance": self.stance,
            "bounded": sorted(chart.boundary) if chart is not None else [],
            "boundary": dict(chart.boundary) if chart is not None else {},
            "landmarks": {side: round(value, 1) for side, value in sorted(self.landmarks.items())},
            "sighted": sorted(self.sighted),
            "cells": census,
            "coverage": round(observed / scope, 3) if scope else 0.0,
            "frontier": len(chart.targets()) if chart is not None else 0,
            "clusters": len(pockets),
            "unreachable": len(chart.unreachable) if chart is not None else 0,
            # 退休格逐格明寫：它們同時退出待掃格與缺口，所以 complete 可以在那幾格
            # 從沒被觀測的情況下成立。只記個數的話那條路就是無聲丟失。
            "retired": [list(cell) for cell in sorted(chart.unreachable)]
            if chart is not None
            else [],
            "unlocalised": self.unlocalised,
            "zeroings": self.zeroings,
            "legs": self.legs,
            "units": len(self.units()),
            "complete": self.complete,
        }

    def reset(self) -> None:
        """鏡頭的比例被動過（縮放）：舊世界的像素座標與地標全部作廢，整個重來。"""
        self._forget()
        self.stance = ZERO
        self.route = list(TOUR_ROUTE)
        self.previous = None
        self.located = None
        self.located_view = None
        self.stalls.clear()
        self.clamps.clear()
        self.bumped.clear()
        self.sighted = frozenset()
        self.lost = 0
        self.tries = 0
        self.retreat = False
        self.contested = 0
        self.legs = 0

    # ---- 歸零 ----

    def _zeroing(self, frame: np.ndarray) -> Reading:
        """往西北推的那幾幀：不談座標，只問「推到底了沒」。

        兩個方向都連續兩次推不動＝鏡頭卡在西北角。那一幀還要**看得到**角落至少一側
        的地圖終止邊才算數——手勢被吃掉的畫面同樣不動，目視的邊分得出兩者。
        """
        view = self._view(frame, (0.0, 0.0))
        self.sighted = view.edges
        if not all(self.stalls.get(side, 0) >= STALL_CONFIRM for side in ZERO_CORNER):
            return Reading(ZEROING, _STILL, (0.0, 0.0), "pushing")
        if not self._anchor(frame, view):
            self.tries += 1
            self.retreat = True
            self.stalls.clear()
            log.warning("the corner frame gave no usable world; backing off and trying again")
            return Reading(ZEROING, _STILL, (0.0, 0.0), "unreadable corner")
        assert self.chart is not None
        self.zeroings += 1
        self.stance = TOUR
        self.route = list(TOUR_ROUTE)
        self.stalls.clear()
        self.clamps.clear()
        self.tries = 0
        self.lost = 0
        self.chart.absorb(view)
        self._learn_edges(view, SOURCE_ANCHOR)
        return Reading(ACCEPTED, _STILL, (0.0, 0.0), SOURCE_ANCHOR)

    def _anchor(self, frame: np.ndarray, view: FrameView) -> bool:
        """西北角這一幀就是世界原點。座標是被定義的，不是量出來的。"""
        if not set(ZERO_CORNER) & view.edges:
            return False
        if self.chart is not None and self._clash(view) is not None:
            log.warning("the corner contradicts the landmarks we kept; starting the world over")
            self._forget()
        if self.chart is None:
            lattice = board.find_lattice(frame)
            grid = None if lattice is None else WorldGrid.anchor(lattice)
            if grid is None:
                return False
            self.chart = KnowledgeMap(grid=grid)
        self.located = (frame, (0.0, 0.0))
        self.located_view = view
        self.contested = 0
        return True

    def _forget(self) -> None:
        self.chart = None
        self.landmarks = {}

    def _rezero(self, reason: str) -> None:
        log.info("re-zeroing at the north-west corner: %s", reason)
        self.stance = ZERO
        self.stalls.clear()
        self.clamps.clear()
        self.bumped.clear()
        self.sighted = frozenset()
        self.previous = None
        self.located = None
        self.located_view = None
        self.lost = 0
        self.tries = 0
        self.retreat = False
        self.contested = 0

    # ---- 定位與寫圖 ----

    def _place(self, frame: np.ndarray, still: bool) -> Reading:
        view = self._view(frame, (0.0, 0.0))
        self.sighted = view.edges
        detail: dict[str, object] = {}
        offset, source = self._locate(frame, view, still, detail)
        if offset is None:
            return self._discard(source, detail)
        placed = view.shifted(offset)
        assert self.chart is not None
        shift = self._shift(offset, source)
        self.chart.absorb(placed)
        self._learn_edges(placed, source)
        self.last_view = placed
        self.located = (frame, offset)
        self.located_view = placed
        self.lost = 0
        self.contested = 0
        return Reading(STALLED if still else ACCEPTED, shift, offset, source, detail)

    def _locate(
        self, frame: np.ndarray, view: FrameView, still: bool, detail: dict[str, object]
    ) -> tuple[Point | None, str]:
        """這一幀在哪。先問地標（絕對），問不到就逐個候選試，每一個都要各自過複驗。

        **逐候選複驗、全部過不了才丟整幀**：稀疏地帶的單位排列比對會被巧合的配對投出
        差幾十像素的候選，當場丟掉整幀會讓那一段連環丟幀掃不完；換下一個候選則兩條
        路都還在。
        """
        axes: dict[str, float] = {}
        for axis in ("x", "y"):
            value, agreed = self._from_landmarks(view, axis)
            if not agreed:
                return (None, EDGE_MISMATCH)
            if value is not None:
                axes[axis] = value
        detail["landmarks"] = {axis: round(value, 1) for axis, value in axes.items()}
        recalled = tuple(axis for axis in ("x", "y") if axis not in axes)
        tried: list[dict[str, object]] = []
        detail["tried"] = tried
        refusal = UNMATCHED
        for candidate, source in self._candidates(view, still, axes, detail):
            note: dict[str, object] = {"source": source}
            tried.append(note)
            # 讀得到地標的那一軸由地標說了算，候選只補另一軸——地標是絕對量，拿它去
            # 否決整幀等於連確定的那一軸也一起丟掉。合起來對不對由複驗裁。
            merged = (axes.get("x", candidate[0]), axes.get("y", candidate[1]))
            note["offset"] = [round(value, 1) for value in merged]
            if self._corroborated(frame, view, merged, recalled, source, note):
                return (merged, source)
            refusal = str(note.get("gate", PICTURE_REFUSED))
        if refusal == OCCUPANCY_REFUSED and axes:
            self._contest()
        return (None, refusal)

    def _from_landmarks(self, view: FrameView, axis: str) -> tuple[float | None, bool]:
        """那一軸的座標＝已記地標的世界像素減去它在這一幀螢幕上的位置。

        回 (座標, 兩側說法對不對得上)。兩側都看得到而彼此差超過半格＝至少一側不是
        地圖邊，兩個都不採信——挑一個信就是「量錯寫入」。
        """
        assert self.chart is not None
        values = [
            self.landmarks[side] - screen
            for side in _SIDES[axis]
            for screen in (screen_border(view, side),)
            if screen is not None and side in self.landmarks
        ]
        if not values:
            return (None, True)
        pitch = self.chart.grid.col_pitch if axis == "x" else self.chart.grid.row_pitch
        if max(values) - min(values) > EDGE_TOLERANCE * pitch:
            log.warning("the two %s landmarks disagree by %.1fpx", axis, max(values) - min(values))
            return (None, False)
        return (values[0], True)

    def _candidates(
        self,
        view: FrameView,
        still: bool,
        axes: dict[str, float],
        detail: dict[str, object],
    ) -> Iterable[tuple[Point, str]]:
        """位置的候選來源，由強到弱：兩軸地標 → 沿用上一張 → 單位排列比對。

        三個都讀的是畫面裡的東西——地圖終止邊與已記的單位排列。中央帶剛好空曠無
        單位時排列比對沒有材料，那一幀就是沒有候選，誠實丟掉。
        """
        if len(axes) == 2:
            yield ((axes["x"], axes["y"]), SOURCE_EDGE)
            return
        if still and self.located is not None and self.located[0] is self.previous:
            yield (self.located[1], SOURCE_STILL)
        match = self._constellation(view, detail)
        if match is not None:
            yield (match, SOURCE_MATCH)

    def _constellation(self, view: FrameView, detail: dict[str, object]) -> Point | None:
        """拿畫面裡的單位排列對回這一代已記的目擊。全域比對，不是逐步累加。"""
        assert self.chart is not None
        marks = self.chart.sightings()
        seen = [sighting.point for sighting in view.units]
        drift = board.relocalise(marks, seen)
        detail["match"] = {
            "marks": len(marks),
            "seen": len(seen),
            "drift": None if drift is None else [round(value, 1) for value in drift],
        }
        if drift is None:
            return None
        return (-drift[0], -drift[1])

    def _corroborated(
        self,
        frame: np.ndarray,
        view: FrameView,
        candidate: Point,
        recalled: tuple[str, ...],
        source: str,
        note: dict[str, object],
    ) -> bool:
        """複驗：把候選座標套上去，看這一幀的機體落不落回知識圖已記的目擊。

        **佔位一致性是主判準**。位置對了，畫面上的機體就落回上一輪記下的那幾格；差
        一整格就對不上。判準是**和差一整格的鄰居比**，不是固定的支持數門檻：往沒看過
        的地方推的那幾幀，畫面上多數機體本來就還沒被記過，湊不到固定門檻是物理不是
        矛盾。鄰居配得比較好就代表這個候選差了一整格，當場拒收。

        兩種例外走影像比對，兩種都在遙測裡記名：

        - **單位排列比對導出的候選**本身就是拿已記目擊解出來的，佔位一致性對它同源
          （而且門檻更鬆），背書不算數。
        - **對得上的一台都沒有**（空曠的中央帶，或整片都是沒記過的新機體）時佔位
          一致性沒有材料。
        """
        assert self.chart is not None
        marks = self.chart.sightings()
        seen = tuple(sighting.point for sighting in view.units)
        pitches = {"x": self.chart.grid.col_pitch, "y": self.chart.grid.row_pitch}
        support = _fits(marks, seen, candidate, pitches)
        rivals: dict[str, int] = {}
        # 鄰居**兩軸都要試**，不只補位那幾軸：地標算出來的軸不會跟自己矛盾，唯一驗得到
        # 它的地方就是這裡（東／南地標必然是在那一側還沒有地標時記下的，來自補位來源）。
        for axis in ("x", "y"):
            for sign in (1.0, -1.0):
                nudged = (
                    (candidate[0] + sign * pitches["x"], candidate[1])
                    if axis == "x"
                    else (candidate[0], candidate[1] + sign * pitches["y"])
                )
                rivals[f"{axis}{sign:+.0f}"] = _fits(marks, seen, nudged, pitches)
        best = max(rivals.values(), default=0)
        note["occupancy"] = {
            "marks": len(marks),
            "seen": len(seen),
            "support": support,
            "rivals": rivals,
        }
        if best >= OCCUPANCY_QUORUM and support < best:
            note["gate"] = OCCUPANCY_REFUSED
            return False
        if support > best and source != SOURCE_MATCH:
            note["gate"] = BY_OCCUPANCY
            return True
        return self._pictured(frame, view, candidate, recalled, note)

    def _pictured(
        self,
        frame: np.ndarray,
        view: FrameView,
        candidate: Point,
        recalled: tuple[str, ...],
        note: dict[str, object],
    ) -> bool:
        """影像比對這一路。**佐證不得與候選同源**——拿產生候選的那一次量測回頭背書
        是恆等式，不是複驗。

        由強到弱：目視終止邊的位移（絕對量，任何週期內容都動不了它）→ 逐窗影像
        複驗（只答得出「這個位移到底發生了沒」）。
        """
        if not recalled:
            note["gate"] = BY_LANDMARK
            return True
        if self.located is None:
            note["gate"] = PICTURE_REFUSED
            return False
        offset = self.located[1]
        implied = {"x": offset[0] - candidate[0], "y": offset[1] - candidate[1]}
        pitches = {"x": self.chart.grid.col_pitch, "y": self.chart.grid.row_pitch}

        moved = self._edges_moved(view, note)
        if all(axis in moved for axis in recalled):
            note["gate"] = BY_EDGES
            return all(
                abs(moved[axis] - implied[axis]) <= EDGE_TOLERANCE * pitches[axis]
                for axis in recalled
            )
        return self._outbids(frame, view, implied, recalled, pitches, note)

    def _outbids(
        self,
        frame: np.ndarray,
        view: FrameView,
        implied: dict[str, float],
        recalled: tuple[str, ...],
        pitches: dict[str, float],
        note: dict[str, object],
    ) -> bool:
        """最後一關：這個位移要**贏過自己差一整格的鄰居**，畫面才算背書。

        逐窗把兩個假設拿去對畫面（`board.null_check`），對得比較準的那個得一票。拿
        「有沒有動」當對手是不夠的——格線是週期訊號，差整數格的錯值照樣把線對得
        整整齊齊，那個問法答不出來（0802 合成世界實測，差兩列的錯值就是這樣過關的）。
        差一整格的鄰居問法就分得出來：只有真值那一個位移能讓地表紋理也對上。

        鄰居也對不上（兩邊都爛）＝這一幀誰都放不下，拒收。
        """
        assert self.located is not None
        before = self.located[0]
        probes = self._probes(view)
        verdicts: dict[str, str] = {}
        for axis in recalled:
            for sign in (1.0, -1.0):
                rival = dict(implied)
                rival[axis] += sign * pitches[axis]
                verdicts[f"{axis}{sign:+.0f}"] = board.null_check(
                    before,
                    frame,
                    (implied["x"], implied["y"]),
                    probes,
                    reference=(rival["x"], rival["y"]),
                    slack=PICTURE_SLACK,
                )
        note["picture"] = verdicts
        won = bool(verdicts) and all(
            verdict == board.NULL_MOVED for verdict in verdicts.values()
        )
        note["gate"] = BY_PICTURE if won else PICTURE_REFUSED
        return won

    def _probes(self, view: FrameView) -> tuple[Point, ...]:
        """逐窗影像複驗的取樣窗心：機體優先，不夠就補地圖區內均勻鋪的一片窗。

        補的窗限在格線覆蓋的矩形內：格線以外那片背景不隨鏡頭動（實機是地圖外的深色
        虛空，下稱星空），拿它問位移只會系統性地投給位移比較小的那個假設。
        """
        points = [sighting.point for sighting in view.units]
        box = view.lattice
        for point in board.OVERLAP_PROBES:
            if box is None or (
                box[0] <= point[0] <= box[0] + box[2] and box[1] <= point[1] <= box[1] + box[3]
            ):
                points.append(point)
        return tuple(points)

    def _edges_moved(self, view: FrameView, note: dict[str, object]) -> dict[str, float]:
        """同一側的地圖終止邊在兩幀螢幕上移動了多少＝內容位移（v2.10 的絕對量測）。

        地圖的物理邊界不週期，格線與同型機編隊那種差整數個週期的誤配對它無效，所以
        它與像素位移量測完全獨立。代價是常常缺席：同一側要在兩幀都讀得到。
        """
        before = self.located_view
        if before is None:
            return {}
        first = dict(before.borders)
        now = dict(view.borders)
        moved: dict[str, float] = {}
        for axis in ("x", "y"):
            value = board.edge_shift(first, now, axis)
            if value is not None:
                moved[axis] = value
        if moved:
            note["edges"] = {axis: round(value, 1) for axis, value in moved.items()}
        return moved

    def _contest(self) -> None:
        """有地標背書的幀連著被佔位一致性判否：地標本身可能就是錯的。

        東側與南側的地標必然是在該側還沒有地標時記下的，那時該軸的座標只能來自補位
        來源。地標跨代保留、界線一定案就把線外的知識整批裁掉，所以寫錯了要有回收路徑
        ——`_forget` 之後整張圖從角落重來。

        單獨一幀對不上可能只是偵測漏，代價是丟一幀；連著 `LOST_PATIENCE` 幀都有兩台
        以上的機體指著隔壁那一格，就不是巧合了。
        """
        self.contested += 1
        if self.contested < LOST_PATIENCE:
            return
        log.warning("the landmarks keep contradicting the recorded sightings; starting the world over")
        self._forget()
        self._rezero("the landmarks contradict the recorded sightings")

    def _discard(self, reason: str, detail: dict[str, object]) -> Reading:
        """定位不出來的幀整張丟掉：不進緩衝、不重錨、不累積。"""
        self.unlocalised += 1
        self.lost += 1
        log.warning("frame %d could not be placed (%s); discarding it", self.observes, reason)
        offset = self.offset or (0.0, 0.0)
        if self.lost >= LOST_PATIENCE:
            self._rezero(f"{self.lost} frames running could not be placed")
        return Reading(BROKEN, _STILL, offset, reason, detail)

    def _shift(self, offset: Point, source: str) -> Shift:
        """這一幀相對上一張定位成功的幀，內容在螢幕上移動了多少。

        **推導值不是量測值**：兩個座標相減。遙測要它才看得出這一把推移實際走了多遠。
        """
        if self.located is None:
            return _STILL
        before = self.located[1]
        return Shift(before[0] - offset[0], before[1] - offset[1], 1.0, source)

    def _view(self, frame: np.ndarray, offset: Point) -> FrameView:
        span = board.read_span(frame)
        view = FrameView(
            offset=offset,
            units=board.find_sightings(frame, self.region),
            region=self.region,
            holes=self.holes,
            lattice=None if span is None else span.box,
            edges=frozenset() if span is None else span.edges,
            borders=() if span is None else span.borders,
            sequence=self.observes,
        )
        self.last_view = view
        return view

    def _learn_edges(self, view: FrameView, source: str) -> None:
        """定位成功的幀看到哪一側的終止邊，就把那一側記成地標並定下界線。

        0723 定則：界線只目視、永不推論。第一次記下就不再改——地標與界線跨代保留，
        寫錯的代價是永久的，所以矛盾的處置是丟棄那一幀（`_clash`），不是改地標。

        **沿用上一張座標的幀不准寫地標**：那一幀沒有帶來任何新的位置證據，讓一次
        「畫面沒動」的判斷定死一條跨代不改的線，代價與收益完全不成比例。
        """
        chart = self.chart
        if chart is None or source == SOURCE_STILL:
            return
        for direction in sorted(view.edges):
            border = sighted_border(view, direction)
            if border is None:
                continue
            if direction not in self.landmarks:
                self.landmarks[direction] = border
                log.info("landmark %s recorded at world x/y %.1f", direction, border)
            if direction not in chart.boundary:
                line = _border_cell(chart.grid, direction, self.landmarks[direction])
                chart.set_boundary(direction, line)
                log.info("boundary %s sighted at cell %s", direction, line)

    def _clash(self, view: FrameView) -> str | None:
        """角落這一幀目視的終止邊與上一代留下的地標差超過半格。

        只有歸零那條路用得到：那裡的座標是被定義成 (0,0) 的，不是從地標算回來的，
        所以地標有沒有跟著對得上是獨立的問題。走定位那條路的幀不需要這一關——地標
        算出來的座標必然貼著地標，而同軸兩側對不對得上在 `_from_landmarks` 就裁了。
        """
        if self.chart is None:
            return None
        for direction in sorted(view.edges):
            known = self.landmarks.get(direction)
            border = sighted_border(view, direction)
            if known is None or border is None:
                continue
            pitch = _pitch_of(self.chart.grid, direction)
            if abs(border - known) > EDGE_TOLERANCE * pitch:
                log.warning(
                    "the sighted %s edge sits %.1fpx from the landmark; dropping the frame",
                    direction,
                    border - known,
                )
                return f"{EDGE_MISMATCH}:{direction}"
        return None

    # ---- 畫面有沒有動 ----

    def _unchanged(self, previous: np.ndarray, frame: np.ndarray, leg: Leg | None) -> bool:
        """畫面到底有沒有動——只回布林不回位移。

        唯一的佐證是逐精靈窗的影像複驗：拿「動了指令那麼多」對「鏡頭沒動」問畫面。
        整區灰階比對一律不用——不隨鏡頭動的星空層在整區裡面積佔優，它答的是背景沒動
        不是地圖沒動（0803 第 10 輪：星空帶 response 0.766、地圖帶 0.041，而真實位移
        −184px 只在近排帶量得到）。

        **「沒動」要有人指著畫面說沒動**：問不出來（沒有指令可問、或裁判沒得看）一律
        當作動過。反過來寫會讓空白幀被判靜止，而靜止的處置是沿用上一張的座標——下一張
        真的移動過的幀於是以舊座標寫進圖，那正是「量錯寫入」（0802 合成世界實測，空白
        幀之後長出兩格鬼影）。
        """
        if leg is None:
            return False
        return board.null_check(previous, frame, leg.expected) == board.NULL_STILL

    def _tally(self, direction: str, still: bool) -> None:
        """推不動的次數（方向別）。連兩次才算卡住——一次可能只是手勢被吃掉。

        推得動就把那個方向的帳全部歸零：會動的方向不是地圖邊。
        """
        if not still:
            self.stalls.pop(direction, None)
            self.clamps.pop(direction, None)
            self.bumped.pop(direction, None)
            return
        hits = self.stalls.get(direction, 0) + 1
        self.stalls[direction] = hits
        offset = self.offset
        if hits == STALL_CONFIRM and offset is not None:
            self.clamps[direction] = offset[0 if _axis_of(direction) == "x" else 1]
            self.bumped[direction] = self.bumped.get(direction, 0) + 1

    # ---- 推去哪 ----

    def _zero_leg(self) -> Leg | None:
        """往西北角推。兩個方向輪流推到卡住，卡住了還讀不出世界就退一步再來。"""
        if self.retreat:
            self.retreat = False
            return self._leg(_opposite(ZERO_CORNER[0]), board.PAN_MAX_REACH * NOMINAL_GAIN)
        if self.tries >= ZERO_TRIES:
            log.warning("the north-west corner never yielded a world; the survey stops here")
            return None
        for side in ZERO_CORNER:
            if self.stalls.get(side, 0) < STALL_CONFIRM:
                return self._leg(side, board.PAN_MAX_REACH * NOMINAL_GAIN)
        return None

    def _tour_leg(self) -> Leg | None:
        """沿邊繞一圈：東、南、西各推到那一側的終止邊進畫面或推不動為止。"""
        while self.route:
            direction = self.route[0]
            if direction in self.sighted or self.stalls.get(direction, 0) >= STALL_CONFIRM:
                self.route.pop(0)
                continue
            return self._leg(direction, LEG_LIMIT[_axis_of(direction)])
        return None

    def _aim(self) -> Leg | None:
        """挑一個待掃格聚類推一把。推不動（該推的方向都夾在邊上）就把目標退休——那一格
        從任何到得了的鏡頭位置都看不清楚，硬要它只會原地空轉。

        退休的一定是**聚類成員**：L 形聚類的質心根本不在聚類裡，退休它既不會讓目標
        清單變短（每次都挑到同一團＝活鎖），又把一格可能是 EMPTY 的格子跨代排除掉
        ＝無聲丟失。一次退休一格，迴圈才保證嚴格縮小。
        """
        chart = self.chart
        if chart is None:
            return None
        pocket = chart.choose(self.viewport())
        if pocket is None:
            return None
        target = _centroid(pocket)
        for axis, wanted in self._needs(target):
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

    def _needs(self, target: Cell) -> list[tuple[str, float]]:
        """把目標格**推進偵測帶**還差多少（軸別，帶號），差得多的軸排前面。

        算的是「進不進得了帶」而不是「離視野中心多遠」：目標已經在帶內的那一軸推它
        只是把它推出去，而另一軸夾在邊上推不動——兩者一湊就是東西向來回空推的活鎖
        （0802 合成世界實測，補中央階段整段來回 100px）。兩軸都不差還是缺口，代表它
        被 HUD 挖洞或終止邊蓋著，那就該退休。
        """
        assert self.chart is not None
        grid = self.chart.grid
        offset = self.offset or (0.0, 0.0)
        x, y, w, h = self.region
        box = grid.box_of(target)
        bands = (
            ("x", box[0], box[2], x + offset[0], x + w + offset[0], grid.col_pitch),
            ("y", box[1], box[3], y + offset[1], y + h + offset[1], grid.row_pitch),
        )
        out: list[tuple[str, float]] = []
        for axis, low, high, band_low, band_high, pitch in bands:
            margin = pitch / 2.0
            if low < band_low + margin:
                out.append((axis, low - band_low - margin))
            elif high > band_high - margin:
                out.append((axis, high - band_high + margin))
            else:
                out.append((axis, 0.0))
        if any(abs(value) >= 1.0 for _, value in out):
            return sorted(out, key=lambda item: -abs(item[1]))
        return self._escapes(target)

    def _escapes(self, target: Cell) -> list[tuple[str, float]]:
        """目標已經在偵測帶裡卻還是缺口＝它壓在 HUD 挖洞底下。挪開最少的那一邊。

        洞在螢幕座標固定不動，鏡頭一動格子就從洞底下移出來——所以「洞蓋著」不是
        永久事實，是這個鏡頭位置的事實。不算這一步的話，暫時被回合橫幅蓋到的格會
        當場退休，而退休是跨代生效的（0802 合成世界實測退掉四格最西的中段）。
        """
        assert self.chart is not None
        offset = self.offset or (0.0, 0.0)
        box = _screen_box(self.chart.grid, target, offset)
        wanted: list[tuple[str, float]] = []
        for hx, hy, hw, hh in self.holes:
            if not _overlaps(box, (hx, hy, hw, hh)):
                continue
            wanted.extend(
                [
                    ("x", box[2] - hx + 1.0),
                    ("x", box[0] - (hx + hw) - 1.0),
                    ("y", box[3] - hy + 1.0),
                    ("y", box[1] - (hy + hh) - 1.0),
                ]
            )
        # 每個候選都要**真的**把格子挪到看得清楚的地方：躲開一個洞卻掉進另一個洞或
        # 掉出偵測帶的候選一律不算數，不然兩個洞會把規劃器夾在中間來回空推。
        clear = [move for move in wanted if self._exposes(box, move)]
        return sorted(clear, key=lambda item: abs(item[1]))

    def _exposes(self, box: tuple[float, float, float, float], move: tuple[str, float]) -> bool:
        axis, value = move
        shifted = (
            (box[0] - value, box[1], box[2] - value, box[3])
            if axis == "x"
            else (box[0], box[1] - value, box[2], box[3] - value)
        )
        return _within(shifted, self.region) and not any(
            _overlaps(shifted, hole) for hole in self.holes
        )

    def _probe(self) -> Leg | None:
        """沒有待掃格可挑時，還沒定界線的方向自己就是強制待掃格——往那邊推去找邊。"""
        fixed = self.chart.boundary if self.chart is not None else {}
        open_sides = [
            direction
            for direction in COMPASS
            if direction not in fixed and not self._clamped(direction)
        ]
        if not open_sides:
            return None
        direction = open_sides[self.legs % len(open_sides)]
        return self._leg(direction, LEG_LIMIT[_axis_of(direction)])

    def _clamped(self, direction: str) -> bool:
        """往這個方向再推收不到覆蓋。兩個來源並列，任一成立即成立：

        1. **目視終止邊**：畫面看得到那一側的格網終止邊，邊外是虛空，再推只是把虛空
           推進畫面。鏡頭移開之後那一側自然讀不到，下一幀就解除。
        2. **推不動當下的世界座標**：連兩次推不動的那一點，而且那個方向要**被確認過
           兩輪**。起手點連續兩次都落在單位精靈上就是連兩次推不動，跟到邊長得一模
           一樣；認一輪就封死的話，被吃掉兩把手勢會讓整欄格子當場退休（0802 合成
           世界實測退掉最東一整欄）。認第二輪最多多花兩把，而退休是跨代生效的。

        這是**規劃層**的節流——定位與簿記一概不看它。
        """
        if direction in self.sighted:
            return True
        line = self.clamps.get(direction)
        offset = self.offset
        if line is None or offset is None or self.bumped.get(direction, 0) < STALL_CONFIRM:
            return False
        return abs(offset[0 if _axis_of(direction) == "x" else 1] - line) < board.EDGE_SHIFT_PX

    def _leg(self, direction: str, wanted: float, target: Cell | None = None) -> Leg:
        reach = min(max(wanted / NOMINAL_GAIN, board.PAN_MIN_REACH), board.PAN_MAX_REACH)
        travel = reach * NOMINAL_GAIN
        dx, dy = board.DIRECTIONS[direction]
        self.legs += 1
        return Leg(direction, reach, (-dx * travel, -dy * travel), target)


def readable(grid: WorldGrid, view: FrameView) -> tuple[Cell, ...]:
    """這一幀讀得清楚的格：整格框都在偵測帶內、且不碰 HUD 挖洞。

    被螢幕邊切一半、或壓在回合橫幅底下的格一律留 UNKNOWN——那裡漏看一台單位是
    沉默的錯，比多推一把貴得多。**這是幾何，不是「掃過」**：見 `covered`。
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
    EMPTY 毯縮到四成）。

    遮罩容差是半格：最外那一排格子的外緣**就是**終止邊，座標差幾個像素就會把它整排
    切掉（0802 合成世界實測：4px 的座標誤差讓最南一列永遠蓋不到，只好整排退休）。半格
    以內的超出仍是界內那一格，真正在線外的格子由界線定案後的裁剪收拾。

    整幀讀不出格線＝零遮罩，這一幀一格都不蓋——單位目擊照收（密度峰不依賴格線）。

    切線用的是**邊界目擊的位置**，不是線位框的邊：邊界掃描讀得到取樣帶以外（實測東緣
    框到 1680、邊界在 1763），拿框當界會把那之間明明有格子的地方一起漏掉。
    """
    if view.lattice is None:
        return ()
    ox, oy = view.offset
    walls = dict(view.borders)
    slack = (EDGE_TOLERANCE * grid.col_pitch, EDGE_TOLERANCE * grid.row_pitch)
    out: list[Cell] = []
    for cell in readable(grid, view):
        box = _screen_box(grid, cell, (ox, oy))
        if "west" in walls and box[0] < walls["west"] - slack[0]:
            continue
        if "east" in walls and box[2] > walls["east"] + slack[0]:
            continue
        if "north" in walls and box[1] < walls["north"] - slack[1]:
            continue
        if "south" in walls and box[3] > walls["south"] + slack[1]:
            continue
        out.append(cell)
    return tuple(out)


def _screen_box(grid: WorldGrid, cell: Cell, offset: Point) -> tuple[float, float, float, float]:
    bx0, by0, bx1, by1 = grid.box_of(cell)
    return (bx0 - offset[0], by0 - offset[1], bx1 - offset[0], by1 - offset[1])


def screen_border(view: FrameView, direction: str) -> float | None:
    """目視終止邊在**螢幕像素**上的位置。定位讀的是這個——它不需要先知道座標。"""
    return dict(view.borders).get(direction)


def _fits(
    marks: Sequence[Point], seen: Sequence[Point], offset: Point, pitches: dict[str, float]
) -> int:
    """這個偏移之下，畫面上有幾台機體落回已記的目擊（同一台在半格內算對上）。"""
    span = (pitches["x"] / 2.0, pitches["y"] / 2.0)
    return sum(
        any(
            abs(point[0] + offset[0] - kx) <= span[0] and abs(point[1] + offset[1] - ky) <= span[1]
            for kx, ky in marks
        )
        for point in seen
    )


def sighted_border(view: FrameView, direction: str) -> float | None:
    """目視終止邊在**世界像素**上的位置（該側地圖的外緣）。沒有目擊就 None。"""
    screen = screen_border(view, direction)
    if screen is None:
        return None
    return screen + view.offset[0 if _axis_of(direction) == "x" else 1]


def _border_cell(grid: WorldGrid, direction: str, border: float) -> int:
    """外緣往界內半格＝該側最外一格的格座標。"""
    pitch = _pitch_of(grid, direction)
    inward = pitch / 2.0 if direction in ("west", "north") else -pitch / 2.0
    if _axis_of(direction) == "x":
        return grid.cell_of((border + inward, grid.phase[1]))[0]
    return grid.cell_of((grid.phase[0], border + inward))[1]


def _pitch_of(grid: WorldGrid, direction: str) -> float:
    return grid.col_pitch if _axis_of(direction) == "x" else grid.row_pitch


def clusters(cells: Sequence[Cell]) -> tuple[tuple[Cell, ...], ...]:
    """四鄰接的連通分量。待掃格要成塊處理才不會在兩個缺口之間來回跑。"""
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


def _opposite(direction: str) -> str:
    return {"west": "east", "east": "west", "north": "south", "south": "north"}[direction]


def _within(box: tuple[float, float, float, float], region: Region) -> bool:
    x, y, w, h = region
    return box[0] >= x and box[1] >= y and box[2] <= x + w and box[3] <= y + h


def _overlaps(box: tuple[float, float, float, float], region: Region) -> bool:
    x, y, w, h = region
    return box[0] < x + w and box[2] > x and box[1] < y + h and box[3] > y
