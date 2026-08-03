"""合成世界：畫布上畫好格線與單位環，裁出視口就是一張截圖。

覆蓋模型的斷言要逐格對答案，實幀系列給不了這種地面真相（人工普查只到 ±1 格），
所以掃描的整段行為對著這個假世界跑：單位擺在哪一格是我們定的，鏡頭移了多少也是
我們定的，於是「四態逐格正確」「跳過的帶被回補」這種話才有意義。

地圖四周留一圈虛空（實機上是地圖以外那片無特徵的深色背景，下稱星空），鏡頭夾在畫布
內（實機的鏡頭同樣推到底就不動）。所以「推到底卡住」與「畫面裡看得到地圖終止邊」都是
世界的性質，不是腳本插旗——v3 的座標全部從這兩件事解出來，假世界要先有得看。

虛空寬度（`MARGIN`）不是隨便挑的：它要讓四側的終止邊在各自的角落都落進格線取樣帶
（`board.GRID_REGION` 是 x150-1750／y250-780），不然讀不到那條邊就等於沒有地標。
`test_the_synthetic_world_shows_every_border_at_its_own_corner` 守著這個性質。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from ggge_ai.runtime import board, coverage

SCREEN = (2340, 1080)
COL_PITCH = 128
ROW_PITCH = 115
# 地圖外圍的虛空寬度（橫、縱）。橫向 600 讓東界推到底時落在 x1740（取樣帶到 1750）、
# 西界落在 x600；縱向 310 讓北界推到底時落在 y310、南界落在 y770（取樣帶 250-780）。
MARGIN = (600, 310)
VOID_LEVEL = (6, 14)
LINE_COLOUR = (196, 196, 196)
# 實機最小縮放下 HP 弧與隊徽環併成一個 ~90-110px 的環，密度峰對著那個尺寸調過
# 門檻；畫成實心小圓的話密度高原會攤平成兩個峰，假世界要跟真世界同一個形狀。
UNIT_RADIUS = 45
UNIT_THICKNESS = 10
# 弧色帶內的紅（HSV 5,160,220）：find_units 只認 ARC_BANDS 的三個色帶。
UNIT_HSV = (5, 160, 220)
# 西北角那一屏必須站得住的兩台。推不動的判定退回逐精靈窗（board.null_check）時，一個
# 窗要成立，「動了指令那麼多」那個假設得把它映回前一幀的畫面內——一把推移 598px，所以
# 角落幀裡 x 或 y 小於 643 的機體全部落到幀外，湊不到兩個窗就是「裁判沒得看」。
# c2-7／r3-4 這兩格同時滿足「在 MAP_REGION 內」與「往西、往北各退 598px 仍在幀內」。
CORNER: tuple[tuple[int, int], ...] = ((2, 3), (7, 4))
# 標記格的填色。刻意選在 ARC_BANDS 三個色帶之外（S=255 超出弧的 S<=210 上界），
# 這樣「填色會不會被密度峰讀成一台機體」是測得出來的事實而不是巧合。
MARKER_HSV = (30, 255, 255)
# 填色離格線內縮幾個像素：實機的填色蓋不蓋得住格線還沒標定，假世界取保守的一邊
# （格線留著），格網讀取才不會因為多了一格填色就換一套線位。
MARKER_INSET = 8


def pan_leg(direction: str, reach: float = 260.0) -> coverage.Leg:
    """一把推移的指令，內容位移與 `Survey._leg` 同一條算式。

    推不動的判定拿 `expected` 當「動了這麼多」的假設去問畫面，所以 (0,0) 這種佔位值
    問不出東西——兩個假設重合，`board.null_check` 直接回 blind。
    """
    dx, dy = board.DIRECTIONS[direction]
    travel = reach * coverage.NOMINAL_GAIN
    return coverage.Leg(direction, reach, (-dx * travel, -dy * travel))


def animated(frame: np.ndarray, step: int = 4) -> np.ndarray:
    """待機動畫的合成版：整幀亮度抖一階。位移是零，但整幀逐像素都變了——任何
    「兩幀像不像」的比法都會把它讀成動過。"""
    return cv2.add(frame, step)


def void_outside(
    frame: np.ndarray,
    box: tuple[int, int, int, int],
    seed: int = 11,
    level: tuple[int, int] = (6, 14),
) -> np.ndarray:
    """框外換成星空虛空（暗噪點）：地圖走到邊緣時畫面就是這樣，格線只剩框內那一角。

    level 調亮就是「框外還是地圖，只是這一帶沒讀到線」——終止邊的亮度閘要擋下它。
    """
    rng = np.random.default_rng(seed)
    out = rng.integers(level[0], level[1], size=frame.shape, dtype=np.uint8)
    x, y, w, h = box
    out[y : y + h, x : x + w] = frame[y : y + h, x : x + w]
    return np.ascontiguousarray(out)


def dim_outside(
    frame: np.ndarray, box: tuple[int, int, int, int], factor: float = 0.35
) -> np.ndarray:
    """框外整片壓暗：地圖還在、格線也還在，只是亮度掉到虛空那一級。

    「線到這裡為止」與「地圖到此為止」的分野在**外面還有沒有格線**，不在亮度——
    這張圖就是拿來守著那條分野的。
    """
    out = frame.astype(np.float32) * factor
    x, y, w, h = box
    out[y : y + h, x : x + w] = frame[y : y + h, x : x + w]
    return np.ascontiguousarray(out.astype(np.uint8))


def mark_world(survey: coverage.Survey, world: World) -> bool:
    """走一次完整的放標記流程：問世界模型要點哪裡、點下去、把前後幀交回去學色簽。

    這就是 `stage/survey.BoardDriver` 那個 `mark` 微步驟做的事，只是不經過執行器
    ——直接對 `Survey.observe` 說話的案例照樣需要標記，不然角落根本確認不了推到底。
    """
    spot = survey.marker_request()
    if spot is None:
        return False
    before = world.frame()
    if world.tap(*spot) is None:
        return False
    return survey.learn_marker(before, world.frame(), spot)


def mark_frame(survey: coverage.Survey, frame: np.ndarray) -> np.ndarray | None:
    """實幀語料的同一件事：借真畫面的格線挑一格，把填色合成上去。

    實機的填色像素還沒標定（`scripts/probe_marker.py` 就是去標它的），所以實幀案例
    只借真畫面的格網、終止邊與機體，填色本身是合成的。回傳蓋了填色的那一張。
    """
    spot = survey.marker_request()
    if spot is None:
        return None
    after = stamped(frame, spot)
    if after is None or not survey.learn_marker(frame, after, spot):
        return None
    return after


def stamped(frame: np.ndarray, point: tuple[float, float]) -> np.ndarray | None:
    """把 point 所在的那一格填成標記色。讀不到格線或點落在線 span 外就 None。"""
    lattice = board.find_lattice(frame)
    if lattice is None:
        return None
    x = _bracket(lattice.cols, point[0])
    y = _bracket(lattice.rows, point[1])
    if x is None or y is None:
        return None
    out = frame.copy()
    out[y[0] + MARKER_INSET : y[1] - MARKER_INSET, x[0] + MARKER_INSET : x[1] - MARKER_INSET] = (
        _bgr(MARKER_HSV)
    )
    return out


def _bracket(positions: tuple[int, ...], value: float) -> tuple[int, int] | None:
    return next(
        ((low, high) for low, high in zip(positions, positions[1:], strict=False)
         if low <= value <= high),
        None,
    )


def _bgr(hsv: tuple[int, int, int]) -> tuple[int, int, int]:
    patch = np.array([[list(hsv)]], np.uint8)
    b, g, r = cv2.cvtColor(patch, cv2.COLOR_HSV2BGR)[0][0]
    return (int(b), int(g), int(r))


@dataclass
class World:
    """已知擺位的假地圖，四周包一圈虛空。cell (0,0) 的左上角在畫布的 MARGIN 處。

    marker ＝ 被點過的那一格（填色）。它畫在取景之後而不是畫進畫布：點一下就換一格，
    而畫布是建構時就固定的。
    """

    cols: int = 22
    rows: int = 12
    units: tuple[tuple[int, int], ...] = ()
    camera: tuple[float, float] = (0.0, 0.0)
    margin: tuple[int, int] = MARGIN
    marker: tuple[int, int] | None = None
    canvas: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        mx, my = self.margin
        width = max(self.cols * COL_PITCH + 2 * mx, SCREEN[0])
        height = max(self.rows * ROW_PITCH + 2 * my, SCREEN[1])
        rng = np.random.default_rng(7)
        canvas = rng.integers(*VOID_LEVEL, size=(height, width, 3), dtype=np.uint8)
        ground = rng.integers(24, 46, size=(self.rows * ROW_PITCH, self.cols * COL_PITCH, 3),
                              dtype=np.uint8)
        canvas[my : my + ground.shape[0], mx : mx + ground.shape[1]] = ground
        for col in range(self.cols + 1):
            x = mx + col * COL_PITCH
            canvas[my : my + self.rows * ROW_PITCH + 2, x : x + 2] = LINE_COLOUR
        for row in range(self.rows + 1):
            y = my + row * ROW_PITCH
            canvas[y : y + 2, mx : mx + self.cols * COL_PITCH + 2] = LINE_COLOUR
        for cell in self.units:
            cv2.circle(canvas, self.centre(cell), UNIT_RADIUS, _bgr(UNIT_HSV), UNIT_THICKNESS)
        self.canvas = canvas

    @property
    def span(self) -> tuple[int, int]:
        return (self.canvas.shape[1] - SCREEN[0], self.canvas.shape[0] - SCREEN[1])

    def centre(self, cell: tuple[int, int]) -> tuple[int, int]:
        return (
            int(self.margin[0] + cell[0] * COL_PITCH + COL_PITCH // 2),
            int(self.margin[1] + cell[1] * ROW_PITCH + ROW_PITCH // 2),
        )

    def corner(self, *sides: str) -> None:
        """把鏡頭推到某幾側推不動的位置（測試要一個確定的角落時用）。"""
        span = self.span
        x, y = self.camera
        for side in sides:
            x = 0.0 if side == "west" else float(span[0]) if side == "east" else x
            y = 0.0 if side == "north" else float(span[1]) if side == "south" else y
        self.camera = (x, y)

    def frame(self) -> np.ndarray:
        """當下鏡頭位置的一張截圖（世界像素 ＝ 螢幕像素 ＋ camera）。"""
        x, y = int(round(self.camera[0])), int(round(self.camera[1]))
        view = np.ascontiguousarray(self.canvas[y : y + SCREEN[1], x : x + SCREEN[0]])
        if self.marker is not None:
            self._fill(view, (x, y))
        return view

    def _fill(self, view: np.ndarray, camera: tuple[int, int]) -> None:
        assert self.marker is not None
        mx, my = self.margin
        x0 = mx + self.marker[0] * COL_PITCH - camera[0] + MARKER_INSET
        y0 = my + self.marker[1] * ROW_PITCH - camera[1] + MARKER_INSET
        x1 = x0 + COL_PITCH - 2 * MARKER_INSET
        y1 = y0 + ROW_PITCH - 2 * MARKER_INSET
        left, top = max(0, x0), max(0, y0)
        right, bottom = min(SCREEN[0], x1), min(SCREEN[1], y1)
        if left < right and top < bottom:
            view[top:bottom, left:right] = _bgr(MARKER_HSV)

    def cell_at(self, point: tuple[float, float]) -> tuple[int, int] | None:
        """螢幕點落在哪一格（地圖外回 None）。"""
        mx, my = self.margin
        col = int((point[0] + self.camera[0] - mx) // COL_PITCH)
        row = int((point[1] + self.camera[1] - my) // ROW_PITCH)
        if 0 <= col < self.cols and 0 <= row < self.rows:
            return (col, row)
        return None

    def tap(self, x: float, y: float) -> tuple[int, int] | None:
        """點一下的遊戲反應：空格＝填色搬到那一格，有單位的格＝變成選取單位（不填色）。

        回傳標記落在哪一格，沒搬就 None。點擊**不會**讓鏡頭置中（使用者實機確認）。
        """
        cell = self.cell_at((x, y))
        if cell is None or cell in self.units:
            return None
        self.marker = cell
        return cell

    def move(self, dx: float, dy: float) -> tuple[float, float]:
        """把鏡頭推一段，夾在畫布內。回傳實際移動量（撞邊時比要求的少）。"""
        span = self.span
        before = self.camera
        self.camera = (
            min(max(self.camera[0] + dx, 0.0), float(span[0])),
            min(max(self.camera[1] + dy, 0.0), float(span[1])),
        )
        return (self.camera[0] - before[0], self.camera[1] - before[1])
