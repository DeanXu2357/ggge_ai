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

from ggge_ai.battle import panels, vision
from ggge_ai.battle.controller import DISTRACTOR_LABELS, MODE_LABELS, resolve_mode
from ggge_ai.actuation.keyguard import Keyguard
from ggge_ai.vision import digits
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


def _check_unit_card_count(frame: np.ndarray, expect: dict[str, int]) -> None:
    actual = vision.count_unit_cards(frame)
    assert actual == expect["count"], f"got {actual}, want {expect['count']}"


def _check_observer_board(frame: np.ndarray, expect: dict) -> None:
    """End-to-end observer case on a real screenshot: arc scan feeds
    build_battle_state with the annotated priors (tracker ally beliefs,
    intel sig positions), and the resolved board must match the bounds.
    Screen coordinates double as world coordinates (zero camera offset)."""
    from ggge_ai.battle.observe import build_battle_state
    from ggge_ai.battle.state import Faction
    from ggge_ai.battle.tacmap import TacticalMap

    tacmap = TacticalMap()
    tacmap.allies.extend(vision.find_ally_units(frame))
    tacmap.enemies.extend(vision.find_enemy_units(frame))
    tacmap.third_party.extend(vision.find_third_party_units(frame))
    inputs = expect["inputs"]
    battle = build_battle_state(
        tacmap,
        sig_positions={k: tuple(v) for k, v in inputs.get("sig_positions", {}).items()},
        ally_sig_positions={
            k: tuple(v) for k, v in inputs.get("ally_sig_positions", {}).items()
        },
        hub_poisoned=inputs.get("hub_poisoned", True),
    )
    actual = {
        "allies": len(battle.allies()),
        "enemies": len(battle.enemies()),
        "third_party": len(battle.by_faction(Faction.THIRD_PARTY)),
    }
    for key, bounds in expect["board"].items():
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


def _check_kill_counter(frame: np.ndarray, expect: dict[str, Any]) -> None:
    got = vision.read_kill_counter(frame)
    want = tuple(expect["value"]) if expect["value"] is not None else None
    assert got == want, f"got {got}, want {want}"


def _forecast_check(fn):
    """Reader checks compare only the keys the fixture pins, so a fixture
    can assert the fields its crop covers without freezing the whole
    dataclass shape. expect=null pins that the reader must decline."""

    def run(frame: np.ndarray, expect: dict[str, Any] | None) -> None:
        got = fn(frame)
        if expect is None:
            assert got is None, f"expected no reading, got {got}"
            return
        assert got is not None, "reader returned None on its own screen"
        for key, want in expect.items():
            actual = getattr(got, key)
            assert actual == want, f"{key}: got {actual!r}, want {want!r} ({got})"

    return run


def _check_weapon_rows(frame: np.ndarray, expect: list[dict[str, Any]]) -> None:
    got = panels.parse_weapon_rows(frame)
    assert len(got) == len(expect), f"got {len(got)} rows, want {len(expect)}: {got}"
    for i, (row, want) in enumerate(zip(got, expect)):
        for key, value in want.items():
            actual = getattr(row, key)
            assert actual == value, f"row {i} {key}: got {actual!r}, want {value!r}"


def _check_digit_read(frame: np.ndarray, expect: dict[str, Any]) -> None:
    """Template-digit OCR over a HUD region. expect:
    {"region": [x,y,w,h], "digit_height": 30, "kind": "number|fraction|percent|text",
     "value": ..., "invert"?: bool, "allow_minus"?: bool}. kind=fraction expects
    a [k, m] pair; a null value pins that the region must NOT read (the
    reader never guesses)."""
    region = tuple(expect["region"])
    kwargs: dict[str, Any] = {"digit_height": expect["digit_height"]}
    if "invert" in expect:
        kwargs["invert"] = expect["invert"]
    kind = expect["kind"]
    if kind == "number":
        if "allow_minus" in expect:
            kwargs["allow_minus"] = expect["allow_minus"]
        actual: Any = digits.read_number(frame, region, **kwargs)
    elif kind == "fraction":
        pair = digits.read_fraction(frame, region, **kwargs)
        actual = list(pair) if pair is not None else None
    elif kind == "percent":
        actual = digits.read_percent(frame, region, **kwargs)
    else:
        if "allow_minus" in expect:
            kwargs["allow_minus"] = expect["allow_minus"]
        actual = digits.read_text(frame, region, **kwargs).text
    assert actual == expect["value"], f"got {actual!r}, want {expect['value']!r}"


CHECKS = {
    "unit_cards_present": _check_bool(vision.unit_cards_present),
    "unit_detail_modal": _check_bool(vision.is_unit_detail_modal),
    "hidden_battle_warning": _check_bool(vision.is_hidden_battle_warning),
    "defeat_screen": _check_bool(vision.is_defeat_screen),
    "dialog_cursor_present": _check_bool(lambda f: vision.locate_dialog_cursor(f) is not None),
    "hp_arc_counts": _check_hp_arc_counts,
    "unit_card_count": _check_unit_card_count,
    "observer_board": _check_observer_board,
    "keyguard_locked": _check_keyguard_locked,
    "mode_label": _check_mode_label,
    "digit_read": _check_digit_read,
    "kill_counter": _check_kill_counter,
    "weapon_select_forecast": _forecast_check(vision.read_weapon_select_forecast),
    "battle_prep_forecast": _forecast_check(vision.read_battle_prep_forecast),
    "enemy_summary": _forecast_check(vision.read_enemy_summary),
    "unit_stats": _forecast_check(panels.parse_unit_stats),
    "weapon_rows": _check_weapon_rows,
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

    for extra in annotation.get("extra_crops", []):
        extra_img = cv2.imread(str(json_path.parent / extra["image"]))
        assert extra_img is not None, f"cannot read extra crop {extra['image']}"
        ex, ey, ew, eh = extra["box"]
        canvas[ey : ey + eh, ex : ex + ew] = extra_img

    check = CHECKS[annotation["check"]]
    check(canvas, annotation["expect"])
