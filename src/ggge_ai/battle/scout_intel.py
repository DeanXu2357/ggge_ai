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

from . import panels, stage_def, vision
from ..content.kit import UnitSpec
from .identity import IdentityResolver, SeedReport
from .observe import SIG_MATCH_RADIUS
from .stage_def import StageDefinition, StageUnit

log = logging.getLogger(__name__)

# live-calibrated 2026-07-14 on HARD 1 (Sazabi EX sample, free abandon):
# the enemy summary card docks at the TOP-RIGHT of the battle map -- the
# old (760, 180) guess pointed at empty map. Tapping the card opens the
# unit-detail modal, which lands on the weapons tab directly; the tab tap
# is kept as an idempotent safety. ABILITY_TAB_TAP reaches the 能力、OP
# page (trait corpus for issues #21/#22).
SUMMARY_CARD_TAP = (1510, 205)
WEAPONS_TAB_TAP = (1381, 173)
ABILITY_TAB_TAP = (1813, 176)
UNIT_DETAIL_CLOSE = (1176, 992)
SUMMARY_SETTLE_S = 1.2
MODAL_SETTLE_S = 1.5
MODAL_POLL_S = 0.5
MODAL_POLL_TRIES = 6

SURVEY_WALL_CLOCK_S = 1200.0
SURVEY_TAP_RETRIES = 3
VALIDATE_SAMPLE_CAP = 4


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


def _read_summary_at(
    capture, tap, screen, sleep, *, retries: int = SURVEY_TAP_RETRIES
):
    for _ in range(retries):
        tap(int(screen[0]), int(screen[1]))
        sleep(SUMMARY_SETTLE_S)
        summary = vision.read_enemy_summary(capture())
        if summary is not None and summary.name_sig is not None:
            return summary
    return None


def _survey_point(
    capture: Callable,
    tap: Callable[[int, int], None],
    screen: tuple[float, float],
    *,
    llm,
    sleep: Callable[[float], None],
) -> tuple[str, str | None, dict, list[dict]]:
    """One unit's full read at a screen point: summary card -> detail
    panel -> stats/weapons (+ LLM name). Raises SurveyIncomplete on any
    unreadable step; the caller decides whether that is fatal (opening
    survey) or a soft note (mid-battle reinforcement)."""
    summary = _read_summary_at(capture, tap, screen, sleep)
    if summary is None:
        raise SurveyIncomplete(f"no summary card at {screen}")
    tap(*SUMMARY_CARD_TAP)
    sleep(MODAL_SETTLE_S)
    modal = _await_modal(capture, sleep)
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
    llm=None,
    ledger_log: Callable[..., None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    wall_clock_s: float = SURVEY_WALL_CLOCK_S,
    cell_size: float = 95.0,
    root: Path | None = None,
) -> StageDefinition:
    """Full survey of every non-ally point (world coordinates from the
    serpentine sweep) into a saved schema-2 definition. Raises
    SurveyIncomplete on the first unreadable unit or on the wall-clock
    guard -- partial definitions are never written."""
    if not points:
        raise SurveyIncomplete("no enemy points to survey")
    factions = factions or ["enemy"] * len(points)
    deadline = time.monotonic() + wall_clock_s

    def record(kind: str, **data) -> None:
        if ledger_log is not None:
            ledger_log(kind, **data)

    surveyed: list[StageUnit] = []
    origin = (min(p[0] for p in points), min(p[1] for p in points))
    for i, (point, faction) in enumerate(zip(points, factions)):
        if time.monotonic() >= deadline:
            raise SurveyIncomplete(
                f"wall clock exhausted after {len(surveyed)}/{len(points)} units"
            )
        screen = bring_to_view(point)
        if screen is None:
            raise SurveyIncomplete(f"unit {i} at {point} cannot be brought into view")
        sig, name, stats_dict, weapons = _survey_point(
            capture, tap, screen, llm=llm, sleep=sleep
        )
        cell = (
            round((point[0] - origin[0]) / cell_size),
            round((point[1] - origin[1]) / cell_size),
        )
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

    defn = StageDefinition(
        stage_id=stage_id,
        layout=stage_def.assign_uids(surveyed),
        cell_size=cell_size,
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
            sig_off = vision.signature_distance(summary.name_sig, unit.sig)
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
        distance = vision.signature_distance(sig, candidate)
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
