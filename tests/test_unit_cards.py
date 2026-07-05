import cv2
import numpy as np

from ggge_ai.battle import vision

rng = np.random.default_rng(seed=5)


def _frame() -> np.ndarray:
    """A dim battle frame whose value channel stays below the bright gate."""
    hsv = np.zeros((1080, 2340, 3), np.uint8)
    hsv[..., 2] = rng.integers(0, 100, (1080, 2340), dtype=np.uint8)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def _card(frame: np.ndarray, x: int) -> None:
    """Paste one bright card block into the strip. Height 60 over the 200px
    strip mirrors a real card: ~0.30 bright fraction inside its own window
    but only ~0.06 averaged over the whole strip (the old metric's blind
    spot)."""
    bx, by = vision.UNIT_CARD_STRIP_BOX[0] + x, vision.UNIT_CARD_STRIP_BOX[1]
    frame[by : by + 60, bx : bx + vision.UNIT_CARD_WINDOW] = (255, 255, 255)


def _global_bright_mean(frame: np.ndarray) -> float:
    x, y, w, h = vision.UNIT_CARD_STRIP_BOX
    hsv = cv2.cvtColor(frame[y : y + h, x : x + w], cv2.COLOR_BGR2HSV)
    return float((hsv[..., 2] > 140).mean())


def test_single_card_present():
    frame = _frame()
    _card(frame, 40)
    # the lone card that broke the old whole-strip mean gate (< 0.08)
    assert _global_bright_mean(frame) < 0.08
    assert vision.unit_cards_present(frame) is True


def test_multiple_cards_present():
    frame = _frame()
    for x in (40, 240, 440, 640):
        _card(frame, x)
    assert vision.unit_cards_present(frame) is True


def test_empty_strip_absent():
    assert vision.unit_cards_present(_frame()) is False
