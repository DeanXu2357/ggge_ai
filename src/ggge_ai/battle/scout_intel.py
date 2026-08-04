"""Stage survey and warm-start validation (S6, fail-loud).

Cold path (no definition on disk): survey_stage walks EVERY enemy and
third-party point of the full-map sweep, brings each into view, taps it,
opens the detail panel (no sig dedup -- two units of one machine share a
sig while their pilots differ, so every unit pays its panel), and writes
the schema-2 stage definition with row-major uids. Anything unreadable
raises SurveyIncomplete: an incomplete game description would make the
solver optimize the wrong game, so the battle aborts loudly instead
(the wall-clock cap is a freeze guard with the same semantics).

Warm path: validate_stage seeds an IdentityResolver from the definition
(free geometry census over the same sweep) and spot-taps a small sample
-- shared-sig groups first, the pilot-difference risk -- comparing the
card's sig and opening HP/EN against the file. Any mismatch expires the
whole stage back to a live survey. The screen stays authoritative.

Interaction constants (tab tap point, settle times) are calibrated from
the 20260705 capture sequence and confirmed live 2026-07-14 (HARD 1).
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import panels, vision
from ..content import stage_def
from ..content.kit import UnitSpec
from .faction import FactionIdentifier, FactionVerdict, move_overlay_verdict
from .identity import IdentityResolver, SeedReport
from .map_view import HUB as HUB_VIEW
from .map_view import SELECTION_SUBSTATES, UNIT_DETAIL_CLOSE
from .observe import SIG_MATCH_RADIUS
from .state import Faction
from ..content.stage_def import DeploySlot, StageDefinition, StageUnit, signature_distance

log = logging.getLogger(__name__)

# the summary card DOCKS ON EITHER SIDE of the top band: left on the
# 20260705 hub capture and the 20260719 event stage, right on the
# 2026-07-14 HARD 1 sample that calibrated the old fixed (1510,205) --
# which, on a left-docked card, lands on empty map and DISMISSES the card
# (the 20260719 survey_abort). The left tap goes first because the
# reader's HP-label anchor sits on the left dock, so a successful summary
# read is itself evidence for it; the point is the mech panel's flat fill
# (avoids the ⊖ collapse toggles at ~(163,150)/(592,151) and the pilot
# panel, whose tap target is unverified). A missed tap dismisses the card,
# so the fallback re-opens it before trying the right-dock point. Tapping
# the card opens the unit-detail modal, which lands on the weapons tab
# directly; the tab tap is kept as an idempotent safety. ABILITY_TAB_TAP
# reaches the 能力、OP page (trait corpus for issues #21/#22).
SUMMARY_CARD_TAPS = ((860, 165), (1510, 205))
WEAPONS_TAB_TAP = (1381, 173)
ABILITY_TAB_TAP = (1813, 176)
SUMMARY_SETTLE_S = 1.2
MODAL_SETTLE_S = 1.5
MODAL_POLL_S = 0.5
MODAL_POLL_TRIES = 6

SURVEY_WALL_CLOCK_S = 1200.0
SURVEY_TAP_RETRIES = 3
VALIDATE_SAMPLE_CAP = 4
# hub arcs double-classify on the pinned pink-ally bug: one unit can enter
# the sweep as an enemy AND an ally a few tens of px apart (20260719 pairs
# 29-85px). Real units sit at least one grid cell (~118px) apart, so an
# unreadable "enemy" within this radius of a scanned ally is that ally's
# ghost twin, not a partial description -- it is dropped with a ledger
# record instead of failing the survey loud.
GHOST_RADIUS = 90.0

# Round 1.9 live re-verify radius, as a fraction of the grid cell pitch
# (cell_size, ~95px). A real unit's density peak sits inside its own cell, so
# when a tap raises no banner we look at the live frame: a peak within this
# radius of the tap point is the unit we meant (snap to its true pixels), and
# no peak at all is current visual proof the point is empty (drop as a phantom
# instead of failing the whole survey). The fraction is kept STRICTLY BELOW one
# full cell precisely to bound mis-attribution: a neighbouring cell's peak is
# >= cell_size away (real units are >= one grid cell / ~118px apart, see
# GHOST_RADIUS), so the snap can only correct an intra-cell offset and can never
# reach across into an adjacent unit. At cell_size=95 the radius is ~71px, which
# still covers the ~40px projection offsets the survey produces.
TAP_PEAK_RADIUS_CELLS = 0.75


class SurveyIncomplete(RuntimeError):
    """The stage could not be read to completion; the caller must stop
    loudly (survey_abort), never proceed on a partial game description."""


@dataclass
class StageIntel:
    specs_by_sig: dict[str, UnitSpec] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)
    assumptions: dict[str, list[str]] = field(default_factory=dict)
    summaries: dict[str, vision.EnemySummary] = field(default_factory=dict)
    positions: dict[str, tuple[int, int]] = field(default_factory=dict)
    panels_opened: int = 0
    cache_hits: int = 0
    cache_stale: bool = False


@dataclass
class ValidationReport:
    ok: bool
    seed: SeedReport | None = None
    resolver: IdentityResolver | None = None
    mismatches: list[str] = field(default_factory=list)
    taps: int = 0


# the Round 1.5 view-gate seam: classify(frame)->view name (map_view
# vocabulary), escape()->reach the hub and report success. Both optional so
# the legacy dock-only tests and callers keep the old unguarded behaviour;
# the controller wires the real map_view functions through survey_stage.
ClassifyView = Callable[[object], str]
EscapeToHub = Callable[[], bool]


def _hub_is_safe_to_tap(
    capture: Callable,
    classify: ClassifyView | None,
    escape: EscapeToHub | None,
) -> bool:
    """True when a map point may be tapped: no gate configured, or the view is
    already the hub. Otherwise back out first (a tap in a selection overlay
    would land on a map cell and commit a move) and report whether the hub was
    reached. Never taps a map cell itself -- escape is dedicated-UI only."""
    if classify is None:
        return True
    if classify(capture()) == HUB_VIEW:
        return True
    if escape is None:
        return False
    return bool(escape())


DetectUnits = Callable[[object], list[tuple[int, int]]]


def _peaks_near(
    detect: DetectUnits | None,
    frame,
    screen: tuple[float, float],
    radius: float,
) -> list[tuple[int, int]]:
    """Unit density peaks within `radius` px of the tap point, nearest first
    (Round 1.9 live re-verify). Empty when no detector is wired or none land in
    range; a raise from the detector on an off-nominal frame counts as no
    evidence rather than a crash."""
    if detect is None:
        return []
    try:
        peaks = detect(frame)
    except Exception:
        return []
    r2 = radius * radius
    near = [
        (int(px), int(py))
        for px, py in peaks
        if (px - screen[0]) ** 2 + (py - screen[1]) ** 2 <= r2
    ]
    near.sort(key=lambda p: (p[0] - screen[0]) ** 2 + (p[1] - screen[1]) ** 2)
    return near


def _read_summary_at(
    capture,
    tap,
    screen,
    sleep,
    *,
    retries: int = SURVEY_TAP_RETRIES,
    classify: ClassifyView | None = None,
    escape: EscapeToHub | None = None,
):
    """Read a unit's summary card, hub-gated (Round 1.5): confirm the hub
    before every tap and, if the tap lands in a selection overlay instead of
    raising a card, escape rather than blind-retry on the overlay."""
    for _ in range(retries):
        if not _hub_is_safe_to_tap(capture, classify, escape):
            return None
        tap(int(screen[0]), int(screen[1]))
        sleep(SUMMARY_SETTLE_S)
        frame = capture()
        if classify is not None and classify(frame) != HUB_VIEW:
            if escape is not None:
                escape()
            continue
        summary = vision.read_enemy_summary(frame)
        if summary is not None and summary.name_sig is not None:
            return summary
    return None


def _identify_at(
    capture,
    tap,
    screen,
    identifier: FactionIdentifier,
    sleep,
    *,
    retries: int = SURVEY_TAP_RETRIES,
    classify: ClassifyView | None = None,
    escape: EscapeToHub | None = None,
) -> FactionVerdict | None:
    """Tap the unit and read which side its banner docks on (定案 5), with a
    view gate in front of the dock reader (Round 1.5). None after every retry
    means no banner appeared on a hub frame -- the caller sentences the point
    (ghost or fail-loud), never guesses a faction.

    The gate makes every attempt safe: confirm the hub before tapping (a tap
    in a selection overlay lands on a map cell and commits a move), then
    classify the post-tap frame. A selection substate is mechanism proof the
    unit is ours -> an ALLY verdict plus a safe escape; the dock reader runs
    only on a genuine hub frame (the weapon-select right panel would otherwise
    forge a lone-right ally hit). Any other non-hub state is escaped and
    retried -- never a blind re-tap on the overlay."""
    for _ in range(retries):
        if not _hub_is_safe_to_tap(capture, classify, escape):
            return None
        tap(int(screen[0]), int(screen[1]))
        sleep(SUMMARY_SETTLE_S)
        frame = capture()
        if classify is not None:
            view = classify(frame)
            if view in SELECTION_SUBSTATES:
                if escape is not None:
                    escape()
                return move_overlay_verdict()
            if view != HUB_VIEW:
                if escape is not None:
                    escape()
                continue
        verdict = identifier.identify(frame)
        if verdict is not None:
            return verdict
    return None


def _survey_point(
    capture: Callable,
    tap: Callable[[int, int], None],
    screen: tuple[float, float],
    *,
    llm,
    sleep: Callable[[float], None],
    classify: ClassifyView | None = None,
    escape: EscapeToHub | None = None,
) -> tuple[str, str | None, dict, list[dict]]:
    """One unit's full read at a screen point: summary card -> detail
    panel -> stats/weapons (+ LLM name). Raises SurveyIncomplete on any
    unreadable step; the caller decides whether that is fatal (opening
    survey) or a soft note (mid-battle reinforcement)."""
    summary = _read_summary_at(
        capture, tap, screen, sleep, classify=classify, escape=escape
    )
    if summary is None:
        raise SurveyIncomplete(f"no summary card at {screen}")
    modal = None
    for point in SUMMARY_CARD_TAPS:
        tap(*point)
        sleep(MODAL_SETTLE_S)
        modal = _await_modal(capture, sleep)
        if modal is not None:
            break
        # the missed tap dismissed the card; re-open it for the next dock
        if _read_summary_at(capture, tap, screen, sleep) is None:
            break
    if modal is None:
        raise SurveyIncomplete(f"detail modal did not open at {screen}")
    tap(*WEAPONS_TAB_TAP)
    sleep(MODAL_SETTLE_S)
    modal = capture()
    stats = panels.parse_unit_stats(modal)
    rows = panels.parse_weapon_rows(modal)
    if stats is None:
        tap(*UNIT_DETAIL_CLOSE)
        sleep(MODAL_SETTLE_S)
        raise SurveyIncomplete(f"stat column unreadable at {screen}")
    name = None
    if llm is not None:
        x, y, w, h = vision.FORECAST_LEFT_NAME_REGION
        name = llm.transcribe(
            modal[y : y + h, x : x + w],
            "Transcribe the unit name on this game UI name plate "
            "(Traditional Chinese / Japanese, single line).",
        )
    tap(*UNIT_DETAIL_CLOSE)
    sleep(MODAL_SETTLE_S)
    stats_dict = {k: getattr(stats, k) for k in stats.__dataclass_fields__}
    weapons = [{k: getattr(r, k) for k in r.__dataclass_fields__} for r in rows]
    return summary.name_sig, name, stats_dict, weapons


def survey_stage(
    capture: Callable,
    tap: Callable[[int, int], None],
    points: list[tuple[float, float]],
    *,
    stage_id: str,
    bring_to_view: Callable[[tuple[float, float]], tuple[float, float] | None],
    factions: list[str] | None = None,
    ally_points: list[tuple[float, float]] | None = None,
    dropped: list[int] | None = None,
    identifier: FactionIdentifier | None = None,
    ally_indices: list[int] | None = None,
    llm=None,
    classify: ClassifyView | None = None,
    escape: EscapeToHub | None = None,
    detect: DetectUnits | None = None,
    diag_save: Callable[[object, str], str | None] | None = None,
    ledger_log: Callable[..., None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    wall_clock_s: float = SURVEY_WALL_CLOCK_S,
    cell_size: float = 95.0,
    map_size: tuple[int | None, int | None] | None = None,
    root: Path | None = None,
) -> StageDefinition:
    """Full survey of the sweep's points into a saved definition. Raises
    SurveyIncomplete on the first unreadable unit or on the wall-clock
    guard -- partial definitions are never written.

    Two faction modes. Legacy (`identifier` None): `factions` carries the
    arc-color census verdicts and every point is stage content. Identify
    mode (定案 5, `identifier` given): points arrive FACTIONLESS; each is
    tapped and the banner's dock side decides -- left docks into the
    layout through the panel chain, right is one of our deploy machines,
    recorded as a DeploySlot cell (出擊格是關卡內容、站誰不 cache) with
    its index in `ally_indices` so the caller can exclude it from the
    layout census.

    Evidence-backed ghost drops (`dropped`): a point that cannot be
    reached or shows no banner while hugging a known ally is the
    pink-bug ghost twin; in identify mode a point whose cell was already
    surveyed is the same tile double-detected. Both continue with a
    ledger record instead of failing loud.

    View gate (Round 1.5, `classify`/`escape`): when wired, every tap is
    guarded -- the hub is confirmed before tapping and the post-tap frame is
    classified. A tap that selects one of our unactioned machines lands in a
    unit-move overlay; that is recorded as an ALLY (side="unit_move") through
    the mechanism channel and escaped, never blind-retried on the overlay
    (the 輪五 defeat). Left unwired (both None) the loop keeps the old
    dock-only behaviour.

    Live re-verify (Round 1.9, `detect`/`diag_save`): before sentencing a
    no-banner candidate, the current frame is re-detected at the tap point. No
    unit peak within one cell is current visual proof the point is empty -- the
    candidate drops as a `survey_phantom` (reason `no_unit_at_tap`) with a saved
    diagnostic frame instead of aborting the whole survey; a peak off the tap
    point is a mis-located real unit and is re-tapped once at the peak's true
    pixels (`snap_tap`). A peak with no banner even after the snap still fails
    loud (zero-guess). The existing ghost-of-ally drop keeps priority. Left
    unwired (`detect` None) the loop keeps the old fail-loud-on-no-banner
    behaviour."""
    if not points:
        raise SurveyIncomplete("no enemy points to survey")
    factions = factions or ["enemy"] * len(points)
    deadline = time.monotonic() + wall_clock_s
    radius = cell_size * TAP_PEAK_RADIUS_CELLS

    def record(kind: str, **data) -> None:
        if ledger_log is not None:
            ledger_log(kind, **data)

    # native-resolution diagnostic frames for identify failures, throttled to
    # the first 3 and every 10th thereafter (reuses the Round 1.7 diag pipeline)
    diag_state = {"fails": 0}

    def save_diag(frame, tag: str) -> str | None:
        diag_state["fails"] += 1
        if diag_save is None:
            return None
        n = diag_state["fails"]
        if not (n <= 3 or n % 10 == 0):
            return None
        return diag_save(frame, tag)

    ally_world: list[tuple[float, float]] = list(ally_points or ())

    def ghost_of_ally(point: tuple[float, float]) -> bool:
        return any(
            (point[0] - a[0]) ** 2 + (point[1] - a[1]) ** 2 < GHOST_RADIUS**2
            for a in ally_world
        )

    def drop_ghost(i: int, point, reason: str, **extra) -> None:
        record(
            "survey_phantom",
            index=i,
            world=[round(point[0], 1), round(point[1], 1)],
            reason=reason,
            **extra,
        )
        if dropped is not None:
            dropped.append(i)

    surveyed: list[StageUnit] = []
    ally_cells: list[tuple[int, int]] = []
    claimed: dict[tuple[int, int], int] = {}
    origin = (min(p[0] for p in points), min(p[1] for p in points))
    for i, (point, faction) in enumerate(zip(points, factions)):
        if time.monotonic() >= deadline:
            raise SurveyIncomplete(
                f"wall clock exhausted after {len(surveyed)}/{len(points)} units"
            )
        cell = (
            round((point[0] - origin[0]) / cell_size),
            round((point[1] - origin[1]) / cell_size),
        )
        if identifier is not None and cell in claimed:
            drop_ghost(i, point, f"duplicate_cell_of_{claimed[cell]}")
            continue
        screen = bring_to_view(point)
        if screen is None:
            if ghost_of_ally(point):
                drop_ghost(i, point, "unreachable_near_ally")
                continue
            raise SurveyIncomplete(f"unit {i} at {point} cannot be brought into view")
        if identifier is not None:
            verdict = _identify_at(
                capture, tap, screen, identifier, sleep,
                classify=classify, escape=escape,
            )
            if verdict is None:
                diag = None
                peaks: list[tuple[int, int]] = []
                if detect is not None:
                    frame = capture()
                    diag = save_diag(frame, f"identify_fail_i{i}")
                    peaks = _peaks_near(detect, frame, screen, radius)
                # ghost-of-ally keeps its existing priority (regression pin): a
                # bannerless point hugging a known ally is that ally's twin,
                # sentenced before the live-peak re-verify ever runs.
                if ghost_of_ally(point):
                    drop_ghost(i, point, "no_banner_near_ally", diag=diag)
                    continue
                # no peak under the tap right now = current visual proof the
                # point is empty -> evidence-backed phantom drop, survey continues
                if detect is not None and not peaks:
                    drop_ghost(
                        i,
                        point,
                        "no_unit_at_tap",
                        tap=[round(screen[0], 1), round(screen[1], 1)],
                        diag=diag,
                    )
                    continue
                # a peak off the tap point = a mis-located real unit -> snap once
                if peaks:
                    snap = peaks[0]
                    record(
                        "snap_tap",
                        index=i,
                        origin=[round(screen[0], 1), round(screen[1], 1)],
                        snap=[snap[0], snap[1]],
                    )
                    verdict = _identify_at(
                        capture, tap, snap, identifier, sleep,
                        retries=1, classify=classify, escape=escape,
                    )
                    if verdict is not None:
                        screen = snap
                # a peak that still yields no banner after the snap stays a
                # loud abort: zero guessing, never a fabricated faction
                if verdict is None:
                    raise SurveyIncomplete(
                        f"no summary banner at {screen}"
                        + (f" (diag={diag})" if diag else "")
                    )
            if verdict.faction is Faction.ALLY:
                claimed[cell] = i
                ally_world.append(point)
                ally_cells.append(cell)
                if ally_indices is not None:
                    ally_indices.append(i)
                record(
                    "survey_ally",
                    index=i,
                    cell=list(cell),
                    side=verdict.side,
                    score=round(verdict.score, 3),
                )
                continue
            faction = "enemy"
        try:
            sig, name, stats_dict, weapons = _survey_point(
                capture, tap, screen, llm=llm, sleep=sleep,
                classify=classify, escape=escape,
            )
        except SurveyIncomplete as exc:
            if not str(exc).startswith("no summary card"):
                raise
            if detect is None:
                if ghost_of_ally(point):
                    drop_ghost(i, point, "no_card_near_ally")
                    continue
                raise
            frame = capture()
            diag = save_diag(frame, f"summary_fail_i{i}")
            if ghost_of_ally(point):
                drop_ghost(i, point, "no_card_near_ally", diag=diag)
                continue
            if not _peaks_near(detect, frame, screen, radius):
                drop_ghost(
                    i,
                    point,
                    "no_unit_at_tap",
                    tap=[round(screen[0], 1), round(screen[1], 1)],
                    diag=diag,
                )
                continue
            raise
        claimed[cell] = i
        surveyed.append(
            StageUnit(
                uid="",
                cell=cell,
                faction=faction,
                sig=sig,
                name_text=name,
                pilot_hint={
                    k: v for k, v in stats_dict.items() if k.startswith("pilot_")
                },
                stats=stats_dict,
                weapons=weapons,
            )
        )
        record("survey_unit", index=i, sig=sig, name=name)

    if not surveyed:
        raise SurveyIncomplete("every survey point was ghost-dropped")
    map_cols, map_rows = map_size if map_size is not None else (None, None)
    defn = StageDefinition(
        stage_id=stage_id,
        layout=stage_def.assign_uids(surveyed),
        cell_size=cell_size,
        deploy_slots=[DeploySlot(cell=c) for c in ally_cells],
        map_cols=map_cols,
        map_rows=map_rows,
    )
    path = stage_def.save_stage_def(defn, root)
    log.info("stage definition written: %s (%d units)", path, len(defn.layout))
    record("survey_complete", units=len(defn.layout), stage_id=stage_id)
    return defn


def _spot_sample(defn: StageDefinition, cap: int = VALIDATE_SAMPLE_CAP) -> list[StageUnit]:
    """Spot-check targets: shared-sig groups first (the pilot-difference
    risk this schema exists for), then layout order; deterministic."""
    n = len(defn.layout)
    want = min(cap, max(2, math.ceil(n / 4)))
    shared = [
        u for u in defn.layout if u.sig and len(stage_def.find_by_sig(defn, u.sig)) > 1
    ]
    rest = [u for u in defn.layout if u not in shared]
    return (shared + rest)[:want]


def validate_stage(
    defn: StageDefinition,
    scan_points: list[tuple[float, float]],
    *,
    capture: Callable,
    tap: Callable[[int, int], None],
    bring_to_view: Callable[[tuple[float, float]], tuple[float, float] | None],
    ledger_log: Callable[..., None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> ValidationReport:
    """Warm-start census: free geometry check (the sweep already
    happened) plus a few summary-card spot taps against the file. Any
    mismatch marks the whole stage stale -- the caller falls back to a
    live survey; the screen is authoritative."""
    resolver = IdentityResolver(defn)
    seed = resolver.seed(scan_points)
    report = ValidationReport(ok=False, seed=seed, resolver=resolver)
    if not seed.ok:
        report.mismatches.append(
            f"geometry census failed: {len(seed.unmatched_uids)} layout units "
            f"unmatched, {len(seed.unmatched_points)} scan points unclaimed"
        )
        return report

    def record(kind: str, **data) -> None:
        if ledger_log is not None:
            ledger_log(kind, **data)

    for unit in _spot_sample(defn):
        world = seed.matched[unit.uid]
        screen = bring_to_view(world)
        if screen is None:
            report.mismatches.append(f"{unit.uid}: cannot be brought into view")
            break
        summary = _read_summary_at(capture, tap, screen, sleep)
        report.taps += 1
        if summary is None:
            report.mismatches.append(f"{unit.uid}: no summary card at {world}")
            continue
        try:
            sig_off = signature_distance(summary.name_sig, unit.sig)
        except ValueError:
            sig_off = 64
        if sig_off > stage_def.SIG_CANDIDATE_MAX_DISTANCE:
            report.mismatches.append(
                f"{unit.uid}: sig off by {sig_off} bits vs the definition"
            )
        if summary.hp is not None and unit.stats.get("hp") not in (None, summary.hp):
            report.mismatches.append(
                f"{unit.uid}: opening HP {summary.hp} != definition {unit.stats.get('hp')}"
            )
        if summary.en is not None and unit.stats.get("en") not in (None, summary.en):
            report.mismatches.append(
                f"{unit.uid}: opening EN {summary.en} != definition {unit.stats.get('en')}"
            )
        record("validate_unit", uid=unit.uid, mismatches=report.mismatches[-2:])

    report.ok = not report.mismatches
    return report


def _await_modal(capture: Callable, sleep: Callable[[float], None]):
    for _ in range(MODAL_POLL_TRIES):
        frame = capture()
        if vision.is_unit_detail_modal(frame):
            return frame
        sleep(MODAL_POLL_S)
    return None


def _canonical_sig(sig: str, known: dict[str, tuple[float, float]]) -> str:
    """Resolve a freshly read signature to the tracked key it jitters
    around (same tolerance as the stage cache); unknown sigs pass through."""
    if sig in known:
        return sig
    best, best_distance = None, stage_def.SIG_CANDIDATE_MAX_DISTANCE + 1
    for candidate in known:
        distance = signature_distance(sig, candidate)
        if distance < best_distance:
            best, best_distance = candidate, distance
    return best if best is not None else sig


@dataclass
class RefreshBudget:
    max_taps: int = 6
    max_seconds: float = 25.0


@dataclass
class SigRefresh:
    positions: dict[str, tuple[float, float]] = field(default_factory=dict)
    matched_quietly: int = 0
    taps: int = 0
    unresolved: list[str] = field(default_factory=list)


def refresh_sig_positions(
    capture: Callable,
    tap: Callable[[int, int], None],
    candidates: list[tuple[float, float]],
    known: dict[str, tuple[float, float]],
    *,
    budget: RefreshBudget | None = None,
    ledger_log: Callable[..., None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    resolve: Callable[[str, tuple[float, float]], str | None] | None = None,
) -> SigRefresh:
    """Re-anchor tracked enemy identities to a fresh arc scan so the sig
    match does not decay as enemies move. When a sig and a candidate are
    each other's unique in-radius neighbour the position updates without
    touching the device; contested candidates are confirmed by budgeted
    summary-card taps (phantom-tolerant: no card means no update, and a
    stale card re-reading an already-placed sig is ignored)."""
    budget = budget or RefreshBudget()
    result = SigRefresh()

    def record(kind: str, **data) -> None:
        if ledger_log is not None:
            ledger_log(kind, **data)

    def _dist2(a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2

    radius2 = SIG_MATCH_RADIUS**2
    near_sigs = {
        i: [sig for sig, pos in known.items() if _dist2(point, pos) <= radius2]
        for i, point in enumerate(candidates)
    }
    near_cands = {
        sig: [i for i, point in enumerate(candidates) if _dist2(point, pos) <= radius2]
        for sig, pos in known.items()
    }
    claimed: set[int] = set()
    for sig, cands in near_cands.items():
        if len(cands) == 1 and near_sigs[cands[0]] == [sig]:
            result.positions[sig] = candidates[cands[0]]
            result.matched_quietly += 1
            claimed.add(cands[0])

    unresolved = [sig for sig in known if sig not in result.positions]
    if unresolved:
        contested = [i for i in range(len(candidates)) if i not in claimed]

        def _closeness(i: int) -> float:
            return min(_dist2(candidates[i], known[sig]) for sig in unresolved)

        deadline = time.monotonic() + budget.max_seconds
        for i in sorted(contested, key=_closeness):
            if not unresolved or result.taps >= budget.max_taps:
                break
            if time.monotonic() >= deadline:
                log.info("sig refresh budget (time) exhausted")
                break
            point = candidates[i]
            tap(int(point[0]), int(point[1]))
            result.taps += 1
            sleep(SUMMARY_SETTLE_S)
            summary = vision.read_enemy_summary(capture())
            sig = summary.name_sig if summary is not None else None
            if sig is None:
                record("sig_refresh", point=list(point), result="no_card")
                continue
            # known is keyed by identity (uid when a resolver is wired in,
            # raw sig otherwise); map the card's raw sig onto that keyspace
            if resolve is not None:
                resolved = resolve(sig, point)
                if resolved is None:
                    record("sig_refresh", sig=sig, point=list(point), result="unresolved")
                    continue
                sig = resolved
            else:
                sig = _canonical_sig(sig, known)
            if sig in result.positions:
                record("sig_refresh", sig=sig, point=list(point), result="stale_card")
                continue
            result.positions[sig] = point
            record("sig_refresh", sig=sig, point=list(point), result="ok")
            if sig in unresolved:
                unresolved.remove(sig)

    result.unresolved = [sig for sig in known if sig not in result.positions]
    return result
