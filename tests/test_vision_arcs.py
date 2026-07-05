import cv2
import numpy as np

from ggge_ai.battle import vision

rng = np.random.default_rng(seed=3)


def _frame() -> np.ndarray:
    """A dim, low-saturation battle-map background in BGR."""
    hsv = np.zeros((1080, 2340, 3), np.uint8)
    hsv[..., 0] = rng.integers(30, 90, (1080, 2340), dtype=np.uint8)
    hsv[..., 1] = rng.integers(0, 40, (1080, 2340), dtype=np.uint8)
    hsv[..., 2] = rng.integers(0, 60, (1080, 2340), dtype=np.uint8)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def _arc(frame: np.ndarray, cx: int, cy: int, hue: int, start: int = 20, end: int = 160) -> None:
    """Paste an HP arc as a thin curved bottom stroke like the game's."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    cv2.ellipse(hsv, (cx, cy), (55, 20), 0, start, end, (int(hue), 180, 205), 10)
    frame[:] = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def _body(frame: np.ndarray, cx: int, cy: int, hue: int) -> None:
    """A filled blob of body paint: same color, wrong shape."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    cv2.rectangle(hsv, (cx - 30, cy - 30), (cx + 30, cy + 30), (int(hue), 180, 200), -1)
    frame[:] = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def test_enemy_red_arc_detected():
    frame = _frame()
    _arc(frame, 900, 500, hue=5)
    hits = vision.find_enemy_units(frame)
    assert len(hits) == 1
    assert abs(hits[0][0] - 900) < 60


def test_ally_arc_not_seen_as_enemy():
    frame = _frame()
    _arc(frame, 900, 500, hue=112)
    assert vision.find_enemy_units(frame) == []
    assert len(vision.find_ally_units(frame)) == 1


def test_shared_orange_segment_alone_is_not_enemy():
    # every faction's arc carries the orange half; on its own it must not
    # register as red or the whole map fills with phantom enemies
    frame = _frame()
    _arc(frame, 900, 500, hue=14)
    assert vision.find_enemy_units(frame) == []


def test_red_body_paint_not_seen_as_arc():
    frame = _frame()
    _body(frame, 900, 500, hue=5)
    assert vision.find_enemy_units(frame) == []
