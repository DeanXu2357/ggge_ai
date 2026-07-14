"""count_unit_cards: synthetic strips pin the algorithm gates that the
PNG fixtures cannot cover (damaged short bars, sub-floor slivers, banner
rejection, off-band blue). Real-frame behavior is pinned by the
tests/fixtures/vision/unit_cards/ regression cases."""

import numpy as np

from ggge_ai.battle import vision

BLUE = (255, 0, 0)
BAR_TOP = 993
BAR_BOTTOM = 1006


def _strip_canvas():
    return np.zeros((1080, 2340, 3), np.uint8)


def _bar(canvas, x, width, y0=BAR_TOP, y1=BAR_BOTTOM):
    canvas[y0:y1, x : x + width] = BLUE


def test_counts_full_and_damaged_bars():
    canvas = _strip_canvas()
    for i, width in enumerate([154, 154, 154, 92, 18]):
        _bar(canvas, 221 + i * 175, width)
    assert vision.count_unit_cards(canvas) == 5


def test_sub_floor_sliver_is_not_counted():
    canvas = _strip_canvas()
    _bar(canvas, 221, 154)
    _bar(canvas, 396, 8)
    assert vision.count_unit_cards(canvas) == 1


def test_full_width_banner_is_rejected():
    canvas = _strip_canvas()
    _bar(canvas, 221, 1400)
    assert vision.count_unit_cards(canvas) == 0


def test_blue_outside_bar_row_band_is_rejected():
    canvas = _strip_canvas()
    _bar(canvas, 221, 154, y0=870, y1=883)
    assert vision.count_unit_cards(canvas) == 0


def test_empty_strip_counts_zero():
    assert vision.count_unit_cards(_strip_canvas()) == 0
