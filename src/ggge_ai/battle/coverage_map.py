"""Coverage-driven scan state (#26 批2): a frame observation reader and a
global cell-space map that localises frames by relative evidence only.

The design red lines (coverage-scan-plan 定案 2026-07-23):
- no gesture / displacement quantity is ever an input -- localisation reads
  only the frame's own relative structure (unit constellation, per-cell terrain
  fingerprints, visible map boundaries) against the accumulated map;
- boundaries count only when SEEN, and once registered they pin an axis exactly
  (定案 1: edges never move);
- when the evidence does not clear a margin the map refuses to place the frame
  (returns None) rather than guess -- a wrong integer offset silently poisons
  the whole board, so "rather not localise" beats "localise wrong".

The map keeps an arbitrary internal origin (the first anchored frame's lattice
cell (0,0)); only to_tacmap / the size + unit exports normalise to the
north-west origin, because the scan order does not guarantee the north-west
cell is seen first (the ex2if series meets west+south before north).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Callable

import numpy as np

from .tacmap import TacticalMap
from .vision import (
    UNIT_DENSITY_REGION,
    MapLattice,
    cell_fingerprints,
    find_threat_cells,
    find_unit_density_peaks,
    read_map_lattice,
)

Cell = tuple[int, int]
Detector = Callable[[np.ndarray], list[tuple[int, int]]]

SIDES = ("west", "east", "north", "south")


class MapStateInconsistent(RuntimeError):
    """frontier() cannot classify the map: observations have been integrated yet
    no cell is covered -- an upstream contradiction, not a finished scan. The
    07-23 case: opposing edges registered on the same lattice line make
    integrate()'s interior filter reject every cell (west==east or north==south),
    so _covered stays empty while terrain accrues. The caller must surface this
    (SurveyIncomplete), never read the empty coverage as 'complete'."""

# a peak within this many px of the scan region's top/bottom rim is a
# boundary-clamped read (a half-cut unit's ring reads 30-70px off centre, HUD
# above the region bleeds in through the density box filter); it still anchors
# nothing reliable, so it is dropped at observe time -- mirrors map_stitch's
# CLAMP_BAND.
RIM_CLAMP = 6

# a cell is "distinctive" when its Lab mean stands this far off the frame's own
# uniform-space median: the localisation signal lives only in these cells (the
# open-space majority is ambiguous by construction), so voting weighs them and
# ignores the rest. Measured against the frame-local median so each frame's own
# starfield sets the floor.
DISTINCT_THRESHOLD = 18.0
# two fingerprints of the same world cell across frames sit under this Lab
# distance; above it the cells are different terrain (batch1 measured same-cell
# medians ~11 and adjacent-cell medians >30).
TERRAIN_MATCH = 14.0
# a terrain vote needs at least this many overlapping distinctive cells before
# its match fraction is trusted; below it the fraction is statistical noise.
TERRAIN_MIN_OVERLAP = 5
# score = unit_hits + TERRAIN_WEIGHT * terrain_match_fraction. Terrain fraction
# carries the margin (unit hits alias on grid-regular formations -- the central
# deploy block self-aligns under a cell shift, so unit votes AND their pixel
# deltas both stay consistent on a wrong offset; the off-formation terrain does
# not), unit hits corroborate and cover the terrain-poor frames.
TERRAIN_WEIGHT = 15.0
# the winning offset must beat the runner-up by this much or the frame is
# refused. Worst true-offset margin on the ex2if chain is ~4.8 (pt4), synthetic
# periodic layouts tie under 1, so 2.5 sits in the gap.
LOCALIZE_MARGIN = 2.5
# the winner must also clear an absolute evidence floor: enough unit hits OR a
# high enough terrain fraction. Unit hits and terrain fraction are opposite
# failure modes -- a grid-regular formation aliases unit hits (terrain then
# carries the win, e.g. pt6), a terrain-poor corner frame aliases terrain (unit
# hits then carry it, e.g. pt8->pt9) -- so a real placement is strong in at
# least one. A win strong in neither is the ambiguous case the plan refuses.
# Every ex2if chain/strong-pair winner clears unit>=3 (min 4); the pt8->pt9
# alias sits at unit 2 / frac 0.42 and is refused.
MIN_UNIT_EVIDENCE = 3
MIN_TERRAIN_FRACTION = 0.5
# how far past the covered extent the free-axis search reaches, in cells, so a
# frame that barely overlaps the map is still enumerable.
SEARCH_PAD = 6

# a map unit is "confirmed" once this many frames place a detection on its cell;
# a lone detection is usually detector noise (HUD furniture lands on a different
# internal cell every frame, so it never accrues support). Real units on the
# ex2if series are seen 2-5 times.
MIN_SUPPORT = 2


@dataclass(frozen=True)
class UnitObs:
    """One detected unit in a frame: its foot pixel and the lattice cell that
    contains it (col index, row index into the frame's own lattice)."""

    px: tuple[int, int]
    cell: Cell


@dataclass(frozen=True)
class FrameObservation:
    """Everything one frame contributes to the map, in the frame's own lattice
    indexing. `edges` maps each side to the lattice line index of the map
    boundary seen on that side, or None when that side is off-screen."""

    lattice: MapLattice
    edges: dict[str, int | None]
    units: list[UnitObs]
    fingerprints: dict[Cell, np.ndarray]
    distinctive: frozenset[Cell]
    threats: list[tuple[int, int]]


@dataclass(frozen=True)
class LocalizeReport:
    """The diagnostic behind localize(): the placed offset (None on refusal),
    which mechanism placed it, and the evidence. `source` is 'edge_pin' when both
    axes are pinned exactly by visible boundaries (no vote, no margin), 'vote'
    when the terrain/unit vote decided (margin is the winner's lead over the
    runner-up), or None when the frame was refused. The loop logs `margin` and
    `source` from here; localize() returns only `offset`."""

    offset: Cell | None
    source: str | None
    margin: float | None
    unit_hits: int
    terrain_fraction: float


def _snap_cell(lines: tuple[int, ...], value: float) -> int | None:
    for i in range(len(lines) - 1):
        if lines[i] <= value < lines[i + 1]:
            return i
    return None


def _nearest_line(lines: tuple[int, ...], value: int) -> int:
    return min(range(len(lines)), key=lambda i: abs(lines[i] - value))


def observe_frame(
    frame: np.ndarray, *, detect: Detector = find_unit_density_peaks
) -> FrameObservation | None:
    """Read one frame into a FrameObservation, or None when no lattice is on
    screen. Pure: it only reads `frame` (架構原則 5) and the injected detector,
    never a device or gesture. The detector is injected so the min-zoom
    full-scan detector (find_unit_density_peaks) and any future variant swap
    without touching the reader."""
    lattice = read_map_lattice(frame)
    if lattice is None:
        return None

    _, ry0, _, rh = UNIT_DENSITY_REGION
    rim_top, rim_bottom = ry0 + RIM_CLAMP, ry0 + rh - RIM_CLAMP
    units: list[UnitObs] = []
    for x, y in detect(frame):
        if not rim_top < y < rim_bottom:
            continue
        col = _snap_cell(lattice.cols, x)
        row = _snap_cell(lattice.rows, y)
        if col is not None and row is not None:
            units.append(UnitObs(px=(int(x), int(y)), cell=(col, row)))

    fingerprints = cell_fingerprints(frame, lattice)
    edges: dict[str, int | None] = {}
    for side in SIDES:
        px = lattice.edges[side]
        axis = lattice.cols if side in ("west", "east") else lattice.rows
        edges[side] = None if px is None else _nearest_line(axis, px)

    distinctive: frozenset[Cell] = frozenset()
    if fingerprints:
        median = np.median(np.stack(list(fingerprints.values())), axis=0)
        distinctive = frozenset(
            cell
            for cell, fp in fingerprints.items()
            if float(np.linalg.norm((fp - median)[:3])) > DISTINCT_THRESHOLD
        )

    return FrameObservation(
        lattice=lattice,
        edges=edges,
        units=units,
        fingerprints=fingerprints,
        distinctive=distinctive,
        threats=find_threat_cells(frame),
    )


@dataclass
class _MapUnit:
    support: int = 0
    px_sum: tuple[float, float] = (0.0, 0.0)


class CellMap:
    """Accumulated cell-space map. Pure state: it never captures a frame or
    taps -- callers hand it FrameObservations. Internal cell coordinates use an
    arbitrary origin (the anchor frame's lattice (0,0)); registered boundary
    lines are stored in the same internal indexing and only the exports
    normalise to the north-west origin."""

    def __init__(self, size_hint: tuple[int, int] | None = None) -> None:
        # (cols, rows) expected extent from a cached stage definition. A planning
        # hint ONLY (frontier reach); it never registers an edge and is dropped
        # the instant the seen geometry contradicts it (架構紅線: 邊界必須目視
        # 看見). None on a first-ever scan of a stage.
        self._hint = size_hint
        self._hint_dropped = False
        self._hint_drop_reason: str | None = None
        self._units: dict[Cell, _MapUnit] = {}
        self._terrain: dict[Cell, np.ndarray] = {}
        # threat ("!" overlay) cells in internal coordinates. Threats only ever
        # render around the enemy force, so downstream keeps them as a
        # classification-independent bearing (tacmap.threat_centroid); the
        # coverage map folds them to cell space here so to_tacmap can export
        # them in the same world-px frame as the units.
        self._threats: set[Cell] = set()
        self._covered: set[Cell] = set()
        self._reg: dict[str, int | None] = {s: None for s in SIDES}
        self._col_pitch: float | None = None
        self._row_pitch: float | None = None

    def is_empty(self) -> bool:
        return not self._terrain and not self._units

    def anchor(self, obs: FrameObservation) -> None:
        """Place the first frame at the internal origin. Explicit bootstrap:
        an empty map has nothing to localise against (定位紅線 -- no gesture
        prior), so the first frame is registered directly."""
        self.integrate(obs, (0, 0))

    def _axis_pin(
        self, obs: FrameObservation, low: str, high: str
    ) -> int | str | None:
        """The exact axis offset forced by a visible, already-registered
        boundary (定案 1). 'conflict' when two registered edges disagree, None
        when no registered edge is visible on this axis."""
        values = []
        for side in (low, high):
            line = obs.edges[side]
            if line is not None and self._reg[side] is not None:
                values.append(self._reg[side] - line)
        if not values:
            return None
        return values[0] if len(set(values)) == 1 else "conflict"

    def _score(
        self, obs: FrameObservation, dcol: int, drow: int
    ) -> tuple[float, int, float]:
        unit_hits = sum(
            1
            for u in obs.units
            if (u.cell[0] + dcol, u.cell[1] + drow) in self._units
        )
        overlap = matched = 0
        for cell in obs.distinctive:
            gcell = (cell[0] + dcol, cell[1] + drow)
            known = self._terrain.get(gcell)
            if known is not None:
                overlap += 1
                if (
                    float(np.linalg.norm(obs.fingerprints[cell] - known))
                    < TERRAIN_MATCH
                ):
                    matched += 1
        fraction = matched / overlap if overlap >= TERRAIN_MIN_OVERLAP else 0.0
        return unit_hits + TERRAIN_WEIGHT * fraction, unit_hits, fraction

    def _edge_consistent(
        self, obs: FrameObservation, dcol: int, drow: int, bbox: tuple[int, int, int, int]
    ) -> bool:
        """A candidate is culled when a boundary SEEN in the frame would place
        already-covered terrain beyond it (定案 1 / plan 4: no cell exists past a
        visible map edge). One cell of slack absorbs a fingerprint sampled just
        past the boundary line under the min-zoom perspective."""
        cmin, cmax, rmin, rmax = bbox
        west, east = obs.edges["west"], obs.edges["east"]
        north, south = obs.edges["north"], obs.edges["south"]
        if west is not None and cmin < west + dcol - 1:
            return False
        if east is not None and cmax > east + dcol:
            return False
        if north is not None and rmin < north + drow - 1:
            return False
        if south is not None and rmax > south + drow:
            return False
        return True

    def _search_range(self, obs: FrameObservation, axis: int) -> range:
        if not self._covered:
            return range(0, 1)
        span = len(obs.lattice.cols if axis == 0 else obs.lattice.rows)
        values = [c[axis] for c in self._covered]
        return range(min(values) - span - SEARCH_PAD, max(values) + span + SEARCH_PAD)

    def localize(self, obs: FrameObservation) -> Cell | None:
        """The internal cell offset (dcol, drow) that places this frame on the
        map -- frame cell k belongs to internal cell k + offset -- or None when
        the map cannot place it with confidence. Thin wrapper over
        localize_report (same decision, offset only)."""
        return self.localize_report(obs).offset

    def localize_report(self, obs: FrameObservation) -> LocalizeReport:
        """localize() with its reasoning exposed for the ledger (source, margin,
        evidence). Layer 1: a visible registered boundary pins that axis exactly
        (both axes -> 'edge_pin', no vote). Layer 2: the free axis (or both, on
        an unpinned frame) is voted per candidate offset by the distinctive
        terrain match fraction (the high-weight margin carrier, TERRAIN_WEIGHT)
        with unit hits corroborating; the winner must clear LOCALIZE_MARGIN and
        the evidence floor or the frame is refused ('vote' with offset None)."""
        refused = LocalizeReport(
            offset=None, source=None, margin=None, unit_hits=0, terrain_fraction=0.0
        )
        if self.is_empty():
            return refused
        col_pin = self._axis_pin(obs, "west", "east")
        row_pin = self._axis_pin(obs, "north", "south")
        if col_pin == "conflict" or row_pin == "conflict":
            return refused
        if isinstance(col_pin, int) and isinstance(row_pin, int):
            return LocalizeReport(
                offset=(col_pin, row_pin), source="edge_pin", margin=None,
                unit_hits=0, terrain_fraction=0.0,
            )

        col_range = (
            [col_pin] if isinstance(col_pin, int) else self._search_range(obs, 0)
        )
        row_range = (
            [row_pin] if isinstance(row_pin, int) else self._search_range(obs, 1)
        )
        bbox = self._covered_bbox()
        best: tuple[float, Cell, int, float] | None = None
        second = 0.0
        for dcol in col_range:
            for drow in row_range:
                if not self._edge_consistent(obs, dcol, drow, bbox):
                    continue
                score, unit_hits, fraction = self._score(obs, dcol, drow)
                if unit_hits == 0 and fraction == 0.0:
                    continue
                if best is None or score > best[0]:
                    second = best[0] if best is not None else 0.0
                    best = (score, (dcol, drow), unit_hits, fraction)
                elif score > second:
                    second = score
        if best is None:
            return refused
        margin = best[0] - second
        vote = LocalizeReport(
            offset=best[1], source="vote", margin=margin,
            unit_hits=best[2], terrain_fraction=best[3],
        )
        if margin < LOCALIZE_MARGIN:
            return LocalizeReport(
                offset=None, source=None, margin=margin,
                unit_hits=best[2], terrain_fraction=best[3],
            )
        if best[2] < MIN_UNIT_EVIDENCE and best[3] < MIN_TERRAIN_FRACTION:
            return LocalizeReport(
                offset=None, source=None, margin=margin,
                unit_hits=best[2], terrain_fraction=best[3],
            )
        return vote

    def verify_offset(self, obs: FrameObservation, offset: Cell) -> bool:
        """Is `offset` consistent with every boundary this frame SEES? The public
        guardrail for an externally-proposed offset (the LLM assist hypothesis,
        plan 4 layer 3): wraps _edge_consistent so an LLM guess that would place
        already-covered terrain past a visible map edge is rejected before it can
        touch a coordinate. Trivially true on an empty map (nothing to
        contradict)."""
        if not self._covered:
            return True
        dcol, drow = offset
        return self._edge_consistent(obs, dcol, drow, self._covered_bbox())

    def integrate(self, obs: FrameObservation, offset: Cell) -> int:
        """Fold a localised frame into the map at `offset`: unit support with
        px refinement, terrain fingerprints, coverage, and first-seen boundary
        registration.

        Terrain is first-write-wins (輪八 定案): the first frame to see a cell
        fixes its reference fingerprint and later frames only fill cells not yet
        seen -- they never overwrite an existing one. Unit evidence already earns
        a support consensus (批2); terrain now gets the same, so a single
        barely-passing mislocalised integration can no longer rewrite the
        reference truth that every honest later frame votes against (the 輪八
        east dead-lock: one wrong overwrite corrupted hundreds of cells, then
        every honest frame refused forever). A correct re-sighting writes a
        near-identical value, so keeping the first is behaviourally equivalent on
        the healthy path; the divergence is exactly the wrong-overwrite case.

        Returns the terrain_conflict count: overlapped cells whose already-stored
        fingerprint disagrees with this frame's by TERRAIN_MATCH or more. Zero (or
        near-zero) on an honest re-integration; high on a mislocalised offset --
        an immediate ledger warning of a bad placement."""
        dcol, drow = offset
        if self._col_pitch is None:
            self._col_pitch = obs.lattice.col_pitch
            self._row_pitch = obs.lattice.row_pitch
        for u in obs.units:
            gcell = (u.cell[0] + dcol, u.cell[1] + drow)
            unit = self._units.setdefault(gcell, _MapUnit())
            unit.support += 1
            ox = u.px[0] - obs.lattice.cols[u.cell[0]]
            oy = u.px[1] - obs.lattice.rows[u.cell[1]]
            unit.px_sum = (unit.px_sum[0] + ox, unit.px_sum[1] + oy)
        west, east = obs.edges["west"], obs.edges["east"]
        north, south = obs.edges["north"], obs.edges["south"]
        terrain_conflict = 0
        for cell, fp in obs.fingerprints.items():
            col, row = cell
            gcell = (col + dcol, row + drow)
            known = self._terrain.get(gcell)
            if known is None:
                self._terrain[gcell] = fp
            elif float(np.linalg.norm(fp - known)) >= TERRAIN_MATCH:
                terrain_conflict += 1
            # coverage counts map interior only: cell_fingerprints samples the
            # starfield past a visible edge too, and marking that off-map space
            # covered both inflates the coverage report and forges edge
            # contradictions against later frames.
            if west is not None and col < west:
                continue
            if east is not None and col >= east:
                continue
            if north is not None and row < north:
                continue
            if south is not None and row >= south:
                continue
            self._covered.add(gcell)
        for tx, ty in obs.threats:
            tcol = _snap_cell(obs.lattice.cols, tx)
            trow = _snap_cell(obs.lattice.rows, ty)
            if tcol is not None and trow is not None:
                self._threats.add((tcol + dcol, trow + drow))
        for side in SIDES:
            line = obs.edges[side]
            if line is not None and self._reg[side] is None:
                axis = 0 if side in ("west", "east") else 1
                self._reg[side] = line + (dcol if axis == 0 else drow)
        self._check_hint()
        return terrain_conflict

    def _check_hint(self) -> None:
        """Drop the cache size hint the moment the SEEN geometry contradicts it
        (架構紅線): both opposing edges registered at a span that disagrees with
        the hint, or covered terrain already reaching past the hint's projected
        edge from a registered opposite edge (the real map is bigger than the
        cache claimed). A dropped hint never comes back -- the scan reverts to
        pure exploration."""
        if self._hint is None:
            return
        cols, rows = self._hint
        w, e = self._reg["west"], self._reg["east"]
        n, s = self._reg["north"], self._reg["south"]
        cmin = cmax = rmin = rmax = None
        if self._covered:
            cmin, cmax, rmin, rmax = self._covered_bbox()
        contradicted = (
            (w is not None and e is not None and e - w != cols)
            or (n is not None and s is not None and s - n != rows)
            or (w is not None and cmax is not None and cmax >= w + cols)
            or (e is not None and cmin is not None and cmin < e - cols)
            or (n is not None and rmax is not None and rmax >= n + rows)
            or (s is not None and rmin is not None and rmin < s - rows)
        )
        if contradicted:
            self._hint = None
            self._hint_dropped = True
            self._hint_drop_reason = "seen_geometry_contradicts_cache"

    def _hint_projection(self) -> dict[str, int | None]:
        """Each side's expected boundary line from the hint plus the registered
        OPPOSITE edge (west+cols -> east line, etc.), or None where the hint is
        absent or the opposite edge is unseen. Steers the frontier toward where
        the cache says the edge is; the edge still only counts once SEEN."""
        proj: dict[str, int | None] = {s: None for s in SIDES}
        if self._hint is None:
            return proj
        cols, rows = self._hint
        w, e = self._reg["west"], self._reg["east"]
        n, s = self._reg["north"], self._reg["south"]
        if w is not None:
            proj["east"] = w + cols
        if e is not None:
            proj["west"] = e - cols
        if n is not None:
            proj["south"] = n + rows
        if s is not None:
            proj["north"] = s - rows
        return proj

    @property
    def size_hint(self) -> tuple[int, int] | None:
        """The live cache size hint (None once dropped or never set)."""
        return self._hint

    @property
    def hint_dropped(self) -> bool:
        return self._hint_dropped

    @property
    def hint_drop_reason(self) -> str | None:
        return self._hint_drop_reason

    def _covered_bbox(self) -> tuple[int, int, int, int]:
        cols = [c[0] for c in self._covered]
        rows = [c[1] for c in self._covered]
        return min(cols), max(cols), min(rows), max(rows)

    def frontier(self) -> Cell | None:
        """The next internal cell worth steering toward, or None when the scan
        is genuinely complete (all four edges seen and no uncovered cell inside
        them). Priority (plan 5): an unseen edge (extrapolate outward) over the
        largest uncovered region inside the known frame.

        None means ONLY a true completion. An empty coverage with observations
        already integrated is an upstream inconsistency, not a finish, and raises
        MapStateInconsistent rather than masquerading as complete (the 07-23
        north==south bug that starved the ledger to a 0-nudge abort)."""
        if not self._covered:
            if not self.is_empty():
                raise MapStateInconsistent(
                    "coverage empty after integrating observations: "
                    f"edges {dict(self._reg)}, {len(self._terrain)} terrain cells, "
                    f"{len(self._units)} unit cells"
                )
            return None
        cmin, cmax, rmin, rmax = self._covered_bbox()
        mid_col, mid_row = (cmin + cmax) // 2, (rmin + rmax) // 2
        proj = self._hint_projection()
        outward = {
            "east": (proj["east"] if proj["east"] is not None else cmax + 1, mid_row),
            "south": (mid_col, proj["south"] if proj["south"] is not None else rmax + 1),
            "west": (proj["west"] if proj["west"] is not None else cmin - 1, mid_row),
            "north": (mid_col, proj["north"] if proj["north"] is not None else rmin - 1),
        }
        for side in ("east", "south", "west", "north"):
            if self._reg[side] is None:
                return outward[side]
        return self._largest_hole()

    def _largest_hole(self) -> Cell | None:
        west, east = self._reg["west"], self._reg["east"]
        north, south = self._reg["north"], self._reg["south"]
        frame = {
            (c, r)
            for c in range(west, east)
            for r in range(north, south)
            if (c, r) not in self._covered
        }
        if not frame:
            return None
        best: list[Cell] = []
        seen: set[Cell] = set()
        for start in frame:
            if start in seen:
                continue
            comp: list[Cell] = []
            queue = deque([start])
            seen.add(start)
            while queue:
                cell = queue.popleft()
                comp.append(cell)
                for nb in (
                    (cell[0] + 1, cell[1]),
                    (cell[0] - 1, cell[1]),
                    (cell[0], cell[1] + 1),
                    (cell[0], cell[1] - 1),
                ):
                    if nb in frame and nb not in seen:
                        seen.add(nb)
                        queue.append(nb)
            if len(comp) > len(best):
                best = comp
        cx = sum(c[0] for c in best) // len(best)
        cy = sum(c[1] for c in best) // len(best)
        return (cx, cy)

    @property
    def bounds(self) -> dict[str, int | None]:
        """Registered boundary line indices in internal coordinates (None for
        an unseen side)."""
        return dict(self._reg)

    def size(self) -> tuple[int | None, int | None]:
        """(cols, rows) cell counts once the opposing edges are both seen."""
        west, east = self._reg["west"], self._reg["east"]
        north, south = self._reg["north"], self._reg["south"]
        return (
            east - west if west is not None and east is not None else None,
            south - north if north is not None and south is not None else None,
        )

    def units(self, min_support: int = MIN_SUPPORT) -> list[Cell]:
        """Confirmed unit cells, normalised to the north-west origin. Requires
        west+north registered (the origin); raises otherwise."""
        west, north = self._reg["west"], self._reg["north"]
        if west is None or north is None:
            raise ValueError("north-west origin not anchored (west/north unseen)")
        return sorted(
            (cell[0] - west, cell[1] - north)
            for cell, unit in self._units.items()
            if unit.support >= min_support
        )

    def coverage(self) -> tuple[int, int]:
        """(covered_cells, frame_cells) inside the known bounds; frame count is
        0 until all four edges are seen."""
        cols, rows = self.size()
        if cols is None or rows is None:
            return (len(self._covered), 0)
        west, north = self._reg["west"], self._reg["north"]
        frame = {(west + c, north + r) for c in range(cols) for r in range(rows)}
        return (len(self._covered & frame), len(frame))

    def to_tacmap(self) -> tuple[TacticalMap, dict[str, float | None]]:
        """Export for the unchanged downstream: a factionless TacticalMap of
        world-px unit points plus a west/north/east/south px bounds dict, both
        in a north-west-origin frame (the west/north gridlines at px 0). Cell
        index times pitch restores world px, the accumulated sub-cell offset
        keeps the px refinement."""
        west, north = self._reg["west"], self._reg["north"]
        if west is None or north is None:
            raise ValueError("north-west origin not anchored (west/north unseen)")
        col_pitch = self._col_pitch or 1.0
        row_pitch = self._row_pitch or 1.0
        tac = TacticalMap()
        for cell, unit in self._units.items():
            if unit.support < MIN_SUPPORT:
                continue
            mean_ox = unit.px_sum[0] / unit.support
            mean_oy = unit.px_sum[1] / unit.support
            wx = (cell[0] - west) * col_pitch + max(0.0, min(mean_ox, col_pitch))
            wy = (cell[1] - north) * row_pitch + max(0.0, min(mean_oy, row_pitch))
            tac.units.append((wx, wy))
        for cell in self._threats:
            tx = (cell[0] - west) * col_pitch + col_pitch / 2
            ty = (cell[1] - north) * row_pitch + row_pitch / 2
            tac.threats.append((tx, ty))
        cols, rows = self.size()
        bounds: dict[str, float | None] = {
            "west": 0.0,
            "north": 0.0,
            "east": float(cols) * col_pitch if cols is not None else None,
            "south": float(rows) * row_pitch if rows is not None else None,
        }
        return tac, bounds
