"""Turn-1 enemy intel acquisition: tap enemies, read their panels, fill
specs_by_sig for the reconciliation chain.

Flow per enemy point (until the budget runs out): tap the unit -> the
summary card pops (sig + current HP/EN) -> known sig? record position
only. New sig with a cache entry? take the cached kit ([cache] hit). New
sig without one? open the detail modal, switch to the weapons tab, parse
stats and rows, cache the result, close the modal.

The screen is authoritative: a summary card whose signature has no
plausible cache match marks the cache stale for this stage (ledger
`cache_stale`) and everything is re-read live. Budget exhaustion is not
an error -- unscouted enemies simply stay spec-less and the bridge's
assumption machinery reports them.

Interaction constants (tab tap point, settle times) are calibrated from
the 20260705 capture sequence; they get one live confirmation pass in the
M3b validation battle before this flow is trusted in the clear loop.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import panels, stage_cache, vision
from .bridge import UnitSpec
from .observe import SIG_MATCH_RADIUS

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


@dataclass
class IntelBudget:
    """None means dynamic (user's 2026-07-14 call): follow the number of
    enemy candidates on the board, capped, so no stage loses enemies to a
    fixed panel count; explicit values stay fixed for tests and probes."""

    max_panels: int | None = None
    max_seconds: float | None = None

    DYNAMIC_PANEL_CAP = 12
    SECONDS_PER_PANEL = 15.0
    SECONDS_SLACK = 30.0

    def resolve(self, candidates: int) -> tuple[int, float]:
        panels = (
            self.max_panels
            if self.max_panels is not None
            else min(self.DYNAMIC_PANEL_CAP, candidates)
        )
        seconds = (
            self.max_seconds
            if self.max_seconds is not None
            else self.SECONDS_PER_PANEL * panels + self.SECONDS_SLACK
        )
        return panels, seconds


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


def acquire_stage_intel(
    capture: Callable,
    tap: Callable[[int, int], None],
    enemy_points: list[tuple[int, int]],
    *,
    stage_id: str | None = None,
    cache_root: Path | None = None,
    llm=None,
    budget: IntelBudget | None = None,
    ledger_log: Callable[..., None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> StageIntel:
    budget = budget or IntelBudget()
    max_panels, max_seconds = budget.resolve(len(enemy_points))
    intel = StageIntel()
    cached = stage_cache.load_stage(stage_id, cache_root) if stage_id else {}
    updated: dict[str, stage_cache.CachedUnit] = dict(cached)
    deadline = time.monotonic() + max_seconds

    def record(kind: str, **data) -> None:
        if ledger_log is not None:
            ledger_log(kind, **data)

    for point in enemy_points:
        if time.monotonic() >= deadline:
            log.info("intel budget (time) exhausted, %d enemies unscouted", 0)
            break
        tap(*point)
        sleep(SUMMARY_SETTLE_S)
        frame = capture()
        summary = vision.read_enemy_summary(frame)
        if summary is None or summary.name_sig is None:
            log.debug("no summary card at %s, skipping", point)
            continue
        sig = summary.name_sig
        if sig in intel.summaries:
            continue
        intel.summaries[sig] = summary
        intel.positions[sig] = point

        hit = stage_cache.find(cached, sig)
        if hit is not None:
            spec, assumptions = hit.to_spec()
            intel.specs_by_sig[sig] = spec
            intel.assumptions[sig] = assumptions
            if hit.name_text:
                intel.names[sig] = hit.name_text
            intel.cache_hits += 1
            record("unit_intel", sig=sig, source="cache", name=hit.name_text)
            continue

        if cached and not intel.cache_stale:
            intel.cache_stale = True
            log.warning("signature %s not in the stage cache -- cache stale, re-reading live", sig)
            record("cache_stale", sig=sig, stage_id=stage_id)

        if intel.panels_opened >= max_panels:
            log.info("intel budget (panels) exhausted, %s stays spec-less", sig[:6])
            continue

        tap(*SUMMARY_CARD_TAP)
        sleep(MODAL_SETTLE_S)
        modal = _await_modal(capture, sleep)
        if modal is None:
            log.warning("detail modal did not open for %s, skipping", sig[:6])
            continue
        intel.panels_opened += 1
        tap(*WEAPONS_TAB_TAP)
        sleep(MODAL_SETTLE_S)
        modal = capture()
        stats = panels.parse_unit_stats(modal)
        rows = panels.parse_weapon_rows(modal)
        name = None
        if llm is not None:
            x, y, w, h = vision.FORECAST_LEFT_NAME_REGION
            name = llm.transcribe(
                frame[y : y + h, x : x + w],
                "Transcribe the unit name on this game UI name plate "
                "(Traditional Chinese / Japanese, single line).",
            )
        if stats is None:
            log.warning("stat column unreadable for %s", sig[:6])
        else:
            spec, assumptions = panels.to_unit_spec(stats, rows)
            if not rows:
                assumptions = [*assumptions, "no weapon rows read (wrong tab or scrolled)"]
            intel.specs_by_sig[sig] = spec
            intel.assumptions[sig] = assumptions
            if name:
                intel.names[sig] = name
            updated[sig] = stage_cache.CachedUnit(
                sig=sig,
                name_text=name,
                stats={k: getattr(stats, k) for k in stats.__dataclass_fields__},
                weapons=[{k: getattr(r, k) for k in r.__dataclass_fields__} for r in rows],
            )
            record(
                "unit_intel",
                frame=modal,
                sig=sig,
                source="panel",
                name=name,
                assumptions=intel.assumptions[sig],
            )
        tap(*UNIT_DETAIL_CLOSE)
        sleep(MODAL_SETTLE_S)

    if stage_id and updated != cached:
        path = stage_cache.save_stage(stage_id, updated, cache_root)
        log.info("stage cache updated: %s (%d units)", path, len(updated))
    return intel


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
    best, best_distance = None, stage_cache.SIG_MATCH_MAX_DISTANCE + 1
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
