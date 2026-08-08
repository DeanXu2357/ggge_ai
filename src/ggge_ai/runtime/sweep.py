"""每格點擊清算掃描：不看弧色，逐格點一次，用點擊回饋裁決那一格。

與 `runtime/coverage.py` 的弧色掃描完全並行，兩邊互不呼叫。三分裁決：

- 點空格 → 那一格填出半透明填色（全圖唯一，點別格會搬走）＝ EMPTY
- 點到單位 → 出摘要卡，橫幅停靠敵側＝ENEMY，非敵側＝NPC（第三方，不當我方）
- 點到我方 → 進選擇狀態、鏡頭自動置中 ＝ SHIFTED（重錨後仍記 ALLY）

不變量：帳本**只收點擊裁決過的事實，一律記世界格**。分不出結果的格記 UNSURE
留白——寧可留白不留假帳。

出卡讀取、陣營裁決與 escape 鏈住 `battle/`，這一層不得 import 它（新包自足），
所以那幾件事一律由呼叫端以 callable 注入。
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from . import board
from .board import Cell, MarkerSignature, Point, Region
from .coverage import WorldGrid
from .device import DANGER_BANDS, DangerBand, blocked_for_map_tap
from .settle import SettleReport, await_still

log = logging.getLogger(__name__)

UNKNOWN = "unknown"
EMPTY = "empty"
# 視覺主張的空格：候選過濾說「這一格沒有單位」，沒有點擊背書。與 EMPTY 分級，
# 帳本與 summary 都要看得出來哪一格是點出來的、哪一格是推斷的。
EMPTY_INFERRED = "empty_inferred"
ENEMY = "enemy"
ALLY = "ally"
# 第三方（協力 NPC 機體）：出了卡、停靠側說不是敵方，但「是我方」沒有被選擇態背書。
# 盤面不保證只有敵我兩方，分不出來的一律留在這一類，不硬塞進二分。
NPC = "npc"
UNSURE = "unsure"
DECIDED: tuple[str, ...] = (EMPTY, EMPTY_INFERRED, ENEMY, ALLY, NPC, UNSURE)
# UNIT 級事實永遠只來自點擊：視覺這一層只准說「空」。
INFERABLE: tuple[str, ...] = (EMPTY_INFERRED,)

FILTER_FULL = "full"
FILTER_CANDIDATES = "candidates"
# 帳齊即收：候選過濾之上再加人口普查閘。三方台數都對上真值檔就不再逐格確認空格。
FILTER_ROSTER = "roster"
FILTER_MODES: tuple[str, ...] = (FILTER_FULL, FILTER_CANDIDATES, FILTER_ROSTER)
FILTERED: tuple[str, ...] = (FILTER_CANDIDATES, FILTER_ROSTER)

# 早收豁免的理由碼：這一格從沒被視覺質疑過，也沒被點過，是算術把它劃掉的。
CENSUS_CLOSED = "census_closed"

# 候選檢測的門檻：調參目標是**零漏報**。密度門檻放到最寬、去重距離放鬆，寧可誤報
# （多點一次，成本 4.4s）不可漏報（漏＝該格被推斷成空＝假帳）。
CANDIDATE_MIN_COUNT = 90
CANDIDATE_LOCAL_MAX = board.UNIT_DENSITY_LOCAL_MAX
CANDIDATE_MIN_DIST = 40.0
# 一個密度峰要暈開成候選格的半徑（格距倍數）：峰心是弧環的密度重心，不保證落在
# 單位站的那一格中央，暈開到鄰格才不會漏。
CANDIDATE_HALO_PITCH = 0.75

COMPASS: tuple[str, ...] = ("west", "east", "north", "south")
_SIDES: dict[str, tuple[str, str]] = {"x": ("west", "east"), "y": ("north", "south")}

# 安全點擊窗：上緣避開回合橫幅帶、下緣停在鈕列之上。窗外的格不點，等推鏡把它輪進來。
#
# 右緣 1750 是批 2d（6c8124d）沿用 board.MAP_REGION 的初猜，沒有文件背書。0809 拿
# run 20260809-011740 的 321 張 hub 態窗幀做逐像素變異數審計：x1750–2100（y250–870）
# 全區沒有任何凍結像素，也就是那一帶沒有螢幕固定 HUD，於是東擴到 2050 留 50px 餘裕。
# col-24 九格在東界鏡位只超出舊窗緣 14.6px，被這個初猜擋成結構洞。
#
# 刻意不動 board.MAP_REGION：SCREEN_CENTRE 與格線／相位量測都掛在它身上，整條加寬
# 會把置中期望平移 150px、超出半格容差。
TAP_REGION: Region = (150, 250, 1900, 620)
SCREEN_CENTRE: Point = (board.MAP_REGION[0] + board.MAP_REGION[2] / 2.0, 540.0)

TAP_EMPTY = "empty"
TAP_CARD = "card"
TAP_SHIFTED = "shifted"
# 幾何對得上置中、但畫面沒給出我方選擇態證據：鏡頭要重錨，陣營不記。
TAP_SHIFTED_UNSURE = "shifted_unsure"
TAP_NONE = "none"
# 鏡位對不上這一幀的格線：這一格不裁決，先把鏡位問回來。
TAP_ADRIFT = "adrift"
# 鏡頭被拉走的兩種結局：陣營記不記得下另說，重錨都躲不掉。
TAP_SHIFTS: tuple[str, ...] = (TAP_SHIFTED, TAP_SHIFTED_UNSURE)

SOURCE_EDGE = "edge"
SOURCE_CENTRE = "centre"
SOURCE_MIXED = "mixed"
SOURCE_LOST = "lost"

# 填色要落在**被點的那一格**：半格容差內才算數，落到隔壁就是認錯了地標。
#
# 這一關對「鏡頭被拉走」是瞎的：填色永遠出現在手指按下去的地方，所以它比的是同一
# 個點。鏡位偏掉時它照樣過關，帳本就把鄰格的空記到目標格頭上（20260805-140958 第
# 一窗實證）。管鏡位偏移的是 `aim_drift`。
MARKER_HIT_PITCH = 0.5

# 瞄準閘：點之前先問這一幀的格線相位對不對得上當前鏡位。20260805-140958 十一張
# 剛錨定的 window 幀殘差最大 0.17 格，同一輪鏡頭被選擇態無聲拉走 219px 時是 0.38
# 格——0.25 格剛好把量測噪音與真的偏掉分開。
AIM_SLACK_PITCH = 0.25
# 內容位移超過這麼多像素＝鏡頭被置中拉走。一格約 90，六成格已遠大於偵測抖動。
CENTRE_SHIFT_PX = 60.0
# 光看位移量級不夠：20260805-122213 的 seq 528／547 兩格量到 107px 的半格級位移就被
# 判成 ALLY，實際是空格。真置中是「被點的那一格跳到螢幕中心」，位移向量必須與
# centre - target 對得上（逐軸容差半格）。
CENTRE_MATCH_PITCH = 0.5
# 同軸兩側地標各算一次偏移，差超過半格就是至少一側不是地圖邊，整軸不採信。
EDGE_AGREEMENT_PITCH = 0.5

# 地標一次目擊就凍住的代價是永久的：0805 那輪 east 被一次「置中反推」的鏡位寫成
# 世界 2529，其後 96 次目擊一致指向 2318.9（標準差 2.9），每一次都撞成 clash、
# 每一次回退又都成功，保險絲抓不到，兩小時只前進 6 格。所以升格要 K 次互相對得上
# 的目擊，撤換要 N 次一致的反證——K=N=3 在那輪的數據下第一次撞完三輪就會翻案。
LANDMARK_VOTES = 3
LANDMARK_REVOKE_CLASHES = 3

# 置中反推的鏡位是**假說**，不是量到的。20260805-075310 第 17 窗起連續 centre 錨定
# 卻照常逐格裁決，offset 誤差累積超過一格，後段整段記錯世界格（敵 32／我 17 超計就
# 是這麼來的）。所以非 grounded 錨定只准連著出現這麼多次，而且在被強證人（標記填色
# ／與帳本對得上的界線）背書之前一格都不裁決；超過就當失位，走既有回退。
UNGROUNDED_ANCHOR_LIMIT = 1

HEADINGS: tuple[str, str] = ("east", "west")

# 單位星座重認：帳本裡已裁決的單位格是現成星圖（我方回合內單位不動），失位時拿當
# 下幀的密度峰去對齊它。別名（aliasing）寧可漏認不可錯認——同型機外觀不可分辨，唯
# 一能背書的是「多台的相對格距組合」，所以峰太少構不成獨特圖形就直接認不出。
#
# 五顆是量出來的門檻，不是猜的。三支歷史 run 的 window 幀離線重跑（收下的筆數／其中
# 錯超過半格的筆數）：122213 三顆 8/2、四顆 6/0、五顆 1/0；075310 三顆 24/19、四顆
# 5/4、五顆 0/0；091621 三顆 35/26、四顆 4/3、五顆 1/1。後兩支的帳本本身就有錯格
# （offset 累積誤差那兩輪），而現場失位時帳本本來就可能帶著錯格——門檻要撐得住那個
# 情境，所以取五顆。代價是召回低（122213 的 47 張只認得出 1 張），這是刻意的：認不
# 出來只是少一個備援，認錯是整幀寫進錯的世界位置。
CONSTELLATION_MIN_PEAKS = 5
CONSTELLATION_MIN_MATCH = 5
CONSTELLATION_TOLERANCE_PITCH = 0.5

CONSTELLATION_OK = "ok"
CONSTELLATION_FEW_PEAKS = "few_peaks"
CONSTELLATION_FEW_UNITS = "few_units"
CONSTELLATION_NO_MATCH = "no_match"
CONSTELLATION_AMBIGUOUS = "ambiguous"

# 窗基準：開窗那一幀的標記螢幕位置。格線相位閘是 mod 格距的量，整數格的漂移它看
# 不見（20260805 那幾輪的假帳都在這個盲區裡）；標記位置是未包裝的像素證人，補得上。
# 我們自己點空格會把標記搬走，所以基準逐點更新——搬去哪一格是我們自己下的令。
MARKER_DRIFT_PITCH = 0.5
# 基準附近開這麼多格距的小窗找標記：夠寬吃得下半格容差與偵測抖動，夠窄不會撈到
# 遠處另一塊同色美術。
MARKER_SEARCH_PITCH = 1.5

# 推鏡後標記要留在點擊窗內、再往內縮這麼多格才算「還看得見」——量測誤差與透視
# 校正的殘差都吃在這個餘裕裡。
MARKER_KEEP_PITCH = 0.75
# 同一個節點連續兩次擴張失敗才升級回角落歸零。角落是根節點、最後防線，不是預設救援。
NODE_FAIL_LIMIT = 2
STRIDE_HALVING = 0.5

STEP_EXPAND = "expand"
STEP_RETREAT = "retreat"
STEP_ROOT = "root"

_ADVANCE: dict[str, Callable[[Cell], int]] = {
    "east": lambda cell: cell[0],
    "west": lambda cell: -cell[0],
    "south": lambda cell: cell[1],
    "north": lambda cell: -cell[1],
}

OPPOSITE: dict[str, str] = {"east": "west", "west": "east", "north": "south", "south": "north"}

ANCHORED = "anchored"
LOST = "lost"

# 一把推鏡後格線相位至少要走這麼多像素才算「手勢生效」。取半格的一小截：真的推
# 一把走 150-240px，被吃掉的那把是 0。
GESTURE_PHASE_PX = 8.0
# 連續被吃這麼多把就 Halt——再推下去只是對著同一個吞點空轉。
GESTURE_EATEN_LIMIT = 3
# 標記位移至少要走到預期行程的這個比例才算真的推動了鏡頭。
GESTURE_TRAVEL_RATIO = 1.0 / 3.0
# 兩把都夾停才敢說夾停——一把可能只是那一幀標記認錯。
GESTURE_PINNED_LIMIT = 2

PAN_LANDED = "landed"
PAN_PINNED = "pinned"
PAN_EATEN = "eaten"


class Adrift(RuntimeError):
    """失位（LOST）時送進來的格點擊請求。

    紅線不是啟發式：世界格未知時點下去既錨不了新標記，又會把唯一的舊證人搬到一
    個記不下來的地方，還可能誤觸單位指令。LOST 的唯一出路是推鏡與**全幀視覺重
    認**（找標記／邊界／星座都是「看」不是「點」）。
    """


@dataclass
class Fix:
    """定位狀態機，兩態：ANCHORED／LOST。"""

    state: str = ANCHORED

    @property
    def anchored(self) -> bool:
        return self.state == ANCHORED

    def lose(self) -> None:
        self.state = LOST

    def regain(self) -> None:
        self.state = ANCHORED

    def allow_tap(self) -> None:
        if self.state != ANCHORED:
            raise Adrift("失位中不點任何格：只准推鏡與視覺重認")


def gesture_landed(
    shift: Point | None, direction: str, minimum: float = GESTURE_PHASE_PX
) -> bool:
    """這一把推鏡到底生效了沒（格線相位說了算）。

    相位讀不出來（`shift is None`）時回 True：那是「不知道」不是「沒動」，交給後面
    的重錨去問——在這裡當成沒動會讓腳本對著讀不到格線的畫面無限重發手勢。
    """
    if shift is None:
        return True
    axis = 0 if direction in ("east", "west") else 1
    return abs(shift[axis]) >= minimum


def gesture_verdict(
    shift: Point | None,
    direction: str,
    *,
    travel: float,
    moved: Point | None = None,
    minimum: float = GESTURE_PHASE_PX,
    ratio: float = GESTURE_TRAVEL_RATIO,
) -> str:
    """一把推鏡的驗收：LANDED／PINNED／EATEN。

    相位是 mod 格距的量（`phase_shift` 收進 ±半格），量得出「有沒有動」，量不出
    整把行程——0805 run 那三把「相位不動」的南推，標記其實各走了一整把 ~250px。
    所以真行程問標記像素位移這個未包裝的證人；標記看不見才退回相位獨撐。

    夾停與被吃的差別在**再推有沒有意義**：夾停是遊戲不肯再動鏡頭（改方向即可），
    被吃是手勢沒送達（原樣重發）。分不出來的時候（沒有標記）一律當被吃，保留
    Halt 保險絲。
    """
    axis = 0 if direction in ("east", "west") else 1
    if moved is not None:
        return PAN_LANDED if abs(moved[axis]) >= travel * ratio else PAN_PINNED
    return PAN_LANDED if gesture_landed(shift, direction, minimum) else PAN_EATEN


def at_border(
    direction: str,
    borders: Mapping[str, float],
    *,
    ledger: SweepLedger | None = None,
    offset: Point | None = None,
    region: Region = TAP_REGION,
) -> bool:
    """推進方向這一側是不是已經到邊。

    實機定讞：鏡頭推到地圖某緣之外，遊戲直接不動鏡頭，格線相位跟被吞掉的手勢一
    模一樣——相位這個證人分不出兩者，得另外問界線。看得見界線，或帳本記過界線且
    當前窗已經吃到那一格，就是到邊。
    """
    if direction in borders:
        return True
    if ledger is None or offset is None:
        return False
    edge = ledger.boundary.get(direction)
    if edge is None:
        return False
    first, last = window_bounds(ledger.grid, offset, region)
    reached = {"east": last[0] >= edge, "west": first[0] <= edge,
               "south": last[1] >= edge, "north": first[1] <= edge}
    return reached[direction]


def frontier_cell(ledger: SweepLedger, heading: str = "east") -> Cell | None:
    """帳本上還沒裁決、蛇形順序最先輪到的那一格＝掃描鋒面。"""
    pending = ledger.pending()
    if not pending:
        return None
    return serpentine(pending, heading)[0]


def homing_route(
    grid: WorldGrid,
    offset: Point,
    frontier: Cell,
    *,
    region: Region = TAP_REGION,
    stride: float = board.PAN_GAIN * board.PAN_MAX_REACH,
    limit: int = 40,
) -> tuple[str, ...]:
    """從現在的鏡位回到鋒面格要推的方向序列，每站一把。看得到就空序列。

    歸零＝重錨不＝重掃：帳本記的是世界格事實，回角落不清帳，返航沿已裁決區走，
    每站只要「點已知空格搬標記＋一把推鏡＋重認」，不重複清算任何一格。
    """
    legs: list[str] = []
    cursor = offset
    for _ in range(limit):
        first, last = window_bounds(grid, cursor, region)
        if first[0] <= frontier[0] <= last[0] and first[1] <= frontier[1] <= last[1]:
            break
        if frontier[0] > last[0]:
            legs.append("east")
            cursor = (cursor[0] + stride, cursor[1])
        elif frontier[0] < first[0]:
            legs.append("west")
            cursor = (cursor[0] - stride, cursor[1])
        elif frontier[1] > last[1]:
            legs.append("south")
            cursor = (cursor[0], cursor[1] + stride)
        else:
            legs.append("north")
            cursor = (cursor[0], cursor[1] - stride)
    return tuple(legs)


def screen_of(grid: WorldGrid, cell: Cell, offset: Point) -> Point:
    centre = grid.centre_of(cell)
    return (centre[0] - offset[0], centre[1] - offset[1])


def border_cell(grid: WorldGrid, direction: str, border: float) -> int:
    """終止邊往界內半格＝該側最外一格的格座標。"""
    pitch = grid.col_pitch if direction in ("west", "east") else grid.row_pitch
    inward = pitch / 2.0 if direction in ("west", "north") else -pitch / 2.0
    if direction in ("west", "east"):
        return grid.cell_of((border + inward, grid.phase[1]))[0]
    return grid.cell_of((grid.phase[0], border + inward))[1]


@dataclass
class SweepLedger:
    """世界格帳本。每一筆都由一次點擊裁決背書，永遠不記螢幕座標。"""

    grid: WorldGrid
    state: dict[Cell, str] = field(default_factory=dict)
    names: dict[Cell, str] = field(default_factory=dict)
    frames: dict[Cell, str] = field(default_factory=dict)
    reasons: dict[Cell, str] = field(default_factory=dict)
    boundary: dict[str, int] = field(default_factory=dict)
    charted: set[Cell] = field(default_factory=set)
    blocked: dict[Cell, int] = field(default_factory=dict)
    taps: int = 0

    def verdict(self, cell: Cell) -> str:
        return self.state.get(cell, UNKNOWN)

    def decided(self, cell: Cell) -> bool:
        return self.verdict(cell) in DECIDED

    def chart(self, cell: Cell) -> None:
        self.charted.add(cell)

    def record(
        self,
        cell: Cell,
        verdict: str,
        *,
        name: str | None = None,
        frame: str | None = None,
        reason: str | None = None,
    ) -> None:
        if verdict not in DECIDED:
            raise ValueError(f"not a decided verdict: {verdict!r}")
        self.chart(cell)
        self.state[cell] = verdict
        self.blocked.pop(cell, None)
        if name:
            self.names[cell] = name
        if frame:
            self.frames[cell] = frame
        if reason:
            self.reasons[cell] = reason

    def retract(self, cell: Cell) -> bool:
        """把一格的推斷空格退回未裁決。回傳有沒有真的退。

        推斷是暫定的，點擊裁決才是終審：視覺只要再一次說這一格可能有單位，那筆沒有
        點擊背書的空格就得讓位。單幀漏檢本來就會發生（run 20260805-180518 的 [1,5]
        ／[2,6] 在數十個窗都是候選，只因 seq 373 那一幀沒偵測到就被一次性寫成空、
        之後永不翻案，我方 10 台只記到 8）——不可逆的推斷就是這樣把單位吞掉的。
        """
        if self.state.get(cell) != EMPTY_INFERRED:
            return False
        del self.state[cell]
        self.reasons.pop(cell, None)
        return True

    def defer(self, cell: Cell) -> None:
        """這個鏡位下進不了安全窗；等推鏡把它輪過來。"""
        self.chart(cell)
        if not self.decided(cell):
            self.blocked[cell] = self.blocked.get(cell, 0) + 1

    def see_border(self, direction: str, world: float, *, replace: bool = False) -> None:
        """界線一律目視。第一次記下就不再改——寫錯的代價是永久的。

        `replace` 只給地標撤換用：地標翻案時界線跟著翻，否則帳本會留著一條由已被
        推翻的地標算出來的界線。
        """
        if direction in self.boundary and not replace:
            return
        self.boundary[direction] = border_cell(self.grid, direction, world)

    @property
    def bounded(self) -> bool:
        return all(direction in self.boundary for direction in COMPASS)

    def in_bounds(self, cell: Cell) -> bool:
        col, row = cell
        limits = (
            ("west", col, 1),
            ("east", col, -1),
            ("north", row, 1),
            ("south", row, -1),
        )
        for direction, value, sign in limits:
            edge = self.boundary.get(direction)
            if edge is not None and sign * (value - edge) < 0:
                return False
        return True

    def rectangle(self) -> tuple[Cell, ...]:
        if not self.bounded:
            return ()
        return tuple(
            (col, row)
            for row in range(self.boundary["north"], self.boundary["south"] + 1)
            for col in range(self.boundary["west"], self.boundary["east"] + 1)
        )

    def pending(self) -> tuple[Cell, ...]:
        cells = self.rectangle() if self.bounded else tuple(sorted(self.charted))
        return tuple(cell for cell in cells if self.in_bounds(cell) and not self.decided(cell))

    @property
    def complete(self) -> bool:
        """建構性判準：四界都定 ∧ 界內每格都裁決過（UNSURE 也算裁決過）。"""
        return self.bounded and not self.pending()

    def cells_of(self, verdict: str) -> tuple[Cell, ...]:
        return tuple(sorted(cell for cell, value in self.state.items() if value == verdict))

    def summary(self) -> dict[str, Any]:
        counts = {value: len(self.cells_of(value)) for value in DECIDED}
        return {
            "bounded": self.bounded,
            "complete": self.complete,
            "boundary": dict(sorted(self.boundary.items())),
            "counts": counts,
            "taps": self.taps,
            "enemies": [
                {"cell": list(cell), "name": self.names.get(cell)} for cell in self.cells_of(ENEMY)
            ],
            "allies": [list(cell) for cell in self.cells_of(ALLY)],
            "unsure": [
                {"cell": list(cell), "reason": self.reasons.get(cell)}
                for cell in self.cells_of(UNSURE)
            ],
            "pending": len(self.pending()),
            "deferred": [list(cell) for cell in sorted(self.blocked)],
        }


@dataclass(frozen=True)
class TapTarget:
    cell: Cell
    point: Point


@dataclass(frozen=True)
class WindowPlan:
    """本鏡位下要點的格（蛇形）與擋掉的格。blocked 是這個鏡位的事實，不是永久的。

    `inferred` 只在候選過濾模式下非空：窗內、點得下去、但視覺說沒有單位的格。
    """

    taps: tuple[TapTarget, ...]
    blocked: tuple[Cell, ...]
    window: tuple[Cell, Cell] | None = None
    inferred: tuple[Cell, ...] = ()
    # 這一窗被視覺翻案、退回點擊佇列的推斷空格。
    retracted: tuple[Cell, ...] = ()


def _tap_blocked(point: Point, bands: Sequence[DangerBand]) -> bool:
    return blocked_for_map_tap(point, bands)


def _box_overlaps(box: tuple[float, float, float, float], region: Region) -> bool:
    x, y, w, h = region
    return not (box[2] <= x or box[0] >= x + w or box[3] <= y or box[1] >= y + h)


def _box_within(box: tuple[float, float, float, float], region: Region) -> bool:
    x, y, w, h = region
    return box[0] >= x and box[1] >= y and box[2] <= x + w and box[3] <= y + h


def window_bounds(
    grid: WorldGrid, offset: Point, region: Region = TAP_REGION
) -> tuple[Cell, Cell]:
    x, y, w, h = region
    first = grid.cell_of((x + offset[0], y + offset[1]))
    last = grid.cell_of((x + w + offset[0], y + h + offset[1]))
    return (first, last)


def in_window(
    grid: WorldGrid, offset: Point, cell: Cell | None, region: Region = TAP_REGION
) -> bool:
    if cell is None:
        return False
    first, last = window_bounds(grid, offset, region)
    return first[0] <= cell[0] <= last[0] and first[1] <= cell[1] <= last[1]


def window_targets(
    grid: WorldGrid,
    offset: Point,
    *,
    region: Region = TAP_REGION,
    holes: Sequence[Region] = board.UNIT_DENSITY_HUD_HOLES,
    bands: Sequence[DangerBand] = DANGER_BANDS,
) -> dict[Cell, Point | None]:
    """本鏡位下整格框**完整**落在點擊窗內的格 → 螢幕點；點不下去的格是 None。

    完整落入是硬條件：被窗邊切一半的格點下去可能命中隔壁那一格，而帳本收的是
    「這一格的事實」。
    """
    first, last = window_bounds(grid, offset, region)
    out: dict[Cell, Point | None] = {}
    for row in range(first[1], last[1] + 1):
        for col in range(first[0], last[0] + 1):
            cell = (col, row)
            bx0, by0, bx1, by1 = grid.box_of(cell)
            box = (bx0 - offset[0], by0 - offset[1], bx1 - offset[0], by1 - offset[1])
            if not _box_within(box, region):
                continue
            point = ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)
            blocked = any(_box_overlaps(box, hole) for hole in holes) or _tap_blocked(point, bands)
            out[cell] = None if blocked else point
    return out


def candidate_points(
    frame: np.ndarray,
    *,
    region: Region = board.UNIT_DENSITY_REGION,
    min_count: int = CANDIDATE_MIN_COUNT,
    local_max: int = CANDIDATE_LOCAL_MAX,
    min_dist: float = CANDIDATE_MIN_DIST,
) -> tuple[Point, ...]:
    """這一幀裡「可能站著單位」的密度峰。門檻放到最寬——這是過濾器不是裁決者。"""
    return board.find_unit_screen_hints(
        frame, region, min_count=min_count, local_max=local_max, min_dist=min_dist
    )


def candidate_ranking(
    grid: WorldGrid,
    offset: Point,
    points: Iterable[Point],
    *,
    halo: float = CANDIDATE_HALO_PITCH,
) -> dict[Cell, int]:
    """密度峰（螢幕座標）→ 要點的世界格，值是「最強的那個峰排第幾」。

    `find_unit_screen_hints` 吐出來的順序就是密度由強到弱，所以名次直接用序號。名次是給點擊
    排序用的：峰強的先點，真單位早出帳，誤報留在隊尾等著被算術豁免。
    """
    out: dict[Cell, int] = {}
    dx, dy = halo * grid.col_pitch, halo * grid.row_pitch
    for rank, (x, y) in enumerate(points):
        world = (x + offset[0], y + offset[1])
        low = grid.cell_of((world[0] - dx, world[1] - dy))
        high = grid.cell_of((world[0] + dx, world[1] + dy))
        for row in range(low[1], high[1] + 1):
            for col in range(low[0], high[0] + 1):
                cell = (col, row)
                if cell not in out:
                    out[cell] = rank
    return out


def candidate_cells(
    grid: WorldGrid,
    offset: Point,
    points: Iterable[Point],
    *,
    halo: float = CANDIDATE_HALO_PITCH,
) -> frozenset[Cell]:
    """密度峰（螢幕座標）→ 要點的世界格。每個峰暈開 halo 格，寧可多不可漏。"""
    return frozenset(candidate_ranking(grid, offset, points, halo=halo))


def plan_window(
    ledger: SweepLedger,
    offset: Point,
    *,
    heading: str = "east",
    region: Region = TAP_REGION,
    holes: Sequence[Region] = board.UNIT_DENSITY_HUD_HOLES,
    bands: Sequence[DangerBand] = DANGER_BANDS,
    candidates: Collection[Cell] | None = None,
    order: Mapping[Cell, int] | None = None,
) -> WindowPlan:
    """本鏡位裡還沒裁決、點得下去的格，蛇形排序。

    `candidates` 給了就進過濾模式：只有候選格排進 taps，其餘的格列進 `inferred`
    交給呼叫端入帳 EMPTY_INFERRED。擋掉的格（HUD 洞／危險帶／窗邊切一半）不算
    推斷——那些格連「視覺看得清楚」都不成立。

    `order` 給了就改成峰強度優先（同名次仍照蛇形，排序是穩定的）。
    """
    grid = ledger.grid
    first, last = window_bounds(grid, offset, region)
    targets = window_targets(grid, offset, region=region, holes=holes, bands=bands)
    taps: list[TapTarget] = []
    blocked: list[Cell] = []
    inferred: list[Cell] = []
    retracted: list[Cell] = []
    for index, row in enumerate(range(first[1], last[1] + 1)):
        cols = list(range(first[0], last[0] + 1))
        if (heading == "west") != (index % 2 == 1):
            cols.reverse()
        for col in cols:
            cell = (col, row)
            if cell not in targets or not ledger.in_bounds(cell):
                continue
            ledger.chart(cell)
            if ledger.decided(cell):
                # 候選名單再次點到這一格＝視覺翻案：推斷退場，重排點擊佇列。
                if candidates is None or cell not in candidates or not ledger.retract(cell):
                    continue
                retracted.append(cell)
            point = targets[cell]
            if point is None:
                blocked.append(cell)
                continue
            if candidates is not None and cell not in candidates:
                inferred.append(cell)
                continue
            taps.append(TapTarget(cell, point))
    if order is not None:
        taps.sort(key=lambda target: order.get(target.cell, len(order)))
    return WindowPlan(
        tuple(taps), tuple(blocked), (first, last), tuple(inferred), tuple(retracted)
    )


@dataclass(frozen=True)
class TrustNode:
    """一個能被視覺重認的已知世界格，附重認所需的最小證據。

    `cell` 是標記所在的世界格（標記全圖唯一、可攜、點別格會搬移）；`borders` 與
    `units` 是入帳當下那一窗的邊界可見性與已裁決單位格，回退時交叉驗證，防同色
    美術冒充標記。
    """

    cell: Cell
    offset: Point
    borders: tuple[str, ...] = ()
    units: tuple[Cell, ...] = ()


@dataclass
class NodeWalk:
    """節點鏈上的擴張／回退狀態機。**只管決策，不碰裝置**。

    丟失是常態，所以救援是局部的：反向等幅推回上一節點（成本一把推鏡），回到節點
    後半步幅重試；同一節點連兩敗才升級回角落歸零；回程也丟就沿鏈往回走。
    """

    full_reach: float = board.PAN_MAX_REACH
    nodes: list[TrustNode] = field(default_factory=list)
    reach: float = 0.0
    failures: int = 0
    retreating: bool = False

    def __post_init__(self) -> None:
        self.reach = self.reach or self.full_reach

    def expanded(self, node: TrustNode) -> None:
        self.nodes.append(node)
        self.failures = 0
        self.reach = self.full_reach
        self.retreating = False

    def recovered(self) -> str:
        """回程重見標記＝回到上一節點。這一次擴張記一敗。"""
        self.retreating = False
        self.failures += 1
        if self.failures >= NODE_FAIL_LIMIT:
            return STEP_ROOT
        self.reach = max(board.PAN_MIN_REACH, self.reach * STRIDE_HALVING)
        return STEP_EXPAND

    def lost(self) -> str:
        if not self.retreating:
            self.retreating = True
            return STEP_RETREAT
        if self.nodes:
            self.nodes.pop()
            return STEP_RETREAT
        return STEP_ROOT

    def rooted(self) -> None:
        self.nodes.clear()
        self.failures = 0
        self.reach = self.full_reach
        self.retreating = False


def stride_cap(
    marker: Point,
    direction: str,
    *,
    region: Region = TAP_REGION,
    gain: float = board.PAN_GAIN,
    margin: float = 0.0,
) -> float:
    """推鏡步幅的硬上限＝推完標記仍留在新窗視野內的最長行程。

    位移量測不參與定位，但**推多遠**還是要算得出來，否則新窗裡沒有東西可以重認。
    """
    x, y, w, h = region
    dx, dy = board.DIRECTIONS[direction]
    if dx:
        room = marker[0] - (x + margin) if dx > 0 else (x + w - margin) - marker[0]
    else:
        room = (y + h - margin) - marker[1] if dy < 0 else marker[1] - (y + margin)
    return max(0.0, room / gain)


def frontier_tap(
    ledger: SweepLedger,
    offset: Point,
    marker_cell: Cell | None,
    direction: str,
    *,
    region: Region = TAP_REGION,
    holes: Sequence[Region] = board.UNIT_DENSITY_HUD_HOLES,
    bands: Sequence[DangerBand] = DANGER_BANDS,
    accept: tuple[str, ...] = (EMPTY,),
) -> TapTarget | None:
    """推鏡前把標記搬到本窗靠推進方向的前緣格。已經在前緣就 None。

    只點**已判空**的格：搬標記是定位動作不是裁決動作，不拿一格未知的裁決機會去換
    （那一格的回饋會被當成搬標記的結果讀掉）。過濾模式下窗內多半只有推斷空格，
    呼叫端把 EMPTY_INFERRED 也放進 `accept`——點下去反而是替那一格補上點擊背書。
    """
    forward = _ADVANCE[direction]
    targets = window_targets(ledger.grid, offset, region=region, holes=holes, bands=bands)
    movable = [
        (cell, point)
        for cell, point in targets.items()
        if point is not None and ledger.verdict(cell) in accept and cell != marker_cell
    ]
    if not movable:
        return None
    # 「已經在前緣」只有標記看得見時才說得通。回角落歸零後標記還留在遠方舊鋒面，
    # 拿它當前緣會判定不用搬——推完鏡新窗裡一個標記都沒有，重認必定落空。窗外就
    # 當沒有標記：本窗重新種一顆。
    visible = in_window(ledger.grid, offset, marker_cell, region)
    anchor = marker_cell if visible else None
    cell, point = max(movable, key=lambda entry: (forward(entry[0]), -_span(entry[0], anchor)))
    if anchor is not None and forward(cell) <= forward(anchor):
        return None
    return TapTarget(cell, point)


def _span(cell: Cell, other: Cell | None) -> int:
    if other is None:
        return 0
    return abs(cell[0] - other[0]) + abs(cell[1] - other[1])


def contradicts(
    ledger: SweepLedger,
    landmarks: Mapping[str, float],
    borders: Mapping[str, float],
    offset: Point,
    *,
    slack: float = EDGE_AGREEMENT_PITCH,
) -> str | None:
    """這一幀目視到的終止邊對不對得上帳本的界線。回矛盾的那一側，沒有就 None。

    標記重認解出來的鏡位是整幀的座標，認錯一塊同色美術就是整幀寫進錯的世界位置——
    所以錨定之後還要用當下看得見的邊界回頭質詢它。
    """
    for side, screen in borders.items():
        known = landmarks.get(side)
        if known is None:
            continue
        axis = 0 if side in ("west", "east") else 1
        pitch = ledger.grid.col_pitch if axis == 0 else ledger.grid.row_pitch
        if abs(screen + offset[axis] - known) > slack * pitch:
            return side
    return None


def settled_reading(
    readings: Sequence[float], slack: float, votes: int = LANDMARK_VOTES
) -> float | None:
    """一疊同側目擊收斂成一個世界座標：夠多次、而且彼此對得上，才給答案。

    只看最近 `votes` 次——舊的目擊可能來自已經被推翻的鏡位。
    """
    if len(readings) < votes:
        return None
    recent = sorted(readings[-votes:])
    if recent[-1] - recent[0] > slack:
        return None
    return recent[len(recent) // 2]


def plan_pan(
    ledger: SweepLedger,
    offset: Point,
    heading: str = "east",
    *,
    region: Region = TAP_REGION,
    pinned: Collection[str] = (),
) -> tuple[str | None, str]:
    """下一段推鏡方向與更新後的橫向朝向。沒得推就 (None, heading)。

    沿列帶蛇形推進；**界線未見的方向優先探**——那個方向的格還沒被枚舉過，
    「界內沒有待裁決的格」在那裡不成立。

    `pinned` 是這個鏡位上已經證實推不動的方向：不寫界線（界線只由目視寫入），
    只是這一站不再往那邊推。鏡頭一動就作廢——透視斜邊讓同一側在別的鏡位可能
    重新推得動、界線也可能升進可讀帶。
    """
    if heading not in HEADINGS:
        heading = "east"
    if heading not in pinned and _more_that_way(ledger, offset, heading, region):
        return (heading, heading)
    flipped = "west" if heading == "east" else "east"
    for side in ("south", "north"):
        if side not in pinned and _more_that_way(ledger, offset, side, region):
            return (side, flipped)
    return (None, heading)


def _more_that_way(
    ledger: SweepLedger, offset: Point, direction: str, region: Region
) -> bool:
    if direction not in ledger.boundary:
        return True
    first, last = window_bounds(ledger.grid, offset, region)
    limits = {
        "east": lambda cell: cell[0] > last[0],
        "west": lambda cell: cell[0] < first[0],
        "south": lambda cell: cell[1] > last[1],
        "north": lambda cell: cell[1] < first[1],
    }
    beyond = limits[direction]
    return any(beyond(cell) for cell in ledger.pending())


@dataclass(frozen=True)
class TapOutcome:
    """一次點擊的回饋三分類。delta ＝ 量得到的內容位移（置中時才有意義）。"""

    verdict: str
    delta: Point | None = None
    marker: Point | None = None
    learned: MarkerSignature | None = None


def _displacement(before: np.ndarray, after: np.ndarray) -> Point | None:
    delta = board.relocalise(board.find_unit_screen_hints(before), board.find_unit_screen_hints(after))
    return None if delta is None else (float(delta[0]), float(delta[1]))


# 點擊回饋的等待上限與收斂輪詢間隔。上限的餘裕來自舊 screencap 路徑：那條路上有效
# 取樣點落在點擊後 ~2.8s（tap_interval＋一張截圖 ~2.4s），回饋早就渲染完了；串流取幀
# 只要 ~11ms，沒有等待就會在回饋出現前定案。「等滿上限仍無回饋」本身是 UNSURE 的
# 正當證據，上限不可拿掉。
#
# 但「有訊號就定案」也不夠：選中我方單位的過渡期，移動範圍填色先亮、選擇態 UI 後到，
# 動畫中間幀會讓 classify_tap 的填色分支假陽性回 TAP_EMPTY（run 20260808-184706 把
# (1,5) 我方格記成 empty）。所以取樣點只准落在動畫收斂之後：FEEDBACK_POLL_S 是幀差
# 收斂的輪詢間隔，收斂後的那一張才准送進 classify。
FEEDBACK_WAIT_S = 3.0
FEEDBACK_POLL_S = 0.15


def judge_tap(
    grab: Callable[[], np.ndarray],
    judge: Callable[[np.ndarray], TapOutcome],
    *,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    deadline: float,
    poll: float = FEEDBACK_POLL_S,
    observe: Callable[[SettleReport], None] | None = None,
) -> TapOutcome:
    """點擊後的判定取樣：等收斂 → 問 `judge`，說不出結果就續輪到預算盡。

    `judge` 拿到的一律是收斂後的那一張；動畫中間幀一次都不送進去。
    """
    while True:
        after = await_still(
            grab, clock=clock, sleep=sleep, deadline=deadline, poll=poll, observe=observe
        )
        outcome = judge(after)
        if outcome.verdict != TAP_NONE or clock() >= deadline:
            return outcome


def classify_tap(
    before: np.ndarray,
    after: np.ndarray,
    target: Point,
    *,
    signature: MarkerSignature | None = None,
    card: Callable[[np.ndarray], bool] | None = None,
    displace: Callable[[np.ndarray, np.ndarray], Point | None] | None = None,
    selected: Callable[[np.ndarray], bool] | None = None,
    pitch: tuple[float, float] | None = None,
    centre: Point = SCREEN_CENTRE,
    region: Region = board.MAP_REGION,
) -> TapOutcome:
    """點擊前後幀 → EMPTY／CARD／SHIFTED／SHIFTED_UNSURE／NONE。

    順序有意義：出卡先問（卡片本身就是答案），選擇態 UI 次之，再來是幾何（鏡頭一
    動，「填色在不在被點的那一格」這個問法就失去意義），最後才問填色。

    選擇態 UI 一出現就是我方，位移量不再有發言權：站在螢幕中心附近的我方單位被點
    到時位移接近 0，過不了 `_recentres`，20260805-140958 那一輪就是這樣一路把我方
    格記成 NONE、鏡頭卻已經被拉走。UI 沒背書、幾何過的仍回 SHIFTED_UNSURE——鏡頭
    照樣要重錨，但陣營不記。

    還沒有色簽時用 `learn_marker` 現學：**第一次點到空格**同時是學色簽的唯一機會，
    學到了就回傳給呼叫端收下。
    """
    if card is not None and card(after):
        return TapOutcome(TAP_CARD)
    if selected is not None and selected(after):
        return TapOutcome(TAP_SHIFTED)
    moved = (displace or _displacement)(before, after)
    if moved is not None and _recentres(moved, target, centre, pitch):
        return TapOutcome(TAP_SHIFTED_UNSURE, delta=moved)
    if signature is not None:
        found = board.find_marker(after, signature, region=region)
        if found is not None and _near(found, target, pitch or signature.size):
            return TapOutcome(TAP_EMPTY, marker=found)
        return TapOutcome(TAP_NONE)
    learned = board.learn_marker(before, after, target, region=region)
    if learned is not None:
        return TapOutcome(TAP_EMPTY, marker=target, learned=learned)
    return TapOutcome(TAP_NONE)


def _recentres(
    moved: Point, target: Point, centre: Point, pitch: tuple[float, float] | None
) -> bool:
    if math.hypot(*moved) < CENTRE_SHIFT_PX:
        return False
    span = pitch or (board.MARKER_FALLBACK_PITCH, board.MARKER_FALLBACK_PITCH)
    expected = (centre[0] - target[0], centre[1] - target[1])
    return all(
        abs(moved[axis] - expected[axis]) <= CENTRE_MATCH_PITCH * span[axis]
        for axis in (0, 1)
    )


def _near(point: Point, target: Point, pitch: tuple[float, float]) -> bool:
    return (
        abs(point[0] - target[0]) <= MARKER_HIT_PITCH * pitch[0]
        and abs(point[1] - target[1]) <= MARKER_HIT_PITCH * pitch[1]
    )


def marker_search(
    baseline: Point,
    pitch: tuple[float, float],
    *,
    region: Region = TAP_REGION,
    radius: float = MARKER_SEARCH_PITCH,
) -> Region:
    """基準位置附近的小搜尋窗（夾在安全窗內），給 `find_marker` 用。"""
    x, y, w, h = region
    half = (radius * pitch[0], radius * pitch[1])
    x0 = max(x, baseline[0] - half[0])
    y0 = max(y, baseline[1] - half[1])
    x1 = min(x + w, baseline[0] + half[0])
    y1 = min(y + h, baseline[1] + half[1])
    return (int(x0), int(y0), max(0, int(x1 - x0)), max(0, int(y1 - y0)))


def window_steady(
    baseline: Point,
    found: Point | None,
    pitch: tuple[float, float],
    *,
    slack: float = MARKER_DRIFT_PITCH,
) -> bool | None:
    """本窗的畫面還停在基準上嗎。標記找不到就回 None——那是「不知道」，交給相位閘。"""
    if found is None:
        return None
    return abs(found[0] - baseline[0]) <= slack * pitch[0] and (
        abs(found[1] - baseline[1]) <= slack * pitch[1]
    )


def aim_drift(phase: Point, grid: WorldGrid, offset: Point) -> Point:
    """這一幀的格線相位與當前鏡位推出來的相位差，逐軸收進 ±半格。

    鏡位在一個窗裡是**假設**：選擇態會無聲把鏡頭拉走，而點擊回饋（填色）永遠出現
    在手指按下去的地方，一格都測不出偏移。格線是遊戲自己渲染的，相位就是畫面直接
    給的證人——半格以內的偏它量得到，整數格距的偏它看不見（那一段靠標記與界線）。
    """
    pitch = (grid.col_pitch, grid.row_pitch)
    expected = (
        (grid.phase[0] - offset[0]) % pitch[0],
        (grid.phase[1] - offset[1]) % pitch[1],
    )
    return board.phase_shift(expected, phase, pitch)


def aimed(drift: Point, grid: WorldGrid, slack: float = AIM_SLACK_PITCH) -> bool:
    return abs(drift[0]) <= slack * grid.col_pitch and abs(drift[1]) <= slack * grid.row_pitch


def recentre_offset(grid: WorldGrid, cell: Cell, centre: Point = SCREEN_CENTRE) -> Point:
    """置中發生時：被點的那一格就是螢幕中心格，鏡位由它反推。"""
    world = grid.centre_of(cell)
    return (world[0] - centre[0], world[1] - centre[1])


def border_offsets(
    grid: WorldGrid,
    landmarks: Mapping[str, float],
    borders: Mapping[str, float],
) -> dict[str, float]:
    """由已記的地圖終止邊（世界像素）與這一幀的螢幕終止邊解出的逐軸鏡位。

    同軸兩側都讀得到就要互相對得上——差太多代表至少一側不是地圖邊，整軸不採信。
    """
    out: dict[str, float] = {}
    for axis, sides in _SIDES.items():
        slack = EDGE_AGREEMENT_PITCH * (grid.col_pitch if axis == "x" else grid.row_pitch)
        readings = [
            landmarks[side] - borders[side]
            for side in sides
            if side in landmarks and side in borders
        ]
        if not readings:
            continue
        if max(readings) - min(readings) > slack:
            continue
        out[axis] = sum(readings) / len(readings)
    return out


def reanchor(
    grid: WorldGrid,
    *,
    landmarks: Mapping[str, float],
    borders: Mapping[str, float],
    candidate: Point | None = None,
) -> tuple[Point | None, str]:
    """重錨：地標（絕對）優先，置中反推的候選只補地標沒說話的那一軸。

    地標與候選矛盾時**地標說了算**，因為地標不會被置中演出弄錯；兩者都沒有就回
    (None, lost)，呼叫端只剩回角落歸零這一條路。
    """
    axes = border_offsets(grid, landmarks, borders)
    if "x" in axes and "y" in axes:
        return ((axes["x"], axes["y"]), SOURCE_EDGE)
    if candidate is None:
        return (None, SOURCE_LOST)
    if not axes:
        return (candidate, SOURCE_CENTRE)
    return (
        (axes.get("x", candidate[0]), axes.get("y", candidate[1])),
        SOURCE_MIXED,
    )


def identified_units(ledger: SweepLedger) -> tuple[Cell, ...]:
    """星座的參考集：點擊出卡、名字讀得出來的 ENEMY 格。

    ALLY（置中反推）不夠格當座標基準——那一類裁決本身就是幾何推斷來的，拿它當星圖
    等於讓一個推斷替另一個推斷背書。名字讀不到的 ENEMY 也排除：那一格只證明「有東
    西」，證不了它是同一台。
    """
    return tuple(
        cell
        for cell in ledger.cells_of(ENEMY)
        if ledger.names.get(cell)
    )


def unit_cells(ledger: SweepLedger) -> tuple[Cell, ...]:
    """帳本上已確認站著單位的格，不分陣營。"""
    return tuple(
        sorted(ledger.cells_of(ENEMY) + ledger.cells_of(ALLY) + ledger.cells_of(NPC))
    )


def retract_inferred(ledger: SweepLedger, cells: Iterable[Cell]) -> tuple[Cell, ...]:
    """這批候選格裡，哪幾格的推斷空格被翻掉了（翻案已就地生效）。"""
    return tuple(sorted(cell for cell in set(cells) if ledger.retract(cell)))


@dataclass(frozen=True)
class Census:
    """一張盤面的三方台數。"""

    enemies: int
    allies: int
    npcs: int


def census(ledger: SweepLedger) -> Census:
    """帳本上已確認的三方台數。UNSURE 不算——那是留白不是單位。"""
    return Census(
        len(ledger.cells_of(ENEMY)), len(ledger.cells_of(ALLY)), len(ledger.cells_of(NPC))
    )


def census_closed(ledger: SweepLedger, target: Census | None) -> bool:
    """帳齊了嗎：三方台數都對上，而且四界都定得出來。

    `target` 是 None 就永遠不收——那是「這一關沒有真值可比對」（首刷）。目標數只
    能來自真值檔，猜出來的數會把還沒清完的區域一起劃掉。

    台數用等號不用大於等於：超計代表帳本裡有假帳（同一台被記兩格之類），那種情況
    下早收一樣危險。四界是硬條件——界線沒湊齊連「剩下哪些格」都枚舉不出來。
    """
    if target is None or not ledger.bounded:
        return False
    return census(ledger) == target


def roster_missing(
    ledger: SweepLedger,
    peaks: Sequence[Point],
    offset: Point,
    *,
    region: Region = board.UNIT_DENSITY_REGION,
    tolerance: float = CONSTELLATION_TOLERANCE_PITCH,
) -> tuple[Cell, ...]:
    """收尾閘：帳本裡投影進這一幀偵測區的單位格，哪幾格在幀上找不到峰。

    方向是帳→幀，與 `_covers` 同一條紀律：帳本說有的東西，畫面就該看得見。空集合
    ＝這一幀背書了帳本。幀側多餘的峰不計較（它們可能是視野外還沒裁決的東西，或是
    誤報）——這裡問的是「帳有沒有虛」，不是「幀有沒有多」。
    """
    grid = ledger.grid
    span = (tolerance * grid.col_pitch, tolerance * grid.row_pitch)
    x0, y0, w, h = region
    remaining = list(peaks)
    missing: list[Cell] = []
    for cell in sorted(unit_cells(ledger)):
        centre = grid.centre_of(cell)
        screen = (centre[0] - offset[0], centre[1] - offset[1])
        if not (x0 <= screen[0] <= x0 + w and y0 <= screen[1] <= y0 + h):
            continue
        best: tuple[float, int] | None = None
        for index, peak in enumerate(remaining):
            dx, dy = abs(peak[0] - screen[0]), abs(peak[1] - screen[1])
            if dx > span[0] or dy > span[1]:
                continue
            if best is None or dx + dy < best[0]:
                best = (dx + dy, index)
        if best is None:
            missing.append(cell)
            continue
        remaining.pop(best[1])
    return tuple(missing)


@dataclass(frozen=True)
class Constellation:
    """星座重認的結果。`offset` 是 None 就看 `reason`，不猜。"""

    offset: Point | None
    matched: int = 0
    reason: str = CONSTELLATION_NO_MATCH


def _covers(
    references: Sequence[Cell],
    peaks: Sequence[Point],
    grid: WorldGrid,
    offset: Point,
    tolerance: tuple[float, float],
    region: Region,
) -> tuple[int, Point] | None:
    """這個鏡位假說下，**每一個投影進偵測區的參考格都有峰**才算數。

    方向是帳→幀：參考集是已確認身分的格，它們該出現的地方沒有精靈就是假說錯了。
    投影落在偵測區外的參考格不苛求（那一格根本不在這一幀裡）。幀側多餘的峰不計分，
    它們可能是還沒裁決的單位。
    """
    x0, y0, w, h = region
    remaining = list(peaks)
    residuals: list[Point] = []
    for cell in references:
        centre = grid.centre_of(cell)
        screen = (centre[0] - offset[0], centre[1] - offset[1])
        if not (x0 <= screen[0] <= x0 + w and y0 <= screen[1] <= y0 + h):
            continue
        best: tuple[float, int, Point] | None = None
        for index, peak in enumerate(remaining):
            dx, dy = peak[0] - screen[0], peak[1] - screen[1]
            if abs(dx) > tolerance[0] or abs(dy) > tolerance[1]:
                continue
            score = abs(dx) + abs(dy)
            if best is None or score < best[0]:
                best = (score, index, (dx, dy))
        if best is None:
            return None
        remaining.pop(best[1])
        residuals.append(best[2])
    if not residuals:
        return None
    refined = (
        offset[0] - sum(value[0] for value in residuals) / len(residuals),
        offset[1] - sum(value[1] for value in residuals) / len(residuals),
    )
    return (len(residuals), refined)


def constellation_offset(
    references: Sequence[Cell],
    peaks: Sequence[Point],
    grid: WorldGrid,
    *,
    region: Region = board.UNIT_DENSITY_REGION,
    tolerance: float = CONSTELLATION_TOLERANCE_PITCH,
    min_peaks: int = CONSTELLATION_MIN_PEAKS,
    min_match: int = CONSTELLATION_MIN_MATCH,
) -> Constellation:
    """帳本身分確認格（世界格）對幀內密度峰（螢幕像素）→ 唯一鏡位，或 None＋原因。

    第三備援證人：填色標記會被推鏡手勢誤判成點擊而搬走或消滅，邊界只在圖緣說得上
    話，中央帶失位時就只剩這張星圖。

    唯一性是硬條件——能構成第二個全覆蓋解（規則陣列的別名）就整體拒收，寧可漏認不
    可錯認。輸出是**假說級**：呼叫端必須沿既有 `confirm()` 機制拿強證人背書才恢復
    裁決。
    """
    references = tuple(dict.fromkeys(references))
    peaks = tuple(peaks)
    if len(peaks) < min_peaks:
        return Constellation(None, 0, CONSTELLATION_FEW_PEAKS)
    if len(references) < min_match:
        return Constellation(None, 0, CONSTELLATION_FEW_UNITS)
    span = (tolerance * grid.col_pitch, tolerance * grid.row_pitch)
    solutions: list[tuple[int, Point]] = []
    for cell in references:
        centre = grid.centre_of(cell)
        for peak in peaks:
            seed = (centre[0] - peak[0], centre[1] - peak[1])
            covered = _covers(references, peaks, grid, seed, span, region)
            if covered is not None and covered[0] >= min_match:
                solutions.append(covered)
    if not solutions:
        return Constellation(None, 0, CONSTELLATION_NO_MATCH)
    matched = max(count for count, _ in solutions)
    offsets = [offset for _, offset in solutions]
    first = offsets[0]
    for other in offsets[1:]:
        if abs(other[0] - first[0]) > span[0] or abs(other[1] - first[1]) > span[1]:
            return Constellation(None, matched, CONSTELLATION_AMBIGUOUS)
    return Constellation(
        (
            sum(offset[0] for offset in offsets) / len(offsets),
            sum(offset[1] for offset in offsets) / len(offsets),
        ),
        matched,
        CONSTELLATION_OK,
    )


def anchor_northwest(
    lattice: board.Lattice, borders: Mapping[str, float]
) -> tuple[WorldGrid, Point] | None:
    """西北角幀 → 世界座標系：西界＝世界 x 0、北界＝世界 y 0。

    座標在這裡是被**定義**的，不是量出來的；角落可重現，所以跨輪重新歸零回到同一套。
    """
    if "west" not in borders or "north" not in borders:
        return None
    offset = (-float(borders["west"]), -float(borders["north"]))
    grid = WorldGrid.anchor(lattice, offset)
    if grid is None:
        return None
    return (grid, offset)


def read_borders(frame: np.ndarray) -> dict[str, float]:
    """這一幀目視到的終止邊（螢幕像素），只收裁決為 EDGE 的那幾側。"""
    return {
        side: float(position)
        for side, (verdict, position, _) in board.scan_edges(frame).items()
        if verdict == board.EDGE_SEEN
    }


def serpentine(cells: Iterable[Cell], heading: str = "east") -> tuple[Cell, ...]:
    """列帶蛇形排序（離線規劃與測試共用）。"""
    rows: dict[int, list[int]] = {}
    for col, row in cells:
        rows.setdefault(row, []).append(col)
    out: list[Cell] = []
    for index, row in enumerate(sorted(rows)):
        cols = sorted(rows[row], reverse=(heading == "west") != (index % 2 == 1))
        out.extend((col, row) for col in cols)
    return tuple(out)
