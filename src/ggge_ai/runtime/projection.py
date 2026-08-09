"""盤面透視投影：世界等距格網 → 螢幕格線位置，以及位置空間的逐線殘差。

盤面在螢幕上是**固定的平面單應性**、與鏡位無關（`docs/reviews/perspective-measurement.md`
§1／§2.3，758 幀兩 run）：縱線斜率場 `dx/dy = K·(x − VP_X)`、欄距 ∝ s、列距 ∝ s²。
本模組把那組形狀參數變成「這一幀的格線該落在哪裡」，再與實測線位**逐線比對位置**。

不取模是重點：`sweep.aim_drift` 比的是兩個相位，而兩側的週期取自不同來源（同報告
§3.4，中位 0.052 格、p95 0.156 格的系統項），位置空間比對沒有這個問題。

## 世界座標的唯一約定

**世界 ＝ 螢幕座標量在 `world_ref_y` 這個高度上的值 ＋ 鏡位。**

`world_ref_y` ＝主格線帶（`board.GRID_REGION`）的中線。縱線是斜的，同一條線的螢幕 x
隨高度變，所以「螢幕 x」不講高度就沒有意義：帶內投影取到的是**帶中線那個高度**的 x
（報告 §3.3 中位差 0），錨定要把它換算到 `world_ref_y` 才是同一套座標。橫線水平，
世界 y 就是原始螢幕 y，列距同樣歸一到 `world_ref_y`。

`ref_y`（`board.PERSPECTIVE_REF_Y`）是另一回事：那是形狀參數的展開點，也就是
`board.rectify_columns` 的校正座標所在的高度，`col_scale` 在那裡恆為 1。

## 還沒補的那道縫

**界線讀數（`board.scan_edges`）天生在 `ref_y` 上**（`EDGE_SCAN_REGION` 的中線恰為
650），與世界座標差一次 `restaged` 換算；世界 y 是原始螢幕 y，而模型的世界 y 是攤平
座標，同樣差一次換算。兩者都沒有在這裡補，因為補了就必須連**單位目擊與點擊點**一起
換空間——那些位置現在是「原始螢幕座標＋鏡位」，只換世界格網不換位置，格座標指派會
比現在更錯（中帶 ±15px、頂帶 ±46px）。離線重放量到的代價是絕對口徑欄殘差常數
8-13px、列殘差 1.5-3.5px；補它是「整條定位鏈走 projection」那一批的事，而且要先讓
`tests/fixtures/synthetic_map` 帶上透視，否則平面假世界驗不了這件事。

坑：這道縫與**格距精度耦合**。舊的整數中位格距系統性偏大 0.6-0.9%，方向剛好部分
抵銷界線那道縫的尺規誤差，所以換上次像素格距之後，幀內殘差變好（離線重放 centred
口徑 p95 0.117→0.055、0.086→0.060）而絕對殘差可能反而變差（run 133305 欄中位
10.7→20.5px）。改動任一邊都要重看 `aim_shadow` 的實測分布，不能只看幀內。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from . import board

Point = tuple[float, float]
Region = tuple[int, int, int, int]

# 世界座標的參考高度：主格線帶的中線。帶內投影取的是帶中線那個高度的線位
# （報告 §3.3 中位差 0），世界格距與相位都歸一在這裡。
WORLD_REF_Y = board.GRID_REGION[1] + board.GRID_REGION[3] / 2.0


class Grid(Protocol):
    """`coverage.WorldGrid` 的結構型別（本模組不倒著相依 coverage）。"""

    phase: Point
    col_pitch: float
    row_pitch: float


@dataclass(frozen=True)
class Projection:
    """盤面透視的**形狀**參數。scale 在 `ref_y` 上恆為 1。

    預設值出自 `docs/reviews/perspective-measurement.md`：§2.2 的縱線斜率
    `dx/dy = 1.100e-4·(x − 1164.1)`、§3 列距單應性 `pitch ∝ (1 + k₂·Δy)²` 擬合
    k₂ = 1.180e-4（與欄距的理論關係是 k₂ ≈ K，實測差 7%，報告 §5 存疑第 8 條）。

    **絕對格距不在這裡**：它逐 run 差 0.9%（報告 §5），一律取自 `Grid` 錨定當場量到的
    `col_pitch` / `row_pitch`。形狀參數日後要現場擬合就整組換掉——
    `dataclasses.replace(PROJECTION, ...)` 之後傳進各函式的 `projection`，本模組不留可變全域。
    """

    vp_x: float = 1164.1
    col_k: float = 1.100e-4
    row_k: float = 1.180e-4
    ref_y: float = board.PERSPECTIVE_REF_Y
    world_ref_y: float = WORLD_REF_Y

    def col_scale(self, y: float) -> float:
        return 1.0 + self.col_k * (y - self.ref_y)

    def row_scale(self, y: float) -> float:
        return 1.0 + self.row_k * (y - self.ref_y)

    def restaged(self, x: float, source_y: float, target_y: float) -> float:
        """量在 `source_y` 上的螢幕 x → 同一條世界縱線量在 `target_y` 上的螢幕 x。"""
        return self.vp_x + (x - self.vp_x) * self.col_scale(target_y) / self.col_scale(source_y)

    def screen_x(self, world_x: float, offset_x: float, y: float) -> float:
        """世界縱線在螢幕高度 y 上的 x。世界 x ＝ `world_ref_y` 上的螢幕 x ＋鏡位。"""
        return self.restaged(world_x - offset_x, self.world_ref_y, y)

    def world_x(self, x: float, offset_x: float, y: float) -> float:
        return self.restaged(x, y, self.world_ref_y) + offset_x

    def world_y(self, y: float, offset_y: float) -> float:
        """螢幕 y → 世界 y。世界 y 的尺規是 `world_ref_y` 上的螢幕像素（列距在其中為常數）。"""
        span = self.row_scale(self.world_ref_y) ** 2
        flat = self._row_flat(y) - self._row_flat(self.world_ref_y)
        return self.world_ref_y + flat * span + offset_y

    def screen_y(self, world_y: float, offset_y: float) -> float:
        span = self.row_scale(self.world_ref_y) ** 2
        flat = self._row_flat(self.world_ref_y) + (world_y - offset_y - self.world_ref_y) / span
        return self._row_unflat(flat)

    def _row_flat(self, y: float) -> float:
        delta = y - self.ref_y
        return self.ref_y + delta / (1.0 + self.row_k * delta)

    def _row_unflat(self, flat: float) -> float:
        delta = flat - self.ref_y
        return self.ref_y + delta / (1.0 - self.row_k * delta)


PROJECTION = Projection()


@dataclass(frozen=True)
class Residual:
    """逐線殘差（實測 − 最近的預測線），螢幕像素。`offsets` 與傳進來的實測線同序。"""

    offsets: tuple[float, ...]
    median: float | None


def lines_between(phase: float, pitch: float, low: float, high: float) -> tuple[float, ...]:
    """世界座標 [low, high] 內的等距格線位置。"""
    if pitch <= 0 or high < low:
        return ()
    first = math.ceil((low - phase) / pitch)
    last = math.floor((high - phase) / pitch)
    if last < first:
        return ()
    return tuple(phase + index * pitch for index in range(first, last + 1))


def anchor(
    lattice: board.Lattice,
    band: Region,
    offset: Point = (0.0, 0.0),
    *,
    projection: Projection = PROJECTION,
) -> tuple[Point, Point] | None:
    """錨定幀的格線 → (世界相位, 世界格距)。湊不出等距序列就 None。

    這是世界座標唯一的產出口。`band` 決定線位量在哪個高度上：主帶（`GRID_REGION`）的
    中線就是 `world_ref_y`，換算是恆等；主帶讀不出來退到四象限窗時中線差 110／200px，
    不換算的話同一條線的世界 x 會差到 22px＝0.24 格（縱線斜率場 §2.2）。
    """
    eval_y = band[1] + band[3] / 2.0
    ruler = projection.world_ref_y
    columns = board.fit_lines([projection.restaged(x, eval_y, ruler) for x in lattice.cols])
    rows = board.fit_lines(lattice.rows)
    if columns is None or rows is None:
        return None
    row_span = (projection.row_scale(ruler) / projection.row_scale(eval_y)) ** 2
    return (
        (columns[0] + offset[0], rows[0] + offset[1]),
        (columns[1], rows[1] * row_span),
    )


def expected_columns(
    grid: Grid,
    offset: Point,
    y: float,
    span: tuple[float, float],
    *,
    projection: Projection = PROJECTION,
) -> tuple[float, ...]:
    """在螢幕高度 y 上，螢幕 x 落在 `span` 內的各世界縱線位置。"""
    low = projection.world_x(span[0], offset[0], y)
    high = projection.world_x(span[1], offset[0], y)
    return tuple(
        projection.screen_x(line, offset[0], y)
        for line in lines_between(grid.phase[0], grid.col_pitch, low, high)
    )


def expected_rows(
    grid: Grid,
    offset: Point,
    span: tuple[float, float],
    *,
    projection: Projection = PROJECTION,
) -> tuple[float, ...]:
    """螢幕 y 落在 `span` 內的各世界橫線位置。"""
    low = projection.world_y(span[0], offset[1])
    high = projection.world_y(span[1], offset[1])
    return tuple(
        projection.screen_y(line, offset[1])
        for line in lines_between(grid.phase[1], grid.row_pitch, low, high)
    )


def line_residual(expected: Sequence[float], measured: Sequence[float]) -> Residual:
    """每一條實測線配最近的預測線，取差。不取模——半格以上的偏一樣會混疊，但兩側是
    同一把尺，不會憑空生出 `aim_drift` 那種週期錯配的假訊號。

    缺線（預測有、實測沒有）只是少一筆；多線（實測有假脊）會配到某條預測線並留下大殘差，
    由中位數擋掉。
    """
    if not len(expected) or not len(measured):
        return Residual((), None)
    guess = np.asarray(expected, dtype=float)
    seen = np.asarray(measured, dtype=float)
    delta = seen[:, None] - guess[None, :]
    picked = delta[np.arange(len(seen)), np.argmin(np.abs(delta), axis=1)]
    return Residual(tuple(float(value) for value in picked), float(np.median(picked)))


def shadow_drift(
    lattice: board.Lattice,
    band: Region,
    grid: Grid,
    offset: Point,
    *,
    at: Point,
    projection: Projection = PROJECTION,
) -> Point | None:
    """實測格線與模型預測格線的殘差，換算到螢幕位置 `at` 上的像素。

    坑：`lattice.cols` 是**帶內投影**的產物，量的是帶中線那個高度上的 x（報告 §3.3：
    全高投影與分帶投影的中位差 0），所以預測必須在同一個高度上算。拿別的高度（例如
    點擊窗中心）去預測帶中線量到的線就是換了座標系，殘差整批作廢；`at` 只用來把算好
    的殘差按透視縮放搬過去。
    """
    x0, y0, width, height = band
    eval_y = y0 + height / 2.0
    # 坑：預測窗要比量測窗各外擴一格。貼著窗邊的實測線若沒有預測線可配，會配到窗內
    # 最後一條、留下一整格的假殘差。
    columns = line_residual(
        expected_columns(
            grid,
            offset,
            eval_y,
            (x0 - grid.col_pitch, x0 + width + grid.col_pitch),
            projection=projection,
        ),
        lattice.cols,
    )
    rows = line_residual(
        expected_rows(
            grid,
            offset,
            (y0 - grid.row_pitch, y0 + height + grid.row_pitch),
            projection=projection,
        ),
        lattice.rows,
    )
    if columns.median is None or rows.median is None:
        return None
    drift_x = columns.median * projection.col_scale(at[1]) / projection.col_scale(eval_y)
    scaled = [
        value * (projection.row_scale(at[1]) / projection.row_scale(line)) ** 2
        for value, line in zip(rows.offsets, lattice.rows, strict=True)
    ]
    return (drift_x, float(np.median(scaled)))
