"""名冊跳轉掃描的純邏輯：每一步都要有定位點。

跳轉是硬切（無滑鏡動畫），每一台的落點幀都是一個獨立鏡位。這一層不做任何「無標記
的跨窗圖樣比對」——那是拿兩張圖片猜對齊，沒有任何一端是被驗證過的格子。落點的世界
座標只有兩條路：

- **march**：自力用標記接力往西／往北推到界，逐把重認標記算累計格數。目標的幀格讀的是
  **遊戲自己畫出來的範圍**：敵方＝攻擊範圍紅菱形的中心（`attack_centre`，半徑未知，取
  最小包覆），我方＝移動範圍菱形的中心（`diamond_centre`，半徑＝名冊讀到的移動力）。

- **march_meet**：march 的順路結帳，**零額外點擊**。march 本來就一路在點格種標記，這些點
  偶然落在單位上時（回應不是空格填色而是出卡／出行動 UI），順勢讀簡化資訊窗的 HP／EN 去
  `roster_lookup` 反查名冊：唯一且已解就用幀內格差（`meet_cell`，里程計 `MarkerOdometer`
  給目標在這一幀的格）兩軸同時結帳。撞名或未解就照舊換一格種標繼續推。

- **constellation**（`window_offset`／平移唯一配對）：0806 使用者裁決**從 visit 流程下架**，
  程式與測試留著待日後疊加，現在不被任何腳本呼叫。

**身分靠位置認，不靠圖案認**：卡面 `name_sig` 完全退出定位——同型量產機的卡面不可分，認錯
一台就是毒帳。點擊只取「這一格有東西」這個 bit，不讀卡面內容。

`board.find_unit_screen_hints` 的密度峰**只准拿來挑要點哪一格**（`probe_order`），一律不進座標
計算。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

import cv2
import numpy as np

from ggge_ai.runtime import board
from ggge_ai.runtime.device import blocked_for_map_tap

Point = tuple[float, float]
Cell = tuple[int, int]
Region = tuple[int, int, int, int]
Key = tuple[str, int]

SCREEN_CENTRE: Point = (1170.0, 540.0)

SOURCE_CONSTELLATION = "constellation"
SOURCE_MARCH = "march"
SOURCE_MARCH_MEET = "march_meet"
UNRESOLVED = "unresolved"

AXIS_NAMES = ("x", "y")

# 我方跳轉會進入「單位移動」行動模式，解除只能點右下「返回」；移動格點下去是真的
# 下移動指令。返回鈕帶自己的 intent 過危險帶（見 device.DANGER_BANDS）。
ALLY_DISMISS_TAP: tuple[int, int] = (1798, 971)
ALLY_DISMISS_INTENT = "ally_dismiss"

# 疊在地圖上層的 UI：這些矩形底下的「格」點不到，點下去命中的是 UI。0806 實機
# run 挑到 (2238,1011) 撞上 device 的 weapon_dial 帶才發現——空白格挑選原本完全
# 沒有覆蓋區概念，而它專挑離畫面中心最遠的格，等於專挑四角的 UI。
# 矩形量自 assets/screenshots/20260806-013329.png（敵方指定中）與 20260806-013000.png
# （我方回合地圖），(x, y, w, h) 螢幕座標，各邊留了一格餘裕。
UI_EXCLUSION_ZONES: tuple[Region, ...] = (
    # 頂部狀態帶：回合旗／TURN／破壞數／勝利條件字樣，橫貫全寬。
    (0, 0, 2340, 130),
    # 右上 AUTO ＋快進 ＋☰。
    (1700, 0, 640, 140),
    # 左上單位資訊卡：跳轉到某一台之後這裡會長出駕駛員／HP／EN 兩張卡。
    (140, 120, 840, 180),
    # 左側「回合結束」與「變更初期配置」兩顆鈕（對齊 device 的同名危險帶）。
    (140, 130, 320, 210),
    # 左下訊息列。
    (0, 940, 1560, 140),
    # 右下「單位列表」鈕：點下去會展開卡條，之後每一幀的 find_unit_screen_hints 都被污染。
    (1740, 930, 600, 150),
)


def in_ui_zone(point: Point, zones: Sequence[Region] = UI_EXCLUSION_ZONES) -> bool:
    return any(x <= point[0] <= x + w and y <= point[1] <= y + h for x, y, w, h in zones)


# 兩幀在地圖區的變化佔比：鏡頭在動＝整片都在變，待機動畫＝只有幾個百分點。
DESIGNATION_LEVEL = 40


def changed_fraction(
    before: np.ndarray, after: np.ndarray, region: Region = board.UNIT_DENSITY_REGION
) -> float:
    """兩幀在 `region` 內的變化佔比。

    0806 run 20260806-103335 量到的分界：同鏡位的兩張乾淨幀 0.007-0.04，鏡頭剛跳完還沒
    落定的兩張 0.15-0.37。面板的淡入轉場也用同一把尺（換一個 region）。
    """
    x, y, w, h = region
    lhs, rhs = before[y : y + h, x : x + w], after[y : y + h, x : x + w]
    if lhs.shape != rhs.shape or lhs.size == 0:
        return 1.0
    return float((cv2.absdiff(lhs, rhs).max(axis=2) > DESIGNATION_LEVEL).mean())


# ---------- 我方的目標端：移動範圍菱形 ----------

# 我方跳轉直接進入「單位移動」模式（screens.BATTLE_UNIT_MOVE），畫面把**可抵達格**逐格
# 標出來：可走的畫藍徽章、被敵方攻擊範圍蓋到的畫紅「!」徽章。兩種都是可抵達格，聯集才是
# 完整的菱形（0806 assets/screenshots/20260806-013500.png：藍 19 格、紅 18 格，聯集對
# 半徑 5＝該台移動力的菱形唯一吻合，中心正是那台的格）。
@dataclass(frozen=True)
class MarkKind:
    """一種可抵達格徽章的量測規格：色域，以及相對格距的尺寸／填充率／長寬比。

    數字全部量自 0806 實幀 assets/screenshots/20260806-013500.png（格距 128x120）：
    藍徽章 45x43、填充 0.62-0.75、長寬比 ~1；紅「!」45x63、填充 0.44-0.59、長寬比 ~0.67。
    形狀開成區間是留給縮放誤差，不是留給「差不多的美術」——右側敵方那條 34x64 的藍色
    HUD 條就是靠長寬比擋掉的，放它進來菱形就無解。
    """

    hsv: tuple[tuple[int, int, int], tuple[int, int, int]]
    width: tuple[float, float]
    height: tuple[float, float]
    fill: tuple[float, float]
    aspect: tuple[float, float]


# 藍＝可走，紅「!」＝可走但站上去會被敵方打到。兩種都是可抵達格，少收一種菱形就缺一整
# 側，中心跟著往另一側偏（實幀：只用藍的最小包覆菱形給出 (1,5)，聯集才唯一解出 (3,4)）。
RANGE_REACHABLE = MarkKind(((90, 80, 130), (120, 255, 255)), (0.28, 0.42), (0.28, 0.45),
                           (0.55, 0.85), (0.85, 1.20))
RANGE_THREATENED = MarkKind(((160, 120, 50), (179, 255, 140)), (0.28, 0.42), (0.42, 0.62),
                            (0.38, 0.70), (0.50, 0.85))
RANGE_MARKS: tuple[MarkKind, ...] = (RANGE_REACHABLE, RANGE_THREATENED)


def _mark_points(
    frame: np.ndarray, kind: MarkKind, pitch: tuple[float, float], region: Region
) -> list[Point]:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(kind.hsv[0], np.uint8), np.array(kind.hsv[1], np.uint8))
    x, y, w, h = region
    bounded = np.zeros_like(mask)
    bounded[y : y + h, x : x + w] = mask[y : y + h, x : x + w]
    for hx, hy, hw, hh in board.UNIT_DENSITY_HUD_HOLES:
        bounded[hy : hy + hh, hx : hx + hw] = 0
    count, _, stats, centroids = cv2.connectedComponentsWithStats(bounded, 8)
    out: list[Point] = []
    for index in range(1, count):
        width = int(stats[index, cv2.CC_STAT_WIDTH])
        height = int(stats[index, cv2.CC_STAT_HEIGHT])
        area = int(stats[index, cv2.CC_STAT_AREA])
        if width <= 0 or height <= 0:
            continue
        spans = (width / pitch[0], height / pitch[1])
        if not kind.width[0] <= spans[0] <= kind.width[1]:
            continue
        if not kind.height[0] <= spans[1] <= kind.height[1]:
            continue
        if not kind.fill[0] <= area / float(width * height) <= kind.fill[1]:
            continue
        if not kind.aspect[0] <= spans[0] / spans[1] <= kind.aspect[1]:
            continue
        out.append((float(centroids[index][0]), float(centroids[index][1])))
    return out


def range_marks(
    frame: np.ndarray,
    pitch: tuple[float, float],
    *,
    region: Region = board.UNIT_DENSITY_REGION,
) -> tuple[Point, ...]:
    """單位移動模式下每一個可抵達格的徽章中心（螢幕像素）。藍與紅都收。

    回傳的是點，對格由呼叫端用 `battle.map_grid` 做（runtime 不得 import battle）。
    """
    out: list[Point] = []
    for kind in RANGE_MARKS:
        out.extend(_mark_points(frame, kind, pitch, region))
    return tuple(out)


def _manhattan(a: Cell, b: Cell) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def diamond_centre(
    marks: Iterable[Cell],
    reach: int,
    *,
    window: tuple[int, int, int, int] | None = None,
    prefer: Cell | None = None,
) -> Cell | None:
    """可抵達格 → 那台單位站的格：以移動力為半徑的菱形中心。

    硬條件是**每一個看到的可抵達格都要落在半徑 reach 之內**——標記是遊戲自己畫的，畫出
    來的格不可能超出移動力。漏看的格不罰（單位圖示、地形、紅格都會蓋掉徽章），多看到的
    格直接否決那個中心。

    貼邊的單位菱形會被截掉，這時候可行中心不只一個：改用「預測最少沒看到的區域」收尾
    ——同樣的觀測下，預測範圍愈小的假設愈該被採信（`window` 給的是看得到的格範圍，
    截斷就在這裡發生）。仍然並列時取離 `prefer`（跳轉把目標帶到畫面中心，那一格就是
    先驗）最近的。
    """
    seen = sorted(set(marks))
    if not seen or reach < 0:
        return None
    lo_x = min(cell[0] for cell in seen) - reach
    hi_x = max(cell[0] for cell in seen) + reach
    lo_y = min(cell[1] for cell in seen) - reach
    hi_y = max(cell[1] for cell in seen) + reach
    scored: list[tuple[int, int, Cell]] = []
    for x in range(lo_x, hi_x + 1):
        for y in range(lo_y, hi_y + 1):
            centre = (x, y)
            if any(_manhattan(cell, centre) > reach for cell in seen):
                continue
            predicted = sum(
                1
                for cx in range(x - reach, x + reach + 1)
                for cy in range(y - reach, y + reach + 1)
                if _manhattan((cx, cy), centre) <= reach
                and (window is None or _inside_box((cx, cy), window))
            )
            away = 0 if prefer is None else _manhattan(centre, prefer)
            scored.append((predicted, away, centre))
    if not scored:
        return None
    scored.sort()
    best = scored[0]
    if len(scored) > 1 and scored[1][:2] == best[:2]:
        return None
    return best[2]


def _inside_box(cell: Cell, box: tuple[int, int, int, int]) -> bool:
    return box[0] <= cell[0] <= box[2] and box[1] <= cell[1] <= box[3]


# ---------- 敵方的目標端：攻擊範圍紅菱形 ----------

# 跳轉指定敵方時，畫面把該台的攻擊範圍**整片染紅**（以它為中心的菱形），目標自己那一格
# 還多一圈亮環。紅格的填色遠比任何美術強：0806 run 20260806-121910 的 36 張落點幀，範圍
# 內的格紅色佔比 0.5 以上、範圍外不到 0.05。
ATTACK_FILL_MIN = 0.35


def attack_cells(
    frame: np.ndarray,
    centres: Mapping[Cell, Point],
    *,
    half: float,
    min_fill: float = ATTACK_FILL_MIN,
    zones: Sequence[Region] = UI_EXCLUSION_ZONES,
) -> tuple[Cell, ...]:
    """落點幀上被攻擊範圍染紅的格。UI 遮罩先濾——左上單位卡的 HP 紅條就在地圖上層。"""
    return tuple(
        sorted(
            cell
            for cell, point in centres.items()
            if not in_ui_zone(point, zones) and red_fraction(frame, point, half) >= min_fill
        )
    )


def attack_centre(
    marks: Iterable[Cell],
    *,
    window: tuple[int, int, int, int] | None = None,
    prefer: Cell | None = None,
) -> Cell | None:
    """紅格 → 那台敵方站的格：**最小包覆菱形**的中心，唯一才收。

    與我方那條路的差別在證據形狀，不是喜好：我方的可抵達格是稀疏徽章（圖示會蓋掉一堆）
    而半徑已知（移動力），所以走「硬條件＋預測面積最小」；敵方的紅範圍是**整片實心**、
    半徑未知（移動力＋射程，名冊讀不到），所以「能把所有紅格包進去的最小半徑」就是最利的
    刀——0806 run 20260806-121910 的 36 張落點幀，最小半徑的中心**每一張都唯一**，而且
    與「跳轉把目標帶到畫面中心」這個獨立線索完全一致（36/36）。

    半徑並列時再比預測面積（同樣的觀測下預測愈小愈可信），還並列就回 None：那時候
    `prefer` 只當最後的排序，不當裁決。
    """
    seen = sorted(set(marks))
    if not seen:
        return None
    lo_x = min(cell[0] for cell in seen) - 1
    hi_x = max(cell[0] for cell in seen) + 1
    lo_y = min(cell[1] for cell in seen) - 1
    hi_y = max(cell[1] for cell in seen) + 1
    scored: list[tuple[int, int, int, Cell]] = []
    for x in range(lo_x, hi_x + 1):
        for y in range(lo_y, hi_y + 1):
            centre = (x, y)
            reach = max(_manhattan(cell, centre) for cell in seen)
            predicted = sum(
                1
                for cx in range(x - reach, x + reach + 1)
                for cy in range(y - reach, y + reach + 1)
                if _manhattan((cx, cy), centre) <= reach
                and (window is None or _inside_box((cx, cy), window))
            )
            away = 0 if prefer is None else _manhattan(centre, prefer)
            scored.append((reach, predicted, away, centre))
    scored.sort()
    best = scored[0]
    if len(scored) > 1 and scored[1][:2] == best[:2]:
        return None
    return best[3]


def probe_order(peaks: Iterable[Point], target: Point, *, limit: int = 2) -> tuple[Point, ...]:
    """要點哪幾格去問身分：離目標最近的幾個密度峰，目標自己那一顆不算。

    這是密度峰唯一的用途——挑點擊順序。峰的位置不進任何座標計算：格號一律由
    「我們點下去、而且真的出了卡」的那個點決定。
    """
    others = [
        peak
        for peak in peaks
        if abs(peak[0] - target[0]) > 1.0 or abs(peak[1] - target[1]) > 1.0
    ]
    others.sort(key=lambda peak: (peak[0] - target[0]) ** 2 + (peak[1] - target[1]) ** 2)
    return tuple(others[:limit])


# ---------- 標記接力平移：自力路徑的計格帳 ----------


@dataclass(frozen=True)
class MarchLeg:
    """一把推鏡的標記帳：推之前標記在第幾格、推之後在第幾格（同一軸的格索引）。

    重種標記不需要另記一筆——重種發生在同一幀內（鏡位沒變），下一把的 `before` 直接
    用新標記在該幀的格索引即可。
    """

    before: int
    after: int


def march_origin(legs: Sequence[MarchLeg], border_cell: int) -> int:
    """出發那一幀的「幀格 0 等於世界第幾格」。

    幀格與世界格差一個鏡位常數 origin：world = frame + origin。標記是同一顆實體，
    推鏡前後它的世界格不變，所以 origin 每把減少 (after - before)。推到界之後那一幀
    的 origin 由界定死（西界／北界＝世界 0），回推就得到出發幀的 origin。
    """
    travel = sum(leg.after - leg.before for leg in legs)
    return -border_cell + travel


def march_world(target_cell: int, legs: Sequence[MarchLeg], border_cell: int) -> int:
    """目標在出發幀的格索引 → 它的世界格索引。"""
    return target_cell + march_origin(legs, border_cell)


# ---------- march 順路結帳：種標點到單位就地認人 ----------

# 名冊反查的裁決。數值撞名（同型雜魚整批 29265/424）就是撞名，不猜。
MEET_UNIQUE = "unique"
MEET_COLLISION = "collision"
MEET_UNSOLVED = "unsolved"
MEET_NO_MATCH = "no_match"
MEET_NO_READ = "no_read"


@dataclass(frozen=True)
class MeetMatch:
    """摘要窗數值 → 名冊上的哪一台，以及說得出口的理由。"""

    key: Key | None
    reason: str


def roster_lookup(
    values: Sequence[int | None],
    table: Mapping[Key, Sequence[int | None]],
    resolved: Iterable[Key],
) -> MeetMatch:
    """簡化資訊窗讀到的數值 → 名冊上的那一台，唯一且已解才算數。

    掃描輪是 turn 1、還沒開打，所以摘要窗的 HP／EN 就是名冊詳情頁的滿血值，兩邊直接對。
    對到多台（同型量產機整批同數值）就是撞名——身分不猜，交回去繼續推到界。
    """
    if not values or any(value is None for value in values):
        return MeetMatch(None, MEET_NO_READ)
    wanted = tuple(values)
    hits = [key for key, row in table.items() if tuple(row) == wanted]
    if not hits:
        return MeetMatch(None, MEET_NO_MATCH)
    if len(hits) > 1:
        return MeetMatch(None, MEET_COLLISION)
    found = hits[0]
    if found not in set(resolved):
        return MeetMatch(found, MEET_UNSOLVED)
    return MeetMatch(found, MEET_UNIQUE)


def meet_cell(anchor: Cell, met: Cell, target_frame: Cell) -> Cell:
    """認出來的那台在世界的 `anchor`、它在這一幀的 `met` 格、目標在這一幀的 `target_frame`
    格 → 目標的世界格。兩軸同時出帳；幀內格差就是世界格差（同一幀＝同一個鏡位）。"""
    return (
        anchor[0] - (met[0] - target_frame[0]),
        anchor[1] - (met[1] - target_frame[1]),
    )


# ---------- （已下架）march 順路結帳：里程計 × 已解帳的指派驗證 ----------

# 幀格對格有抖動（格線偵測在邊緣多裁／少裁一條、圖示中心不在格心），所以 hint 與
# 「該假設下應該在的格」相差一格仍算命中。
MEET_TOLERANCE = 1
# 已解單位落在窗內卻連一個 hint 都沒有：圖示被地形／彈窗蓋掉是常事，容忍一台。
MEET_MISS_ALLOW = 1
# 假設本身一定自我命中（被指派的那台就站在那個 hint 上），所以命中數要 ≥2 才叫「有佐證」。
# 少了這一條，把其他已解單位全推出視野的假設就無從否證——它們沒有任何預測會被檢查到，
# 於是每個 (hint, 已解單位) 配對都活著，指派永遠不唯一。
MEET_MIN_HITS = 2

MEET_OK = "ok"
MEET_NO_LEDGER = "no_ledger"
MEET_NO_HINT = "no_hint"
MEET_NO_HYPOTHESIS = "no_hypothesis"
MEET_AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class MarkerOdometer:
    """標記相對目標的累計格差（世界格差），二維都記。

    西推時 y 名義上不變，但每一把重種標記算出來的格差兩軸都要入帳——只記推進那一軸，
    斜漂（重種挑的前緣格常常不同列）會靜靜累積成一個沒人看見的偏移。
    """

    offset: Cell

    @classmethod
    def seeded(cls, marker: Cell, target: Cell) -> MarkerOdometer:
        return cls((marker[0] - target[0], marker[1] - target[1]))

    def reseeded(self, old: Cell, new: Cell) -> MarkerOdometer:
        """同一幀內把證人換成另一顆標記：兩顆的幀格差就是世界格差。"""
        return MarkerOdometer(
            (self.offset[0] + new[0] - old[0], self.offset[1] + new[1] - old[1])
        )

    def target_frame(self, marker_frame: Cell) -> Cell:
        """目標自己在這一幀的格（可能已經出視野，格號照樣算得出來）。"""
        return (marker_frame[0] - self.offset[0], marker_frame[1] - self.offset[1])

    def delta(self, cell: Cell, marker_frame: Cell) -> Cell:
        """這一幀的格 `cell` 相對目標的世界格差。"""
        return (
            cell[0] - marker_frame[0] + self.offset[0],
            cell[1] - marker_frame[1] + self.offset[1],
        )


@dataclass(frozen=True)
class MeetFix:
    """順路結帳的裁決：目標的世界格、被指派的那個 hint 格，以及說得出口的理由。"""

    cell: Cell | None
    hint: Cell | None
    hypotheses: int
    reason: str


def march_meet(  # 已下架：0806 使用者裁決改走「點擊讀摘要反查名冊」，留著待日後疊加
    hints: Iterable[Cell],
    marker_frame: Cell,
    odometer: MarkerOdometer,
    resolved: Iterable[Cell],
    *,
    window: tuple[int, int, int, int] | None = None,
    tolerance: int = MEET_TOLERANCE,
    miss_allow: int = MEET_MISS_ALLOW,
    min_hits: int = MEET_MIN_HITS,
) -> MeetFix:
    """推鏡途中撞見已解單位就地結帳：**指派驗證**，不是平移搜索。

    里程計已經把平移量死了——這一幀的每一格相對目標差多少格是算得出來的，剩下的自由度
    只有「幀內哪一個 hint 是哪一台已解單位」。逐一假設 (hint, 已解單位)，反推目標的世界
    格，再拿同一個假設去問幀內其他已解單位「你該在的那一格有沒有 hint」：撐得住的假設
    唯一才收，否則繼續推到界（界是兜底，不是這條路的替代品）。

    `hints` 是 `board.find_unit_screen_hints` 對格後的候選——啟發式、會漏會多，所以命中
    容 `tolerance` 格、漏檢容 `miss_allow` 台；它們在這裡只當**驗證證據**，座標仍由里程計
    給。`window` 是這一幀看得見的格範圍（幀格），用來判斷某台已解單位「應該入鏡」。
    """
    world = sorted(set(resolved))
    seen = sorted(set(hints))
    if not world:
        return MeetFix(None, None, 0, MEET_NO_LEDGER)
    if not seen:
        return MeetFix(None, None, 0, MEET_NO_HINT)
    survivors: dict[Cell, Cell] = {}
    for hint in seen:
        shift = odometer.delta(hint, marker_frame)
        for anchor in world:
            target = (anchor[0] - shift[0], anchor[1] - shift[1])
            if target[0] < 0 or target[1] < 0 or target in survivors:
                continue
            if not _meet_consistent(
                seen, marker_frame, odometer, world, target, window, tolerance, miss_allow,
                min_hits,
            ):
                continue
            survivors[target] = hint
    if not survivors:
        return MeetFix(None, None, 0, MEET_NO_HYPOTHESIS)
    if len(survivors) > 1:
        return MeetFix(None, None, len(survivors), MEET_AMBIGUOUS)
    cell, hint = next(iter(survivors.items()))
    return MeetFix(cell, hint, 1, MEET_OK)


def _meet_consistent(
    hints: Sequence[Cell],
    marker_frame: Cell,
    odometer: MarkerOdometer,
    world: Sequence[Cell],
    target: Cell,
    window: tuple[int, int, int, int] | None,
    tolerance: int,
    miss_allow: int,
    min_hits: int,
) -> bool:
    """這個「目標在 target」的假設撐不撐得住幀內所有已解單位的檢查。"""
    if any(
        _meet_world(hint, marker_frame, odometer, target)[axis] < 0
        for hint in hints
        for axis in (0, 1)
    ):
        return False
    hits = 0
    misses = 0
    for anchor in world:
        shift = odometer.delta((0, 0), marker_frame)
        cell = (anchor[0] - target[0] - shift[0], anchor[1] - target[1] - shift[1])
        if window is not None and not _inside_box(cell, window):
            continue
        if any(
            abs(hint[0] - cell[0]) <= tolerance and abs(hint[1] - cell[1]) <= tolerance
            for hint in hints
        ):
            hits += 1
        else:
            misses += 1
    return hits >= min_hits and misses <= miss_allow


def _meet_world(
    cell: Cell, marker_frame: Cell, odometer: MarkerOdometer, target: Cell
) -> Cell:
    shift = odometer.delta(cell, marker_frame)
    return (target[0] + shift[0], target[1] + shift[1])


# ---------- 窗位：平移唯一配對 ----------

# 配對至少要兩格才有形狀可言；一格到處都對得上。
CONSTELLATION_MIN_MATCH = 2

MATCH_OK = "ok"
MATCH_FEW_CELLS = "few_cells"
MATCH_NO_MATCH = "no_match"
MATCH_AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class WindowFix:
    """幀格 → 世界格的平移，以及裁決過程說得出口的理由。"""

    delta: Cell | None
    matched: int
    reason: str


def window_offset(
    references: Iterable[Cell],
    occupied: Iterable[Cell],
    *,
    min_match: int = CONSTELLATION_MIN_MATCH,
) -> WindowFix:
    """已解單位的世界格 × 幀內**點擊確認有單位**的格 → 這一窗的平移。

    `occupied` 的每一格都必須是點下去真的有反應的格（出卡或進選取）——只取「存在」這個
    bit，不看是誰。配對允許幀裡有還沒解的單位（它們只是配不到參考），但**每一個對得上的
    平移都要用命中數比大小，唯一才收**：兩個平移打平就是拒收，寧可漏認不可錯認。
    """
    world = set(references)
    seen = sorted(set(occupied))
    if not world or len(seen) < min_match:
        return WindowFix(None, 0, MATCH_FEW_CELLS)
    scored: dict[Cell, int] = {}
    for cell in seen:
        for reference in world:
            delta = (reference[0] - cell[0], reference[1] - cell[1])
            if delta in scored:
                continue
            scored[delta] = sum(
                1 for other in seen if (other[0] + delta[0], other[1] + delta[1]) in world
            )
    ranked = sorted(scored.items(), key=lambda item: -item[1])
    best, hits = ranked[0]
    if hits < min_match:
        return WindowFix(None, hits, MATCH_NO_MATCH)
    if len(ranked) > 1 and ranked[1][1] == hits:
        return WindowFix(None, hits, MATCH_AMBIGUOUS)
    return WindowFix(best, hits, MATCH_OK)


# ---------- 座標帳 ----------


@dataclass
class JumpLedger:
    """逐台的座標帳：全部是絕對世界格，沒有相對座標這種半成品。"""

    cells: dict[Key, Cell] = field(default_factory=dict)
    sources: dict[Key, str] = field(default_factory=dict)
    failures: dict[Key, int] = field(default_factory=dict)
    retired: set[Key] = field(default_factory=set)

    def anchor(self, key: Key, cell: Cell, source: str = SOURCE_MARCH) -> None:
        self.cells[key] = cell
        self.sources[key] = source
        self.failures.pop(key, None)

    def fail(self, key: Key) -> int:
        self.failures[key] = self.failures.get(key, 0) + 1
        return self.failures[key]

    def retire(self, key: Key) -> None:
        self.retired.add(key)

    def resolved(self, key: Key) -> bool:
        return key in self.cells

    def references(self) -> tuple[Cell, ...]:
        """平移配對的參考集：已解單位的世界格。"""
        return tuple(sorted(set(self.cells.values())))


def next_target(
    ledger: JumpLedger,
    roster: Sequence[Key],
    *,
    give_up_after: int = 2,
) -> Key | None:
    """排程：名冊順序，但已解台數 >0 之後優先挑「名冊上緊鄰已解單位」的那一台。

    同勢力單位在地圖上成群，名冊相鄰大概率地圖相鄰——鄰居入鏡的機率高，接力路徑
    （便宜）才有機會命中。第一台必然沒有鄰居可接，走自力路徑當種子。
    """
    pending = [
        key
        for key in roster
        if key not in ledger.cells
        and key not in ledger.retired
        and ledger.failures.get(key, 0) < give_up_after
    ]
    if not pending:
        return None
    order = {key: index for index, key in enumerate(roster)}
    solved = [order[key] for key in ledger.cells if key in order]
    if not solved:
        return pending[0]
    return min(pending, key=lambda key: (min(abs(order[key] - at) for at in solved), order[key]))


def ledger_report(ledger: JumpLedger, roster: Sequence[Key]) -> list[Mapping[str, object]]:
    """最終座標帳。寫得出來的一律是絕對格；寫不出來就是 `unresolved`，不寫半成品。"""
    out: list[Mapping[str, object]] = []
    for faction, index in roster:
        key = (faction, index)
        cell = ledger.cells.get(key)
        out.append(
            {
                "faction": faction,
                "index": index,
                "cell": None if cell is None else [cell[0], cell[1]],
                "source": ledger.sources.get(key, UNRESOLVED) if cell else UNRESOLVED,
            }
        )
    return out


# ---------- 解除敵方指定用的空白格 ----------

# 敵方跳轉後畫面留著紅圈指定與紅色攻擊範圍格，點任一個「不是峰、也不是紅格」的
# 格心就解除，鏡頭留在原地。紅格用格內紅色像素佔比判，不吃 battle/vision 的門檻表。
RED_CELL_FRACTION = 0.12
PEAK_KEEP_OUT_PITCH = 0.9


def red_fraction(frame: np.ndarray, centre: Point, half: float) -> float:
    x0, y0 = max(int(centre[0] - half), 0), max(int(centre[1] - half), 0)
    patch = frame[y0 : y0 + int(half * 2), x0 : x0 + int(half * 2)]
    if patch.size == 0:
        return 1.0
    pixels = patch.reshape(-1, 3).astype(np.float32)
    blue, green, red = pixels[:, 0], pixels[:, 1], pixels[:, 2]
    return float(((red > 90) & (red > blue + 30) & (red > green + 30)).mean())


def clean_points(
    frame: np.ndarray,
    centres: Iterable[Point],
    peaks: Sequence[Point],
    *,
    keep_out: float,
    red_half: float,
    region: Region = board.UNIT_DENSITY_REGION,
    red_max: float = RED_CELL_FRACTION,
    zones: Sequence[Region] = UI_EXCLUSION_ZONES,
    blocked: Callable[[Point], bool] = blocked_for_map_tap,
) -> list[Point]:
    """點得下去的空白格心：離峰遠、不紅、不在 UI 遮罩底下、不撞危險帶。

    `centres` 是**這一幀自己的**格心（螢幕像素），由呼叫端用 `battle.map_grid` 的逐線
    格網算——固定 pitch 除法會被縱向透視咬掉一列，挑出來的「格心」其實壓在格線上。

    UI 遮罩之外還要問危險帶：帶的範圍比可見鈕大（帶要包住鈕在各畫面的所有位置），
    逐一補遮罩去追帶的形狀沒有盡頭，所以 `device.blocked_for_map_tap` 才是權威。
    """
    x, y, w, h = region
    out: list[Point] = []
    for point in centres:
        if not (x <= point[0] <= x + w and y <= point[1] <= y + h):
            continue
        if any(
            abs(peak[0] - point[0]) <= keep_out and abs(peak[1] - point[1]) <= keep_out
            for peak in peaks
        ):
            continue
        if in_ui_zone(point, zones) or blocked(point):
            continue
        if red_fraction(frame, point, red_half) >= red_max:
            continue
        out.append(point)
    return out


def blank_cell_tap(
    frame: np.ndarray,
    centres: Iterable[Point],
    peaks: Sequence[Point],
    **filters,
) -> tuple[int, int] | None:
    """解除敵方指定用的空白格：乾淨格裡離畫面中心最遠的那一個。

    挑最遠的是為了離目標與它的攻擊範圍越遠越好——貼著目標點下去等於在紅格裡賭。
    """
    points = clean_points(frame, centres, peaks, **filters)
    if not points:
        return None
    best = max(
        points,
        key=lambda point: float(
            np.hypot(point[0] - SCREEN_CENTRE[0], point[1] - SCREEN_CENTRE[1])
        ),
    )
    return (int(round(best[0])), int(round(best[1])))
