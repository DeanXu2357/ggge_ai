"""Stage definition file: the solver's complete game description.

Schema v2 supersedes the sig-keyed kit cache (stage_cache, schema 1):
layout entries carry a backend-issued uid as the unit's sole identity --
the name-plate sig is demoted to matching evidence, because two units of
the same machine share a sig while their pilots differ. Conditions and
events make objective-driven search and in-tree reinforcement expansion
possible; both tolerate types outside the v1 taxonomy (recorded
verbatim, inert to the planner).

Schema v3 splits our deployed squad out of `layout` into `deploy_slots`:
the slot *positions* are stage content (the game always deploys onto the
same fixed cells), while the unit standing on each slot is per-sortie
content that must never be cached (2026-07-20 user ruling on the ex2if
scan, where 10 of 27 scanned units turned out to be the sortie squad).

Permitted content cache per the 2026-07-05 red-line revision: everything
here originated from screen reads or manual transcription, the screen
stays authoritative (opening census validation; any mismatch expires the
whole stage back to live reading), and ally actuals are never cached.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .kit import UnitSpec, UnitStats, WeaponRow, to_unit_spec

log = logging.getLogger(__name__)

SCHEMA_VERSION = 3
DEFAULT_STAGE_ROOT = Path("data") / "cache" / "stages"
# same tolerance as the retired stage_cache constant: measured 0 bits of
# drift across +/-4px name-plate shifts, 25+ bits between different units
SIG_CANDIDATE_MAX_DISTANCE = 6

UID_PREFIX = {"enemy": "e", "third_party": "t"}


def signature_distance(a: str | None, b: str | None) -> int:
    """Hamming distance between two name signatures; unknowns are maximally
    distant so a None never aliases a real unit."""
    if a is None or b is None:
        return 64
    return (int(a, 16) ^ int(b, 16)).bit_count()


@dataclass
class StageUnit:
    """One layout (or reinforcement) entry. `cell` is (col, row) on the
    stage grid; map-scan-produced files anchor the origin at the map's NW
    corner (corner-anchored sweep, 定案 1), legacy survey files used the
    min corner over enemy and third-party starting cells. Either way the
    sortie squad never anchors the frame -- it lives in deploy_slots, not
    layout. `pilot_hint` snapshots the detail panel's pilot column at
    survey time: it is what distinguishes two uids that share a machine
    sig, and it is survey-time evidence only (never a live-read
    substitute)."""

    uid: str
    cell: tuple[int, int]
    faction: str = "enemy"
    # cells occupied, (cols, rows) anchored at `cell` as the NW corner;
    # (1,1) for every unit except oversized ones (2x2 and 3x2 confirmed
    # on the 20260719 ex2if survey). Ring geometry cannot derive this --
    # both large units there were misjudged from their rings; footprints
    # come from in-game confirmation until a move-range/blocking probe
    # exists.
    footprint: tuple[int, int] = (1, 1)
    sig: str | None = None
    name_text: str | None = None
    pilot_hint: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    weapons: list[dict] = field(default_factory=list)
    abilities: list[dict] = field(default_factory=list)

    def to_spec(self) -> tuple[UnitSpec, list[str]]:
        unit_stats = UnitStats(**self.stats)
        rows = [WeaponRow(**w) for w in self.weapons]
        return to_unit_spec(unit_stats, rows)


@dataclass
class DeploySlot:
    """One fixed deployment cell. The game maps roster team/slot numbers
    onto these cells by its own placement logic; `observed` records the
    (team, slot) seen standing here on past sorties, so the number-to-cell
    mapping stays an accumulating hypothesis until repeated sorties confirm
    it. Team ordering is the assignable planning variable -- which actual
    unit occupies a slot is per-sortie content and is never cached."""

    cell: tuple[int, int]
    observed: list[dict] = field(default_factory=list)


@dataclass
class Condition:
    """`type` from the v1 taxonomy (annihilate / decapitate / protect /
    turn_limit / reach and the defeat mirrors) or anything else recorded
    verbatim and inert. `source`: screen | manual | default."""

    type: str
    params: dict = field(default_factory=dict)
    text: str | None = None
    source: str = "default"


@dataclass
class StageConditions:
    victory: list[Condition] = field(default_factory=list)
    defeat: list[Condition] = field(default_factory=list)


def default_conditions() -> StageConditions:
    return StageConditions(
        victory=[Condition(type="annihilate")],
        defeat=[Condition(type="all_allies_lost")],
    )


@dataclass
class StageEvent:
    """trigger -> board change. Reinforcement units inside a spawn effect
    are pre-issued uids at first observation, so the second playthrough
    already knows them. `observations` keeps the raw first-blind-run
    records that justified the trigger; contradictions between plays are
    reported to the user, never auto-rewritten."""

    event_id: str
    trigger: dict
    effect: dict
    source: str = "observed"
    observations: list[dict] = field(default_factory=list)

    def spawn_units(self) -> list[StageUnit]:
        if self.effect.get("type") != "spawn":
            return []
        return [_unit_from_dict(u) for u in self.effect.get("units", [])]


@dataclass
class StageDefinition:
    stage_id: str
    layout: list[StageUnit] = field(default_factory=list)
    deploy_slots: list[DeploySlot] = field(default_factory=list)
    conditions: StageConditions = field(default_factory=default_conditions)
    events: list[StageEvent] = field(default_factory=list)
    status: str = "complete"
    game_version: str | None = None
    cell_size: float = 95.0


def stage_path(stage_id: str, root: Path | None = None) -> Path:
    safe = stage_id.replace("..", "_")
    return (root or DEFAULT_STAGE_ROOT) / f"{safe}.json"


def assign_uids(units: list[StageUnit]) -> list[StageUnit]:
    """Issue uids in row-major cell order (row, then col), per faction
    prefix. Cell order is the only input: scan order is an implementation
    detail of the serpentine sweep and would not reproduce across program
    versions, while the board itself does. Once a definition file is
    written it is authoritative -- later sessions parse, never re-issue."""
    counters: dict[str, int] = {}
    out = []
    for unit in sorted(units, key=lambda u: (u.cell[1], u.cell[0])):
        prefix = UID_PREFIX.get(unit.faction, unit.faction[:1] or "u")
        counters[prefix] = counters.get(prefix, 0) + 1
        unit.uid = f"{prefix}{counters[prefix]:02d}"
        out.append(unit)
    return out


def next_uid(defn: StageDefinition, prefix: str = "e") -> str:
    """The next free uid for an observed reinforcement -- pre-issued at
    first observation so the second playthrough already knows it."""
    taken = [u.uid for u in defn.layout]
    for event in defn.events:
        taken.extend(u.uid for u in event.spawn_units())
    highest = 0
    for uid in taken:
        if uid.startswith(prefix) and uid[len(prefix) :].isdigit():
            highest = max(highest, int(uid[len(prefix) :]))
    return f"{prefix}{highest + 1:02d}"


def append_observed_spawn(
    defn: StageDefinition,
    units: list[StageUnit],
    *,
    turn: int,
    observations: list[dict],
) -> StageEvent:
    """First-blind-run event recording: v1 infers the conservative
    turn_start trigger at the observed turn; the raw observations stay in
    the file so a contradicting second playthrough is reported to the
    user, never auto-rewritten."""
    highest = 0
    for event in defn.events:
        tail = event.event_id.removeprefix("ev")
        if tail.isdigit():
            highest = max(highest, int(tail))
    event = StageEvent(
        event_id=f"ev{highest + 1}",
        trigger={"type": "turn_start", "turn": turn},
        effect={"type": "spawn", "units": [asdict(u) for u in units]},
        source="observed",
        observations=observations,
    )
    defn.events.append(event)
    return event


def find_by_sig(defn: StageDefinition, sig: str | None) -> list[StageUnit]:
    """All units whose recorded sig sits within rendering-jitter
    tolerance -- a candidate set, not an identity: several uids sharing
    one machine sig is the normal case this schema exists to represent.
    Searches layout and reinforcement spawns alike."""
    if sig is None:
        return []
    pool = list(defn.layout)
    for event in defn.events:
        pool.extend(event.spawn_units())
    out = []
    for unit in pool:
        if unit.sig is None:
            continue
        try:
            if signature_distance(sig, unit.sig) <= SIG_CANDIDATE_MAX_DISTANCE:
                out.append(unit)
        except ValueError:
            continue
    return out


def _unit_from_dict(data: dict) -> StageUnit:
    return StageUnit(
        uid=data.get("uid", ""),
        cell=tuple(data.get("cell", (0, 0))),
        faction=data.get("faction", "enemy"),
        footprint=tuple(data.get("footprint", (1, 1))),
        sig=data.get("sig"),
        name_text=data.get("name_text"),
        pilot_hint=data.get("pilot_hint", {}),
        stats=data.get("stats", {}),
        weapons=data.get("weapons", []),
        abilities=data.get("abilities", []),
    )


def _slot_from_dict(data: dict) -> DeploySlot:
    return DeploySlot(
        cell=tuple(data.get("cell", (0, 0))),
        observed=data.get("observed", []),
    )


def _condition_from_dict(data: dict) -> Condition:
    return Condition(
        type=data.get("type", "verbatim"),
        params=data.get("params", {}),
        text=data.get("text"),
        source=data.get("source", "default"),
    )


def load_stage_def(stage_id: str, root: Path | None = None) -> StageDefinition | None:
    """None on any problem -- a broken or older-schema file must never
    block a live survey."""
    path = stage_path(stage_id, root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != SCHEMA_VERSION:
            log.info("stage def %s has schema %s, ignoring", path, data.get("schema"))
            return None
        conditions = data.get("conditions", {})
        return StageDefinition(
            stage_id=data.get("stage_id", stage_id),
            layout=[_unit_from_dict(u) for u in data.get("layout", [])],
            deploy_slots=[_slot_from_dict(s) for s in data.get("deploy_slots", [])],
            conditions=StageConditions(
                victory=[_condition_from_dict(c) for c in conditions.get("victory", [])],
                defeat=[_condition_from_dict(c) for c in conditions.get("defeat", [])],
            ),
            events=[
                StageEvent(
                    event_id=e.get("event_id", f"ev{i}"),
                    trigger=e.get("trigger", {}),
                    effect=e.get("effect", {}),
                    source=e.get("source", "observed"),
                    observations=e.get("observations", []),
                )
                for i, e in enumerate(data.get("events", []), start=1)
            ],
            status=data.get("status", "complete"),
            game_version=data.get("game_version"),
            cell_size=float(data.get("cell_size", 95.0)),
        )
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        log.warning("stage def %s unreadable (%s), falling back to live survey", path, exc)
        return None


def save_stage_def(defn: StageDefinition, root: Path | None = None) -> Path:
    path = stage_path(defn.stage_id, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA_VERSION,
        "game_version": defn.game_version,
        "stage_id": defn.stage_id,
        "status": defn.status,
        "cell_size": defn.cell_size,
        "layout": [asdict(u) for u in defn.layout],
        "deploy_slots": [asdict(s) for s in defn.deploy_slots],
        "conditions": {
            "victory": [asdict(c) for c in defn.conditions.victory],
            "defeat": [asdict(c) for c in defn.conditions.defeat],
        },
        "events": [asdict(e) for e in defn.events],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
