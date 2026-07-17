"""Semantic contract of the M2 game-forecast readers.

Accuracy on real captures is pinned by tests/fixtures/vision/forecast/;
these tests cover reader semantics that need no screenshots: declining on
frames without the screen anchor, and name-signature behavior.
"""

from __future__ import annotations

import cv2
import numpy as np

from ggge_ai.battle import vision
from ggge_ai.content.stage_def import signature_distance


def _blank_frame() -> np.ndarray:
    return np.zeros((1080, 2340, 3), np.uint8)


def _text_frame(text: str, origin: tuple[int, int] = (600, 160)) -> np.ndarray:
    frame = _blank_frame()
    cv2.putText(frame, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    return frame


def test_readers_decline_without_anchor() -> None:
    frame = _blank_frame()
    assert vision.read_weapon_select_forecast(frame) is None
    assert vision.read_battle_prep_forecast(frame) is None
    assert vision.read_enemy_summary(frame) is None
    assert vision.read_kill_counter(frame) is None
    assert vision.is_battle_prep_reaction(frame) is False


def test_signature_distance_semantics() -> None:
    sig = vision.name_signature(_text_frame("GUNDAM"), vision.FORECAST_LEFT_NAME_REGION)
    assert sig is not None
    assert signature_distance(sig, sig) == 0
    assert signature_distance(None, sig) == 64
    assert signature_distance(sig, None) == 64
    assert signature_distance(None, None) == 64


def test_signature_is_shift_invariant_and_discriminative() -> None:
    base = vision.name_signature(_text_frame("GUNDAM"), vision.FORECAST_LEFT_NAME_REGION)
    shifted = vision.name_signature(
        _text_frame("GUNDAM", origin=(604, 157)), vision.FORECAST_LEFT_NAME_REGION
    )
    other = vision.name_signature(_text_frame("ZAKU II"), vision.FORECAST_LEFT_NAME_REGION)
    assert signature_distance(base, shifted) <= 4
    assert signature_distance(base, other) > 10


def test_signature_none_on_empty_band() -> None:
    assert vision.name_signature(_blank_frame(), vision.FORECAST_LEFT_NAME_REGION) is None
