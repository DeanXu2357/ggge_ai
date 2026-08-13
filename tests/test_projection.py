"""透視投影：合成一組已知單應性的格線，驗預測與殘差往返為零。

假格線由 `Projection` 自己的正向映射生出來——這一支驗的是「世界↔螢幕的往返、線位
列舉、逐線配對」這條鏈自洽，不是驗參數擬合得準不準（那是離線重放
`scripts/validate_projection.py` 的事）。
"""

from __future__ import annotations

import math

import pytest

from ggge_ai.runtime import board, projection
from ggge_ai.runtime.board import Lattice
from ggge_ai.runtime.coverage import WorldGrid

SHAPE = projection.PROJECTION
GRID = WorldGrid(phase=(120.0, 40.0), col_pitch=91.0, row_pitch=85.5)
OFFSET = (-604.0, -399.0)
BAND = (150, 250, 1600, 530)
AT = (1100.0, 560.0)


def synthetic(grid: WorldGrid, offset: projection.Point, band: tuple[int, int, int, int]) -> Lattice:
    """把模型預測的線位當成「實測」——完美對齊的一幀長這樣。"""
    x0, y0, width, height = band
    cols = projection.expected_columns(grid, offset, y0 + height / 2.0, (x0, x0 + width))
    rows = projection.expected_rows(grid, offset, (y0, y0 + height))
    return Lattice(tuple(round(value) for value in cols), tuple(round(value) for value in rows))


def test_the_world_screen_round_trip_returns_the_same_point():
    for y in (260.0, 515.0, 650.0, 940.0):
        world = SHAPE.world_x(830.0, OFFSET[0], y)
        assert SHAPE.screen_x(world, OFFSET[0], y) == pytest.approx(830.0)
    for y in (260.0, 515.0, 650.0, 940.0):
        world = SHAPE.world_y(y, OFFSET[1])
        assert SHAPE.screen_y(world, OFFSET[1]) == pytest.approx(y)


def test_the_world_ruler_is_the_screen_at_one_declared_height():
    """世界座標＝ `world_ref_y` 上的螢幕座標＋鏡位，兩軸同一個高度。"""
    assert SHAPE.col_scale(SHAPE.ref_y) == pytest.approx(1.0)
    assert SHAPE.world_x(700.0, 0.0, SHAPE.world_ref_y) == pytest.approx(700.0)
    assert SHAPE.world_y(SHAPE.world_ref_y, 0.0) == pytest.approx(SHAPE.world_ref_y)
    for y in (300.0, 650.0, 900.0):
        assert SHAPE.world_x(700.0, 0.0, y) == pytest.approx(
            SHAPE.restaged(700.0, y, SHAPE.world_ref_y)
        )


def test_the_anchor_puts_every_band_on_the_same_world_ruler():
    """主帶讀不出來時 `find_lattice` 退四象限窗，帶中線差 110px。不換算的話同一個世界
    在兩個帶上會錨出兩套座標——「一個世界錨定只准一種座標約定」要擋的就是這件事。
    """
    truth = WorldGrid(phase=(1180.0, 620.0), col_pitch=91.65, row_pitch=84.58)
    camera = (-980.0, -370.0)
    main = (150, 250, 1600, 530)
    quadrant = (150, 250, 800, 310)

    anchors = [
        projection.anchor(synthetic(truth, camera, band), band, camera)
        for band in (main, quadrant)
    ]

    assert all(anchor is not None for anchor in anchors)
    for phase, pitch in anchors:
        assert pitch[0] == pytest.approx(truth.col_pitch, abs=0.2)
        assert _lines_up(phase[0], truth.phase[0], truth.col_pitch) == pytest.approx(0.0, abs=1.5)
    # 不換算的話象限窗量到的欄距小 1.2%（帶中線 405 vs 515），17 欄上就累積一格的兩成
    raw = board.fit_lines(synthetic(truth, camera, quadrant).cols)
    assert raw is not None
    assert abs(raw[1] - truth.col_pitch) > 5 * abs(anchors[1][1][0] - truth.col_pitch)


def test_the_anchored_world_reproduces_the_frame_it_was_anchored_on():
    """錨定幀自己要對得上。縱線三個帶都收到 1px 內（帶換算就是為了這件事）。

    列留 6px：世界 y 是**原始螢幕 y**（與界線讀數同一個空間），而模型的世界 y 是攤平
    座標，兩者在相位上差幾個像素。這一項與離線重放量到的絕對列殘差（中位 1.5-3.5px）
    同源，補它要連界線與單位位置一起換空間——見模組說明「還沒補的那道縫」。
    """
    truth = WorldGrid(phase=(1180.0, 620.0), col_pitch=91.65, row_pitch=84.58)
    camera = (-980.0, -370.0)

    for band in ((150, 250, 1600, 530), (150, 250, 800, 310), (950, 560, 800, 310)):
        lattice = synthetic(truth, camera, band)
        anchored = projection.anchor(lattice, band, camera)
        assert anchored is not None
        phase, pitch = anchored
        grid = WorldGrid(phase, pitch[0], pitch[1])
        drift = projection.shadow_drift(lattice, band, grid, camera, at=AT)
        assert drift is not None
        assert drift[0] == pytest.approx(0.0, abs=1.0)
        assert drift[1] == pytest.approx(0.0, abs=6.0)


def _lines_up(value: float, reference: float, pitch: float) -> float:
    """兩個相位差幾個像素（模格距，取進 ±半格）。"""
    return (value - reference + pitch / 2.0) % pitch - pitch / 2.0


def test_an_unreadable_lattice_gives_no_anchor():
    assert projection.anchor(Lattice((), ()), (150, 250, 1600, 530)) is None
    assert projection.anchor(Lattice((100, 200), ()), (150, 250, 1600, 530)) is None


def test_the_screen_pitch_grows_with_screen_y_two_to_one_between_the_axes():
    """列距 ∝ s²、欄距 ∝ s ＝平面投影的簽名（量測報告 §2.3，實測比值 1.98／2.26）。

    模型的 row_k 與 col_k 是各自擬合的，比值 2·row_k/col_k ＝ 2.15 而不是理論的 2.0
    （報告 §5 存疑第 8 條），所以容差開到 ±0.2 而不是釘死 2。
    """
    columns = {
        y: projection.expected_columns(GRID, OFFSET, y, (500, 2280))
        for y in (350.0, 785.0)
    }
    col_ratio = (columns[785.0][1] - columns[785.0][0]) / (columns[350.0][1] - columns[350.0][0])
    top = projection.expected_rows(GRID, OFFSET, (250, 470))
    low = projection.expected_rows(GRID, OFFSET, (690, 910))
    row_ratio = (low[1] - low[0]) / (top[1] - top[0])
    assert col_ratio > 1.0
    assert math.log(row_ratio) / math.log(col_ratio) == pytest.approx(2.0, abs=0.2)


def test_a_frame_that_matches_the_model_has_zero_residual():
    lattice = synthetic(GRID, OFFSET, BAND)

    drift = projection.shadow_drift(lattice, BAND, GRID, OFFSET, at=AT)

    assert drift is not None
    assert drift[0] == pytest.approx(0.0, abs=0.6)
    assert drift[1] == pytest.approx(0.0, abs=0.6)


def test_a_camera_that_moved_shows_up_as_the_move():
    """鏡位記錯了：殘差（實測 − 預測）就該是那個差在評估高度上的像素數。"""
    lattice = synthetic(GRID, OFFSET, BAND)
    stale = (OFFSET[0] + 30.0, OFFSET[1] + 20.0)

    drift = projection.shadow_drift(lattice, BAND, GRID, stale, at=AT)

    assert drift is not None
    assert drift[0] == pytest.approx(
        30.0 * SHAPE.col_scale(AT[1]) / SHAPE.col_scale(SHAPE.world_ref_y), abs=1.0
    )
    assert drift[1] == pytest.approx(20.0, abs=1.5)


def test_the_residual_tolerates_a_missing_line_and_a_spurious_one():
    expected = (100.0, 190.0, 280.0, 370.0)

    missing = projection.line_residual(expected, (102.0, 282.0, 372.0))
    spurious = projection.line_residual(expected, (102.0, 145.0, 192.0, 282.0, 372.0))

    assert missing.median == pytest.approx(2.0)
    assert len(missing.offsets) == 3
    assert spurious.median == pytest.approx(2.0)  # 假脊被中位數擋掉
    assert len(spurious.offsets) == 5


def test_no_lines_on_one_side_is_no_answer_not_a_zero():
    assert projection.line_residual((), (100.0,)).median is None
    assert projection.line_residual((100.0,), ()).median is None
    empty = Lattice((), ())
    assert projection.shadow_drift(empty, BAND, GRID, OFFSET, at=AT) is None


def test_lines_between_stays_inside_the_range():
    lines = projection.lines_between(10.0, 100.0, 95.0, 415.0)

    assert lines == (110.0, 210.0, 310.0, 410.0)
    assert projection.lines_between(10.0, 100.0, 415.0, 95.0) == ()
    assert projection.lines_between(10.0, 0.0, 0.0, 400.0) == ()


def test_the_uniform_model_disagrees_most_at_the_top_and_bottom_of_the_screen():
    """把斜格當垂直線的誤差在螢幕中段最小、頂底最大（量測報告 §3.3）。

    等距模型在每個高度都用同一個欄距，而真正的欄距隨螢幕 y 縮放：同一帶內離消失點
    越遠偏得越多（殘差全距），帶越往上整體偏移也越大（殘差中位）。
    """
    lattice = synthetic(GRID, OFFSET, BAND)
    flat = tuple(
        line - OFFSET[0]
        for line in projection.lines_between(
            GRID.phase[0], GRID.col_pitch, 150 + OFFSET[0], 1750 + OFFSET[0]
        )
    )
    middle = projection.line_residual(flat, lattice.cols)

    top_band = (150, 250, 1600, 200)
    top = projection.line_residual(
        flat, synthetic(GRID, OFFSET, top_band).cols
    )

    assert _spread(top.offsets) > _spread(middle.offsets)
    assert abs(top.median) > abs(middle.median)


def _spread(offsets: tuple[float, ...]) -> float:
    return max(offsets) - min(offsets)
