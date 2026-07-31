"""地圖縮放：兩指 pinch 後端，以及「縮到最小」的收斂迴圈。

搬自凍結的 `actuation/pinch.py`，只留這台裝置上真的跑得動的那一條路。裝置實情
（0720 實機量測，R5CRC37JBYJ／SM-G9900）：sendevent 寫 /dev/input/event7 被
SELinux 擋死（Enforcing、無 su、production build 拒 `adb root`），所以唯一可行
的後端是 GesturePincher——經 uiautomator server 注入兩指 MotionEvent（`adb shell
input` 走的同一條非 root 注入路），該次實機驗證確實把戰鬥地圖縮小了。凍結層那條
sendevent 路留在原地不動，這裡不重複。

縮放是**最佳化不是前提**：縮不動照樣掃得完，只是截圖次數變多。所以這裡每一步
失敗都只讓鏡頭少縮一點，不擋任何流程。

pinch 的兩根手指是螢幕座標，注入時繞過裝置層的 tap 白名單，所以落點自己守：
候選中心只在 PINCH_SAFE_REGION 內挑，出手前四個點再過一次 check_tap。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from . import board
from .device import check_tap

log = logging.getLogger(__name__)

Point = tuple[float, float]


class Pincher(Protocol):
    """縮放接縫：一次呼叫跑完一整個兩指手勢。測試注入錄音機。"""

    def pinch(self, finger_a: tuple[Point, Point], finger_b: tuple[Point, Point]) -> None: ...


@dataclass
class GesturePincher:
    """注入 API 後端：直接以橫向螢幕像素做兩指手勢（uiautomator server 在顯示層
    注入，不必換算面板 raw 座標）。`gesture` 是注入接縫，簽名對齊 uiautomator2 的
    ``d(...).gesture(start1, start2, end1, end2, steps)``。"""

    gesture: Callable[[Point, Point, Point, Point, int], object]
    steps: int = 40

    def pinch(self, finger_a: tuple[Point, Point], finger_b: tuple[Point, Point]) -> None:
        self.gesture(finger_a[0], finger_b[0], finger_a[1], finger_b[1], self.steps)


# 遊戲的 Unity 繪圖面：手勢注在這個 view 上才落在地圖而不是周邊 chrome。
SURFACE_RESOURCE_ID = "com.bandainamcoent.gget_WW:id/unitySurfaceView"


def gesture_pincher_for(
    device: Any, *, resource_id: str = SURFACE_RESOURCE_ID, steps: int = 40
) -> GesturePincher:
    """把 GesturePincher 接上一台 uiautomator2 裝置——本機唯一可用的縮放後端。"""
    return GesturePincher(
        gesture=lambda s1, s2, e1, e2, n: device(resourceId=resource_id).gesture(
            s1, s2, e1, e2, n
        ),
        steps=steps,
    )


ZOOM_START_SPAN = 1000.0
ZOOM_END_SPAN = 120.0

# 固定中心的退路：地圖中段，避開上方的結束回合 (275,182)／AUTO (1815,52) 與下緣
# 的可行動單位卡條。
PINCH_CENTER_DEFAULT: Point = (1170.0, 500.0)
# 起手落在單位精靈上會被遊戲吃掉（board.pick_pan_origin 躲的同一個坑），所以中心
# 逐幀重挑。最寬的兩點是起手點（中心 ± start_span/2），格子的範圍就以「cx ± 500
# 仍留在安全區內」為界。
PINCH_SAFE_REGION = (400, 330, 1500, 320)  # x, y, w, h -> x in [400,1900], y in [330,650]
PINCH_CENTER_GRID: tuple[Point, ...] = tuple(
    (float(x), float(y))
    for y in (380.0, 490.0, 600.0)
    for x in (900.0, 1050.0, 1170.0, 1290.0, 1400.0)
)


def zoom_out_fingers(
    center: Point = PINCH_CENTER_DEFAULT,
    *,
    start_span: float = ZOOM_START_SPAN,
    end_span: float = ZOOM_END_SPAN,
    horizontal: bool = True,
) -> tuple[tuple[Point, Point], tuple[Point, Point]]:
    """兩根對稱手指：起手相距 start_span，收到 end_span——捏合＝鏡頭拉遠。"""
    cx, cy = center
    h0, h1 = start_span / 2.0, end_span / 2.0
    if horizontal:
        return ((cx - h0, cy), (cx - h1, cy)), ((cx + h0, cy), (cx + h1, cy))
    return ((cx, cy - h0), (cx, cy - h1)), ((cx, cy + h0), (cx, cy + h1))


def pick_pinch_center(
    peaks: Sequence[Point],
    *,
    start_span: float = ZOOM_START_SPAN,
    end_span: float = ZOOM_END_SPAN,
    horizontal: bool = True,
    candidates: Sequence[Point] = PINCH_CENTER_GRID,
    region: tuple[int, int, int, int] = PINCH_SAFE_REGION,
    default: Point = PINCH_CENTER_DEFAULT,
) -> Point:
    """四個手指點離所有單位最遠、且四點都留在 region 內的中心。

    純函式：peaks 由呼叫端注入。對假峰容忍——多一個幽靈只會把中心推開一點，
    不會弄壞手勢。沒有峰（沒東西要躲）或沒有合格候選就回 default。
    """
    if not peaks:
        return default
    rx, ry, rw, rh = region
    best: tuple[float, Point] | None = None
    for center in candidates:
        a, b = zoom_out_fingers(
            center, start_span=start_span, end_span=end_span, horizontal=horizontal
        )
        points = (a[0], a[1], b[0], b[1])
        if not all(rx <= px <= rx + rw and ry <= py <= ry + rh for px, py in points):
            continue
        clearance = min(
            ((px - ux) ** 2 + (py - uy) ** 2) ** 0.5 for px, py in points for ux, uy in peaks
        )
        if best is None or clearance > best[0]:
            best = (clearance, center)
    return best[1] if best is not None else default


LATTICE_SOURCE = "lattice"
FRAME_SOURCE = "frame"


@dataclass(frozen=True)
class PitchStep:
    """一次 pinch 之後量到的東西，供流水帳重建整段縮放。"""

    index: int
    col_pitch: float | None
    row_pitch: float | None
    change: float | None  # 與上一幀的地圖區平均絕對差
    source: str  # 判定依據："lattice" 讀到格距／"frame" 退幀差


def _lattice_pitch(frame: np.ndarray) -> tuple[float | None, float | None, str | None]:
    """格距（欄／列線位的中位間距）。讀不出格網就三個 None，收斂改吃幀差。"""
    lattice = board.read_lattice(frame)
    if lattice is None:
        return None, None, None
    return lattice.col_pitch, lattice.row_pitch, LATTICE_SOURCE


def zoom_out_max(
    capture: Callable[[], Any],
    pinch_step: Callable[[], None],
    *,
    measure: Callable[[Any], tuple[float | None, float | None, str | None]] = _lattice_pitch,
    frame_change: Callable[[Any, Any], float] = board.frame_difference,
    sleep: Callable[[float], None] = time.sleep,
    settle_s: float = 1.3,
    max_pinches: int = 10,
    shrink_tol: float = 1.5,
    change_tol: float = 2.5,
    on_step: Callable[[PitchStep], None] | None = None,
) -> list[PitchStep]:
    """一直 pinch 到地圖不再縮小為止（冪等：已經在最小縮放時只多量兩次）。

    主判準是格距：連兩次 pinch 都沒讓欄距縮掉 shrink_tol 以上＝鏡頭到底。讀不出
    格網時（格線關著、彈窗蓋住）退幀差 fail-soft——連兩幀幾乎一樣（change <
    change_tol）就算停住。每一步都經 on_step 回報並收進回傳值。
    """
    frame = capture()
    col, row, reader = measure(frame)
    steps = [PitchStep(0, col, row, None, reader or FRAME_SOURCE)]
    if on_step:
        on_step(steps[0])

    stable = 0
    previous, previous_col = frame, col
    for index in range(1, max_pinches + 1):
        pinch_step()
        sleep(settle_s)
        frame = capture()
        col, row, reader = measure(frame)
        change = frame_change(previous, frame)

        if col is not None and previous_col is not None:
            shrank = (previous_col - col) > shrink_tol
        else:
            shrank = change > change_tol

        stable = 0 if shrank else stable + 1
        record = PitchStep(index, col, row, round(change, 3), reader or FRAME_SOURCE)
        steps.append(record)
        if on_step:
            on_step(record)
        if stable >= 2:
            break
        previous, previous_col = frame, (col if col is not None else previous_col)
    return steps


@dataclass
class ZoomOut:
    """掃描行動的 zoom_out 注入件：一次呼叫＝把鏡頭縮到最小。

    pinch 中心逐步從當下的幀重挑（單位會吃掉起手點），所以這裡把 zoom_out_max
    抓的幀留一份給下一次挑中心用，不另外多截一張。
    """

    capture: Callable[[], np.ndarray]
    pincher: Pincher
    sleep: Callable[[float], None] = field(default=time.sleep)
    on_step: Callable[[PitchStep], None] | None = None
    latest: np.ndarray | None = field(default=None, init=False)

    def __call__(self) -> None:
        zoom_out_max(self._capture, self._pinch, sleep=self.sleep, on_step=self.on_step)

    def _capture(self) -> np.ndarray:
        self.latest = self.capture()
        return self.latest

    def _pinch(self) -> None:
        frame = self.latest if self.latest is not None else self._capture()
        finger_a, finger_b = zoom_out_fingers(pick_pinch_center(board.find_units(frame)))
        for x, y in (finger_a[0], finger_a[1], finger_b[0], finger_b[1]):
            check_tap(round(x), round(y))
        self.pincher.pinch(finger_a, finger_b)
