"""盤面透視投影：世界等距格網 → 螢幕格線位置，以及位置空間的逐線殘差。

盤面在螢幕上是**固定的平面單應性**、與鏡位無關（`docs/reviews/perspective-measurement.md`
§1／§2.3，758 幀兩 run）：縱線斜率場 `dx/dy = K·(x − VP_X)`、欄距 ∝ s、列距 ∝ s²。
本模組把那組形狀參數變成「這一幀的格線該落在哪裡」，再與實測線位**逐線比對位置**。

不取模是重點：`sweep.aim_drift` 比的是兩個相位，而兩側的週期取自不同來源（同報告
§3.4，中位 0.052 格、p95 0.156 格的系統項），位置空間比對沒有這個問題。

只算不用——目前唯一的呼叫端是 `scripts/sweep_scan.py` 的影子入帳，不參與任何判定。
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

# 世界座標的參考高度：`WorldGrid` 的 phase／pitch 是錨定幀在 GRID_REGION 帶量出來的，
# 而帶內投影取的是帶中線那個高度的線位（報告 §3.3 中位差 0）。
GRID_REF_Y = board.GRID_REGION[1] + board.GRID_REGION[3] / 2.0


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
    grid_ref_y: float = GRID_REF_Y

    def col_scale(self, y: float) -> float:
        return 1.0 + self.col_k * (y - self.ref_y)

    def row_scale(self, y: float) -> float:
        return 1.0 + self.row_k * (y - self.ref_y)

    def screen_x(self, world_x: float, offset_x: float, y: float) -> float:
        """世界縱線在螢幕高度 y 上的 x。世界 x ＝「參考高度上的螢幕 x」＋鏡位。"""
        rect = world_x - offset_x
        return self.vp_x + (rect - self.vp_x) * self.col_scale(y) / self.col_scale(self.grid_ref_y)

    def world_x(self, x: float, offset_x: float, y: float) -> float:
        return (
            self.vp_x
            + (x - self.vp_x) * self.col_scale(self.grid_ref_y) / self.col_scale(y)
            + offset_x
        )

    def world_y(self, y: float, offset_y: float) -> float:
        """螢幕 y → 世界 y。世界 y 的尺規是參考高度上的螢幕像素（列距在其中為常數）。"""
        span = self.row_scale(self.grid_ref_y) ** 2
        flat = self._row_flat(y) - self._row_flat(self.grid_ref_y)
        return self.grid_ref_y + flat * span + offset_y

    def screen_y(self, world_y: float, offset_y: float) -> float:
        span = self.row_scale(self.grid_ref_y) ** 2
        flat = self._row_flat(self.grid_ref_y) + (world_y - offset_y - self.grid_ref_y) / span
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
