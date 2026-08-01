"""合成世界：畫布上畫好格線與單位環，裁出視口就是一張截圖。

覆蓋模型的斷言要逐格對答案，實幀系列給不了這種地面真相（人工普查只到 ±1 格），
所以掃描的整段行為對著這個假世界跑：單位擺在哪一格是我們定的，鏡頭移了多少也是
我們定的，於是「四態逐格正確」「跳過的帶被回補」這種話才有意義。

畫布邊界就是地圖邊界——鏡頭夾在畫布內（實機的鏡頭同樣推到邊就不動），所以撞邊
事件是世界的性質，不是腳本插旗。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from ggge_ai.runtime import board

SCREEN = (2340, 1080)
COL_PITCH = 128
ROW_PITCH = 115
LINE_COLOUR = (196, 196, 196)
# 實機最小縮放下 HP 弧與隊徽環併成一個 ~90-110px 的環，密度峰對著那個尺寸調過
# 門檻；畫成實心小圓的話密度高原會攤平成兩個峰，假世界要跟真世界同一個形狀。
UNIT_RADIUS = 45
UNIT_THICKNESS = 10
# 弧色帶內的紅（HSV 5,160,220）：find_units 只認 ARC_BANDS 的三個色帶。
UNIT_HSV = (5, 160, 220)


def freeze_correlator(monkeypatch, response: float = 0.3) -> None:
    """把 phaseCorrelate 的水平分量鎖在靜態峰——0801 t27/t28/t30 的實機情境。

    垂直分量照實回：實機證據是南北向量測健康，只有水平被格線 alias 與 HUD 靜態成分
    搶峰。response 壓在 `SHIFT_MIN_RESPONSE` 之上，所以退星座的 fallback 不會觸發
    ——那正是舊碼在這個情境下救不回來的原因。
    """
    real = board._phase_shift

    def frozen(previous, current, region=board.MAP_REGION):
        _, dy, measured = real(previous, current, region)
        return (0.0, dy, max(measured, response))

    monkeypatch.setattr(board, "_phase_shift", frozen)


def blind_correlator(monkeypatch) -> None:
    """相位相關整個瞎掉（信賴度 0）——無特徵星空的實機情境。

    這是星座 fallback 唯一會被叫到的路徑，影像複驗閘要在這裡受測。
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


def _bgr(hsv: tuple[int, int, int]) -> tuple[int, int, int]:
    patch = np.array([[list(hsv)]], np.uint8)
    b, g, r = cv2.cvtColor(patch, cv2.COLOR_HSV2BGR)[0][0]
    return (int(b), int(g), int(r))


@dataclass
class World:
    """已知擺位的假地圖。cell (0,0) 的左上角就是畫布原點。"""

    cols: int = 22
    rows: int = 12
    units: tuple[tuple[int, int], ...] = ()
    camera: tuple[float, float] = (0.0, 0.0)
    canvas: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        width = max(self.cols * COL_PITCH, SCREEN[0])
        height = max(self.rows * ROW_PITCH, SCREEN[1])
        rng = np.random.default_rng(7)
        canvas = rng.integers(24, 46, size=(height, width, 3), dtype=np.uint8)
        for col in range(self.cols + 1):
            x = col * COL_PITCH
            if x < width:
                canvas[:, x : x + 2] = LINE_COLOUR
        for row in range(self.rows + 1):
            y = row * ROW_PITCH
            if y < height:
                canvas[y : y + 2, :] = LINE_COLOUR
        for cell in self.units:
            cv2.circle(canvas, self.centre(cell), UNIT_RADIUS, _bgr(UNIT_HSV), UNIT_THICKNESS)
        self.canvas = canvas

    @property
    def span(self) -> tuple[int, int]:
        return (self.canvas.shape[1] - SCREEN[0], self.canvas.shape[0] - SCREEN[1])

    def centre(self, cell: tuple[int, int]) -> tuple[int, int]:
        return (
            int(cell[0] * COL_PITCH + COL_PITCH // 2),
            int(cell[1] * ROW_PITCH + ROW_PITCH // 2),
        )

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
