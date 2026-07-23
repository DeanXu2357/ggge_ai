"""Round 1.7: enemy-selection residue defence + localisation-starving brake
+ refused-frame forensics, driven against the synthetic malicious world reused
from test_coverage_scan.

The residue is modelled as an overlay that POISONS localisation (observe returns
None) until an empty-land tap dismisses it -- the 輪七 signature where a docked
比較 HUD refused every frame from the scan's very start. The starving brake and
the refused-evidence throttle are proved by contrast: with the brake disarmed the
same starving world burns to the outer nudge budget (the 輪七 9-minute failure),
with it armed the scan fails loud in K refusals. frontier / integrate / localize
/ recovery-direction semantics are untouched -- only refused bookkeeping and an
early-stop exit are added on a path that WOULD have burned the budget."""

from __future__ import annotations

import pytest

from ggge_ai.battle import live_scan as ls
from ggge_ai.battle import vision
from ggge_ai.battle.live_scan import STARVE_LIMIT, CoverageScanSource
from ggge_ai.battle.scout_intel import SurveyIncomplete
from tests.test_coverage_scan import _found_cells, _World


@pytest.fixture(autouse=True)
def _no_modal(monkeypatch):
    # the synthetic world hands back opaque tuple tokens; keep the modal probe
    # off them (mirrors test_coverage_scan's own autouse fixture)
    monkeypatch.setattr(vision, "is_unit_detail_modal", lambda f: False)


# --- residue at the scan start (輪七) ---------------------------------------


def _residue_source(world, state, events, taps):
    def tap(x, y):
        taps.append((x, y))
        state["active"] = False  # an empty-land tap deselects -> residue gone

    def observe(token):
        if state["active"]:
            return None  # a docked comparison HUD poisons localisation
        return world.observe(token)

    return CoverageScanSource(
        capture=world.capture,
        swipe=world.swipe,
        tap=tap,
        ledger_log=lambda k, **d: events.append({"kind": k, **d}),
        sleep=lambda s: None,
        detect=world.detect,
        observe=observe,
    )


def test_start_residue_cleared_before_anchor_then_converges(monkeypatch):
    """後綠: the pre-anchor defence detects the residue, taps empty land to
    dismiss it, and the scan localises and converges on every unit."""
    state = {"active": True}
    monkeypatch.setattr(vision, "enemy_selection_active", lambda f: state["active"])
    units = {(1, 1), (4, 2), (7, 5), (2, 4)}
    world = _World(9, 7, view=(6, 4), units=units, start=(0, 0), step=1)
    events, taps = [], []
    src = _residue_source(world, state, events, taps)

    census = src.collect()

    assert taps, "the residue was never dismissed by an empty-land tap"
    assert state["active"] is False
    assert _found_cells(census) == units
    assert any(e["kind"] == "scan_selection_cleared" for e in events)


def test_start_residue_is_red_without_the_defence(monkeypatch):
    """先紅: with the residue defence bypassed (pre-anchor reverts to modal-only,
    as before Round 1.7) the poisoned anchor frame carries no lattice and the
    scan fails loud -- the defence above is exactly what turns this green."""
    state = {"active": True}
    monkeypatch.setattr(vision, "enemy_selection_active", lambda f: state["active"])
    monkeypatch.setattr(
        CoverageScanSource, "_clear_full", CoverageScanSource._clear_obstruction
    )
    world = _World(9, 7, view=(6, 4), units={(1, 1)}, start=(0, 0), step=1)
    events, taps = [], []
    src = _residue_source(world, state, events, taps)

    with pytest.raises(SurveyIncomplete):
        src.collect()
    assert taps == []  # no empty-land tap ever fired


def test_unclearable_residue_fails_loud_before_anchor(monkeypatch):
    """殘留無法解除 -> fail loud, no anchor. The HUD survives both the initial
    attempt and its one retry, so the scan aborts before touching the map."""
    monkeypatch.setattr(vision, "enemy_selection_active", lambda f: True)  # never clears
    world = _World(9, 7, view=(6, 4), units={(1, 1)}, start=(0, 0), step=1)
    events, taps = [], []
    src = _residue_source(world, {"active": True}, events, taps)

    with pytest.raises(SurveyIncomplete, match="survived"):
        src.collect()
    assert len(taps) == 2  # initial + one retry, then loud
    # never reached the anchor / fill loop
    assert not any(e["kind"] == "frame_localized" for e in events)


# --- localisation-starving brake (輪七) -------------------------------------


def _starving_source(events, *, diag_save=None):
    """A world that anchors at the NW corner but refuses every frame elsewhere:
    each fill push loses the lock, recovery relocates back to the covered corner
    (no new coverage), and the streak never breaks -- the 輪七 signature."""
    world = _World(40, 40, view=(6, 4), units=set(), start=(0, 0), step=1)

    def observe(token):
        return world.observe(token) if tuple(token) == (0, 0) else None

    return CoverageScanSource(
        capture=world.capture,
        swipe=world.swipe,
        tap=lambda x, y: None,
        ledger_log=lambda k, **d: events.append({"kind": k, **d}),
        sleep=lambda s: None,
        detect=world.detect,
        observe=observe,
        diag_save=diag_save,
    )


def test_starving_scan_brakes_early(monkeypatch):
    """後綠: K consecutive refusals with zero integration progress -> fail loud
    with 'localization starving', far short of the outer budget."""
    monkeypatch.setattr(vision, "enemy_selection_active", lambda f: False)
    events = []
    src = _starving_source(events)

    with pytest.raises(SurveyIncomplete, match="localization starving"):
        src.collect()

    report = next(e for e in events if e["kind"] == "coverage_report")
    assert report["outcome"] == "starved"
    assert report["refused"] >= STARVE_LIMIT
    assert report["nudges"] < ls.SCAN_MAX_NUDGES  # early stop, not budget burn


def test_starving_without_brake_burns_to_budget(monkeypatch):
    """先紅: with the brake disarmed (STARVE_LIMIT out of reach) the same
    starving world runs all the way to the outer nudge budget -- the 輪七
    9-minute failure the brake exists to cut short."""
    monkeypatch.setattr(vision, "enemy_selection_active", lambda f: False)
    monkeypatch.setattr(ls, "STARVE_LIMIT", 10**9)
    events = []
    src = _starving_source(events)

    with pytest.raises(SurveyIncomplete):
        src.collect()

    report = next(e for e in events if e["kind"] == "coverage_report")
    assert report["outcome"] == "budget"
    assert report["nudges"] > ls.SCAN_MAX_NUDGES  # burned well past the early stop


def test_normal_convergence_never_starves(monkeypatch):
    """The brake stays out of the way on a healthy scan: a clean converging
    world integrates progress, so the refused streak never reaches K and the
    census is published (輪六-type behaviour unchanged)."""
    monkeypatch.setattr(vision, "enemy_selection_active", lambda f: False)
    units = {(1, 1), (4, 2), (7, 5), (2, 4), (6, 1)}
    world = _World(9, 7, view=(6, 4), units=units, start=(0, 0), step=1)
    events = []
    src = CoverageScanSource(
        capture=world.capture,
        swipe=world.swipe,
        tap=lambda x, y: None,
        ledger_log=lambda k, **d: events.append({"kind": k, **d}),
        sleep=lambda s: None,
        detect=world.detect,
        observe=world.observe,
    )

    census = src.collect()

    assert _found_cells(census) == units
    report = next(e for e in events if e["kind"] == "coverage_report")
    assert report["outcome"] in ("complete", "unreachable_only")


# --- refused-frame forensics ------------------------------------------------


def test_refused_evidence_is_throttled_and_pathed(monkeypatch):
    """First 3 refusals + every 20th after are stashed at native resolution via
    the diag_save seam, each recorded with its ledger path."""
    monkeypatch.setattr(vision, "enemy_selection_active", lambda f: False)
    monkeypatch.setattr(ls, "STARVE_LIMIT", 10**9)  # let refusals accumulate past 20
    saved = []

    def diag_save(frame, tag):
        saved.append(tag)
        return f"frames/battle_01/diag_turn1_{tag}.png"

    events = []
    src = _starving_source(events, diag_save=diag_save)

    with pytest.raises(SurveyIncomplete):
        src.collect()

    refused = [e for e in events if e["kind"] == "refused_frame"]
    assert [e["n"] for e in refused] == [1, 2, 3, 20, 40]
    assert saved == ["refused001", "refused002", "refused003", "refused020", "refused040"]
    assert all(e["path"] and e["path"].endswith(".png") for e in refused)


def test_refused_evidence_survives_without_a_diag_sink(monkeypatch):
    """No diag_save wired (no ledger frames dir): the throttle still logs the
    refused_frame events, just with a null path."""
    monkeypatch.setattr(vision, "enemy_selection_active", lambda f: False)
    events = []
    src = _starving_source(events)  # diag_save=None

    with pytest.raises(SurveyIncomplete):
        src.collect()

    refused = [e for e in events if e["kind"] == "refused_frame"]
    assert [e["n"] for e in refused] == [1, 2, 3]  # brake fires at K=6, before 20
    assert all(e["path"] is None for e in refused)


def test_abort_stats_carry_refused_and_relocated(monkeypatch):
    """The coverage_report event and the SurveyIncomplete message both carry the
    refused / relocated tally (輪七 forensics: the abort names why)."""
    monkeypatch.setattr(vision, "enemy_selection_active", lambda f: False)
    events = []
    src = _starving_source(events)

    with pytest.raises(SurveyIncomplete, match="refused") as exc:
        src.collect()

    assert "relocated" in str(exc.value)
    report = next(e for e in events if e["kind"] == "coverage_report")
    assert "refused" in report and "relocated" in report
    assert report["relocated"] >= 1
