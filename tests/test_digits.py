"""Semantic contract of vision/digits.py.

Accuracy on real captures is pinned by tests/fixtures/vision/digits/
(test_vision_regression.py, check "digit_read"); these tests cover the
API semantics on synthetic bands composed from the glyph templates
themselves, which match at score 1.0 by construction.
"""

from __future__ import annotations

import cv2
import numpy as np

from ggge_ai.vision import digits

BACKGROUND = 40


def _glyph_image(name: str) -> np.ndarray:
    img = cv2.imread(str(digits.TEMPLATE_ROOT / "hud" / f"{name}.png"), cv2.IMREAD_GRAYSCALE)
    assert img is not None, name
    return img


def _compose(names: list[str], gaps: list[int] | None = None) -> np.ndarray:
    images = [_glyph_image(n) for n in names]
    gaps = gaps if gaps is not None else [8] * (len(images) - 1)
    h = digits.CANON_H + 16
    w = sum(i.shape[1] for i in images) + sum(gaps) + 16
    canvas = np.full((h, w), BACKGROUND, np.uint8)
    x = 8
    for i, img in enumerate(images):
        y = (h - img.shape[0]) // 2
        canvas[y : y + img.shape[0], x : x + img.shape[1]] = img
        x += img.shape[1] + (gaps[i] if i < len(gaps) else 0)
    return cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)


def _full_region(frame: np.ndarray) -> tuple[int, int, int, int]:
    return (0, 0, frame.shape[1], frame.shape[0])


def test_empty_region_reads_nothing() -> None:
    frame = np.zeros((100, 100, 3), np.uint8)
    reading = digits.read_text(frame, (50, 50, 0, 0), digit_height=30)
    assert reading.text == ""
    assert reading.value is None
    assert reading.glyphs == []


def test_blank_frame_never_guesses() -> None:
    frame = np.zeros((120, 400, 3), np.uint8)
    region = _full_region(frame)
    assert digits.read_number(frame, region, digit_height=30) is None
    assert digits.read_fraction(frame, region, digit_height=30) is None
    assert digits.read_percent(frame, region, digit_height=30) is None


def test_reads_composed_number() -> None:
    frame = _compose(["4", "2"])
    assert digits.read_number(frame, _full_region(frame), digit_height=digits.CANON_H) == 42


def test_allow_minus_semantics() -> None:
    frame = _compose(["minus", "4", "2"])
    region = _full_region(frame)
    assert digits.read_number(frame, region, digit_height=digits.CANON_H) == -42
    assert (
        digits.read_number(frame, region, digit_height=digits.CANON_H, allow_minus=False) == 42
    )


def test_interior_minus_is_dropped() -> None:
    frame = _compose(["4", "minus", "2"])
    reading = digits.read_text(frame, _full_region(frame), digit_height=digits.CANON_H)
    assert reading.text == "42"
    assert reading.value == 42


def test_percent_requires_trailing_glyph() -> None:
    bare = _compose(["6", "2"])
    assert digits.read_percent(bare, _full_region(bare), digit_height=digits.CANON_H) is None
    suffixed = _compose(["6", "2", "percent_s"])
    assert (
        digits.read_percent(suffixed, _full_region(suffixed), digit_height=digits.CANON_H) == 62
    )


def test_distant_stray_glyph_is_dropped() -> None:
    frame = _compose(["4", "2", "7"], gaps=[8, 60])
    reading = digits.read_text(frame, _full_region(frame), digit_height=digits.CANON_H)
    assert reading.text == "42"


def test_fraction_requires_slash() -> None:
    bare = _compose(["4", "2"])
    assert digits.read_fraction(bare, _full_region(bare), digit_height=digits.CANON_H) is None
    pair = _compose(["8", "slash_s", "1", "0"])
    assert digits.read_fraction(pair, _full_region(pair), digit_height=digits.CANON_H) == (8, 10)
