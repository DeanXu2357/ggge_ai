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
3. **單位排列比對**：畫面上的單位排列每一對配對投一個平移、有兩台以上支持的眾數
   勝（`relocalise`：拿當下的密度峰對已記目擊解偏移，解出來還要回頭驗支持台數）。
4. **終止邊**：`edge_shift` 讀同一側地圖終止邊在兩幀之間的螢幕位移。地圖邊界不
   週期，格線與同型機編隊那種差整數個週期的誤配動不了它。
5. **影像複驗**：`null_check` 逐窗把「內容位移了這麼多」拿去對畫面問話。
6. **標記格**：點地圖上沒有單位的空格，那一格會填滿顏色，之後只要不再點別的東西
   就留在原格。`learn_marker` 從點擊前後幀學它的色簽，`find_marker` 在往後的幀
   重找它——那是我們自己放上去的絕對地標，一次解出兩軸。

世界座標與四態知識圖在 `runtime/coverage.py`——這裡只做像素。**指令的量永遠
不寫進位置**（0719 紅線）：手勢只決定往哪推，位置一律解自畫面內容。

**背景圖案不是位置證據**（0803 第 10 輪定讞）：畫面有兩層，星空那一層不隨鏡頭動，
而它在整區灰階量測裡面積佔優——同一對幀星空帶 response 0.766、地圖帶 0.041，真實
位移 −184px 只在近排帶量得到。所以這裡不再有整區相位相關；問「這一幀在哪」只准
問單位、終止邊與逐精靈窗，格線只答「格網幾何長什麼樣」。

單位一律**不帶陣營**出去。腳下弧的顏色不是陣營的權威——我方回合未行動的我方
單位弧色偏紅、與敵紅在同一幀上 HSV 幾乎重合（fixtures hp_arc/*，定案 5）。掃描
只回報「這裡有一台」＋弧色線索，陣營由證據分層那一步決定。

**掃描前置**：可行動單位卡條要先收起來（展開時蓋住地圖下緣，密度峰的掃描帶
一路到 y1020）。
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

log = logging.getLogger(__name__)

Point = tuple[float, float]
Cell = tuple[int, int]
Region = tuple[int, int, int, int]
# 量測鏈的遙測水槽：給了就逐步驟填進去，永遠不影響裁決（純觀察者）。
Trace = dict[str, Any] | None


def _note(trace: Trace, key: str, value: Any) -> None:
    if trace is not None:
        trace[key] = value

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
# 是防誤配的關鍵：粗帶的最小間距套在細格網上會隔行取線，湊出翻倍的「均勻」格距
# 而且過得了合理性閘——那正是「自信錯值」，寧可先問細帶。
SPACING_BANDS: tuple[tuple[int, int], ...] = ((60, 105), (90, 160))

# 終止邊掃描窗。上緣 330 避開左上「變更初期配置」鈕（實測 y≤315 的藍框會被當成脊），
# 下緣 970 停在底部鈕列之上；橫向取滿整幀——縱線的終止邊常落在 GRID_REGION（到 x1750）
# 之外，0803 語料實測東緣讀到 1763。
EDGE_SCAN_REGION: Region = (0, 330, 2340, 640)

# 實機投影是固定的單消失點透視（0803 兩輪 14 幀、多個鏡頭位置擬合）：縱線的斜率場
# slope(x) = K·(x − XV)，XV 的 IQR 1164~1171、K 的 IQR ±5%、逐幀 rms ≤0.006；橫線
# 平行（k≈0）、列距均勻 87-88，所以只有縱線要校正。
#
# 校正映射把縱線轉正：x_rect = XV + (x − XV) / (1 + K·(y − Y_REF))。Y_REF 取掃描窗
# 中心，於是映射在 y=Y_REF 上是恆等——**校正空間的 x 就是螢幕在參考列上的 x**，位置
# 回報不必再換算回去。
PERSPECTIVE_VP_X = 1166.0
PERSPECTIVE_K = 1.10e-4
PERSPECTIVE_REF_Y = 650.0

# 終止邊三分裁決的門檻（0803 原型 edge_scan_v2 對 259 幀語料掃描定出來的）。
# 短繩延伸：候選要有脊列中位峰高的三成才算一條線。檢驗帶：外側一格寬的帶沿線方向
# 切四帶各自檢驗，≥3/4 帶過關才算虛空——**全帶取一個平均會被星空稀釋**，斜邊界外
# 殘留的格線因此溜過門檻（t1-precheck 的假西邊界），分帶後有線的那一帶自己不及格。
# 單帶硬帽是第二道保險：任何一帶的平均超過 CAP 就一票否決。
EDGE_EXTEND_RATIO = 0.30
EDGE_VOID_MEAN_RATIO = 0.25
EDGE_VOID_MAX_RATIO = 0.60
EDGE_VOID_MEAN_CAP = 0.50
EDGE_VOID_BANDS = 4
EDGE_VOID_BANDS_MIN_PASS = 3
# 脊列末端離取樣範圍邊不足這麼多格就算被切斷（地圖還沒看完，不是邊界）。
EDGE_MARGIN_PITCH = 0.8
# 短繩：延伸只准伸出取樣窗一個格距。夠撿回貼著窗外的終止線（0803 r8 北緣 307），
# 又搆不到回合橫幅那條強邊緣。
EDGE_LEASH_PITCH = 1.0

EDGE_SEEN = "EDGE"
EDGE_TRUNCATED = "truncated"
EDGE_BLOCKED = "blocked"

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
# 待掃格回補，補不到就明寫退休）。右上洞**不要再往下挖**：實測 t19／t20／t35 都有真
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
# 相位殘量至少要離 0 這麼遠，一把推鏡才判得出「走了」還是「被吞了」。門檻
# GESTURE_PHASE_PX 是 8，量測散布實測約 ±8（同一種行程的殘量落在 -31..-39），
# 取 25 留三倍餘裕；上限是半格（85/2），25 還撐得住。
PHASE_LEGIBLE_MARGIN = 25.0
# 拖得慢比較不會被吃掉：0719 星圖上 500ms 的拖曳整段被吞（動作後的鏡頭緩動
# ＋adb 掉線）。呼叫端把手勢打出去時用這兩個值。
PAN_DURATION_S = 0.7
PAN_SETTLE_S = 1.5

# 一把推鏡換到的內容位移／手指行程。run 20260804-221825 逐把量測：東推（行程
# PAN_HALF["x"]=250）四把換到 233.6／236／238／240px；北推（行程 PAN_HALF["y"]=170）
# zero 段四把總位移 622 與 641.5，每把 155.5／160px。兩軸同一個比例 0.94-0.95，
# **遊戲不吃慣性甩動**（舊註解的「一把 570-600px」是別的縮放層級留下的），所以北推
# 慢的唯一原因就是 y 行程只有 x 的 68%——每把同樣吃掉 15-18s 卻少走三分之一的路。
PAN_GAIN = 0.95
# 手勢兩端都要留在這個框內：起手落在鈕上整把會被吃掉，終點掉進底部鈕列會誤點。
# 框比 PAN_ORIGIN_GRID 大出一個 PAN_MAX_REACH 有餘，所以縱向也吃得下滿行程。
PAN_GESTURE_BOUNDS: Region = (500, 300, 1340, 530)

DIRECTIONS: dict[str, tuple[int, int]] = {
    "east": (1, 0),
    "west": (-1, 0),
    "north": (0, -1),
    "south": (0, 1),
}

# 一次平移的位移小於這個像素數就算沒動＝停滯（到邊或指令被吃掉）。實測推一把約
# 570-600px，半格已是巨大差距，取 40 對量測雜訊有餘裕。
EDGE_SHIFT_PX = 40.0
# 兩側終止邊各量一次同一個剛體平移，差超過這個像素數就是至少一側不是地圖邊——
# 兩個都不採信（誠實承認定位中斷勝過挑一個信）。
EDGE_WITNESS_AGREEMENT = EDGE_SHIFT_PX


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


def fit_lines(positions: Sequence[float]) -> tuple[float, float] | None:
    """等距線列的最小平方擬合，回 (第 0 條線的位置, 格距)。線少於兩條或格距非正就 None。

    坑：整數線位取中位差（`_median_gap`）只有 1px 解析度＝0.85% 的格距誤差，19 欄上
    累積 0.16 格——離線重放（`scripts/validate_projection.py`）證實那是位置殘差的主源。
    世界錨定要的是次像素格距，畫面內的吸附／索引照舊用線位本身。
    """
    if len(positions) < 2:
        return None
    values = np.asarray(positions, dtype=float)
    pitch, first = np.polyfit(np.arange(len(values), dtype=float), values, 1)
    if pitch <= 0:
        return None
    return (float(first), float(pitch))


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
    highpass = _highpass(patch)
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

    `box` 是線位圍出來的矩形（不是格心）；`borders` 只收有證據的那幾側，看不出來就
    不出證言——半幅星空虛空與「地圖還沒看完」在幾何上長得一樣。

    **邊界位置與 box 是兩回事**：box 來自 `GRID_REGION` 帶讀到的線位，終止邊來自
    `scan_edges` 的全幀掃描，後者看得到帶外（實測東緣 box 1680、邊界 1763）。
    """

    lattice: Lattice
    box: Region
    borders: tuple[tuple[str, float], ...] = ()

    @property
    def edges(self) -> frozenset[str]:
        return frozenset(side for side, _ in self.borders)

    def border(self, side: str) -> float | None:
        """該側終止邊的螢幕座標。沒有目擊就 None。"""
        return dict(self.borders).get(side)


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
        witnessed = scan_edges(frame)
        borders = tuple(
            (side, position)
            for side, (verdict, position, _) in sorted(witnessed.items())
            if verdict == EDGE_SEEN
        )
        return GridSpan(lattice, box, borders)
    return None


def _lattice_bands() -> Iterable[tuple[Region, tuple[int, int]]]:
    yield (GRID_REGION, (GRID_MIN_COLS, GRID_MIN_ROWS))
    for window in LATTICE_WINDOWS:
        yield (window, _window_minimum(window))


def _highpass(patch: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return np.abs(gray - cv2.GaussianBlur(gray, (0, 0), 6))


def rectify_columns(
    patch: np.ndarray, region: Region = EDGE_SCAN_REGION
) -> tuple[np.ndarray, tuple[float, float]]:
    """把 patch 逐列水平重取樣，讓實機的斜縱線在輸出裡變成真的垂直線。

    回 (校正後的 patch, 校正空間的有效 x 範圍)。輸出的第 j 欄對應校正座標 x0+j，而
    x0+j 在 y=PERSPECTIVE_REF_Y 上就是螢幕 x，所以位置不必再換算回螢幕。

    **有效範圍以外不可取樣**：每一列的源範圍只有 [x0, x0+w)，映到校正空間之後各列
    的可視範圍不同（最寬與最窄差約 41px），交集之外的欄只有部分列有內容——那裡的
    投影是被虛假地稀釋過的，拿去比門檻會把真線讀成虛空。
    """
    x0, y0, w, h = region
    rows = np.arange(patch.shape[0], dtype=np.float32)
    scale = 1.0 + PERSPECTIVE_K * (rows + y0 - PERSPECTIVE_REF_Y)
    columns = np.arange(patch.shape[1], dtype=np.float32) + x0
    map_x = (
        PERSPECTIVE_VP_X + (columns[None, :] - PERSPECTIVE_VP_X) * scale[:, None] - x0
    ).astype(np.float32)
    map_y = np.repeat(rows[:, None], patch.shape[1], axis=1)
    rectified = cv2.remap(
        patch, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0
    )
    ends = (float(scale.min()), float(scale.max()))
    low = max(PERSPECTIVE_VP_X + (x0 - PERSPECTIVE_VP_X) / s for s in ends)
    high = min(PERSPECTIVE_VP_X + (x0 + w - 1 - PERSPECTIVE_VP_X) / s for s in ends)
    return (rectified, (low, high))


def scan_edges(
    frame: np.ndarray, region: Region = EDGE_SCAN_REGION
) -> dict[str, tuple[str, float, dict[str, Any]]]:
    """四側的終止邊目擊：{側: (裁決, 位置, 統計)}。讀不出脊列的那個軸整個缺席。

    裁決三分——把「看到邊」與「看不出來」分開，是這一層唯一該說的話：

    - `EDGE`      脊列在取樣範圍內收尾，外側一格寬的檢驗帶分帶都平整＝邊外是虛空
    - `truncated` 脊列（含延伸）頂到取樣範圍邊——多條線被切斷，地圖還沒看完
    - `blocked`   脊列收尾但外側不平整（美術、斜的地形交界、UI），不表態

    **縱線軸在校正過的空間讀**：未校正的全窗投影會把離消失點遠的線攤成 40px 寬的
    低矮丘（斜率 K·(x−XV) 乘上 640 的窗高），最外側幾條線因此讀不到，真邊界漏報、
    斜的地形交界誤判成邊界——那正是舊的三閘錨在「最外偵測格線」上失敗的兩個樣態。
    橫線軸不校正（橫線平行），但投影讀**全幀高度**：種子脊限在窗內、延伸只放一個
    格距的短繩，這樣撿得回貼著窗外的終止線又搆不到回合橫幅。
    """
    x0, y0, w, h = region
    image, valid = _column_space(_highpass(crop(frame, region)), region)
    columns = _axis_edges(
        image, valid, valid, offset=x0, along=1, leash=0.0, sides=("west", "east")
    )
    strip = _highpass(frame[:, x0 : x0 + w])
    rows = _axis_edges(
        strip,
        (float(y0), float(y0 + h - 1)),
        (0.0, float(frame.shape[0] - 1)),
        offset=0,
        along=0,
        leash=EDGE_LEASH_PITCH,
        sides=("north", "south"),
    )
    return {**columns, **rows}


def _column_space(
    highpass: np.ndarray, region: Region
) -> tuple[np.ndarray, tuple[float, float]]:
    """縱線軸要在校正過的空間讀還是原樣讀，回 (影像, 可用的 x 範圍)。

    **投影模型對不對，由畫面自己裁**：模型對了，每條線的能量收進同一欄，脊的中位
    峰高就高；模型錯了，校正只是把本來就正的線攤平。實機語料校正後峰高是原樣的兩倍
    （t15 甚至多讀到九條線），沒有透視的輸入（合成世界）則反過來差五倍。硬套校正會
    讓後者的位置讀數抖到 ±10px，硬不套則實機的最外側幾條線永遠讀不到。
    """
    x0, _, w, _ = region
    candidates = (
        (highpass, (float(x0), float(x0 + w - 1))),
        rectify_columns(highpass, region),
    )
    ranked = [
        (0.0 if seen is None else seen[2], image, limits)
        for image, limits in candidates
        for seen in (_ridge_run(image.mean(axis=0), x0, limits),)
    ]
    _, image, limits = max(ranked, key=lambda entry: entry[0])
    return (image, limits)


def _ridge_run(
    profile: np.ndarray, offset: int, seeds: tuple[float, float]
) -> tuple[list[int], float, float] | None:
    """種子脊列＝間距均勻的最長連續段，回 (線位, 格距, 中位峰高)。

    格距帶由細到粗逐帶試，第一個湊得出三條線的贏——與 `read_lattice` 同一條理由
    （粗帶的最小間距套在細格網上會隔行取線、湊出翻倍的假格距）。
    """
    for low, high in SPACING_BANDS:
        found = [
            ridge for ridge in _ridges(profile, offset, low) if seeds[0] <= ridge <= seeds[1]
        ]
        run = _longest_run(found, low, high)
        if len(run) < 3:
            continue
        pitch = _median_gap(run)
        if pitch > 0:
            return (run, pitch, float(np.median([profile[p - offset] for p in run])))
    return None


def _axis_edges(
    highpass: np.ndarray,
    seeds: tuple[float, float],
    limits: tuple[float, float],
    offset: int,
    along: int,
    leash: float,
    sides: tuple[str, str],
) -> dict[str, tuple[str, float, dict[str, Any]]]:
    """一個軸的兩端各裁一次。種子脊列限在 seeds 內，延伸與截斷判準看 limits。"""
    profile = highpass.mean(axis=0 if along == 1 else 1)
    seen = _ridge_run(profile, offset, seeds)
    if seen is None:
        return {}
    run, pitch, peak = seen
    return {
        side: _judge_side(
            profile, highpass, offset, along, run, pitch, peak, direction, seeds, limits, leash
        )
        for side, direction in ((sides[0], -1), (sides[1], 1))
    }


def _longest_run(ridges: Sequence[int], low: int, high: int) -> list[int]:
    """間距全落在格距帶內的最長連續脊段。"""
    best: list[int] = []
    current: list[int] = []
    for position in ridges:
        if current and not (low <= position - current[-1] <= high):
            if len(current) > len(best):
                best = current
            current = []
        current.append(position)
    return current if len(current) > len(best) else best


def _judge_side(
    profile: np.ndarray,
    highpass: np.ndarray,
    offset: int,
    along: int,
    run: Sequence[int],
    pitch: float,
    peak: float,
    direction: int,
    seeds: tuple[float, float],
    limits: tuple[float, float],
    leash: float,
) -> tuple[str, float, dict[str, Any]]:
    reach = (
        max(limits[0], seeds[0] - leash * pitch),
        min(limits[1], seeds[1] + leash * pitch),
    )
    picked, end, stop = _extend_line(profile, offset, run, pitch, peak, direction, reach)
    distance = abs((limits[1] if direction > 0 else limits[0]) - end)
    stats: dict[str, Any] = {
        "stop": stop,
        "distance": round(distance, 1),
        "pitch": round(pitch, 1),
        "peak": round(peak, 1),
        "extended": picked,
    }
    if distance < EDGE_MARGIN_PITCH * pitch:
        return (EDGE_TRUNCATED, float(end), stats)
    bands = _banded_void(highpass, along, end - offset, pitch, peak, direction, limits, offset)
    if bands is None:
        return (EDGE_TRUNCATED, float(end), stats)
    stats["bands"] = bands
    passed = sum(1 for band in bands if band["ok"])
    stats["bands_passed"] = passed
    if passed >= EDGE_VOID_BANDS_MIN_PASS and not any(band["capped"] for band in bands):
        return (EDGE_SEEN, float(end), stats)
    return (EDGE_BLOCKED, float(end), stats)


def _extend_line(
    profile: np.ndarray,
    offset: int,
    run: Sequence[int],
    pitch: float,
    peak: float,
    direction: int,
    reach: tuple[float, float],
) -> tuple[list[int], int, str]:
    """從脊列末端往 direction 一格一格外推，撿回種子帶漏掉的線。

    候選只准落在 `reach` 內，而且要有中位峰高的 EDGE_EXTEND_RATIO——沒有線就停，
    停在哪裡就是那一側的終端。
    """
    picked: list[int] = []
    position = run[-1] if direction > 0 else run[0]
    for _ in range(30):
        expected = position + direction * pitch
        low = max(offset, int(reach[0]), int(expected - GRID_GAP_RANGE))
        high = min(offset + len(profile) - 1, int(reach[1]), int(expected + GRID_GAP_RANGE))
        if low > high:
            return (picked, position, "reach")
        window = profile[low - offset : high - offset + 1]
        candidate = low + int(np.argmax(window))
        if profile[candidate - offset] < EDGE_EXTEND_RATIO * peak:
            return (picked, position, "no line")
        picked.append(candidate)
        position = candidate
    return (picked, position, "cap")


def _banded_void(
    highpass: np.ndarray,
    along: int,
    end: int,
    pitch: float,
    peak: float,
    direction: int,
    limits: tuple[float, float],
    offset: int,
) -> list[dict[str, Any]] | None:
    """終端外側一格寬的檢驗帶，沿線方向切 EDGE_VOID_BANDS 帶各自檢驗。

    `along=1` ＝線是縱的（帶沿 y 切）。帶落到取樣範圍外就回 None ＝沒得檢驗。
    """
    near, far = int(0.25 * pitch), int(1.25 * pitch)
    low, high = (end + near, end + far) if direction > 0 else (end - far, end - near)
    if low < limits[0] - offset or high > limits[1] - offset + 1:
        return None
    span = highpass[:, low:high] if along == 1 else highpass[low:high, :]
    if (span.shape[1] if along == 1 else span.shape[0]) < 4:
        return None
    total = span.shape[0] if along == 1 else span.shape[1]
    step = total // EDGE_VOID_BANDS
    bands: list[dict[str, Any]] = []
    for index in range(EDGE_VOID_BANDS):
        chunk = (
            span[index * step : (index + 1) * step, :]
            if along == 1
            else span[:, index * step : (index + 1) * step]
        )
        line = chunk.mean(axis=0 if along == 1 else 1)
        mean, top = float(line.mean()), float(line.max())
        bands.append(
            {
                "mean": round(mean, 2),
                "max": round(top, 2),
                "ok": mean < EDGE_VOID_MEAN_RATIO * peak and top < EDGE_VOID_MAX_RATIO * peak,
                "capped": mean >= EDGE_VOID_MEAN_CAP * peak,
            }
        )
    return bands


def find_lattice(frame: np.ndarray | None) -> Lattice | None:
    """找得到格線就回：先問全幀 GRID_REGION 帶，讀不出來再問 MAP_REGION 的四象限窗。

    相位是 mod pitch 的量，子窗的線位一樣驗得了相位——所以邊緣區沒必要因為「整條
    帶湊不到六欄四列」就整個放棄相位交叉驗證。0801 實測（run 20260801-080213）：
    走到北緣之後 t7-leg 到 t13-precheck 七幀全幀帶一律 None，`_snap` 於是連驗都不驗
    直接放行，t11／t12 兩把實際各滑了 200px 以上卻被記成停滯，同一片場景以同一個
    offset 重複吸收——台數膨脹的第一顆齒輪。

    **回的是線位，不是新的量測**：呼叫端（`coverage.Survey._snap`）只拿它跟世界格網的
    相位對答案，pitch 仍取世界格網的。錨定（`Survey._anchor`）刻意不走這裡，新世界的
    格距要全幀帶那種取樣量才敢定。
    """
    found = find_lattice_band(frame)
    return None if found is None else found[0]


def find_lattice_band(frame: np.ndarray | None) -> tuple[Lattice, Region] | None:
    """同 `find_lattice`，外加線位是從哪一個帶量出來的。

    帶決定了線位的座標系：縱線是斜的，帶內投影取到的是**帶中線那個高度**上的 x
    （`docs/reviews/perspective-measurement.md` §3.3），要把線位拿去跟幾何模型對答案
    就得知道那個高度。
    """
    for band, minimum in _lattice_bands():
        lattice = read_lattice(frame, band, minimum=minimum)
        if lattice is not None:
            return (lattice, band)
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


def find_unit_screen_hints(
    frame: np.ndarray | None,
    region: Region = UNIT_DENSITY_REGION,
    *,
    min_count: int = UNIT_DENSITY_MIN_COUNT,
    local_max: int = UNIT_DENSITY_LOCAL_MAX,
    min_dist: float = UNIT_DENSITY_MIN_DIST,
) -> tuple[Point, ...]:
    """啟發式：大地圖上疑似有單位的位置，輸出**螢幕像素座標**的候選點。

    候選就只是候選——不論陣營、不保證存在，更不是已驗證的世界座標；要當座標用必須
    另外拿點擊回饋或系統指定標示背書（命名家族同 `arc_hint`：線索就只是線索）。

    三個門檻開成參數是給「候選過濾」用的：那邊要的是零漏報，寧可多吐幾個假峰
    （多點一次）也不能漏（漏＝假帳）。預設值仍是校出來的定位用值，不要改。
    """
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
    dilated = cv2.dilate(bounded, np.ones((local_max,) * 2, np.uint8))
    ys, xs = np.nonzero((bounded >= min_count) & (bounded >= dilated))
    kept: list[Point] = []
    for x, y in sorted(zip(xs, ys, strict=True), key=lambda p: -int(bounded[p[1], p[0]])):
        if all(
            (x - px) ** 2 + (y - py) ** 2 >= min_dist**2 for px, py in kept
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
    return tuple(
        Sighting(point, arc_hint(frame, point))
        for point in find_unit_screen_hints(frame, region)
    )


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


def edge_shift(
    before: Mapping[str, float], after: Mapping[str, float], axis: str
) -> float | None:
    """同一側的地圖終止邊在兩幀之間的螢幕位移＝內容位移。讀不到就 None。

    兩個引數都是「側名 → 該側終止邊的螢幕座標」，只收目擊得到的側。

    地圖的物理邊界是**絕對地標**：它不週期，所以格線（欄距 92）與同型機編隊
    （縱距 90-96）那種差整數個週期的誤配對它都無效，靜態的深色背景與 HUD 也搶不走
    它。0801 第 7 輪離線鑑識：東西向 17 條定位中斷的平移有 15 條至少一側可用，與
    真值差 3.5-8px。`coverage` 的複驗拿它當「不得與候選同源」那一關的第一選擇。

    兩側都讀得到就要互相對得上（`EDGE_WITNESS_AGREEMENT`）——差太多代表至少一側
    不是地圖邊（脊偵測在取樣帶緣多撿或漏撿一條線），兩個都不採信。
    """
    sides = ("west", "east") if axis == "x" else ("north", "south")
    readings = [after[side] - before[side] for side in sides if side in before and side in after]
    if not readings:
        return None
    if max(readings) - min(readings) > EDGE_WITNESS_AGREEMENT:
        return None
    return sum(readings) / len(readings)


CONSTELLATION_TOLERANCE = 24
CONSTELLATION_MIN_VOTES = 2
# 一致性打分只罰「該在畫面裡卻對不上」的單位：離偵測帶邊緣這麼近的位置，平移之後
# 本來就可能滑出去，配不上是物理不是矛盾。
CONSTELLATION_MARGIN = 70.0
# 排列比對棄權的三個口，逐筆進遙測——票數多寡分不出「沒得投」與「投了但分不出來」。
CONSTELLATION_VETO_UNITS = "too_few_units"
CONSTELLATION_VETO_TALLY = "max_tally_1"
CONSTELLATION_VETO_TIE = "tie"


def _constellation_shift(
    before: Sequence[Point], after: Sequence[Point], trace: Trace = None
) -> tuple[float, float, float] | None:
    """每一對單位配對投一個平移，支持最多的那一團勝，取團內中位數。

    **不用固定桶**：`round(delta / 容差)` 的桶邊界會把容差內的兩個 delta 切進不同的
    桶。0801 第 7 輪實測——t49 的 (−129,0) 與 (−130,+20) 只差 20px 卻分家，t50 的
    (136,−11) 與 (125,1) 同理，兩邊各剩一票，最高票 1 於是排列比對這一路連著八把缺席。
    改成 seed-and-recollect：每一個 delta 當一次種子、收所有落在它 ±容差內的 delta，
    收得最多的那一團勝——桶邊界就不存在了。

    最高票並列時不直接棄權，先用雙向一致性打分裁（`_pairing_score`）。票數只數支持
    不數矛盾，週期編隊的錯位候選照樣拿得到票；分數把矛盾算進去，仍平才回 None。
    """
    if len(before) < CONSTELLATION_MIN_VOTES or len(after) < CONSTELLATION_MIN_VOTES:
        _note(trace, "constellation", {"veto": CONSTELLATION_VETO_UNITS,
                                       "units": [len(before), len(after)]})
        return None
    deltas = np.array(
        [(bx - ax, by - ay) for ax, ay in before for bx, by in after], dtype=np.float64
    )
    near = (np.abs(deltas[:, 0, None] - deltas[None, :, 0]) <= CONSTELLATION_TOLERANCE) & (
        np.abs(deltas[:, 1, None] - deltas[None, :, 1]) <= CONSTELLATION_TOLERANCE
    )
    tally = near.sum(axis=1)
    best = int(tally.max())
    groups: list[tuple[Point, int]] = []
    for seed in np.argsort(-tally, kind="stable"):
        if int(tally[seed]) < best and len(groups) >= 3:
            break
        members = deltas[near[seed]]
        centre = (float(np.median(members[:, 0])), float(np.median(members[:, 1])))
        if any(
            abs(centre[0] - x) <= CONSTELLATION_TOLERANCE
            and abs(centre[1] - y) <= CONSTELLATION_TOLERANCE
            for (x, y), _ in groups
        ):
            continue
        groups.append((centre, int(tally[seed])))
    detail: dict[str, Any] = {
        "units": [len(before), len(after)],
        "top": [[round(x, 1), round(y, 1), count] for (x, y), count in groups[:3]],
    }
    winners = [centre for centre, count in groups if count == best]
    if best < CONSTELLATION_MIN_VOTES:
        _note(trace, "constellation", {**detail, "veto": CONSTELLATION_VETO_TALLY})
        return None
    if len(winners) > 1:
        scored = [(_pairing_score(before, after, centre), centre) for centre in winners]
        detail["scores"] = [[round(x, 1), round(y, 1), score] for score, (x, y) in scored]
        top = max(score for score, _ in scored)
        winners = [centre for score, centre in scored if score == top]
    if len(winners) != 1:
        _note(trace, "constellation", {**detail, "veto": CONSTELLATION_VETO_TIE})
        return None
    dx, dy = winners[0]
    _note(trace, "constellation", {**detail, "vote": [round(dx, 1), round(dy, 1)]})
    return (dx, dy, best / max(len(before), len(after)))


def _pairing_score(
    before: Sequence[Point],
    after: Sequence[Point],
    delta: Point,
    region: Region = UNIT_DENSITY_REGION,
) -> int:
    """候選平移的雙向一致性：配得上的對數減去解釋不掉的單位數。

    票數只數支持不數矛盾——週期編隊裡「錯一個編隊間距」的候選拿得到票，但它會留下
    一整排落在畫面裡卻沒有對應者的單位。那些矛盾才分得出真假（0801 第 7 輪 t21：
    正解得 2 分，差一整欄的候選得 −3）。
    """
    matched = 0
    unexplained = 0
    used: set[int] = set()
    for source in before:
        target = (source[0] + delta[0], source[1] + delta[1])
        hit = next(
            (
                index
                for index, seen in enumerate(after)
                if index not in used
                and abs(seen[0] - target[0]) <= CONSTELLATION_TOLERANCE
                and abs(seen[1] - target[1]) <= CONSTELLATION_TOLERANCE
            ),
            None,
        )
        if hit is not None:
            matched += 1
            used.add(hit)
        elif _well_inside(target, region) and _well_inside(source, region):
            unexplained += 1
    for index, seen in enumerate(after):
        if index in used:
            continue
        origin = (seen[0] - delta[0], seen[1] - delta[1])
        if _well_inside(seen, region) and _well_inside(origin, region):
            unexplained += 1
    return matched - unexplained


def _well_inside(point: Point, region: Region) -> bool:
    x, y, w, h = region
    margin = CONSTELLATION_MARGIN
    return (
        x + margin <= point[0] <= x + w - margin and y + margin <= point[1] <= y + h - margin
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
    reference: Point = (0.0, 0.0),
    slack: int = 0,
) -> str:
    """「內容位移了 delta」與「內容位移了 reference」兩個假設，拿畫面對質。

    `reference` 預設 (0,0)＝原地假設，所以預設語意就是「動了 delta 沒有」；回
    `NULL_STILL` 一律讀成「reference 那一邊勝」。呼叫端要驗的如果是「我量到的這個
    小位移對不對」，就把量到的值放進 reference——**兩個假設要在同一個粒度上比**：
    真的滑了 20px 的幀拿「原地」當對手一定輸（環偏 20px 的差比對上另一塊背景還大），
    那不是「動了指令那麼多」的證據。

    逐個精靈開一個窗，比 `current` 的窗對上 `previous` 平移 reference 之後那個位置
    與 `previous` 平移 delta 之後那個位置的平均絕對差，明顯低的那個假設得一票。
    票數要過門檻又要勝過對手才算數，否則回 `NULL_UNCLEAR`＝看過了但兩個假設都對
    不上；窗湊不到門檻數（鏡頭底下沒幾台）回 `NULL_BLIND`＝沒得看。

    **為什麼是逐精靈窗而不是整個 region 取一個平均**：畫面有兩層，星空那一層不隨鏡頭
    動、地圖層才動。整區平均由面積大的那一層說了算，0801 實測（run 20260801-080213）
    因此把真移動判成原地——t15 的真位移 (−13,−177) 整區比分 20.11 vs 18.22（原地
    勝）、t16 0.995、t24 1.315，全是誤判；逐精靈窗同一批幀分別是 4:0、4:0、1:1，
    真移動全過、可疑的落回 unclear。精靈窗還天生只取樣地圖層。

    取樣窗的中心限在 `region` 內（預設地圖區）：卡條與畫面下緣那一帶的密度峰品質
    差，放進來會把 0801 t24 這種本該 unclear 的幀投成 still（實測 4:6）。

    兩個假設差不到一次平移的判準門檻時它們在畫面上根本分不開（窗幾乎重疊），直接
    回 blind——那種量值下游本來就當沒動處理。

    `slack` ＝ 兩個假設各自允許的對位誤差（像素），取鄰域內最小的那個差。要問的是
    「差一整格的兩個位置哪個對」時一定要給：量測本來就帶幾個像素的誤差，逐像素硬比
    會讓**正確**的假設也對不上（合成世界的地表是逐像素白噪，1px 偏差就全毀）。兩個
    假設吃同一份餘裕，所以不偏袒誰。預設 0 ＝逐像素比，既有呼叫端行為不變。
    """
    if math.hypot(delta[0] - reference[0], delta[1] - reference[1]) < EDGE_SHIFT_PX:
        return NULL_BLIND
    x, y, w, h = region
    before = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY).astype(np.float32)
    after = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY).astype(np.float32)
    polled = 0
    moved = 0
    stayed = 0
    for px, py in find_unit_screen_hints(current) if points is None else points:
        if not (x <= px <= x + w and y <= py <= y + h):
            continue
        here = _window(after, px, py)
        if here is None:
            continue
        staying = _closest(before, here, px - reference[0], py - reference[1], slack)
        moving = _closest(before, here, px - delta[0], py - delta[1], slack)
        if moving is None or staying is None:
            continue
        polled += 1
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


OVERLAP_PROBES: tuple[Point, ...] = tuple(
    (
        float(MAP_REGION[0] + MAP_REGION[2] * (col + 1) / 6.0),
        float(MAP_REGION[1] + MAP_REGION[3] * (row + 1) / 4.0),
    )
    for col in range(5)
    for row in range(3)
)
"""鏡頭底下沒有機體可比對時，`null_check` 改用的取樣窗心：地圖區內均勻鋪一片。

逐窗比對本來就只取樣窗心附近那一小塊，窗心是不是精靈不影響它問的問題；空曠地帶
的地表紋理照樣答得出「這個位移對不對得上畫面」。整區取一個平均則不行——畫面有
兩層，不隨鏡頭動的背景那一層面積大就會說了算。
"""


def _closest(
    image: np.ndarray, patch: np.ndarray, x: float, y: float, slack: int
) -> float | None:
    """`patch` 對上 image 這個位置附近最像的那一塊，回平均絕對差。slack=0 ＝就地比。"""
    best: float | None = None
    for dx in range(-slack, slack + 1):
        for dy in range(-slack, slack + 1):
            window = _window(image, x + dx, y + dy)
            if window is None:
                continue
            value = float(np.abs(patch - window).mean())
            best = value if best is None else min(best, value)
    return best


def _window(image: np.ndarray, x: float, y: float, half: int = NULL_PATCH_HALF) -> np.ndarray | None:
    height, width = image.shape[:2]
    x0, y0 = int(round(x)) - half, int(round(y)) - half
    if x0 < 0 or y0 < 0 or x0 + 2 * half > width or y0 + 2 * half > height:
        return None
    return image[y0 : y0 + 2 * half, x0 : x0 + 2 * half]


def frame_difference(
    previous: np.ndarray, current: np.ndarray, region: Region = MAP_REGION
) -> float:
    a = crop(previous, region).astype(np.float32)
    b = crop(current, region).astype(np.float32)
    return float(np.abs(a - b).mean())


def median_residual(lines: Sequence[float], pitch: float, anchor: float) -> float:
    """整組線位對世界相位的殘差，取（環狀）中位數。

    單線取樣會被格線讀取的抖動整支帶走：0801 複驗輪逐幀實測單線位置抖動 ±10px。
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

    **不是主要的位置來源**——它只在讀不到地標時補位。除了排列比對投出唯一眾數，解出
    來的偏移還要**回頭驗**：至少 minimum 台單位真的對上位置才算數。滿場二十幾台時光靠
    「兩票且唯一」太便宜，而定位一錯就是整幀寫進錯的世界座標——那正是這個模型不准
    存在的路徑。
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


MARKER_PITCH_SPAN = (0.5, 1.5)
# 讀不到格線時的退路格距（實測最小縮放 86-92）。
MARKER_FALLBACK_PITCH = 90.0
# 前後幀相減算「這裡變了」的門檻。待機動畫整幀抖一階，填色是整格換色。
MARKER_CHANGE_LEVEL = 30
# 學色簽時只認點擊點附近的色塊（格距的倍數）：同一幀別處的變化不是我們點出來的。
MARKER_NEAR_PITCH = 1.5
# 色簽的容差（HSV 三軸）。**實機標定會調**，所以集中在這裡不散落。
MARKER_TOLERANCE: tuple[int, int, int] = (10, 60, 60)
# 重找時第二名的面積佔比上限：兩塊差不多大就沒有唯一贏家，不敢說哪一塊是標記。
MARKER_RUNNER_UP = 0.5


@dataclass(frozen=True)
class MarkerSignature:
    """標記格（點空格填出來的那一格顏色）的色簽與參考尺寸。

    尺寸留著當往後每一次重找的尺規：色簽容差內的色塊要跟放置當下差不多大，才算
    同一格填色而不是同色系的美術。
    """

    hsv: tuple[int, int, int]
    tolerance: tuple[int, int, int]
    size: tuple[float, float]


def marker_pitch(frame: np.ndarray) -> tuple[float, float]:
    lattice = find_lattice(frame)
    if lattice is None or lattice.col_pitch <= 0 or lattice.row_pitch <= 0:
        return (MARKER_FALLBACK_PITCH, MARKER_FALLBACK_PITCH)
    return (lattice.col_pitch, lattice.row_pitch)


def learn_marker(
    before: np.ndarray,
    after: np.ndarray,
    tap_point: Point,
    region: Region = MAP_REGION,
) -> MarkerSignature | None:
    """剛點下去的那一格填了什麼色。學不到合格色塊就 None（點到單位或點擊被吃掉）。

    只看前後幀相減：填色是我們自己弄出來的變化，所以「哪一塊是標記」不必猜，變化
    本身就指得出來。點擊點附近＋一格大小兩個閘擋掉待機動畫與 HUD 計時那類雜訊。
    """
    pitch = marker_pitch(after)
    diff = cv2.absdiff(before, after).max(axis=2)
    mask = np.zeros(diff.shape, np.uint8)
    x, y, w, h = region
    mask[y : y + h, x : x + w] = (diff[y : y + h, x : x + w] > MARKER_CHANGE_LEVEL).astype(
        np.uint8
    )
    block = _largest_block(mask, pitch, tap_point)
    if block is None:
        return None
    x0, y0, bw, bh, patch = block
    hsv = cv2.cvtColor(after, cv2.COLOR_BGR2HSV)[y0 : y0 + bh, x0 : x0 + bw][patch]
    if not hsv.size:
        return None
    middle = np.median(hsv, axis=0)
    return MarkerSignature(
        hsv=(int(middle[0]), int(middle[1]), int(middle[2])),
        tolerance=MARKER_TOLERANCE,
        size=(float(bw), float(bh)),
    )


def find_marker(
    frame: np.ndarray,
    signature: MarkerSignature,
    region: Region = MAP_REGION,
    holes: Sequence[Region] = (),
) -> Point | None:
    """色簽容差內、一格大小、而且沒有第二名的那一塊填色的中心。找不到就 None。

    唯一贏家是硬性的：同色系的美術或另一格殘留的填色會讓「最大的那一塊」變成擲
    骰子，而標記解出來的是整幀的座標——認錯一塊就是整幀寫進錯的世界位置。

    `holes` 挖掉固定位置的 HUD 鈕：那幾塊跟著螢幕不跟著地圖，一旦有一塊撞進色簽的
    容差，唯一贏家這一關就會永遠判「兩塊差不多大」，標記從此再也認不回來。
    """
    mask = _signature_mask(frame, signature)
    x, y, w, h = region
    bounded = np.zeros_like(mask)
    bounded[y : y + h, x : x + w] = mask[y : y + h, x : x + w]
    for hx, hy, hw, hh in holes:
        bounded[hy : hy + hh, hx : hx + hw] = 0
    count, _, stats, centroids = cv2.connectedComponentsWithStats(bounded, 8)
    sized = sorted(
        (
            (int(stats[index, cv2.CC_STAT_AREA]), centroids[index])
            for index in range(1, count)
            if _marker_sized(
                int(stats[index, cv2.CC_STAT_WIDTH]),
                int(stats[index, cv2.CC_STAT_HEIGHT]),
                signature.size,
            )
        ),
        key=lambda entry: -entry[0],
    )
    if not sized:
        return None
    if len(sized) > 1 and sized[1][0] >= MARKER_RUNNER_UP * sized[0][0]:
        return None
    centre = sized[0][1]
    return (float(centre[0]), float(centre[1]))


def _signature_mask(frame: np.ndarray, signature: MarkerSignature) -> np.ndarray:
    hue, sat, val = signature.hsv
    span, sat_span, val_span = signature.tolerance
    low = (max(0, sat - sat_span), max(0, val - val_span))
    high = (min(255, sat + sat_span), min(255, val + val_span))
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = np.zeros(hsv.shape[:2], np.uint8)
    # 色相是環狀量：接近 0／180 的色簽要拆成兩段問，不然容差在環的接縫上憑空縮一半。
    for start, end in _hue_bands(hue, span):
        mask |= cv2.inRange(hsv, (start, low[0], low[1]), (end, high[0], high[1]))
    return (mask > 0).astype(np.uint8)


def _hue_bands(hue: int, span: int) -> tuple[tuple[int, int], ...]:
    low, high = hue - span, hue + span
    if low < 0:
        return ((0, high), (180 + low, 179))
    if high > 179:
        return ((low, 179), (0, high - 180))
    return ((low, high),)


def _largest_block(
    mask: np.ndarray, pitch: tuple[float, float], near: Point
) -> tuple[int, int, int, int, np.ndarray] | None:
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    reach = MARKER_NEAR_PITCH * max(pitch)
    best: tuple[int, int, int, int, np.ndarray] | None = None
    area = 0
    for index in range(1, count):
        x0 = int(stats[index, cv2.CC_STAT_LEFT])
        y0 = int(stats[index, cv2.CC_STAT_TOP])
        width = int(stats[index, cv2.CC_STAT_WIDTH])
        height = int(stats[index, cv2.CC_STAT_HEIGHT])
        if not _marker_sized(width, height, pitch):
            continue
        centre = centroids[index]
        if math.hypot(centre[0] - near[0], centre[1] - near[1]) > reach:
            continue
        size = int(stats[index, cv2.CC_STAT_AREA])
        if size <= area:
            continue
        area = size
        best = (x0, y0, width, height, labels[y0 : y0 + height, x0 : x0 + width] == index)
    return best


def _marker_sized(width: int, height: int, reference: tuple[float, float]) -> bool:
    low, high = MARKER_PITCH_SPAN
    return (
        low * reference[0] <= width <= high * reference[0]
        and low * reference[1] <= height <= high * reference[1]
    )


def lattice_phase(frame: np.ndarray | None) -> tuple[Point, Point] | None:
    """(格線相位, 格距)。讀不出格線就 None。

    相位＝第一條線的位置模格距。格線是遊戲**渲染的 UI 層**，不受星空動畫與待機
    精靈干擾，所以「手勢到底生效了沒」問它最準——發出去的手勢不等於生效的手勢
    （省電觸控鎖無聲吞掉整把是實證教訓）。
    """
    lattice = find_lattice(frame)
    if lattice is None or lattice.col_pitch <= 0 or lattice.row_pitch <= 0:
        return None
    pitch = (lattice.col_pitch, lattice.row_pitch)
    return ((lattice.cols[0] % pitch[0], lattice.rows[0] % pitch[1]), pitch)


def phase_shift(before: Point, after: Point, pitch: Point) -> Point:
    """兩幀的格線相位差，逐軸取進 ±半格的最小代表。

    相位是模量：位移剛好是格距整數倍時差會回到 0，看起來像「沒動」。方向是安全
    的——只會多推一把（重錨那一關會把真實鏡位問回來），不會把沒動誤判成動了。
    """
    return (
        _wrap_phase(after[0] - before[0], pitch[0]),
        _wrap_phase(after[1] - before[1], pitch[1]),
    )


def _wrap_phase(value: float, period: float) -> float:
    return (value + period / 2.0) % period - period / 2.0


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


def pan_shift(reach: float, gain: float = PAN_GAIN) -> float:
    """行程 → 內容位移。兩軸同一個增益（0804 逐把量測）。"""
    return gain * reach


def legible_reach(
    direction: str,
    reach: float,
    pitch: Point,
    *,
    gain: float = PAN_GAIN,
    margin: float = PHASE_LEGIBLE_MARGIN,
    floor: float = PAN_MIN_REACH,
    step: float = 5.0,
) -> float:
    """把行程縮到相位驗收讀得出來的長度。

    相位是模格距的量：位移落在格距整數倍附近時，走了一整把跟整把被吞掉的相位
    差同樣接近 0。0805-031635 那三把北推就死在這個盲點——row_pitch 85、行程
    260（位移 247）殘量只剩 -5，三把各自真的走了約 250px 卻被判 eaten，重發到
    Halt（同 run seq 539 有標記背書：相位 y=0.0、實際位移 -259.8）。

    所以寧可少走一點路，換一個離 0 夠遠的殘量：行程由要求值往下找，第一個殘量
    夠大的就用。找不到（格距太小或已到下限）就原樣回傳，讓後面的判準自己收。
    """
    period = pitch[0] if direction in ("east", "west") else pitch[1]
    if period <= 0.0 or margin >= period / 2.0:
        return reach
    candidate = reach
    while candidate >= floor:
        if abs(_wrap_phase(gain * candidate, period)) >= margin:
            return candidate
        candidate -= step
    return reach


def pan_headroom(direction: str, origin: Point, bounds: Region = PAN_GESTURE_BOUNDS) -> float:
    """從這個起手點往 direction 推，行程最多能拉多長還留在安全框內。"""
    dx, dy = DIRECTIONS[direction]
    x, y, w, h = bounds
    # 手指往推進方向的反向拉，所以吃掉的是反向那一側的餘裕。
    if dx:
        return origin[0] - x if dx > 0 else x + w - origin[0]
    return y + h - origin[1] if dy < 0 else origin[1] - y


def pan_stroke(
    direction: str,
    reach: float,
    sightings: Iterable[Sighting],
    *,
    candidates: Sequence[Point] = PAN_ORIGIN_GRID,
    bounds: Region = PAN_GESTURE_BOUNDS,
) -> tuple[Point, float]:
    """要推 reach 這麼長時的起手點與**真的推得動**的行程。

    先篩掉行程會拉出安全框的起手點，再在剩下的裡挑離所有單位最遠的（起手抓到精靈
    整把會被吃掉）。全部都不夠長就退而求其次挑餘裕最大的那一個，並把行程縮到它撐
    得住的長度——回報縮過的行程，讓呼叫端算得出實際位移，不要以為推滿了。
    """
    reach = min(max(reach, PAN_MIN_REACH), PAN_MAX_REACH)
    roomy = [point for point in candidates if pan_headroom(direction, point, bounds) >= reach]
    if roomy:
        return (pick_pan_origin(sightings, roomy), reach)
    origin = max(candidates, key=lambda point: pan_headroom(direction, point, bounds))
    room = pan_headroom(direction, origin, bounds)
    return (origin, max(PAN_MIN_REACH, min(reach, room)))


def pan_gesture(direction: str, origin: Point, reach: float | None = None) -> tuple[int, int, int, int]:
    """把鏡頭往 direction 推的拖曳：手指往反方向拉（往東看＝內容往西拖）。

    reach ＝ 手指行程（螢幕像素）。不給就用 PAN_HALF 的軸別預設；掃描端會依推移距離
    的規則自己算——一把推移的內容位移必須留在無歧義量測範圍的一半以內。
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
