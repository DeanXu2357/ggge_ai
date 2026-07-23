"""Stage survey / validation (S6 fail-loud) and the per-turn sig
refresh, driven by the real capture sequence the 20260705 corpus
recorded (tap enemy -> summary card -> detail modal), with frames
reconstructed from the committed fixtures so every read runs the
production recognition path."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from ggge_ai.battle import map_view, scout_intel, vision
from ggge_ai.battle.state import Faction
from ggge_ai.content import stage_def
from ggge_ai.battle.scout_intel import (
    RefreshBudget,
    SurveyIncomplete,
    refresh_sig_positions,
    survey_stage,
    validate_stage,
)
from ggge_ai.content.stage_def import StageDefinition, StageUnit, assign_uids
from ggge_ai.vision.manifest import TemplateManifest

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "vision"
TEMPLATE_ROOT = Path(__file__).resolve().parent.parent / "assets" / "templates"


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
    # AUDIT (Round 1.6-A): survey_stage tests inject this fake for bring_to_view,
    # so the REAL CoverageScanSource.bring_to_view()->nudge() path is a blind spot
    # here -- it hid the 07-24 輪六 _navigator lifecycle crash. That path is now
    # covered directly by tests/test_bring_to_view_lifecycle.py.
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
    # same machine sig twice, and still one panel per unit -- no dedup;
    # the left-dock tap suffices when the modal opens on the first try
    assert script.taps.count(scout_intel.SUMMARY_CARD_TAPS[0]) == 2
    assert script.taps.count(scout_intel.SUMMARY_CARD_TAPS[1]) == 0
    by_cell = {u.cell: u.uid for u in defn.layout}
    assert by_cell[(0, 0)] == "e01"
    assert by_cell[(3, 5)] == "e02"
    saved = stage_def.load_stage_def("g/hard_2", root=tmp_path)
    assert saved is not None and saved.status == "complete"
    assert any(e["kind"] == "survey_complete" for e in events)


def test_survey_falls_back_to_right_dock_tap(tmp_path):
    """Left-dock tap misses (modal never opens), the card gets re-opened and
    the right-dock point succeeds -- the 20260714 HARD 1 layout."""
    frames = (
        [HUB]                # summary read
        + [HUB] * 6          # _await_modal polls after the left tap: no modal
        + [HUB]              # re-open read
        + [MODAL, MODAL, HUB]  # right tap opens the modal; weapons; close
    )
    script = _Script(frames)
    defn = survey_stage(
        script.capture,
        script.tap,
        [(900.0, 150.0)],
        stage_id="g/hard_2",
        bring_to_view=_identity_view,
        sleep=lambda s: None,
        root=tmp_path,
    )
    assert [u.uid for u in defn.layout] == ["e01"]
    assert script.taps.count(scout_intel.SUMMARY_CARD_TAPS[0]) == 1
    assert script.taps.count(scout_intel.SUMMARY_CARD_TAPS[1]) == 1


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


def test_survey_drops_cardless_ghost_hugging_an_ally(tmp_path):
    """A card-less 'enemy' within GHOST_RADIUS of a scanned ally is the
    pink-bug ghost twin: recorded, dropped, survey continues. The same
    failure away from every ally still fails loud (previous test)."""
    blank = np.zeros((1080, 2340, 3), np.uint8)
    # ghost point: 3 no-card retries see blank frames; real point follows
    frames = [blank, blank, blank] + [HUB, MODAL, MODAL, HUB]
    script = _Script(frames)
    events, log = _events()
    dropped: list[int] = []
    defn = survey_stage(
        script.capture,
        script.tap,
        [(65.0, 819.0), (900.0, 150.0)],
        stage_id="g/hard_2",
        bring_to_view=_identity_view,
        ally_points=[(65.0, 904.0)],
        dropped=dropped,
        ledger_log=log,
        sleep=lambda s: None,
        root=tmp_path,
    )
    assert dropped == [0]
    assert [u.sig for u in defn.layout] == [SIG]
    assert any(e["kind"] == "survey_phantom" for e in events)


def test_survey_all_ghosts_still_fails_loud(tmp_path):
    blank = np.zeros((1080, 2340, 3), np.uint8)
    script = _Script([blank])
    with pytest.raises(SurveyIncomplete):
        survey_stage(
            script.capture,
            script.tap,
            [(65.0, 819.0)],
            stage_id="g/hard_2",
            bring_to_view=_identity_view,
            ally_points=[(65.0, 904.0)],
            dropped=[],
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
        c.tacmap.units.append(p)
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
    # definition HP is a file opening value, never screen-confirmed
    assert c.tracker.beliefs["e01"].hp_turn == 0


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
    c.tacmap.units.append(surplus)
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

    c.tacmap.units.append((1600.0, 901.0))
    c._observe_new_units(None, battle)
    saved_again = stage_def.load_stage_def("g/hard_2", root=tmp_path)
    assert len(saved_again.events) == 1


# ---- identify mode (定案 5): factionless points, dock side decides ----

RIGHT = _canvas("faction/right_dock_hard1_20260714.png", (0, 0, 2340, 300))
BLANK = np.zeros((1080, 2340, 3), np.uint8)


def _identifier():
    from ggge_ai.battle.faction import DockBannerIdentifier

    return DockBannerIdentifier()


def test_identify_survey_splits_layout_from_deploy_slots(tmp_path):
    script = _Script(
        [HUB, HUB, MODAL, MODAL, RIGHT, HUB, HUB, MODAL, MODAL, HUB]
    )
    events, log = _events()
    ally_indices: list[int] = []
    defn = survey_stage(
        script.capture,
        script.tap,
        [(900.0, 150.0), (1185.0, 625.0), (1350.0, 340.0)],
        stage_id="g/hard_2",
        bring_to_view=_identity_view,
        identifier=_identifier(),
        ally_indices=ally_indices,
        ledger_log=log,
        sleep=lambda s: None,
        root=tmp_path,
    )
    assert [u.uid for u in defn.layout] == ["e01", "e02"]
    assert {u.cell for u in defn.layout} == {(0, 0), (5, 2)}
    assert all(u.faction == "enemy" for u in defn.layout)
    assert [s.cell for s in defn.deploy_slots] == [(3, 5)]
    assert ally_indices == [1]
    ally_events = [e for e in events if e["kind"] == "survey_ally"]
    assert len(ally_events) == 1 and ally_events[0]["side"] == "right"
    saved = stage_def.load_stage_def("g/hard_2", root=tmp_path)
    assert [s.cell for s in saved.deploy_slots] == [(3, 5)]


def test_identify_survey_drops_same_cell_twin(tmp_path):
    script = _Script([HUB, HUB, MODAL, MODAL, HUB])
    events, log = _events()
    dropped: list[int] = []
    defn = survey_stage(
        script.capture,
        script.tap,
        [(900.0, 150.0), (930.0, 170.0)],
        stage_id="g/hard_2",
        bring_to_view=_identity_view,
        identifier=_identifier(),
        dropped=dropped,
        ledger_log=log,
        sleep=lambda s: None,
        root=tmp_path,
    )
    assert [u.uid for u in defn.layout] == ["e01"]
    assert dropped == [1]
    phantom = next(e for e in events if e["kind"] == "survey_phantom")
    assert phantom["reason"] == "duplicate_cell_of_0"


def test_identify_survey_ghosts_bannerless_point_near_identified_ally(tmp_path):
    script = _Script(
        [RIGHT, BLANK, BLANK, BLANK, HUB, HUB, MODAL, MODAL, HUB]
    )
    events, log = _events()
    dropped: list[int] = []
    ally_indices: list[int] = []
    defn = survey_stage(
        script.capture,
        script.tap,
        [(900.0, 150.0), (950.0, 180.0), (1500.0, 700.0)],
        stage_id="g/hard_2",
        bring_to_view=_identity_view,
        identifier=_identifier(),
        dropped=dropped,
        ally_indices=ally_indices,
        ledger_log=log,
        sleep=lambda s: None,
        root=tmp_path,
    )
    assert ally_indices == [0]
    assert dropped == [1]
    assert [u.uid for u in defn.layout] == ["e01"]
    phantom = next(e for e in events if e["kind"] == "survey_phantom")
    assert phantom["reason"] == "no_banner_near_ally"


def test_identify_survey_bannerless_point_alone_fails_loud(tmp_path):
    script = _Script([BLANK])
    with pytest.raises(SurveyIncomplete):
        survey_stage(
            script.capture,
            script.tap,
            [(900.0, 150.0)],
            stage_id="g/hard_2",
            bring_to_view=_identity_view,
            identifier=_identifier(),
            sleep=lambda s: None,
            root=tmp_path,
        )


# ---- Round 1.5: identify view gate over selection overlays ----


class _GatedWorld:
    """Drives capture/tap/classify/escape for an identify survey with the view
    gate wired. Each candidate point is tagged enemy or ally: tapping an ally
    enters unit-move (a selection overlay, no card); tapping an enemy raises
    its summary card on the hub; the detail-modal taps behave as the real
    _survey_point expects. escape() backs out to the hub. Every tap and every
    escape is recorded in order so a test can prove no blind re-tap ever lands
    on the overlay (the 輪五 defeat)."""

    def __init__(self, plan, *, start_view="hub"):
        self.kind = {(int(x), int(y)): k for (x, y), k in plan}
        self.view = start_view
        self.taps: list = []

    def capture(self):
        if self.view == "move":
            return BLANK
        if self.view == "modal":
            return MODAL
        return HUB

    def classify(self, _frame):
        return {"hub": "hub", "move": "unit_move", "modal": "modal"}[self.view]

    def escape(self) -> bool:
        self.taps.append(("escape",))
        self.view = "hub"
        return True

    def tap(self, x, y):
        pt = (int(x), int(y))
        self.taps.append(pt)
        if pt in self.kind:
            self.view = "move" if self.kind[pt] == "ally" else "hub"
        elif pt == scout_intel.SUMMARY_CARD_TAPS[0]:
            self.view = "modal"
        elif pt == scout_intel.UNIT_DETAIL_CLOSE:
            self.view = "hub"


ENEMY_A = (900.0, 150.0)
ALLY = (1500.0, 700.0)
ENEMY_B = (1185.0, 625.0)


def test_identify_gate_judges_move_overlay_ally_without_reblind_tapping(tmp_path):
    """A candidate tap that selects one of our unactioned machines lands in a
    unit-move overlay. The gate must call it ALLY through the mechanism
    channel (side="unit_move", score 1.0), escape once, and move on -- never
    re-tap the overlay. Without the gate _identify_at blind-retries the tap and
    the survey aborts (the failing pre-Round-1.5 behaviour)."""
    world = _GatedWorld([(ENEMY_A, "enemy"), (ALLY, "ally"), (ENEMY_B, "enemy")])
    events, log = _events()
    ally_indices: list[int] = []
    defn = survey_stage(
        world.capture,
        world.tap,
        [ENEMY_A, ALLY, ENEMY_B],
        stage_id="g/hard_2",
        bring_to_view=_identity_view,
        identifier=_identifier(),
        ally_indices=ally_indices,
        classify=world.classify,
        escape=world.escape,
        ledger_log=log,
        sleep=lambda s: None,
        root=tmp_path,
    )
    assert [u.faction for u in defn.layout] == ["enemy", "enemy"]
    assert ally_indices == [1]
    # the overlay was tapped exactly once, then escaped -- no blind re-tap
    assert world.taps.count((int(ALLY[0]), int(ALLY[1]))) == 1
    assert ("escape",) in world.taps
    ally_events = [e for e in events if e["kind"] == "survey_ally"]
    assert len(ally_events) == 1
    assert ally_events[0]["side"] == "unit_move"
    assert ally_events[0]["score"] == 1.0
    assert [s.cell for s in defn.deploy_slots] == [tuple(ally_events[0]["cell"])]


def test_identify_gate_escapes_a_residual_overlay_before_the_first_tap(tmp_path):
    """Round 1.5 acceptance point: the survey may open on a stale selection
    overlay (the 輪五 opening state). The pre-tap gate must back out to the hub
    before touching any map point -- the escape comes first, no tap lands on
    the overlay."""
    world = _GatedWorld([(ENEMY_A, "enemy")], start_view="move")
    defn = survey_stage(
        world.capture,
        world.tap,
        [ENEMY_A],
        stage_id="g/hard_2",
        bring_to_view=_identity_view,
        identifier=_identifier(),
        classify=world.classify,
        escape=world.escape,
        sleep=lambda s: None,
        root=tmp_path,
    )
    assert [u.uid for u in defn.layout] == ["e01"]
    # the very first action is the escape, before any coordinate tap
    assert world.taps[0] == ("escape",)
    first_coord = next(t for t in world.taps if t != ("escape",))
    assert first_coord == (int(ENEMY_A[0]), int(ENEMY_A[1]))


def test_move_overlay_finish_frame_gate_overrides_the_false_dock_ally():
    """輪五末幀 t0135 (real frame): the raw dock reader forges a lone-right
    ALLY here because the weapon-select right panel shares the summary
    geometry -- so the classify gate MUST run first. It reads unit_move, and
    the 返回 button is present for a dedicated-UI escape. Two uses in one
    fixture: the dock reader's hazard and the gate that neutralises it."""
    frame = cv2.imread(
        str(FIXTURES / "mode_label" / "move_overlay_finish_20260723.jpg")
    )
    assert frame is not None
    recognizer = TemplateManifest.load(TEMPLATE_ROOT).build_recognizer()

    def probe(ids, frame=None):
        return {
            e.id: e
            for e in recognizer.detect_elements(frame, ids)
            if e.confidence >= 0.80
        }

    assert map_view.classify_frame(frame, probe) == "unit_move"
    verdict = _identifier().identify(frame)
    assert verdict is not None
    assert verdict.faction is Faction.ALLY and verdict.side == "right"
    assert map_view.RETURN_BUTTON in probe([map_view.RETURN_BUTTON], frame=frame)


# ---- Round 1.9: identify live re-verify (peak recheck + snap + phantom drop) ----


class _RecheckWorld:
    """Coordinate-sensitive fake for the live re-verify. Tapping a point in
    `units` raises that unit's summary banner (enemy, left dock = HUB); tapping
    anywhere else on the map shows no banner (BLANK). The detail-modal taps
    behave as _survey_point expects. detect() reports the configured density
    `peaks` -- it is only consulted on the no-banner recheck frame. Every tap is
    recorded so a test can prove the snap re-tap lands on the peak, not the
    original point."""

    def __init__(self, units, peaks):
        self.units = {(int(x), int(y)) for x, y in units}
        self.peaks = [(int(x), int(y)) for x, y in peaks]
        self.view = "map"
        self.taps: list = []

    def capture(self):
        return {"map": BLANK, "card": HUB, "modal": MODAL}[self.view]

    def tap(self, x, y):
        pt = (int(x), int(y))
        self.taps.append(pt)
        if pt in self.units:
            self.view = "card"
        elif pt == scout_intel.SUMMARY_CARD_TAPS[0]:
            self.view = "modal"
        elif pt == scout_intel.WEAPONS_TAB_TAP:
            self.view = "modal"
        elif pt == scout_intel.UNIT_DETAIL_CLOSE:
            self.view = "map"
        else:
            self.view = "map"

    def detect(self, _frame):
        return list(self.peaks)


def test_identify_live_reverify_drops_phantom_and_continues(tmp_path):
    """A candidate whose tap raises no banner AND shows no unit peak under it is
    an evidence-backed phantom: dropped with reason no_unit_at_tap, a diag frame
    saved, and the survey continues to the real unit. Pre-Round-1.9 this point
    fails the whole survey loud."""
    world = _RecheckWorld(units=[(900, 150)], peaks=[])
    events, log = _events()
    dropped: list[int] = []
    diag_calls: list = []
    defn = survey_stage(
        world.capture,
        world.tap,
        [(1263.0, 419.0), (900.0, 150.0)],
        stage_id="g/hard_2",
        bring_to_view=_identity_view,
        identifier=_identifier(),
        dropped=dropped,
        detect=world.detect,
        diag_save=lambda frame, tag: diag_calls.append(tag) or f"diag/{tag}.png",
        ledger_log=log,
        sleep=lambda s: None,
        root=tmp_path,
    )
    assert dropped == [0]
    assert [u.uid for u in defn.layout] == ["e01"]
    phantom = next(e for e in events if e["kind"] == "survey_phantom")
    assert phantom["reason"] == "no_unit_at_tap"
    assert phantom["tap"] == [1263.0, 419.0]
    assert phantom["diag"] == "diag/identify_fail_i0.png"
    assert diag_calls == ["identify_fail_i0"]
    assert any(e["kind"] == "survey_complete" for e in events)


def test_identify_live_reverify_snaps_to_offset_peak(tmp_path):
    """The unit's true pixels sit ~50px off the projected tap point: three blind
    origin retries fail, then a single snap re-tap on the detected peak reads the
    banner. Pre-Round-1.9 the three origin retries just fail loud."""
    world = _RecheckWorld(units=[(940, 180)], peaks=[(940, 180)])
    events, log = _events()
    defn = survey_stage(
        world.capture,
        world.tap,
        [(900.0, 150.0)],
        stage_id="g/hard_2",
        bring_to_view=_identity_view,
        identifier=_identifier(),
        detect=world.detect,
        ledger_log=log,
        sleep=lambda s: None,
        root=tmp_path,
    )
    assert [u.uid for u in defn.layout] == ["e01"]
    # three blind retries at the projected origin, then the snap lands on the peak
    assert world.taps.count((900, 150)) == 3
    assert (940, 180) in world.taps
    snap = next(e for e in events if e["kind"] == "snap_tap")
    assert snap["origin"] == [900.0, 150.0]
    assert snap["snap"] == [940, 180]


def test_identify_live_reverify_snap_still_no_banner_fails_loud(tmp_path):
    """A peak is present but even the snap re-tap raises no banner: zero-guess
    holds -- fail loud, write nothing, but record the snap that was attempted."""
    world = _RecheckWorld(units=[], peaks=[(940, 180)])
    events, log = _events()
    with pytest.raises(SurveyIncomplete):
        survey_stage(
            world.capture,
            world.tap,
            [(900.0, 150.0)],
            stage_id="g/hard_2",
            bring_to_view=_identity_view,
            identifier=_identifier(),
            detect=world.detect,
            ledger_log=log,
            sleep=lambda s: None,
            root=tmp_path,
        )
    assert any(e["kind"] == "snap_tap" for e in events)
    assert stage_def.load_stage_def("g/hard_2", root=tmp_path) is None


def test_identify_live_reverify_ghost_of_ally_keeps_priority(tmp_path):
    """No peak AND hugging a known ally: the existing ghost_of_ally drop keeps
    priority (reason no_banner_near_ally), never the new no_unit_at_tap."""
    world = _RecheckWorld(units=[(900, 150)], peaks=[])
    events, log = _events()
    dropped: list[int] = []
    defn = survey_stage(
        world.capture,
        world.tap,
        [(1263.0, 419.0), (900.0, 150.0)],
        stage_id="g/hard_2",
        bring_to_view=_identity_view,
        identifier=_identifier(),
        ally_points=[(1263.0, 419.0)],
        dropped=dropped,
        detect=world.detect,
        ledger_log=log,
        sleep=lambda s: None,
        root=tmp_path,
    )
    assert dropped == [0]
    assert [u.uid for u in defn.layout] == ["e01"]
    phantom = next(e for e in events if e["kind"] == "survey_phantom")
    assert phantom["reason"] == "no_banner_near_ally"


def test_identify_live_reverify_diag_frames_are_throttled(tmp_path):
    """Diagnostic frames for no-banner failures are stashed on the first 3 and
    every 10th thereafter; the saved failures carry the frame path, throttled
    ones carry None."""
    world = _RecheckWorld(units=[(900, 150)], peaks=[])
    events, log = _events()
    diag_calls: list = []
    phantom_pts = [(200.0 + 200 * k, 900.0) for k in range(11)]
    points = phantom_pts + [(900.0, 150.0)]
    defn = survey_stage(
        world.capture,
        world.tap,
        points,
        stage_id="g/hard_2",
        bring_to_view=_identity_view,
        identifier=_identifier(),
        dropped=[],
        detect=world.detect,
        diag_save=lambda frame, tag: diag_calls.append(tag) or f"diag/{tag}.png",
        ledger_log=log,
        sleep=lambda s: None,
        root=tmp_path,
    )
    assert diag_calls == [
        "identify_fail_i0",
        "identify_fail_i1",
        "identify_fail_i2",
        "identify_fail_i9",
    ]
    phantoms = [e for e in events if e["kind"] == "survey_phantom"]
    assert len(phantoms) == 11
    assert all(e["reason"] == "no_unit_at_tap" for e in phantoms)
    saved = [e for e in phantoms if e["diag"] is not None]
    assert len(saved) == 4
    assert [u.uid for u in defn.layout] == ["e01"]


def test_ensure_definition_wires_detect_and_diag(tmp_path, monkeypatch):
    """The controller hands the survey a unit detector and the ledger's
    native-resolution diag saver (Round 1.9 seam), mirroring classify/escape."""
    c = _stage_controller(tmp_path, SCAN)
    captured: dict = {}
    defn = _defn_for_validation(en=SUMMARY_EN)

    def fake_survey(*a, **k):
        captured.update(k)
        return defn

    monkeypatch.setattr(scout_intel, "survey_stage", fake_survey)
    monkeypatch.setattr(
        scout_intel,
        "validate_stage",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no file, no validation")),
    )

    c._ensure_stage_definition(None)

    assert captured["detect"] is vision.find_unit_density_peaks
    assert captured["diag_save"] == c.ledger.save_diag_frame
