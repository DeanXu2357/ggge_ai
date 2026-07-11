"""Regression harness over curated real-screenshot fixtures (issue #18).

Each tests/fixtures/vision/<category>/<case>.json names a check + the
expected output; the paired .jpg is a crop of a real capture, stored at
source resolution and pasted back onto a blank canvas at its recorded box
so vision.py's hardcoded absolute-coordinate regions still line up.

CLAUDE.md's vision red line ("no threshold change without new screenshot
evidence") is enforced here as a pytest gate: any PR touching those
thresholds must keep this whole file green. A fixture with xfail_reason
set is a pinned, not-yet-fixed bug -- it must stay red until the fix lands,
at which point pytest reports it as XPASS and the marker should come off.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from ggge_ai.battle import vision
from ggge_ai.battle.controller import DISTRACTOR_LABELS, MODE_LABELS, resolve_mode
from ggge_ai.actuation.keyguard import Keyguard
from ggge_ai.vision.manifest import TemplateManifest

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "vision"
TEMPLATE_ROOT = Path(__file__).resolve().parent.parent / "assets" / "templates"
# mirrors the element-stage acceptance gate wired in app.py
ELEMENT_ACCEPT = 0.80


def _check_bool(fn):
    def run(frame: np.ndarray, expect: Any) -> None:
        assert fn(frame) is expect

    return run


def _check_hp_arc_counts(frame: np.ndarray, expect: dict[str, dict[str, int]]) -> None:
    actual = {
        "enemies": len(vision.find_enemy_units(frame)),
        "allies": len(vision.find_ally_units(frame)),
        "third_party": len(vision.find_third_party_units(frame)),
    }
    for key, bounds in expect.items():
        n = actual[key]
        if "min" in bounds:
            assert n >= bounds["min"], f"{key}: got {n}, want >= {bounds['min']} ({actual})"
        if "max" in bounds:
            assert n <= bounds["max"], f"{key}: got {n}, want <= {bounds['max']} ({actual})"


def _check_keyguard_locked(frame: np.ndarray, expect: bool) -> None:
    kg = Keyguard(device=None, capture=lambda: frame)
    assert kg.is_game_locked() is expect


@functools.cache
def _recognizer():
    return TemplateManifest.load(TEMPLATE_ROOT).build_recognizer()


def _check_mode_label(frame: np.ndarray, expect: dict[str, Any]) -> None:
    """The controller's ACTIONABLE probe: labels and distractors above the
    element gate resolved by argmax, exactly as _current_mode() runs it.
    expect: {"id": "label_unit_move"} / {"id": null}."""
    elements = _recognizer().detect_elements(frame, MODE_LABELS + DISTRACTOR_LABELS)
    confidences = {e.id: e.confidence for e in elements if e.confidence >= ELEMENT_ACCEPT}
    mode = resolve_mode(confidences)
    assert mode == expect["id"], f"got {mode} ({confidences}), want {expect['id']}"


CHECKS = {
    "unit_cards_present": _check_bool(vision.unit_cards_present),
    "unit_detail_modal": _check_bool(vision.is_unit_detail_modal),
    "hidden_battle_warning": _check_bool(vision.is_hidden_battle_warning),
    "defeat_screen": _check_bool(vision.is_defeat_screen),
    "dialog_cursor_present": _check_bool(lambda f: vision.locate_dialog_cursor(f) is not None),
    "hp_arc_counts": _check_hp_arc_counts,
    "keyguard_locked": _check_keyguard_locked,
    "mode_label": _check_mode_label,
}


def _load_cases() -> list[tuple[str, Path]]:
    if not FIXTURE_ROOT.exists():
        return []
    cases = []
    for json_path in sorted(FIXTURE_ROOT.rglob("*.json")):
        case_id = str(json_path.relative_to(FIXTURE_ROOT).with_suffix(""))
        cases.append((case_id, json_path))
    return cases


CASES = _load_cases()


def _build_params():
    if not CASES:
        return [pytest.param(None, id="no-fixtures", marks=pytest.mark.skip(reason="fixture corpus empty"))]
    params = []
    for case_id, json_path in CASES:
        annotation = json.loads(json_path.read_text(encoding="utf-8"))
        marks = []
        if annotation.get("xfail_reason"):
            marks.append(pytest.mark.xfail(reason=annotation["xfail_reason"], strict=True))
        params.append(pytest.param(json_path, id=case_id, marks=marks))
    return params


@pytest.mark.parametrize("json_path", _build_params())
def test_vision_fixture(json_path: Path | None) -> None:
    if json_path is None:
        return

    annotation = json.loads(json_path.read_text(encoding="utf-8"))
    img_path = json_path.parent / annotation["image"]
    crop = cv2.imread(str(img_path))
    assert crop is not None, f"cannot read {img_path}"

    canvas_w, canvas_h = annotation["canvas_size"]
    x, y, w, h = annotation["box"]
    canvas = np.zeros((canvas_h, canvas_w, 3), np.uint8)
    canvas[y : y + h, x : x + w] = crop

    check = CHECKS[annotation["check"]]
    check(canvas, annotation["expect"])
