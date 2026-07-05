import cv2
import numpy as np

from ggge_ai.battle import vision

rng = np.random.default_rng(seed=11)


def _template() -> np.ndarray:
    tpl = cv2.imread(str(vision.DIALOG_CURSOR_TEMPLATE))
    assert tpl is not None, "dialog cursor template must exist"
    return tpl


def _frame() -> np.ndarray:
    # a dim, textured background like the battle map under the dialog band
    return rng.integers(0, 70, (1080, 2340, 3), dtype=np.uint8)


def _paste(frame: np.ndarray, tpl: np.ndarray, x: int, y: int) -> None:
    th, tw = tpl.shape[:2]
    frame[y : y + th, x : x + tw] = tpl


def test_detects_cursor_at_line_end():
    tpl = _template()
    th, tw = tpl.shape[:2]
    frame = _frame()
    x, y = 860, 840
    _paste(frame, tpl, x, y)
    hit = vision.locate_dialog_cursor(frame)
    assert hit is not None
    assert abs(hit[0] - (x + tw // 2)) <= 2
    assert abs(hit[1] - (y + th // 2)) <= 2


def test_detects_cursor_near_right_edge():
    # short lines park the cursor far right, past x=1900
    tpl = _template()
    tw = tpl.shape[1]
    frame = _frame()
    x, y = 1990, 843
    _paste(frame, tpl, x, y)
    hit = vision.locate_dialog_cursor(frame)
    assert hit is not None
    assert abs(hit[0] - (x + tw // 2)) <= 2


def test_no_false_positive_on_dialogless_frame():
    frame = _frame()
    assert vision.locate_dialog_cursor(frame) is None
