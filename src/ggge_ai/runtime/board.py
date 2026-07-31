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
UNIT_DENSITY_HUD_HOLES: tuple[Region, ...] = ((0, 0, 470, 170),)
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


def read_lattice(frame: np.ndarray | None, region: Region = GRID_REGION) -> Lattice | None:
    """格線位置，讀不出合理格網就 None。

    高通投影取峰：格線是貫穿整張地圖的細亮脊，所以 |高通| 的行／列均值會出峰，
    單位與地圖美術則被平均掉。三重閘擋掉假格網——頭尾間距出帶就裁掉（面板邊
    不是格線）、線數門檻（無格線幀上湊巧對齊的精靈永遠湊不到這個數）、間距全帶
    內且均勻（單位移動模式的藍格覆蓋描同一格網但邊緣抖半格，鬆到不能吸附）。
    """
    if frame is None:
        return None
    x0, y0, w, h = region
    patch = crop(frame, region)
    if patch.shape[0] < h or patch.shape[1] < w:
        return None
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY).astype(np.float32)
    highpass = np.abs(gray - cv2.GaussianBlur(gray, (0, 0), 6))
    cols = _trim(_ridges(highpass.mean(axis=0), x0))
    rows = _trim(_ridges(highpass.mean(axis=1), y0))
    if not _plausible(cols, GRID_MIN_COLS) or not _plausible(rows, GRID_MIN_ROWS):
        return None
    return Lattice(tuple(cols), tuple(rows))


def _ridges(profile: np.ndarray, offset: int) -> list[int]:
    centered = profile - profile.mean()
    gate = centered.std() * 1.2
    out: list[int] = []
    for i in range(2, len(centered) - 2):
        if not (centered[i] >= centered[i - 1] and centered[i] >= centered[i + 1]):
            continue
        if centered[i] <= gate:
            continue
        if not out or i - (out[-1] - offset) >= GRID_MIN_SPACING:
            out.append(offset + i)
        elif centered[i] > centered[out[-1] - offset]:
            out[-1] = offset + i
    return out


def _trim(positions: list[int]) -> list[int]:
    out = list(positions)
    while len(out) >= 2 and not (GRID_MIN_SPACING <= out[1] - out[0] <= GRID_MAX_SPACING):
        out.pop(0)
    while len(out) >= 2 and not (GRID_MIN_SPACING <= out[-1] - out[-2] <= GRID_MAX_SPACING):
        out.pop()
    return out


def _plausible(positions: list[int], minimum: int) -> bool:
    if len(positions) < minimum:
        return False
    gaps = [b - a for a, b in zip(positions, positions[1:], strict=False)]
    if max(gaps) - min(gaps) > GRID_GAP_RANGE:
        return False
    return all(GRID_MIN_SPACING <= gap <= GRID_MAX_SPACING for gap in gaps)


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
    （無特徵星空、或平移過大導致重疊帶不足）就退單位星座投票。兩個都不給答案就
    回 source="none"——寧可承認不知道，也不要拿手勢當位置（0719 西緣鬼影座標
    就是這樣長出來的）。
    """
    a = cv2.cvtColor(crop(previous, region), cv2.COLOR_BGR2GRAY).astype(np.float32)
    b = cv2.cvtColor(crop(current, region), cv2.COLOR_BGR2GRAY).astype(np.float32)
    window = cv2.createHanningWindow((a.shape[1], a.shape[0]), cv2.CV_32F)
    (dx, dy), response = cv2.phaseCorrelate(a, b, window)
    if response >= SHIFT_MIN_RESPONSE:
        return Shift(float(dx), float(dy), float(response), "phase")
    vote = _constellation_shift(find_units(previous), find_units(current))
    if vote is not None:
        return Shift(vote[0], vote[1], vote[2], "constellation")
    return Shift(0.0, 0.0, float(response), "none")


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
    if pitch <= 0:
        return 0.0
    offset = (line - anchor) % pitch
    return offset - pitch if offset > pitch / 2.0 else offset


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
