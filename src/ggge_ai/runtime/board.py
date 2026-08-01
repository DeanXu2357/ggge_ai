"""盤面全覽掃描：最小縮放＋系統平移，把全場單位收成格座標。

三段機制，各自可離線測：

1. **格網**：顯示方格開著時，格線是貫穿地圖的細亮脊。對高通後的投影取峰＝線位。
   直線 pitch 穩定約 128，橫線間距隨 y 從 108 遞增到 123（縱向透視），所以格網
   以線位表示，不概括成單一 cell size。
2. **單位存在**：最小縮放下 HP 弧與隊徽環併成一個 ~90-110px 的環，扁弧的形狀
   閘門會全瞎（實測整幀 25+ 台只抓到 0-7 台）。改用密度峰：三個色帶聯集當「有
   東西」、以一格大小的方框平均後取局部極大。門檻對著 ex2if 系列的逐幀人工
   轉錄調出來（本批重測：完整可見的 103/104，九幀共吐 176 個峰——多出來的是
   靜態 HUD 家具與戰艦這類多格精靈的額外峰，合併與人工複核在下游）。
3. **平移量測**：相位相關給位移與信賴度；星空這種無特徵區信賴度會掉到接近 0，
   改投票制——單位星座每一對配對投一個平移、有兩台以上支持的眾數勝。量測窗要
   ≥2× 最大平移，否則循環相關會繞回（0719 實測：1050px 窗量 600px 位移量出
   −505 反號），所以平移一律走小步：短推才留得住重疊帶。
4. **量測雙閘**：`envelope` 拿指令當包絡（同軸同號、倍率有上界）擋繞回混疊的
   「自信錯值」，`phase_residual` 拿格線相位交叉驗證（混疊差一個窗寬、窗寬 mod
   格距 ≠ 0，相位對不上即拒收）。指令只閘量測，永遠不寫進覆蓋。
5. **邊界**：一次平移後畫面沒動＝那個方向到邊（0730 偵察輪實證此判準）。

世界座標的累積與四態知識圖在 `runtime/coverage.py`——這裡只做像素。

單位一律**不帶陣營**出去。腳下弧的顏色不是陣營的權威——我方回合未行動的我方
單位弧色偏紅、與敵紅在同一幀上 HSV 幾乎重合（fixtures hp_arc/*，定案 5）。掃描
只回報「這裡有一台」＋弧色線索，陣營由證據分層那一步決定。

**掃描前置**：可行動單位卡條要先收起來（展開時蓋住地圖下緣，密度峰的掃描帶
一路到 y1020）。
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import cv2
import numpy as np

log = logging.getLogger(__name__)

Point = tuple[float, float]
Cell = tuple[int, int]
Region = tuple[int, int, int, int]

# 地圖區：上方避開回合橫幅帶、下方停在 MP／技能／支援鈕列之上（它們的亮圓框會
# 被當成可移動格）。相位相關的量測窗就是它，1600 寬對 600px 平移安全。
MAP_REGION: Region = (150, 250, 1600, 620)

GRID_REGION: Region = (150, 250, 1600, 530)
GRID_MIN_SPACING = 90
GRID_MAX_SPACING = 160
GRID_MIN_COLS = 6
GRID_MIN_ROWS = 4
GRID_GAP_RANGE = 35
# 邊帶格線的退路窗（MAP_REGION 的四象限）。走到地圖邊緣時地圖只佔畫面一角，全幀
# GRID_REGION 帶的取樣線數湊不到門檻——0801 實測 t7-leg 到 t13-precheck 這七幀全幀
# 帶一律 None，而下半窗讀得到 pitch 92-93 的格線。線數門檻按窗邊長等比縮，下限 3：
# 兩個間距才談得上「間距均勻」這一閘。
LATTICE_WINDOW_FLOOR = 3
# 格距帶由細到粗。(90,160) 是預設縮放標定出來的（實測 pitch 108-128）；(60,105) 是
# 最小縮放——0731 pinch 煙測（data/runs/20260731-170423 frames/00013）量到欄距 91.5
# ／列距 86.0，列距整排落在舊下限 90 之下，所以整段 grid_on 翻 False。**細帶先試**
# 是防混疊的關鍵：粗帶的最小間距套在細格網上會隔行取線，湊出翻倍的「均勻」格距
# 而且過得了合理性閘——那正是「自信錯值」，寧可先問細帶。
SPACING_BANDS: tuple[tuple[int, int], ...] = ((60, 105), (90, 160))

RED_HINT = "red"
BLUE_HINT = "blue"
TEAL_HINT = "teal"

# HSV 帶域搬自 battle/vision.py（實測校出，未改任何數字）：弧會發光但不飽和
# （S<=210、V>=155），把它和機體塗裝（更暗）與 HUD 條（全飽和）分開。敵紅上界
# 停在 10，因為每條弧的右半都是共用的橘黃漸層（hue ~14），放寬到 25 會讓整幀
# 我方單位變成假敵人。
ARC_BANDS: dict[str, tuple[tuple[tuple[int, int, int], tuple[int, int, int]], ...]] = {
    RED_HINT: (((0, 100, 155), (10, 210, 255)), ((168, 100, 155), (180, 210, 255))),
    BLUE_HINT: (((100, 100, 155), (125, 210, 255)),),
    TEAL_HINT: (((78, 100, 155), (97, 210, 255)),),
}

# 密度峰（最小縮放的單位偵測）。掃描帶一路到 x2250／y1020：卡條收起後地圖遠遠
# 超出 UNIT_SCAN_REGION，右緣停在圖示說明欄之前、下緣停在收合列 ▲ 之上。
UNIT_DENSITY_REGION: Region = (150, 90, 2100, 930)
UNIT_DENSITY_WINDOW = 91
# 是窗內的著色像素**絕對數量**不是比例：248（=3%）會漏掉一個被下緣切掉、只剩
# 212 的環，而每一台已確認的單位都過 200。
UNIT_DENSITY_MIN_COUNT = 200
# 局部極大的測試半徑與去重半徑刻意不同：放到 80 會讓強鄰居的密度高原吃掉旁邊
# 弱單位的鞍點（實測三台暗色單位整批消失），31 保住各自的峰頂，間距仍由下面的
# 貪婪去重管。
UNIT_DENSITY_LOCAL_MAX = 31
UNIT_DENSITY_MIN_DIST = 80
# 回合橫幅（我軍回合／剩餘回合／破壞數）壓在掃描帶左上角，它的彩色字會像單位
# 一樣出峰。洞要從 mask 挖而不是從密度圖挖——密度圖照樣把橫幅的像素透過方框
# 濾波積進來，只在密度層挖洞只是把鬼影趕到洞緣。
#
# 另兩個洞是固定位置的 HUD 鈕（0801 第 6 輪逐幀量測，見 docs/reviews/scan-v2_7-review.md
# 第二節）：左上「變更初期配置」藍鈕實測 x154-437／y250-318，右上加速 teal 鈕
# x1937-2101／y7-88。**鈕只在特定狀態出現，洞卻是永久的**——被洞蓋住的格因此永遠
# 進不了 `coverage.readable`，那幾格由覆蓋模型既有的 HUD 壓角機制承接（留 UNKNOWN、
# 前緣回補，補不到就明寫退休）。右上洞**不要再往下挖**：實測 t19／t20／t35 都有真
# 單位的血弧貼在鈕正下方 y85-115，挖到 y100 就開始吃掉它們。
UNIT_DENSITY_HUD_HOLES: tuple[Region, ...] = (
    (0, 0, 470, 170),
    (146, 242, 300, 84),
    (1928, 0, 182, 95),
)
HINT_SAMPLE_HALF = 50

# 平移手勢起手點格：起手落在單位精靈上會被遊戲吃掉（看起來像到邊但鏡頭沒動），
# 所以逐幀從這格裡挑離所有單位最遠的一點。
PAN_ORIGIN_GRID: tuple[Point, ...] = tuple(
    (float(x), float(y)) for y in (360, 470, 580, 660) for x in (760, 940, 1170, 1400, 1580)
)
PAN_HALF = {"x": 250, "y": 170}
PAN_MIN_REACH = 50.0
PAN_MAX_REACH = 260.0
# 拖得慢比較不會被吃掉：0719 星圖上 500ms 的拖曳整段被吞（動作後的鏡頭緩動
# ＋adb 掉線）。呼叫端把手勢打出去時用這兩個值。
PAN_DURATION_S = 0.7
PAN_SETTLE_S = 1.5
DIRECTIONS: dict[str, tuple[int, int]] = {
    "east": (1, 0),
    "west": (-1, 0),
    "north": (0, -1),
    "south": (0, 1),
}

# 一次平移的位移小於這個像素數就算沒動＝停滯（到邊或指令被吃掉）。實測一腿約
# 570-600px，半格已是巨大差距，取 40 對量測雜訊有餘裕。
EDGE_SHIFT_PX = 40.0
# 相位相關在無特徵星空上會瞎掉；信賴度低於此就不信它的數字，改看幀差。
SHIFT_MIN_RESPONSE = 0.05
EDGE_FRAME_DIFF = 2.5

# 指令包絡閘的三個等級。REPEAT 是「同一個手勢被執行兩次」——腿長規則保證 2× 仍
# 落在無歧義量測範圍內，所以照量入帳（被跳過的帶留 UNKNOWN 由前緣回補）；繞回
# 混疊差一個窗寬，不是反號就是遠超上界，兩種都落在 REFUSED。
ENVELOPE_OK = "ok"
ENVELOPE_REPEAT = "repeat"
ENVELOPE_REFUSED = "refused"
ENVELOPE_SINGLE = 1.5
ENVELOPE_DOUBLE = 2.5
ENVELOPE_CROSS = 0.4
# 格線相位交叉驗證的容差（欄距的比例）。只用在直線軸：直線 pitch 穩定約 128，
# 橫線間距隨 y 從 108 遞增到 123（縱向透視），對橫軸取模的相位本來就不是不變量。
PHASE_TOLERANCE = 0.25

# 水平位移的格線相位通道（`measure_pan`）。source 帶證人後綴，遙測才分得出走哪一條：
# lattice:constellation ／ lattice:phase ／ lattice:commanded。
LATTICE_SOURCE = "lattice"
WITNESS_CONSTELLATION = "constellation"
WITNESS_PHASE = "phase"
WITNESS_COMMANDED = "commanded"
# 星座票被影像複驗判成「確定沒動」——與 `_STILL` 分開記名，遙測才看得出這一幀的
# 停滯是誰認定的。
CONSTELLATION_STILL = "constellation:still"
# 證人與候選的容差（欄距的比例）。半格＝候選之間的一半間距，所以它挑得出唯一候選、
# 只在證人剛好卡在兩個候選正中間時才拒收。
LATTICE_WITNESS_TOLERANCE = 0.5
# 兩幀欄距差超過這個比例＝縮放被動過，格線相位不是同一個世界的量，退回現行路徑。
LATTICE_PITCH_DRIFT = 0.1
# 整數欄候選的枚舉界：相位相關的無歧義範圍是 ±窗長/2。
PAN_UNAMBIGUOUS = MAP_REGION[2] / 2.0


def crop(frame: np.ndarray, region: Region) -> np.ndarray:
    x, y, w, h = region
    return frame[y : y + h, x : x + w]


@dataclass(frozen=True)
class Lattice:
    """格線位置（螢幕像素）。cols／rows 是線位不是格心。"""

    cols: tuple[int, ...]
    rows: tuple[int, ...]

    @property
    def col_pitch(self) -> float:
        return _median_gap(self.cols)

    @property
    def row_pitch(self) -> float:
        return _median_gap(self.rows)

    def snap(self, point: Point) -> Point:
        """最近格心：各軸取夾住它的那對線的中點。線span 之外的軸原值通過。"""
        return (_snap_axis(point[0], self.cols), _snap_axis(point[1], self.rows))

    def cell_of(self, point: Point) -> Cell | None:
        """本幀局部格座標（左上第一格＝(0,0)），落在線span 外就 None。"""
        col = _index_axis(point[0], self.cols)
        row = _index_axis(point[1], self.rows)
        if col is None or row is None:
            return None
        return (col, row)


def _median_gap(positions: Sequence[int]) -> float:
    gaps = sorted(b - a for a, b in zip(positions, positions[1:], strict=False))
    if not gaps:
        return 0.0
    n = len(gaps)
    return float(gaps[n // 2] if n % 2 else (gaps[n // 2 - 1] + gaps[n // 2]) / 2)


def _snap_axis(value: float, positions: Sequence[int]) -> float:
    if not positions or value < positions[0] or value > positions[-1]:
        return value
    for a, b in zip(positions, positions[1:], strict=False):
        if a <= value <= b:
            return (a + b) / 2.0
    return value


def _index_axis(value: float, positions: Sequence[int]) -> int | None:
    if not positions or value < positions[0] or value > positions[-1]:
        return None
    for index, (a, b) in enumerate(zip(positions, positions[1:], strict=False)):
        if a <= value <= b:
            return index
    return None


def read_lattice(
    frame: np.ndarray | None,
    region: Region = GRID_REGION,
    bands: Sequence[tuple[int, int]] = SPACING_BANDS,
    minimum: tuple[int, int] = (GRID_MIN_COLS, GRID_MIN_ROWS),
) -> Lattice | None:
    """格線位置，讀不出合理格網就 None。

    高通投影取峰：格線是貫穿整張地圖的細亮脊，所以 |高通| 的行／列均值會出峰，
    單位與地圖美術則被平均掉。三重閘擋掉假格網——頭尾間距出帶就裁掉（面板邊
    不是格線）、線數門檻（無格線幀上湊巧對齊的精靈永遠湊不到這個數）、間距全帶
    內且均勻（單位移動模式的藍格覆蓋描同一格網但邊緣抖半格，鬆到不能吸附）。

    格距帶**由細到粗逐帶試，第一個過關的贏**：縮放會改格距（0731 實測最小縮放
    落到 68-83），而粗帶的最小間距套在細格網上會隔行取線、湊出翻倍的假格距——
    先問細帶就是不讓那個自信錯值有機會出線。
    """
    if frame is None:
        return None
    x0, y0, w, h = region
    patch = crop(frame, region)
    if patch.shape[0] < h or patch.shape[1] < w:
        return None
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY).astype(np.float32)
    highpass = np.abs(gray - cv2.GaussianBlur(gray, (0, 0), 6))
    columns = highpass.mean(axis=0)
    lines = highpass.mean(axis=1)
    for low, high in bands:
        cols = _trim(_ridges(columns, x0, low), low, high)
        rows = _trim(_ridges(lines, y0, low), low, high)
        if _plausible(cols, minimum[0], low, high) and _plausible(rows, minimum[1], low, high):
            return Lattice(tuple(cols), tuple(rows))
    return None


def lattice_windows(region: Region = MAP_REGION) -> tuple[Region, ...]:
    x, y, w, h = region
    half = (w // 2, h // 2)
    return tuple(
        (x + col * half[0], y + row * half[1], half[0], half[1])
        for row in (0, 1)
        for col in (0, 1)
    )


LATTICE_WINDOWS: tuple[Region, ...] = lattice_windows()


@dataclass(frozen=True)
class GridSpan:
    """這一幀格線實際覆蓋的螢幕矩形，外加四側有沒有看到「格網到此為止」。

    `box` 是線位圍出來的矩形（不是格心）；`edges` 只收有證據的那幾側，看不出來就
    不出證言——星空半幅虛空與「地圖還沒看完」在幾何上長得一樣。
    """

    lattice: Lattice
    box: Region
    edges: frozenset[str]


# 終止邊的三道閘（0801 run 20260801-080213 逐幀實測，見 docs/reviews/scan-v2_6-review.md）：
# 真終止邊外側的高通能量 3.9-8.5、內側 17.3-21.3；灰階 26-34 對 43-52。地圖還沒看完
# 的那幾側外側高通 17-24＝與內側同級。**兩個比值＋一個絕對上限**：批 7 的星空假邊界
# 前科就是只看單一絕對值，這裡要求外側同時安靜、暗、而且比內側安靜得多。
EDGE_QUIET_HIGH = 10.0
EDGE_TEXTURE_RATIO = 0.5
EDGE_BRIGHTNESS_RATIO = 0.75


def read_span(frame: np.ndarray | None) -> GridSpan | None:
    """格線覆蓋範圍＋終止邊目擊。找不到格線就 None（＝這一幀不敢說哪裡有格子）。"""
    for band, minimum in _lattice_bands():
        lattice = read_lattice(frame, band, minimum=minimum)
        if lattice is None:
            continue
        box = (
            lattice.cols[0],
            lattice.rows[0],
            lattice.cols[-1] - lattice.cols[0],
            lattice.rows[-1] - lattice.rows[0],
        )
        return GridSpan(lattice, box, _terminal_edges(frame, lattice, band))
    return None


def _lattice_bands() -> Iterable[tuple[Region, tuple[int, int]]]:
    yield (GRID_REGION, (GRID_MIN_COLS, GRID_MIN_ROWS))
    for window in LATTICE_WINDOWS:
        yield (window, _window_minimum(window))


def _terminal_edges(frame: np.ndarray, lattice: Lattice, band: Region) -> frozenset[str]:
    """哪幾側的最外一條線之外是虛空。

    先要**帶內留得下一整格的檢驗空間**：貼著取樣帶邊緣的線分不出「格網到此為止」
    與「帶就到這裡」，那種側一律不出證言（象限窗的窗緣尤其）。
    """
    out: set[str] = set()
    for side, outside, inside in _edge_strips(lattice, band):
        beyond = _strip_stats(frame, outside)
        within = _strip_stats(frame, inside)
        if beyond is None or within is None:
            continue
        gray, texture = beyond
        if texture > EDGE_QUIET_HIGH:
            continue
        if texture > EDGE_TEXTURE_RATIO * within[1]:
            continue
        if gray > EDGE_BRIGHTNESS_RATIO * within[0]:
            continue
        out.add(side)
    return frozenset(out)


def _edge_strips(lattice: Lattice, band: Region) -> Iterable[tuple[str, Region, Region]]:
    bx, by, bw, bh = band
    cols, rows = lattice.cols, lattice.rows
    span = (cols[-1] - cols[0], rows[-1] - rows[0])
    across = (int(lattice.col_pitch), int(lattice.row_pitch))
    if span[0] <= 0 or span[1] <= 0 or across[0] <= 0 or across[1] <= 0:
        return
    if cols[0] - across[0] >= bx:
        yield ("west", (cols[0] - across[0], rows[0], across[0], span[1]),
               (cols[0], rows[0], across[0], span[1]))
    if cols[-1] + across[0] <= bx + bw:
        yield ("east", (cols[-1], rows[0], across[0], span[1]),
               (cols[-1] - across[0], rows[0], across[0], span[1]))
    if rows[0] - across[1] >= by:
        yield ("north", (cols[0], rows[0] - across[1], span[0], across[1]),
               (cols[0], rows[0], span[0], across[1]))
    if rows[-1] + across[1] <= by + bh:
        yield ("south", (cols[0], rows[-1], span[0], across[1]),
               (cols[0], rows[-1] - across[1], span[0], across[1]))


def _strip_stats(frame: np.ndarray, strip: Region) -> tuple[float, float] | None:
    x, y, w, h = strip
    height, width = frame.shape[:2]
    if x < 0 or y < 0 or w < 4 or h < 4 or x + w > width or y + h > height:
        return None
    patch = cv2.cvtColor(crop(frame, strip), cv2.COLOR_BGR2GRAY).astype(np.float32)
    texture = np.abs(patch - cv2.GaussianBlur(patch, (0, 0), 6))
    return (float(patch.mean()), float(texture.mean()))


def find_lattice(frame: np.ndarray | None) -> Lattice | None:
    """找得到格線就回：先問全幀 GRID_REGION 帶，讀不出來再問 MAP_REGION 的四象限窗。

    相位是 mod pitch 的量，子窗的線位一樣驗得了相位——所以邊緣區沒必要因為「整條
    帶湊不到六欄四列」就整個放棄相位交叉驗證。0801 實測（run 20260801-080213）：
    走到北緣之後 t7-leg 到 t13-precheck 七幀全幀帶一律 None，`_snap` 於是連驗都不驗
    直接放行，t11／t12 兩腿實際各滑了 200px 以上卻被記成停滯，同一片場景以同一個
    offset 重複吸收——台數膨脹的第一顆齒輪。

    **回的是線位，不是新的量測**：呼叫端（`Odometer._snap`／`rephase`）只拿它跟世界
    格網的相位對答案，pitch 仍取世界格網的。錨定（`Survey._anchor`）刻意不走這裡，
    新世界的格距要全幀帶那種取樣量才敢定。
    """
    for band, minimum in _lattice_bands():
        lattice = read_lattice(frame, band, minimum=minimum)
        if lattice is not None:
            return lattice
    return None


def _window_minimum(region: Region) -> tuple[int, int]:
    return (
        max(LATTICE_WINDOW_FLOOR, round(GRID_MIN_COLS * region[2] / GRID_REGION[2])),
        max(LATTICE_WINDOW_FLOOR, round(GRID_MIN_ROWS * region[3] / GRID_REGION[3])),
    )


def _ridges(profile: np.ndarray, offset: int, spacing: int = GRID_MIN_SPACING) -> list[int]:
    centered = profile - profile.mean()
    gate = centered.std() * 1.2
    out: list[int] = []
    for i in range(2, len(centered) - 2):
        if not (centered[i] >= centered[i - 1] and centered[i] >= centered[i + 1]):
            continue
        if centered[i] <= gate:
            continue
        if not out or i - (out[-1] - offset) >= spacing:
            out.append(offset + i)
        elif centered[i] > centered[out[-1] - offset]:
            out[-1] = offset + i
    return out


def _trim(
    positions: list[int], low: int = GRID_MIN_SPACING, high: int = GRID_MAX_SPACING
) -> list[int]:
    out = list(positions)
    while len(out) >= 2 and not (low <= out[1] - out[0] <= high):
        out.pop(0)
    while len(out) >= 2 and not (low <= out[-1] - out[-2] <= high):
        out.pop()
    return out


def _plausible(
    positions: list[int],
    minimum: int,
    low: int = GRID_MIN_SPACING,
    high: int = GRID_MAX_SPACING,
) -> bool:
    if len(positions) < minimum:
        return False
    gaps = [b - a for a, b in zip(positions, positions[1:], strict=False)]
    if max(gaps) - min(gaps) > GRID_GAP_RANGE:
        return False
    return all(low <= gap <= high for gap in gaps)


@dataclass(frozen=True)
class Sighting:
    """一台單位的一次目擊。hint ＝ 腳下弧的主色，**不是陣營**。"""

    point: Point
    hint: str | None = None


def _band_masks(frame: np.ndarray) -> dict[str, np.ndarray]:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    masks: dict[str, np.ndarray] = {}
    for hint, bands in ARC_BANDS.items():
        mask = np.zeros(hsv.shape[:2], np.uint8)
        for low, high in bands:
            mask |= cv2.inRange(hsv, low, high)
        masks[hint] = mask
    return masks


def find_units(
    frame: np.ndarray | None, region: Region = UNIT_DENSITY_REGION
) -> tuple[Point, ...]:
    """單位腳下環的位置，只論存在不論陣營。"""
    if frame is None:
        return ()
    masks = _band_masks(frame)
    mask = np.zeros(frame.shape[:2], np.uint8)
    for band in masks.values():
        mask |= band
    mask = (mask > 0).astype(np.uint8)
    for hx, hy, hw, hh in UNIT_DENSITY_HUD_HOLES:
        mask[hy : hy + hh, hx : hx + hw] = 0
    window = UNIT_DENSITY_WINDOW
    # 整數計數而不是正規化浮點：float32 方框濾波跨執行不決定（OpenCV 平行分塊
    # 改變累加順序），會翻掉高原邊緣的峰、讓拼接出來的鏡頭每次抖幾個像素。
    density = cv2.boxFilter(mask, cv2.CV_32S, (window, window), normalize=False).astype(np.uint16)
    x0, y0, w, h = region
    bounded = np.zeros_like(density)
    bounded[y0 : y0 + h, x0 : x0 + w] = density[y0 : y0 + h, x0 : x0 + w]
    dilated = cv2.dilate(bounded, np.ones((UNIT_DENSITY_LOCAL_MAX,) * 2, np.uint8))
    ys, xs = np.nonzero((bounded >= UNIT_DENSITY_MIN_COUNT) & (bounded >= dilated))
    kept: list[Point] = []
    for x, y in sorted(zip(xs, ys, strict=True), key=lambda p: -int(bounded[p[1], p[0]])):
        if all(
            (x - px) ** 2 + (y - py) ** 2 >= UNIT_DENSITY_MIN_DIST**2 for px, py in kept
        ):
            kept.append((float(x), float(y)))
    return tuple(kept)


def arc_hint(frame: np.ndarray, point: Point, half: int = HINT_SAMPLE_HALF) -> str | None:
    """這一點附近哪個色帶像素最多。**只是線索**——我方回合未行動的我方弧偏紅，
    與敵紅在同一幀上量不開（issue #5／定案 5），所以它永遠不是陣營判定。"""
    masks = _band_masks(frame)
    x, y = int(point[0]), int(point[1])
    counts = {
        hint: int(mask[max(0, y - half) : y + half, max(0, x - half) : x + half].sum() // 255)
        for hint, mask in masks.items()
    }
    best = max(counts, key=lambda hint: counts[hint])
    return best if counts[best] else None


def find_sightings(
    frame: np.ndarray | None, region: Region = UNIT_DENSITY_REGION
) -> tuple[Sighting, ...]:
    if frame is None:
        return ()
    return tuple(Sighting(point, arc_hint(frame, point)) for point in find_units(frame, region))


@dataclass(frozen=True)
class Shift:
    dx: float
    dy: float
    confidence: float
    source: str

    @property
    def magnitude(self) -> float:
        return (self.dx * self.dx + self.dy * self.dy) ** 0.5

    @property
    def known(self) -> bool:
        return self.source != "none"


def measure_shift(
    previous: np.ndarray, current: np.ndarray, region: Region = MAP_REGION
) -> Shift:
    """地圖內容從前一幀到這一幀移動了多少（螢幕像素）。

    內容位移是鏡頭位移的反號：鏡頭往東走，地形往西滑。相位相關優先；信賴度太低
    （無特徵星空、或平移過大導致重疊帶不足）就退單位星座投票——**星座票要先過影像
    複驗**（`_constellation_witness`）。兩個都不給答案就回 source="none"——寧可承認
    不知道，也不要拿手勢當位置（0719 西緣鬼影座標就是這樣長出來的）。
    """
    dx, dy, response = _phase_shift(previous, current, region)
    if response >= SHIFT_MIN_RESPONSE:
        return Shift(dx, dy, response, "phase")
    witness = _constellation_witness(previous, current, region)
    if witness is not None:
        return witness
    return Shift(0.0, 0.0, response, "none")


def _phase_shift(
    previous: np.ndarray, current: np.ndarray, region: Region = MAP_REGION
) -> tuple[float, float, float]:
    a = cv2.cvtColor(crop(previous, region), cv2.COLOR_BGR2GRAY).astype(np.float32)
    b = cv2.cvtColor(crop(current, region), cv2.COLOR_BGR2GRAY).astype(np.float32)
    window = cv2.createHanningWindow((a.shape[1], a.shape[0]), cv2.CV_32F)
    (dx, dy), response = cv2.phaseCorrelate(a, b, window)
    return (float(dx), float(dy), float(response))


def measure_pan(
    previous: np.ndarray,
    current: np.ndarray,
    expected: Point | None,
    region: Region = MAP_REGION,
) -> Shift:
    """有指令的水平平移：**格線相位是量測權威**，相位相關降級成證人之一。

    直欄格線是 90px 的週期訊號，所以水平相位相關天生帶 ±90k 的歧義峰，而 HUD 與
    星空的靜態成分還會來搶峰。0801 複驗輪第 3 輪實測（`data/runs/20260801-060433`
    的 18 對 broken 幀）：東向 7 腿的遙測 dx 凍在 −108.0±0.3，t17／t27／t28／t30
    甚至回 ~0——內容實際移動上百 px，相關器整個鎖在靜態峰，而 response 0.13-0.47
    照樣過 `SHIFT_MIN_RESPONSE`，退星座的 fallback 連觸發的機會都沒有。
    **7/20 前例**：`battle/map_stitch.py` 當時就是因為「相位相關被格線 alias 高分
    假鎖」整條被移除，map_grid 的解法是「整數格偏移三重裁決」——這裡是同一個模式
    搬進 runtime 量測鏈。

    兩層：小數部分由兩幀欄線集合對位算出（高 SNR、精確到幾個像素），整數欄數 k 由
    三個證人裁決（`_resolve_columns`）。裁不出來就回 source="none"＝誠實不知道，
    讓上層 BROKEN 隔離——**不准拿手勢當位置**（0719 西緣鬼影紅線）。星座證人進來
    之前先過影像複驗（`_constellation_witness`）；複驗判「確定沒動」時整條格線通道
    讓位——畫面說沒動就是沒動，沒有 k 好裁。

    格線走 `find_lattice`（全幀帶讀不出來就退象限窗）。**兩幀可以由不同的窗讀出**：
    `_column_phase` 拿的是兩組線位對位後的環狀中位殘差，那是 mod pitch 的量，而同一
    張格網不論從哪個象限取樣，線位都落在同一族相位上——窗不同不影響 frac。整數欄數 k
    本來就不由線位決定（那是 `_resolve_columns` 三個證人的事），所以子窗的取樣量少
    在這條路上不構成風險。擋錯格距的閘仍在下面：兩幀欄距差超過 `LATTICE_PITCH_DRIFT`
    就退回現行路徑，粗帶隔行取線湊出的翻倍 pitch 會在那裡被攔下。

    走不到格線通道（沒指令、指令沒有 x 分量、任一幀讀不出格網、兩幀欄距對不上）就
    **完全走 `measure_shift` 的現行路徑**：靜止閘的取幀比對與 precheck 行為零改變。
    """
    if expected is None or expected[0] == 0.0:
        return measure_shift(previous, current, region)
    before = find_lattice(previous)
    after = find_lattice(current)
    if before is None or after is None:
        return measure_shift(previous, current, region)
    pitch = (before.col_pitch + after.col_pitch) / 2.0
    if pitch <= 0 or abs(before.col_pitch - after.col_pitch) > LATTICE_PITCH_DRIFT * pitch:
        return measure_shift(previous, current, region)
    frac = _column_phase(before.cols, after.cols, pitch)
    if frac is None:
        return measure_shift(previous, current, region)
    dx, dy, response = _phase_shift(previous, current, region)
    constellation = _constellation_witness(previous, current, region)
    if constellation is not None and constellation.source == CONSTELLATION_STILL:
        return constellation
    vote = (
        None
        if constellation is None
        else (constellation.dx, constellation.dy, constellation.confidence)
    )
    verdict = _resolve_columns(
        frac,
        pitch,
        expected[0],
        None if vote is None else vote[0],
        dx if _correlator_credible(previous, current, dx, response, region) else None,
    )
    if verdict is None:
        return Shift(0.0, 0.0, response, "none")
    pan, witness = verdict
    if response >= SHIFT_MIN_RESPONSE:
        drift = dy
    elif vote is not None:
        drift = vote[1]
    else:
        drift = 0.0
    confidence = vote[2] if witness == WITNESS_CONSTELLATION and vote is not None else response
    return Shift(pan, drift, confidence, f"{LATTICE_SOURCE}:{witness}")


def _correlator_credible(
    previous: np.ndarray,
    current: np.ndarray,
    dx: float,
    response: float,
    region: Region,
) -> bool:
    """相關器夠不夠格當整數欄數的證人。

    擋的是本批的決定性證據——靜態峰鎖死：畫面明明變了，相關器卻回「沒動」。它給的
    k 會把移動了一整格的幀寫成停滯，而停滯連兩次就把邊界旗永久釘在錯的地方。真的
    停住的幀（手勢被吃掉、到邊）兩幀幾乎逐像素相同，照樣過得了這一關。
    """
    if response < SHIFT_MIN_RESPONSE:
        return False
    if abs(dx) >= EDGE_SHIFT_PX:
        return True
    return frame_difference(previous, current, region) < EDGE_FRAME_DIFF


def _column_phase(before: Sequence[int], after: Sequence[int], pitch: float) -> float | None:
    """兩幀欄線集合的相位差＝內容位移的小數部分（mod pitch，±pitch/2）。

    每條前幀線配後幀**絕對位置**最近的那條，殘差取環狀中位數。配對用絕對距離而不是
    「mod pitch 最近」：後者會逐線挑殘差最小的那條，把答案系統性地拉向 0。
    """
    if pitch <= 0 or len(before) < 2 or len(after) < 2:
        return None
    residuals = [
        _wrap(min((line - anchor for line in after), key=abs), pitch) for anchor in before
    ]
    return _circular_median(residuals, pitch)


def _resolve_columns(
    frac: float,
    pitch: float,
    expected: float,
    constellation: float | None = None,
    correlator: float | None = None,
    limit: float = PAN_UNAMBIGUOUS,
) -> tuple[float, str] | None:
    """整數欄數 k 的三重裁決：候選 ＝ frac + k×pitch，回 (位移, 證人) 或 None。

    候選先被指令包絡窗篩過（規則同 `envelope`，只是攤成一維）——窗外的值下游本來就
    會被拒收，先篩掉是為了讓證人在**還可能成立的** k 之間選，而不是被一票離譜的
    星座眾數（0801 t19 投出 −945）整筆帶走。

    兩個獨立證人：**星座投票**（單位環是非週期訊號，格線 alias 對它無效）與
    **相關器**（可信時才進來，見 `_correlator_credible`）。各自挑離自己最近的候選：

    - 兩個都有選、選的是同一格 → 採用（0801 東向 t21-t24 就是這一支）。
    - **兩個都有選、選的不是同一格 → 誠實回 None。** 星座名義上較強，但它錯起來
      是整整一個眾數的錯（0801 t11 投 21.5、t13 投 4.7，離真值一整欄），而
      「量錯寫入」那條路徑不准存在，所以獨立證人互相矛盾時寧可斷鏈。
    - 只有一個有選 → 採用它（0801 t28-t32 靜態峰鎖死時只剩星座，那正是本批要救的）。

    指令只在兩個獨立證人都缺席時兜底，而且要求**窗內只剩唯一候選**：0801 實測增益
    還沒學會時 expected 是真值的 2.5 倍（指令 −350 對真值 −142），「取離 expected
    最近的候選」會回一個差兩整欄的自信錯值。窗比一個欄距寬就代表指令分不出 k，那就
    誠實回 None——指令永遠只閘量測，不寫進位置（0719 紅線）。
    """
    if pitch <= 0:
        return None
    low, high = _envelope_window(expected)
    first = math.ceil((max(-limit, low) - frac) / pitch)
    last = math.floor((min(limit, high) - frac) / pitch)
    candidates = [frac + k * pitch for k in range(first, last + 1)]
    if not candidates:
        return None
    tolerance = LATTICE_WITNESS_TOLERANCE * pitch
    spoken: dict[str, float] = {}
    for witness, value in (
        (WITNESS_CONSTELLATION, constellation),
        (WITNESS_PHASE, correlator),
    ):
        if value is None:
            continue
        pick = _nearest_candidate(candidates, value, tolerance)
        if pick is not None:
            spoken[witness] = pick
    if len(set(spoken.values())) > 1:
        return None
    for witness in (WITNESS_CONSTELLATION, WITNESS_PHASE):
        if witness in spoken:
            return (spoken[witness], witness)
    if len(candidates) != 1:
        return None
    return (candidates[0], WITNESS_COMMANDED)


def _nearest_candidate(
    candidates: Sequence[float], witness: float, tolerance: float
) -> float | None:
    ranked = sorted(candidates, key=lambda candidate: abs(candidate - witness))
    gap = abs(ranked[0] - witness)
    if gap > tolerance:
        return None
    if len(ranked) > 1 and abs(abs(ranked[1] - witness) - gap) < 1e-9:
        return None
    return ranked[0]


def _envelope_window(expected: float) -> tuple[float, float]:
    """指令包絡在單軸上的窗（帶號）。規則與 `envelope` 同一套，只是攤成一維。"""
    reach = ENVELOPE_DOUBLE * abs(expected)
    if expected > 0:
        return (-EDGE_SHIFT_PX, reach)
    return (-reach, EDGE_SHIFT_PX)


CONSTELLATION_TOLERANCE = 24
CONSTELLATION_MIN_VOTES = 2


def _constellation_shift(
    before: Sequence[Point], after: Sequence[Point]
) -> tuple[float, float, float] | None:
    """每一對單位配對投一個平移，被兩台以上支持的唯一眾數勝。平手＝不知道。"""
    if len(before) < CONSTELLATION_MIN_VOTES or len(after) < CONSTELLATION_MIN_VOTES:
        return None
    votes: dict[tuple[int, int], list[Point]] = {}
    for ax, ay in before:
        for bx, by in after:
            delta = (bx - ax, by - ay)
            key = (
                round(delta[0] / CONSTELLATION_TOLERANCE),
                round(delta[1] / CONSTELLATION_TOLERANCE),
            )
            votes.setdefault(key, []).append(delta)
    best = max(votes.values(), key=len)
    tallies = sorted((len(group) for group in votes.values()), reverse=True)
    if len(best) < CONSTELLATION_MIN_VOTES:
        return None
    if len(tallies) > 1 and tallies[1] == tallies[0]:
        return None
    return (
        sum(delta[0] for delta in best) / len(best),
        sum(delta[1] for delta in best) / len(best),
        len(best) / max(len(before), len(after)),
    )


NULL_MOVED = "moved"
NULL_STILL = "still"
NULL_UNCLEAR = "unclear"
# 取樣不到足夠的窗＝裁判沒東西可看。與 unclear 分開：unclear 是「看了，兩個假設都
# 對不上」（呼叫端該拒收），blind 是「沒得看」（呼叫端照舊處置，不因為裁判缺席就
# 把原本收得下的量測丟掉）。
NULL_BLIND = "blind"
# 影像複驗閘的取樣窗與判準。窗半徑 45 ＝ 半格：精靈連同腳下環都在裡面，又不會把
# 隔壁那台一起框進來。
NULL_PATCH_HALF = 45
NULL_MARGIN = 0.8
NULL_MIN_WITNESSES = 2


def null_check(
    previous: np.ndarray,
    current: np.ndarray,
    delta: Point,
    points: Sequence[Point] | None = None,
    region: Region = MAP_REGION,
) -> str:
    """「內容位移了 delta」與「根本沒動」兩個假設，拿畫面對質。

    逐個精靈開一個窗，比 `current` 的窗對上 `previous` 同位置（原地假設）與
    `previous` 平移 delta 之後那個位置（位移假設）的平均絕對差，明顯低的那個假設
    得一票。票數要過門檻又要勝過對手才算數，否則回 `NULL_UNCLEAR`＝看過了但兩個
    假設都對不上；窗湊不到門檻數（鏡頭底下沒幾台）回 `NULL_BLIND`＝沒得看。

    **為什麼是逐精靈窗而不是整個 region 取一個平均**：畫面有兩層，星空背景不隨鏡頭
    動、地圖層才動。整區平均由面積大的那一層說了算，0801 實測（run 20260801-080213）
    因此把真移動判成原地——t15 的真位移 (−13,−177) 整區比分 20.11 vs 18.22（原地
    勝）、t16 0.995、t24 1.315，全是誤判；逐精靈窗同一批幀分別是 4:0、4:0、1:1，
    真移動全過、可疑的落回 unclear。精靈窗還天生只取樣地圖層。

    取樣窗的中心限在 `region` 內（預設地圖區）：卡條與畫面下緣那一帶的密度峰品質
    差，放進來會把 0801 t24 這種本該 unclear 的幀投成 still（實測 4:6）。

    delta 小於一次平移的判準門檻時兩個假設在畫面上根本分不開（窗幾乎重疊），直接
    回 blind——那種量值下游本來就當沒動處理。
    """
    if math.hypot(delta[0], delta[1]) < EDGE_SHIFT_PX:
        return NULL_BLIND
    x, y, w, h = region
    before = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY).astype(np.float32)
    after = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY).astype(np.float32)
    polled = 0
    moved = 0
    stayed = 0
    for px, py in find_units(current) if points is None else points:
        if not (x <= px <= x + w and y <= py <= y + h):
            continue
        here = _window(after, px, py)
        origin = _window(before, px, py)
        shifted = _window(before, px - delta[0], py - delta[1])
        if here is None or origin is None or shifted is None:
            continue
        polled += 1
        moving = float(np.abs(here - shifted).mean())
        staying = float(np.abs(here - origin).mean())
        if moving < NULL_MARGIN * staying:
            moved += 1
        elif staying < NULL_MARGIN * moving:
            stayed += 1
    if polled < NULL_MIN_WITNESSES:
        return NULL_BLIND
    if moved >= NULL_MIN_WITNESSES and moved > stayed:
        return NULL_MOVED
    if stayed >= NULL_MIN_WITNESSES and stayed > moved:
        return NULL_STILL
    return NULL_UNCLEAR


def _window(image: np.ndarray, x: float, y: float, half: int = NULL_PATCH_HALF) -> np.ndarray | None:
    height, width = image.shape[:2]
    x0, y0 = int(round(x)) - half, int(round(y)) - half
    if x0 < 0 or y0 < 0 or x0 + 2 * half > width or y0 + 2 * half > height:
        return None
    return image[y0 : y0 + 2 * half, x0 : x0 + 2 * half]


def _constellation_witness(
    previous: np.ndarray, current: np.ndarray, region: Region = MAP_REGION
) -> Shift | None:
    """星座票過影像複驗才算數；原地假設勝出時回「確定沒動」。

    同型薩克與我方編隊是週期陣列（0801 實測幀內縱距 90/93/96），配對投票因此會把
    「錯一個編隊間距」的組合投成票數十足的幽靈位移——票數多寡分不出真假，畫面分得
    出來。原地勝出時刻意回一個零位移但 `known` 的 Shift：`Odometer.feed` 於是走
    STALLED 正軌，不必靠 `frame_difference`（待機動畫實測 5.8-12.5，恆高於
    EDGE_FRAME_DIFF，原地幀永遠走不進那一支）。
    """
    vote = _constellation_shift(find_units(previous), find_units(current))
    if vote is None:
        return None
    verdict = null_check(previous, current, (vote[0], vote[1]), region=region)
    if verdict == NULL_STILL:
        return Shift(0.0, 0.0, vote[2], CONSTELLATION_STILL)
    if verdict == NULL_UNCLEAR:
        return None
    return Shift(vote[0], vote[1], vote[2], WITNESS_CONSTELLATION)


def frame_difference(
    previous: np.ndarray, current: np.ndarray, region: Region = MAP_REGION
) -> float:
    a = crop(previous, region).astype(np.float32)
    b = crop(current, region).astype(np.float32)
    return float(np.abs(a - b).mean())


def envelope(shift: Shift, expected: Point | None) -> str:
    """指令包絡閘：量到的位移得同軸同號、落在指令的 0~1.5 倍（重複執行一次到
    2.5 倍）之內，否則整筆拒收。

    這一關擋的是繞回混疊的「自信錯值」——循環相關的假峰差一整個窗寬，投影回
    指令軸不是反號就是遠超上界。**指令只閘量測，永遠不寫進覆蓋**：閘不過的處置
    是承認斷鏈，不是拿指令當位置。

    沒有指令（expected=None）時只允許「幾乎沒動」：兩個 tick 之間鏡頭本來就不該
    自己跑，量到大位移就是斷鏈。
    """
    if expected is None:
        return ENVELOPE_OK if shift.magnitude < EDGE_SHIFT_PX else ENVELOPE_REFUSED
    span = (expected[0] ** 2 + expected[1] ** 2) ** 0.5
    if span <= 0:
        return ENVELOPE_OK if shift.magnitude < EDGE_SHIFT_PX else ENVELOPE_REFUSED
    ux, uy = expected[0] / span, expected[1] / span
    along = shift.dx * ux + shift.dy * uy
    across = abs(-shift.dx * uy + shift.dy * ux)
    if along < -EDGE_SHIFT_PX or across > ENVELOPE_CROSS * span + EDGE_SHIFT_PX:
        return ENVELOPE_REFUSED
    if along <= ENVELOPE_SINGLE * span:
        return ENVELOPE_OK
    if along <= ENVELOPE_DOUBLE * span:
        return ENVELOPE_REPEAT
    return ENVELOPE_REFUSED


def phase_residual(line: float, pitch: float, anchor: float) -> float:
    """線位離世界格線相位多遠（±pitch/2，帶號）。0 ＝ 對得上。"""
    return _wrap(line - anchor, pitch)


def median_residual(lines: Sequence[float], pitch: float, anchor: float) -> float:
    """整組線位對世界相位的殘差，取（環狀）中位數。

    單線取樣會被格線讀取的抖動整支帶走——0801 複驗輪逐幀實測單線位置抖動 ±10px，
    而相位閘的容差只有 0.25 pitch（~22px），一條抖過頭的線就能讓整幀被拒收。
    """
    if not lines:
        return 0.0
    return _circular_median([line - anchor for line in lines], pitch)


def _wrap(value: float, period: float) -> float:
    if period <= 0:
        return 0.0
    offset = value % period
    return offset - period if offset > period / 2.0 else offset


def _circular_median(values: Sequence[float], period: float) -> float:
    """環狀量的中位數（落在 ±period/2）。

    直接對 wrap 過的值取中位數會在真值靠近 ±period/2 時炸掉：樣本分裂到圓的兩端，
    中位數落在中間＝離真值最遠的地方。先用相量平均定圓心，再繞著圓心取中位數。
    """
    if not values or period <= 0:
        return 0.0
    angles = [2.0 * math.pi * value / period for value in values]
    centre = (
        math.atan2(
            sum(math.sin(angle) for angle in angles) / len(angles),
            sum(math.cos(angle) for angle in angles) / len(angles),
        )
        * period
        / (2.0 * math.pi)
    )
    centred = sorted(_wrap(value - centre, period) for value in values)
    count = len(centred)
    middle = (
        centred[count // 2]
        if count % 2
        else (centred[count // 2 - 1] + centred[count // 2]) / 2.0
    )
    return _wrap(centre + middle, period)


RELOCATE_MIN_SUPPORT = 3


def relocalise(
    known: Sequence[Point], seen: Sequence[Point], minimum: int = RELOCATE_MIN_SUPPORT
) -> Point | None:
    """全域重定位器：拿當前的密度峰對已記目擊解偏移（seen ＝ known ＋ 回傳值）。

    **不是主里程計**——它只在斷鏈之後重錨用。除了星座投票的唯一眾數，解出來的偏移
    還要**回頭驗**：至少 minimum 台單位真的對上位置才算數。滿場二十幾台時光靠
    「兩票且唯一」太便宜，而重錨一錯就是整批島嶼寫進錯的世界座標——那正是這個
    模型不准存在的路徑。
    """
    vote = _constellation_shift(known, seen)
    if vote is None:
        return None
    delta = (vote[0], vote[1])
    support = sum(
        any(
            abs(sx - delta[0] - kx) <= CONSTELLATION_TOLERANCE
            and abs(sy - delta[1] - ky) <= CONSTELLATION_TOLERANCE
            for kx, ky in known
        )
        for sx, sy in seen
    )
    return delta if support >= minimum else None


def pick_pan_origin(
    sightings: Iterable[Sighting], candidates: Sequence[Point] = PAN_ORIGIN_GRID
) -> Point:
    """離所有單位最遠的起手點。起手抓到單位會誤入移動模式（實測兩次），
    而密集編隊可能同時壓住多個靜態起手點，所以逐幀重挑。"""
    points = [sighting.point for sighting in sightings]
    if not points:
        return candidates[len(candidates) // 2]
    return max(
        candidates,
        key=lambda candidate: min(
            (candidate[0] - x) ** 2 + (candidate[1] - y) ** 2 for x, y in points
        ),
    )


def pan_gesture(direction: str, origin: Point, reach: float | None = None) -> tuple[int, int, int, int]:
    """把鏡頭往 direction 推的拖曳：手指往反方向拉（往東看＝內容往西拖）。

    reach ＝ 手指行程（螢幕像素）。不給就用 PAN_HALF 的軸別預設；掃描端會依腿長
    規則自己算——單腿的內容位移必須留在無歧義量測範圍的一半以內。
    """
    dx, dy = DIRECTIONS[direction]
    x0, y0 = origin
    span = {"x": PAN_HALF["x"], "y": PAN_HALF["y"]} if reach is None else {"x": reach, "y": reach}
    return (
        int(x0),
        int(y0),
        int(round(x0 - dx * span["x"])),
        int(round(y0 - dy * span["y"])),
    )
