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

log = logging.getLogger(__name__)

SUMMARY_CARD_TAP = (760, 180)
WEAPONS_TAB_TAP = (1381, 173)
UNIT_DETAIL_CLOSE = (1176, 992)
SUMMARY_SETTLE_S = 1.2
MODAL_SETTLE_S = 1.5
MODAL_POLL_S = 0.5
MODAL_POLL_TRIES = 6


@dataclass
class IntelBudget:
    max_panels: int = 6
    max_seconds: float = 90.0


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
    intel = StageIntel()
    cached = stage_cache.load_stage(stage_id, cache_root) if stage_id else {}
    updated: dict[str, stage_cache.CachedUnit] = dict(cached)
    deadline = time.monotonic() + budget.max_seconds

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

        if intel.panels_opened >= budget.max_panels:
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
