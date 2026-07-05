import cv2
import numpy as np

from ggge_ai.battle import vision

rng = np.random.default_rng(seed=13)


def _template() -> np.ndarray:
    tpl = cv2.imread(str(vision.DEFEAT_SCREEN_TEMPLATE))
    assert tpl is not None, "defeat screen template must exist"
    return tpl


def _frame() -> np.ndarray:
    """A dim, textured frame like the battle map with no FAILED banner."""
    return rng.integers(0, 70, (1080, 2340, 3), dtype=np.uint8)


def test_detects_failed_banner():
    tpl = _template()
    th, tw = tpl.shape[:2]
    frame = _frame()
    # the banner was cropped at original (1020, 40)
    frame[40 : 40 + th, 1020 : 1020 + tw] = tpl
    assert vision.is_defeat_screen(frame) is True


def test_no_false_positive_without_banner():
    assert vision.is_defeat_screen(_frame()) is False
