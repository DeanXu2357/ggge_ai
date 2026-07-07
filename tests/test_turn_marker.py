"""On-screen TURN-number change detection: a stalled modal used to inflate the
internal turn counter past the on-screen TURN. next_turn is now gated on the
marker actually changing between hub frames."""

import numpy as np

from ggge_ai.battle import vision


def _digit(pattern: str) -> np.ndarray:
    h, w = vision.TURN_MARKER_REGION[3], vision.TURN_MARKER_REGION[2]
    a = np.zeros((h, w), np.uint8)
    if pattern == "one":
        a[8:28, 18:23] = 255
    elif pattern == "block":
        a[4:32, 4:36] = 255
    return a


def test_same_marker_is_not_changed():
    a = _digit("one")
    assert vision.turn_marker_changed(a, a.copy()) is False


def test_different_marker_is_changed():
    assert vision.turn_marker_changed(_digit("one"), _digit("block")) is True


def test_missing_prior_marker_counts_as_changed():
    assert vision.turn_marker_changed(None, _digit("one")) is True


def test_shape_mismatch_counts_as_changed():
    assert vision.turn_marker_changed(_digit("one"), np.zeros((10, 10), np.uint8)) is True


def test_crop_turn_marker_matches_region_shape():
    frame = np.zeros((1080, 2340, 3), np.uint8)
    x, y, w, h = vision.TURN_MARKER_REGION
    marker = vision.crop_turn_marker(frame)
    assert marker.shape == (h, w)
