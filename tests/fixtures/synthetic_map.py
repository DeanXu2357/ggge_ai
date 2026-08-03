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

from ggge_ai.runtime import board

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


def freeze_correlator(monkeypatch, response: float = 0.3) -> None:
    """把 phaseCorrelate 的水平分量鎖在靜態峰——0801 t27/t28/t30 的實機情境。

    垂直分量照實回：實機證據是南北向量測健康，只有水平被格線差整數個週期的誤配與 HUD 靜態成分
    搶峰。response 壓在 `SHIFT_MIN_RESPONSE` 之上，所以退去用單位排列比對的那條路不會觸發
    ——那正是舊碼在這個情境下救不回來的原因。
    """
    real = board._phase_shift

    def frozen(previous, current, region=board.MAP_REGION):
        _, dy, measured = real(previous, current, region)
        return (0.0, dy, max(measured, response))

    monkeypatch.setattr(board, "_phase_shift", frozen)


def blind_correlator(monkeypatch) -> None:
    """相位相關整個瞎掉（信賴度 0）——無特徵星空的實機情境。

    這是單位排列比對唯一會被叫到的路徑，影像複驗閘要在這裡受測。
    """
    monkeypatch.setattr(board, "_phase_shift", lambda *args, **kwargs: (0.0, 0.0, 0.0))


def animated(frame: np.ndarray, step: int = 4) -> np.ndarray:
    """待機動畫的合成版：整幀亮度抖一階。位移是零，但 frame_difference 過得了門檻
    ——實機待機動畫實測 5.8-12.5，恆高於 EDGE_FRAME_DIFF（2.5），原地幀因此永遠
    走不進靜止那一支。"""
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


def _bgr(hsv: tuple[int, int, int]) -> tuple[int, int, int]:
    patch = np.array([[list(hsv)]], np.uint8)
    b, g, r = cv2.cvtColor(patch, cv2.COLOR_HSV2BGR)[0][0]
    return (int(b), int(g), int(r))


@dataclass
class World:
    """已知擺位的假地圖，四周包一圈虛空。cell (0,0) 的左上角在畫布的 MARGIN 處。"""

    cols: int = 22
    rows: int = 12
    units: tuple[tuple[int, int], ...] = ()
    camera: tuple[float, float] = (0.0, 0.0)
    margin: tuple[int, int] = MARGIN
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
        return np.ascontiguousarray(self.canvas[y : y + SCREEN[1], x : x + SCREEN[0]])

    def move(self, dx: float, dy: float) -> tuple[float, float]:
        """把鏡頭推一段，夾在畫布內。回傳實際移動量（撞邊時比要求的少）。"""
        span = self.span
        before = self.camera
        self.camera = (
            min(max(self.camera[0] + dx, 0.0), float(span[0])),
            min(max(self.camera[1] + dy, 0.0), float(span[1])),
        )
        return (self.camera[0] - before[0], self.camera[1] - before[1])
