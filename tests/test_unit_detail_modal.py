"""unit_detail_modal detection and its effect on unit_cards_present.

A stray keyguard drag onto a map unit opened the 單位設置詳情 modal on top of
the live battle; unit_cards_present false-reported True on its bright panel,
and nothing dismissed it. Detection must fire on the modal and suppress the
card gate, while leaving a real our-turn hub reporting cards."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from ggge_ai.battle import vision

ROOT = Path(__file__).resolve().parents[1]
MODAL_TMPL = ROOT / "assets" / "templates" / "elements" / "unit_detail_modal.png"
# crop origin the modal template was built from (單位設置詳情 title)
MODAL_ORIGIN = (1050, 72)
MODAL_SAMPLES = [
    ROOT / "assets" / "screenshots" / f"20260706-{s}.png"
    for s in ("233709", "233754", "233821", "235115")
]
HUB_SAMPLE = ROOT / "assets" / "screenshots" / "20260706-233847.png"


def _paste_modal(canvas: np.ndarray) -> np.ndarray:
    tmpl = cv2.imread(str(MODAL_TMPL))
    x, y = MODAL_ORIGIN
    canvas[y : y + tmpl.shape[0], x : x + tmpl.shape[1]] = tmpl
    return canvas


def test_modal_detected_on_pasted_title():
    frame = _paste_modal(np.zeros((1080, 2340, 3), np.uint8))
    assert vision.is_unit_detail_modal(frame) is True


def test_no_modal_on_blank_frame():
    assert vision.is_unit_detail_modal(np.zeros((1080, 2340, 3), np.uint8)) is False


def test_unit_cards_present_false_on_modal():
    # a fully bright canvas would trip the brightness gate to True on its own;
    # the modal guard must override that to False
    frame = _paste_modal(np.full((1080, 2340, 3), 255, np.uint8))
    assert vision.unit_cards_present(frame) is False


@pytest.mark.skipif(not all(p.exists() for p in MODAL_SAMPLES), reason="samples absent")
def test_real_modals_detected_and_reject_cards():
    for p in MODAL_SAMPLES:
        frame = cv2.imread(str(p))
        assert vision.is_unit_detail_modal(frame) is True, p.name
        assert vision.unit_cards_present(frame) is False, p.name


@pytest.mark.skipif(not HUB_SAMPLE.exists(), reason="sample absent")
def test_real_hub_has_cards_and_no_modal():
    frame = cv2.imread(str(HUB_SAMPLE))
    assert vision.is_unit_detail_modal(frame) is False
    assert vision.unit_cards_present(frame) is True
