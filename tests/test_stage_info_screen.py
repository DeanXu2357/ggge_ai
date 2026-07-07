"""stage_info loading-screen anchor: it must classify the pre-battle
conditions screen (previously mis-scored as low-confidence battle_map, hence
translated to `unknown` and skipped) without stealing any other screen."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from ggge_ai.vision.manifest import TemplateManifest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "assets" / "templates"
# gitignored full-frame captures; the real-frame checks skip when they are gone
STAGE_INFO_SAMPLE = ROOT / "assets" / "run-shots" / "20260706-233220-805.png"
HUB_SAMPLE = ROOT / "assets" / "screenshots" / "20260706-233847.png"
# crop origin the anchor template was built from (勝利條件 heading)
ANCHOR_ORIGIN = (375, 328)


def _recognizer():
    return TemplateManifest.load(TEMPLATES).build_recognizer()


def _paste_anchor(canvas: np.ndarray) -> np.ndarray:
    entry = TemplateManifest.load(TEMPLATES).screens["stage_info"]
    tmpl = cv2.imread(str(TEMPLATES / entry.file))
    x, y = ANCHOR_ORIGIN
    canvas[y : y + tmpl.shape[0], x : x + tmpl.shape[1]] = tmpl
    return canvas


def test_stage_info_anchor_registered():
    man = TemplateManifest.load(TEMPLATES)
    assert "stage_info" in man.screens
    assert man.screens["stage_info"].file == "screens/stage_info.png"


def test_pasted_anchor_classifies_as_stage_info():
    frame = _paste_anchor(np.zeros((1080, 2340, 3), np.uint8))
    top = _recognizer().classify_screen(frame)[0]
    assert top.screen == "stage_info"
    assert top.confidence > 0.9


def test_blank_frame_is_not_stage_info():
    top = _recognizer().classify_screen(np.zeros((1080, 2340, 3), np.uint8))[0]
    assert not (top.screen == "stage_info" and top.confidence > 0.9)


@pytest.mark.skipif(not STAGE_INFO_SAMPLE.exists(), reason="gitignored sample absent")
def test_real_stage_info_frame_classifies():
    frame = cv2.imread(str(STAGE_INFO_SAMPLE))
    top = _recognizer().classify_screen(frame)[0]
    assert top.screen == "stage_info"
    assert top.confidence > 0.9


@pytest.mark.skipif(not HUB_SAMPLE.exists(), reason="gitignored sample absent")
def test_real_hub_frame_stays_battle_map():
    # the new anchor must not steal the our-turn hub
    frame = cv2.imread(str(HUB_SAMPLE))
    top = _recognizer().classify_screen(frame)[0]
    assert top.screen == "battle_map"
