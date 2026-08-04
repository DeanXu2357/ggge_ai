"""Round 1.11: the power-saver-lock environmental defence -- keyguard下沉 +
入口存證重試, driven against the synthetic malicious world reused from
test_coverage_scan.

輪十一 crashed a new way: collect()'s anchor read returned observe=None while a
narrow-band reader on the SAME frame still found a lattice -- a contradiction
that points at the game's battery-saver touch lock dimming the frame between the
controller's 15s keyguard checks (批7's brightness filter then starves the
darkened frame of gridline votes). The defence is failure-response only (never
per-frame, to bound adb cost): a refused observation at three points -- collect()
entry, the anchor seek step, and the fill-loop refused branch (before _clear_full)
-- pokes an injected guard (the controller wires keyguard.ensure_unlocked),
re-captures and retries once. The entry additionally stashes the native frame
under `anchor_no_lattice` and names its path in the loud abort, so a wrong
hypothesis has hard offline evidence next round.

Every dark frame is modelled by an observe seam that returns None while a `dark`
flag is set; a fake guard callback lifts it, standing in for the lock dismissal.
The guard never counts as a nudge (spends no scan budget) and, unwired (legacy
None), leaves every path bit-identical -- proved red-then-green by contrasting a
wired guard against none on the same dimmed world.
"""

from __future__ import annotations

import numpy as np
import pytest

from ggge_ai.battle import vision
from ggge_ai.battle.coverage_map import FrameObservation  # noqa: F401  (type parity)
from ggge_ai.battle.live_scan import CoverageScanSource
from ggge_ai.battle.scout_intel import SurveyIncomplete
from tests.test_coverage_scan import _found_cells, _source, _World


@pytest.fixture(autouse=True)
def _no_obstruction(monkeypatch):
    # the synthetic worlds hand back opaque tokens; keep both obstruction probes
    # off them (mirrors the sibling coverage-scan fixtures)
    monkeypatch.setattr(vision, "is_unit_detail_modal", lambda f: False)
    monkeypatch.setattr(vision, "enemy_selection_active", lambda f: False)


def _guarded_source(world, *, events=None, guard=None, diag_save=None):
    return CoverageScanSource(
        capture=world.capture,
        swipe=world.swipe,
        tap=lambda x, y: None,
        ledger_log=(
            (lambda kind, **d: events.append({"kind": kind, **d}))
            if events is not None
            else None
        ),
        sleep=lambda s: None,
        detect=world.detect,
        observe=world.observe,
        guard=guard,
        diag_save=diag_save,
    )




class _DarkEntryWorld(_World):
    """輪十一 at the anchor read: the start frame is dimmed by the battery-saver
    touch lock so observe -> None (批7's brightness filter starved the gridline
    vote). The guard callback lifts the dim; the retry re-reads the real,
    units-bearing start frame."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.dark = True

    def lift(self):
        self.dark = False

    def observe(self, token):
        if self.dark:
            return None
        return super().observe(token)


def test_dark_entry_recovers_via_guard_retry():
    """後綠: the dimmed anchor read refuses, so the entry pokes the guard, the
    dim lifts, the re-capture reads the real frame, and the scan converges on
    every unit."""
    units = {(1, 1), (4, 2), (7, 5), (2, 4)}
    world = _DarkEntryWorld(9, 7, view=(6, 4), units=units, start=(0, 0), step=1)
    calls: list[int] = []

    def guard():
        calls.append(1)
        world.lift()

    src = _guarded_source(world, guard=guard)

    census = src.collect()

    assert calls, "the guard was never poked on the dimmed anchor read"
    assert _found_cells(census) == units


def test_dark_entry_without_guard_aborts_and_saves_native_diag():
    """先紅/legacy + 入口存證: with NO guard wired the dimmed anchor read is never
    recovered -- the scan aborts with 'carried no lattice' exactly as the pre-1.11
    code did. Independently of the guard, the native frame is stashed under
    `anchor_no_lattice` and the loud message names its path (hard evidence for a
    wrong battery-lock hypothesis next round)."""
    world = _DarkEntryWorld(9, 7, view=(6, 4), units={(1, 1)}, start=(0, 0), step=1)
    saved: list[str] = []

    def diag_save(frame, tag):
        saved.append(tag)
        return f"frames/battle_01/diag_turn1_{tag}.png"

    src = _guarded_source(world, diag_save=diag_save)  # guard=None

    with pytest.raises(SurveyIncomplete, match="carried no lattice") as exc:
        src.collect()

    assert saved == ["anchor_no_lattice"]
    assert "frames/battle_01/diag_turn1_anchor_no_lattice.png" in str(exc.value)
    assert src.census is None




class _DarkSeekWorld(_World):
    """輪十一 in the anchor SEEK: a void start (flat -> triggers the seek) whose
    first seek nudge lands on a frame the touch-lock dimmed (observe None). The
    guard lifts the dim so the retry re-reads the real, now units-bearing frame
    the nudge reached. The dim is one-shot: only the first pan is darkened, so a
    guard-less run stays dark (starves) while a guarded run recovers and then
    scans cleanly."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.dark = False

    def swipe(self, *a):
        super().swipe(*a)
        if self.n == 1:  # only the seek's first pan is dimmed by the lock
            self.dark = True

    def lift(self):
        self.dark = False

    def observe(self, token):
        if self.dark:
            return None
        obs = super().observe(token)
        if obs is None:
            return None
        if self.n == 0:  # the pre-nudge start view: a flat void to trigger the seek
            flat = {c: np.zeros(4, np.float32) for c in obs.fingerprints}
            return type(obs)(
                lattice=obs.lattice,
                edges=obs.edges,
                units=[],
                fingerprints=flat,
                distinctive=frozenset(),
                threats=[],
            )
        return obs


def test_dark_seek_step_recovers_via_guard_retry():
    """後綠: the void start seeks the interior; its first seek step lands on a
    dimmed frame, so the seek pokes the guard, the dim lifts, the re-capture
    reads the units-bearing frame, and the scan anchors and converges."""
    units = {(2, 1), (4, 2), (7, 5), (3, 3)}
    world = _DarkSeekWorld(9, 7, view=(6, 4), units=units, start=(0, 0), step=1)
    calls: list[int] = []

    def guard():
        calls.append(1)
        world.lift()

    events: list[dict] = []
    src = _guarded_source(world, events=events, guard=guard)

    census = src.collect()

    assert any(e["kind"] == "anchor_seek" for e in events), "the seek never ran"
    assert calls, "the guard was never poked on the dimmed seek step"
    assert _found_cells(census) == units


def test_dark_seek_step_without_guard_starves_like_legacy():
    """先紅/legacy: the same dimmed seek step with NO guard wired never recovers
    the read -- the seek burns its budget and fails loud exactly as the pre-1.11
    code did, publishing no census."""
    units = {(2, 1), (4, 2), (7, 5), (3, 3)}
    world = _DarkSeekWorld(9, 7, view=(6, 4), units=units, start=(0, 0), step=1)
    events: list[dict] = []
    src = _guarded_source(world, events=events)  # guard=None

    with pytest.raises(SurveyIncomplete):
        src.collect()
    assert src.census is None




def _starving_guarded_source(events, *, guard=None):
    """Anchors at the NW corner but refuses every frame elsewhere (observe None
    off (0,0)): each fill push is refused, so the refused branch pokes the guard,
    then clears, then recovers back to the covered corner -- the 輪七 starving
    signature, now carrying the 輪十一 guard poke ahead of the residue clear."""
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
        guard=guard,
    )


def test_fill_refused_pokes_guard_before_clear_full(monkeypatch):
    """The refused branch pokes the guard BEFORE _clear_full: the entry clear
    runs first, then every refusal emits guard -> clear_full in that order (the
    keyguard poke sits ahead of the residue clear, spec range item 1)."""
    seq: list[str] = []

    def guard():
        seq.append("guard")

    orig_clear = CoverageScanSource._clear_full

    def rec_clear(self, frame):
        seq.append("clear_full")
        return orig_clear(self, frame)

    monkeypatch.setattr(CoverageScanSource, "_clear_full", rec_clear)

    events: list[dict] = []
    src = _starving_guarded_source(events, guard=guard)

    with pytest.raises(SurveyIncomplete):
        src.collect()

    assert "guard" in seq, "the fill refusal never poked the guard"
    gi = seq.index("guard")
    # the entry _clear_full precedes the first guard; inside the refused branch
    # the guard fires immediately before the fill-loop _clear_full
    assert seq.index("clear_full") < gi, seq[:6]
    assert seq[gi + 1] == "clear_full", seq[:6]


def test_guard_does_not_consume_nudge_budget():
    """The guard poke + its re-capture are not nudges: the same starving world
    burns the identical nudge count whether or not a guard is wired (spec range
    item 1: guard呼叫不消耗 nudge 預算)."""
    ev_with: list[dict] = []
    ev_without: list[dict] = []
    calls: list[int] = []

    src_with = _starving_guarded_source(ev_with, guard=lambda: calls.append(1))
    src_without = _starving_guarded_source(ev_without, guard=None)

    with pytest.raises(SurveyIncomplete):
        src_with.collect()
    with pytest.raises(SurveyIncomplete):
        src_without.collect()

    r_with = next(e for e in ev_with if e["kind"] == "coverage_report")
    r_without = next(e for e in ev_without if e["kind"] == "coverage_report")
    assert calls, "guard was never poked (the assertion would be vacuous)"
    assert r_with["nudges"] == r_without["nudges"]




def test_guard_none_healthy_scan_is_unchanged():
    """guard未接 (legacy): a healthy converging scan with guard=None runs the
    pre-1.11 path bit-for-bit -- no dimmed frame, so no retry ever fires and the
    census is published exactly as before."""
    units = {(1, 1), (4, 2), (7, 5), (2, 4)}
    world = _World(9, 7, view=(6, 4), units=units, start=(0, 0), step=1)
    src = _source(world)  # guard defaults to None

    census = src.collect()

    assert _found_cells(census) == units
