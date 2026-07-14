"""Enemy-intel acquisition flow, driven by the real capture sequence the
20260705 corpus recorded (tap enemy -> summary card -> detail modal), with
frames reconstructed from the committed fixtures so every read runs the
production recognition path."""

from pathlib import Path

import cv2
import numpy as np

from ggge_ai.battle import scout_intel, stage_cache, vision
from ggge_ai.battle.scout_intel import (
    IntelBudget,
    RefreshBudget,
    acquire_stage_intel,
    refresh_sig_positions,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "vision"


def _canvas(rel: str, box: tuple[int, int, int, int]) -> np.ndarray:
    crop = cv2.imread(str(FIXTURES / rel))
    assert crop is not None, rel
    canvas = np.zeros((1080, 2340, 3), np.uint8)
    x, y, w, h = box
    canvas[y : y + h, x : x + w] = crop
    return canvas


HUB = _canvas("forecast/hub_summary_top.png", (0, 0, 2340, 300))
MODAL = _canvas("panels/weapons_tab.png", (250, 40, 1840, 980))
SIG = vision.read_enemy_summary(HUB).name_sig


class _Script:
    """capture() returns the scripted frames in order; taps are recorded."""

    def __init__(self, frames):
        self.frames = list(frames)
        self.taps = []

    def capture(self):
        return self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]

    def tap(self, x, y):
        self.taps.append((x, y))


def _events():
    events = []

    def log(kind, **data):
        data.pop("frame", None)
        events.append({"kind": kind, **data})

    return events, log


def test_cold_cache_opens_panel_and_writes_cache(tmp_path):
    script = _Script([HUB, MODAL, MODAL, HUB])
    events, log = _events()
    intel = acquire_stage_intel(
        script.capture,
        script.tap,
        [(900, 150)],
        stage_id="g/hard_1",
        cache_root=tmp_path,
        ledger_log=log,
        sleep=lambda s: None,
    )
    assert intel.panels_opened == 1
    assert intel.cache_hits == 0
    assert not intel.cache_stale
    spec = intel.specs_by_sig[SIG]
    assert spec.max_hp == 51349
    assert len(spec.weapons) == 2
    assert intel.summaries[SIG].hp == 51349
    assert scout_intel.SUMMARY_CARD_TAP in script.taps
    assert scout_intel.UNIT_DETAIL_CLOSE in script.taps
    cached = stage_cache.load_stage("g/hard_1", root=tmp_path)
    assert SIG in cached
    assert any(e["kind"] == "unit_intel" and e["source"] == "panel" for e in events)


def test_warm_cache_skips_the_panel(tmp_path):
    script = _Script([HUB, MODAL, MODAL, HUB])
    acquire_stage_intel(
        script.capture,
        script.tap,
        [(900, 150)],
        stage_id="g/hard_1",
        cache_root=tmp_path,
        sleep=lambda s: None,
    )
    warm = _Script([HUB])
    events, log = _events()
    intel = acquire_stage_intel(
        warm.capture,
        warm.tap,
        [(900, 150)],
        stage_id="g/hard_1",
        cache_root=tmp_path,
        ledger_log=log,
        sleep=lambda s: None,
    )
    assert intel.cache_hits == 1
    assert intel.panels_opened == 0
    assert intel.specs_by_sig[SIG].max_hp == 51349
    assert scout_intel.SUMMARY_CARD_TAP not in warm.taps
    assert any(e["kind"] == "unit_intel" and e["source"] == "cache" for e in events)


def test_unknown_sig_marks_cache_stale_and_rereads(tmp_path):
    stage_cache.save_stage(
        "g/hard_1",
        {"f" * 16: stage_cache.CachedUnit(sig="f" * 16, stats={}, weapons=[])},
        root=tmp_path,
    )
    script = _Script([HUB, MODAL, MODAL, HUB])
    events, log = _events()
    intel = acquire_stage_intel(
        script.capture,
        script.tap,
        [(900, 150)],
        stage_id="g/hard_1",
        cache_root=tmp_path,
        ledger_log=log,
        sleep=lambda s: None,
    )
    assert intel.cache_stale
    assert any(e["kind"] == "cache_stale" for e in events)
    assert intel.specs_by_sig[SIG].max_hp == 51349
    assert SIG in stage_cache.load_stage("g/hard_1", root=tmp_path)


def test_panel_budget_leaves_units_specless(tmp_path):
    script = _Script([HUB])
    intel = acquire_stage_intel(
        script.capture,
        script.tap,
        [(900, 150)],
        stage_id="g/hard_1",
        cache_root=tmp_path,
        budget=IntelBudget(max_panels=0),
        sleep=lambda s: None,
    )
    assert intel.panels_opened == 0
    assert intel.specs_by_sig == {}
    assert SIG in intel.summaries


def test_same_unit_tapped_twice_reads_once():
    script = _Script([HUB, MODAL, MODAL, HUB, HUB])
    intel = acquire_stage_intel(
        script.capture,
        script.tap,
        [(900, 150), (905, 152)],
        sleep=lambda s: None,
    )
    assert intel.panels_opened == 1
    assert len(intel.summaries) == 1


def test_phantom_tap_without_card_is_skipped():
    blank = np.zeros((1080, 2340, 3), np.uint8)
    script = _Script([blank])
    intel = acquire_stage_intel(
        script.capture,
        script.tap,
        [(900, 150)],
        sleep=lambda s: None,
    )
    assert intel.summaries == {}
    assert intel.panels_opened == 0


def test_refresh_unambiguous_match_taps_nothing():
    script = _Script([HUB])
    refresh = refresh_sig_positions(
        script.capture,
        script.tap,
        [(900.0, 150.0), (400.0, 600.0)],
        {"a" * 16: (890.0, 140.0), "b" * 16: (390.0, 590.0)},
        sleep=lambda s: None,
    )
    assert script.taps == []
    assert refresh.positions == {"a" * 16: (900.0, 150.0), "b" * 16: (400.0, 600.0)}
    assert refresh.matched_quietly == 2
    assert refresh.unresolved == []


def test_refresh_contested_candidates_get_tapped_nearest_first():
    script = _Script([HUB])
    events, log = _events()
    refresh = refresh_sig_positions(
        script.capture,
        script.tap,
        [(900.0, 150.0), (1000.0, 150.0)],
        {SIG: (920.0, 150.0)},
        ledger_log=log,
        sleep=lambda s: None,
    )
    assert script.taps == [(900, 150)]
    assert refresh.positions[SIG] == (900.0, 150.0)
    assert refresh.taps == 1
    assert any(e["kind"] == "sig_refresh" and e["result"] == "ok" for e in events)


def test_refresh_phantom_and_stale_reads_do_not_update():
    blank = np.zeros((1080, 2340, 3), np.uint8)
    script = _Script([blank, HUB, HUB])
    other = "f" * 16
    events, log = _events()
    refresh = refresh_sig_positions(
        script.capture,
        script.tap,
        [(900.0, 150.0), (1000.0, 150.0), (1100.0, 150.0)],
        {SIG: (950.0, 150.0), other: (1050.0, 150.0)},
        ledger_log=log,
        sleep=lambda s: None,
    )
    assert refresh.taps == 3
    assert refresh.positions == {SIG: (1000.0, 150.0)}
    assert refresh.unresolved == [other]
    results = [e["result"] for e in events if e["kind"] == "sig_refresh"]
    assert results == ["no_card", "ok", "stale_card"]


def test_refresh_canonicalizes_jittered_card_sigs():
    script = _Script([HUB])
    jittered = hex(int(SIG, 16) ^ 0b101)[2:].zfill(len(SIG))
    refresh = refresh_sig_positions(
        script.capture,
        script.tap,
        [(900.0, 150.0), (1000.0, 150.0)],
        {jittered: (920.0, 150.0)},
        sleep=lambda s: None,
    )
    assert refresh.positions == {jittered: (900.0, 150.0)}
    assert refresh.unresolved == []


def test_refresh_tap_budget_is_honored():
    blank = np.zeros((1080, 2340, 3), np.uint8)
    script = _Script([blank])
    refresh = refresh_sig_positions(
        script.capture,
        script.tap,
        [(900.0, 150.0), (1000.0, 150.0), (1100.0, 150.0)],
        {SIG: (1000.0, 150.0)},
        budget=RefreshBudget(max_taps=1),
        sleep=lambda s: None,
    )
    assert refresh.taps == 1
    assert refresh.unresolved == [SIG]
