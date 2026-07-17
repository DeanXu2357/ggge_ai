"""IdentityResolver: observations -> backend uids.

The knife sits at the BattleState boundary: everything upstream
(vision, scouting, summary cards) keeps speaking evidence -- sig, world
position, HP/EN -- and this resolver combines that evidence against the
stage definition's layout prior to produce the uid that everything
downstream (bridge, sim, solver, tracker, reconcile) treats as the
unit's one identity. Sig is a candidate filter here, never a key:
several uids legitimately share one machine sig, which is the reason
this layer exists.

Evidence order: initial cell assignment (seed, mutual nearest against
the layout), position continuity across turns (mutual unique neighbour,
ambiguity left for a tap to confirm), sig narrowing the candidate set,
HP/EN arbitration staying with the caller. Two resolution registers:
survey/validation callers treat a failed seed as fail-loud; per-turn
callers treat an unresolved point as a drop-with-note or a new-unit
candidate (event observation), never a guess.

Passthrough mode (no definition) exists for the replay harness and
offline tests only: uids degrade to "sig:<hex>" so sig-keyed corpora
keep replaying. The live path is always seeded or fails loudly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..content.stage_def import (
    SIG_CANDIDATE_MAX_DISTANCE,
    StageDefinition,
    find_by_sig,
    signature_distance,
)

Point = tuple[float, float]

# a tap and the arc-scan center of the same unit can sit a cell apart;
# 1.5 cells at the measured ~95px pitch (same constant as observe.py)
MATCH_RADIUS = 145.0
# a seeded layout cell must claim a scan point well inside its own cell
SEED_RADIUS_CELLS = 0.75


@dataclass
class SeedReport:
    matched: dict[str, Point] = field(default_factory=dict)
    unmatched_uids: list[str] = field(default_factory=list)
    unmatched_points: list[Point] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.unmatched_uids and not self.unmatched_points


@dataclass
class RefreshReport:
    updated: dict[str, Point] = field(default_factory=dict)
    ambiguous_points: list[Point] = field(default_factory=list)
    unmatched_uids: list[str] = field(default_factory=list)


def _d2(a: Point, b: Point) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _mutual_pairs(
    expected: dict[str, Point], points: list[Point], max_d2: float
) -> dict[str, int]:
    """Greedy best assignment by ascending distance -- for seeding, where
    the tight per-cell threshold makes the pairing effectively bijective."""
    pairs = sorted(
        (
            (_d2(pos, point), uid, i)
            for uid, pos in expected.items()
            for i, point in enumerate(points)
            if _d2(pos, point) <= max_d2
        ),
    )
    taken_uids: set[str] = set()
    taken_points: set[int] = set()
    out: dict[str, int] = {}
    for _, uid, i in pairs:
        if uid in taken_uids or i in taken_points:
            continue
        taken_uids.add(uid)
        taken_points.add(i)
        out[uid] = i
    return out


def _unique_pairs(
    expected: dict[str, Point], points: list[Point], max_d2: float
) -> dict[str, int]:
    """Mutually unique neighbours only -- the refresh safety property
    (same rule as scout_intel's quiet update): a point claimed by two
    uids, or a uid seeing two points, stays contested for a tap."""
    uid_near = {
        uid: [i for i, p in enumerate(points) if _d2(pos, p) <= max_d2]
        for uid, pos in expected.items()
    }
    point_near: dict[int, list[str]] = {}
    for uid, near in uid_near.items():
        for i in near:
            point_near.setdefault(i, []).append(uid)
    return {
        uid: near[0]
        for uid, near in uid_near.items()
        if len(near) == 1 and len(point_near[near[0]]) == 1
    }


class IdentityResolver:
    def __init__(self, defn: StageDefinition | None = None):
        self.defn = defn
        self._positions: dict[str, Point] = {}
        self._dead: set[str] = set()
        self._spawned: set[str] = set()
        self._sig_registry: dict[str, list[str]] = {}
        self._grid: tuple[Point, tuple[int, int]] | None = None

    @property
    def passthrough(self) -> bool:
        return self.defn is None

    def seed(self, scan_points: list[Point]) -> SeedReport:
        """Bind the layout to a full opening sweep: the scan's min corner
        anchors the stage grid (ally deployment never does), then layout
        cells claim points by mutual nearest inside their own cell. A
        report that is not ok is a validation failure -- survey callers
        must fail loudly, not proceed on a partial board."""
        if self.defn is None:
            raise ValueError("cannot seed a passthrough resolver")
        report = SeedReport()
        layout = self.defn.layout
        if not layout or not scan_points:
            report.unmatched_uids = [u.uid for u in layout]
            report.unmatched_points = list(scan_points)
            return report
        cell = self.defn.cell_size
        origin = (min(p[0] for p in scan_points), min(p[1] for p in scan_points))
        cmin = (min(u.cell[0] for u in layout), min(u.cell[1] for u in layout))
        self._grid = (origin, cmin)
        expected = {
            u.uid: (
                origin[0] + (u.cell[0] - cmin[0]) * cell,
                origin[1] + (u.cell[1] - cmin[1]) * cell,
            )
            for u in layout
        }
        matched = _mutual_pairs(expected, scan_points, (cell * SEED_RADIUS_CELLS) ** 2)
        for uid, i in matched.items():
            report.matched[uid] = scan_points[i]
        report.unmatched_uids = [u.uid for u in layout if u.uid not in matched]
        matched_points = set(matched.values())
        report.unmatched_points = [
            p for i, p in enumerate(scan_points) if i not in matched_points
        ]
        if report.ok:
            self._positions = dict(report.matched)
        return report

    def positions(self) -> dict[str, Point]:
        return {
            uid: pos for uid, pos in self._positions.items() if uid not in self._dead
        }

    def refresh(self, scan_points: list[Point]) -> RefreshReport:
        """Per-turn position continuity: mutually unique neighbours update
        quietly; contested points stay ambiguous for the caller to
        disambiguate with a tap (summary card -> sig -> confirm)."""
        report = RefreshReport()
        known = self.positions()
        matched = _unique_pairs(known, scan_points, MATCH_RADIUS**2)
        for uid, i in matched.items():
            self._positions[uid] = scan_points[i]
            report.updated[uid] = scan_points[i]
        matched_points = set(matched.values())
        report.ambiguous_points = [
            p for i, p in enumerate(scan_points) if i not in matched_points
        ]
        report.unmatched_uids = [uid for uid in known if uid not in matched]
        return report

    def confirm(self, uid: str, world: Point) -> None:
        self._positions[uid] = world
        self._dead.discard(uid)

    def candidates(self, sig: str | None) -> list[str]:
        if self.defn is None:
            return [f"sig:{sig}"] if sig else []
        return [u.uid for u in find_by_sig(self.defn, sig) if u.uid not in self._dead]

    def resolve(self, world: Point, sig: str | None = None) -> str | None:
        """Position continuity first, sig narrowing second; a unique
        survivor is an identity, anything else is None (the caller
        decides between drop-with-note and new-unit candidate)."""
        if self.defn is None:
            return f"sig:{sig}" if sig else None
        near = sorted(
            (
                (d2, uid)
                for uid, pos in self.positions().items()
                if (d2 := _d2(pos, world)) <= MATCH_RADIUS**2
            ),
        )
        pool = [uid for _, uid in near]
        if sig is not None:
            sig_pool = set(self.candidates(sig))
            pool = [uid for uid in pool if uid in sig_pool]
        if len(pool) == 1:
            return pool[0]
        return None

    def sig_uid(self, sig: str, namespace: str = "enemy") -> str:
        """Degraded sig-keyed uid with jitter merging (the old tracker
        _canonical rule): the first signature seen within tolerance is
        the canonical representative for its namespace. Allies always
        take this path -- ally identity is learned incrementally and
        never lives in the stage definition -- and so does everything in
        passthrough mode."""
        registry = self._sig_registry.setdefault(namespace, [])
        for existing in registry:
            try:
                if signature_distance(sig, existing) <= SIG_CANDIDATE_MAX_DISTANCE:
                    return f"sig:{existing}"
            except ValueError:
                continue
        registry.append(sig)
        return f"sig:{sig}"

    def uid_for(
        self, sig: str, namespace: str = "enemy", world: Point | None = None
    ) -> str | None:
        """Sig-first resolution for the screen-read hooks (forecasts,
        intel, panels). Ally and passthrough identities degrade to
        canonical sig uids; a seeded enemy sig narrows to its candidate
        set, position arbitrating when the sig is shared. None means the
        hook should skip with a note rather than guess."""
        if self.defn is None or namespace == "ally":
            return self.sig_uid(sig, namespace)
        pool = self.candidates(sig)
        if world is not None and len(pool) > 1:
            near = {
                uid
                for uid, pos in self.positions().items()
                if _d2(pos, world) <= MATCH_RADIUS**2
            }
            narrowed = [uid for uid in pool if uid in near]
            if narrowed:
                pool = narrowed
        if len(pool) == 1:
            return pool[0]
        return None

    def expected_sig(self, uid: str) -> str | None:
        """The signature this uid should show on a name plate -- the
        executor's composite target verification reads it."""
        if uid.startswith("sig:"):
            return uid[len("sig:") :]
        if self.defn is None:
            return None
        for unit in self.defn.layout:
            if unit.uid == uid:
                return unit.sig
        for event in self.defn.events:
            for unit in event.spawn_units():
                if unit.uid == uid:
                    return unit.sig
        return None

    def world_to_cell(self, world: Point) -> tuple[int, int] | None:
        """Invert the seed transform: a world point back onto the stage
        grid the layout cells were recorded in. None before seeding."""
        if self._grid is None or self.defn is None:
            return None
        origin, cmin = self._grid
        size = self.defn.cell_size
        return (
            cmin[0] + round((world[0] - origin[0]) / size),
            cmin[1] + round((world[1] - origin[1]) / size),
        )

    def register_death(self, uid: str) -> None:
        self._dead.add(uid)

    def register_spawn(self, uid: str, world: Point) -> None:
        self._spawned.add(uid)
        self.confirm(uid, world)

    def expected_alive(self, faction: str = "enemy") -> int | None:
        """The definition-backed denominator for the observer's missing-
        enemy detection (M8-1). None in passthrough -- no prior, no
        denominator."""
        if self.defn is None:
            return None
        uids = {u.uid for u in self.defn.layout if u.faction == faction}
        for event in self.defn.events:
            for unit in event.spawn_units():
                if unit.faction == faction and unit.uid in self._spawned:
                    uids.add(unit.uid)
        return len(uids - self._dead)
