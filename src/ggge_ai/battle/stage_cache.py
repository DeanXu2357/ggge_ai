"""Perception-memoized stage intel cache (data/cache/stages/).

Permitted content cache per the 2026-07-05 red-line revision: everything
in here originated from screen reads (panel OCR) with LLM name text as
advisory metadata. The screen stays authoritative -- a signature census
mismatch or any load failure falls back to live reading, and current HP
is never served from here (only identity and base kit).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .bridge import UnitSpec
from .panels import UnitStats, WeaponRow, to_unit_spec
from .vision import signature_distance

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DEFAULT_CACHE_ROOT = Path("data") / "cache" / "stages"
# dHash bits two renders of the same name plate may plausibly differ by;
# measured 0 across +/-4px shifts, so 6 is generous without aliasing the
# 25+-bit gaps between different units
SIG_MATCH_MAX_DISTANCE = 6


@dataclass
class CachedUnit:
    sig: str
    name_text: str | None = None
    stats: dict = field(default_factory=dict)
    weapons: list[dict] = field(default_factory=list)

    def to_spec(self) -> tuple[UnitSpec, list[str]]:
        unit_stats = UnitStats(**self.stats)
        rows = [WeaponRow(**w) for w in self.weapons]
        return to_unit_spec(unit_stats, rows)


def stage_path(stage_id: str, root: Path | None = None) -> Path:
    safe = stage_id.replace("..", "_")
    return (root or DEFAULT_CACHE_ROOT) / f"{safe}.json"


def load_stage(stage_id: str, root: Path | None = None) -> dict[str, CachedUnit]:
    """The cached units of a stage keyed by signature; empty on any
    problem -- a broken cache must never block a live read."""
    path = stage_path(stage_id, root)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != SCHEMA_VERSION:
            log.info("stage cache %s has schema %s, ignoring", path, data.get("schema"))
            return {}
        return {
            sig: CachedUnit(
                sig=sig,
                name_text=unit.get("name_text"),
                stats=unit.get("stats", {}),
                weapons=unit.get("weapons", []),
            )
            for sig, unit in data.get("units", {}).items()
        }
    except (json.JSONDecodeError, OSError, TypeError) as exc:
        log.warning("stage cache %s unreadable (%s), falling back to live reads", path, exc)
        return {}


def save_stage(stage_id: str, units: dict[str, CachedUnit], root: Path | None = None) -> Path:
    path = stage_path(stage_id, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA_VERSION,
        "stage_id": stage_id,
        "units": {
            sig: {k: v for k, v in asdict(unit).items() if k != "sig"}
            for sig, unit in units.items()
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def find(units: dict[str, CachedUnit], sig: str | None) -> CachedUnit | None:
    """Exact signature hit, else the nearest within tolerance (rendering
    jitter), else None."""
    if sig is None or not units:
        return None
    if sig in units:
        return units[sig]
    best_sig, best_distance = None, SIG_MATCH_MAX_DISTANCE + 1
    for candidate in units:
        distance = signature_distance(sig, candidate)
        if distance < best_distance:
            best_sig, best_distance = candidate, distance
    if best_sig is not None and best_distance <= SIG_MATCH_MAX_DISTANCE:
        return units[best_sig]
    return None
