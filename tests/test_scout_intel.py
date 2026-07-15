"""Stage survey / validation (S6 fail-loud) and the per-turn sig
refresh, driven by the real capture sequence the 20260705 corpus
recorded (tap enemy -> summary card -> detail modal), with frames
reconstructed from the committed fixtures so every read runs the
production recognition path."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from ggge_ai.battle import scout_intel, stage_def, vision
from ggge_ai.battle.scout_intel import (
    RefreshBudget,
    SurveyIncomplete,
    refresh_sig_positions,
    survey_stage,
    validate_stage,
)
from ggge_ai.battle.stage_def import StageDefinition, StageUnit, assign_uids

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
SUMMARY_EN = vision.read_enemy_summary(HUB).en


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


def _identity_view(world):
    return world


def test_survey_reads_every_unit_and_writes_the_definition(tmp_path):
    script = _Script([HUB, MODAL, MODAL, HUB, MODAL, MODAL, HUB])
    events, log = _events()
    defn = survey_stage(
        script.capture,
        script.tap,
        [(900.0, 150.0), (1185.0, 625.0)],
        stage_id="g/hard_2",
        bring_to_view=_identity_view,
        ledger_log=log,
        sleep=lambda s: None,
        root=tmp_path,
    )
    assert [u.uid for u in defn.layout] == ["e01", "e02"]
    assert all(u.sig == SIG for u in defn.layout)
    assert defn.layout[0].stats["hp"] == 51349
    assert len(defn.layout[0].weapons) == 2
    assert defn.layout[0].pilot_hint
    # same machine sig twice, and still one panel per unit -- no dedup
    assert script.taps.count(scout_intel.SUMMARY_CARD_TAP) == 2
    by_cell = {u.cell: u.uid for u in defn.layout}
    assert by_cell[(0, 0)] == "e01"
    assert by_cell[(3, 5)] == "e02"
    saved = stage_def.load_stage_def("g/hard_2", root=tmp_path)
    assert saved is not None and saved.status == "complete"
    assert any(e["kind"] == "survey_complete" for e in events)


def test_survey_missing_card_raises_and_writes_nothing(tmp_path):
    blank = np.zeros((1080, 2340, 3), np.uint8)
    script = _Script([blank])
    with pytest.raises(SurveyIncomplete):
        survey_stage(
            script.capture,
            script.tap,
            [(900.0, 150.0)],
            stage_id="g/hard_2",
            bring_to_view=_identity_view,
            sleep=lambda s: None,
            root=tmp_path,
        )
    assert stage_def.load_stage_def("g/hard_2", root=tmp_path) is None


def test_survey_wall_clock_guard_raises(tmp_path):
    script = _Script([HUB])
    with pytest.raises(SurveyIncomplete):
        survey_stage(
            script.capture,
            script.tap,
            [(900.0, 150.0)],
            stage_id="g/hard_2",
            bring_to_view=_identity_view,
            sleep=lambda s: None,
            wall_clock_s=0.0,
            root=tmp_path,
        )


def test_survey_unreachable_point_raises(tmp_path):
    script = _Script([HUB])
    with pytest.raises(SurveyIncomplete):
        survey_stage(
            script.capture,
            script.tap,
            [(900.0, 150.0)],
            stage_id="g/hard_2",
            bring_to_view=lambda world: None,
            sleep=lambda s: None,
            root=tmp_path,
        )


def _defn_for_validation(hp=51349, en=None):
    stats = {"hp": hp}
    if en is not None:
        stats["en"] = en
    layout = assign_uids(
        [
            StageUnit(uid="", cell=(0, 0), sig=SIG, stats=dict(stats)),
            StageUnit(uid="", cell=(3, 0), sig=SIG, stats=dict(stats)),
            StageUnit(uid="", cell=(1, 2), sig=SIG, stats=dict(stats)),
        ]
    )
    return StageDefinition(stage_id="g/hard_2", layout=layout)


SCAN = [(900.0, 150.0), (1185.0, 150.0), (995.0, 340.0)]


def test_validate_ok_seeds_the_resolver():
    script = _Script([HUB])
    report = validate_stage(
        _defn_for_validation(en=SUMMARY_EN),
        SCAN,
        capture=script.capture,
        tap=script.tap,
        bring_to_view=_identity_view,
        sleep=lambda s: None,
    )
    assert report.ok, report.mismatches
    assert report.taps == 2
    assert report.resolver is not None
    assert set(report.resolver.positions()) == {"e01", "e02", "e03"}


def test_validate_geometry_mismatch_skips_taps():
    script = _Script([HUB])
    report = validate_stage(
        _defn_for_validation(),
        SCAN[:2],
        capture=script.capture,
        tap=script.tap,
        bring_to_view=_identity_view,
        sleep=lambda s: None,
    )
    assert not report.ok
    assert report.taps == 0
    assert any("geometry census failed" in m for m in report.mismatches)


def test_validate_hp_mismatch_marks_stale():
    script = _Script([HUB])
    report = validate_stage(
        _defn_for_validation(hp=99999),
        SCAN,
        capture=script.capture,
        tap=script.tap,
        bring_to_view=_identity_view,
        sleep=lambda s: None,
    )
    assert not report.ok
    assert any("opening HP" in m for m in report.mismatches)


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


def _stage_controller(tmp_path, tacmap_enemies):
    from ggge_ai.battle.controller import ManualBattleController
    from ggge_ai.battle.ledger import BattleLedger

    class _Perception:
        def capture(self):
            return np.zeros((1080, 2340, 3), np.uint8)

        def probe(self, ids):
            return {}

    class _Actuator:
        def tap(self, x, y):
            pass

        def swipe(self, *a):
            pass

    c = ManualBattleController(
        perception=_Perception(),
        actuator=_Actuator(),
        ledger=BattleLedger(),
        intel_enabled=True,
        stage_id="g/hard_2",
        intel_cache_root=tmp_path,
    )
    for p in tacmap_enemies:
        c.tacmap.enemies.append(p)
    return c


def test_ensure_definition_cold_start_surveys_and_adopts(tmp_path, monkeypatch):
    c = _stage_controller(tmp_path, SCAN)
    defn = _defn_for_validation(en=SUMMARY_EN)
    monkeypatch.setattr(
        scout_intel, "survey_stage", lambda *a, **k: defn
    )
    monkeypatch.setattr(
        scout_intel,
        "validate_stage",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no file, no validation")),
    )

    c._ensure_stage_definition(None)

    assert not c.resolver.passthrough
    assert c.tracker.resolver is c.resolver
    assert set(c._id_positions) == {"e01", "e02", "e03"}
    assert c.tracker.beliefs["e01"].hp == 51349
    assert c.tracker.beliefs["e01"].source == "definition"


def test_ensure_definition_warm_start_validates_and_adopts(tmp_path, monkeypatch):
    defn = _defn_for_validation(en=SUMMARY_EN)
    stage_def.save_stage_def(defn, root=tmp_path)
    c = _stage_controller(tmp_path, SCAN)
    monkeypatch.setattr(
        scout_intel,
        "survey_stage",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("warm start must not survey")),
    )
    monkeypatch.setattr(c, "_bring_to_view", lambda world: world)
    monkeypatch.setattr(scout_intel.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        c.perception, "capture", lambda: HUB
    )

    c._ensure_stage_definition(None)

    assert not c.resolver.passthrough
    assert "e01" in c.specs_by_id or c.specs_by_id == {}
    assert set(c._id_positions) == {"e01", "e02", "e03"}


def test_ensure_definition_requires_stage_id(tmp_path):
    c = _stage_controller(tmp_path, SCAN)
    c.stage_id = None
    with pytest.raises(SurveyIncomplete):
        c._ensure_stage_definition(None)


def test_ensure_definition_stale_file_falls_back_to_survey(tmp_path, monkeypatch):
    defn = _defn_for_validation(hp=99999)
    stage_def.save_stage_def(defn, root=tmp_path)
    fresh = _defn_for_validation(en=SUMMARY_EN)
    c = _stage_controller(tmp_path, SCAN)
    monkeypatch.setattr(scout_intel, "survey_stage", lambda *a, **k: fresh)
    monkeypatch.setattr(c, "_bring_to_view", lambda world: world)
    monkeypatch.setattr(scout_intel.time, "sleep", lambda s: None)
    monkeypatch.setattr(c.perception, "capture", lambda: HUB)

    c._ensure_stage_definition(None)

    marked = stage_def.load_stage_def("g/hard_2", root=tmp_path)
    assert marked is not None and marked.status == "stale"
    assert set(c._id_positions) == {"e01", "e02", "e03"}


def test_surplus_arc_becomes_a_recorded_reinforcement(tmp_path, monkeypatch):
    defn = _defn_for_validation(en=SUMMARY_EN)
    stage_def.save_stage_def(defn, root=tmp_path)
    c = _stage_controller(tmp_path, SCAN)
    monkeypatch.setattr(c, "_bring_to_view", lambda world: world)
    monkeypatch.setattr(scout_intel.time, "sleep", lambda s: None)
    monkeypatch.setattr(c.perception, "capture", lambda: HUB)
    c._ensure_stage_definition(None)
    assert c.resolver.expected_alive() == 3

    surplus = (1600.0, 900.0)
    c.tacmap.enemies.append(surplus)
    monkeypatch.setattr(c, "_bring_to_view", lambda world: None)
    battle, _ = c._board_with_resync(None)

    events = {e["kind"] for e in c.ledger.events}
    assert "stage_event_observed" in events
    assert "stage_event_recorded" in events
    saved = stage_def.load_stage_def("g/hard_2", root=tmp_path)
    assert saved.events, "spawn event must be written back"
    spawned = saved.events[0].spawn_units()
    assert spawned[0].uid == "e04"
    assert c.resolver.resolve(surplus) == "e04"
    assert c.resolver.expected_alive() == 4

    c.tacmap.enemies.append((1600.0, 901.0))
    c._observe_new_units(None, battle)
    saved_again = stage_def.load_stage_def("g/hard_2", root=tmp_path)
    assert len(saved_again.events) == 1
