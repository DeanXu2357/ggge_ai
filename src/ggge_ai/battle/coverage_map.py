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

    def __init__(self) -> None:
        self._units: dict[Cell, _MapUnit] = {}
        self._terrain: dict[Cell, np.ndarray] = {}
        self._covered: set[Cell] = set()
        self._reg: dict[str, int | None] = {s: None for s in SIDES}
        self._col_pitch: float | None = None
        self._row_pitch: float | None = None

    # -- bootstrap ----------------------------------------------------------

    def is_empty(self) -> bool:
        return not self._terrain and not self._units

    def anchor(self, obs: FrameObservation) -> None:
        """Place the first frame at the internal origin. Explicit bootstrap:
        an empty map has nothing to localise against (定位紅線 -- no gesture
        prior), so the first frame is registered directly."""
        self.integrate(obs, (0, 0))

    # -- localisation -------------------------------------------------------

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
        the map cannot place it with confidence.

        Layer 1: a visible registered boundary pins that axis exactly. Layer 2:
        the free axis (or both, on an unpinned frame) is voted per candidate
        offset by unit hits (high weight) plus distinctive-terrain match
        fraction (the margin carrier); the winner must clear LOCALIZE_MARGIN or
        the frame is refused."""
        if self.is_empty():
            return None
        col_pin = self._axis_pin(obs, "west", "east")
        row_pin = self._axis_pin(obs, "north", "south")
        if col_pin == "conflict" or row_pin == "conflict":
            return None
        if isinstance(col_pin, int) and isinstance(row_pin, int):
            return (col_pin, row_pin)

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
        if best is None or best[0] - second < LOCALIZE_MARGIN:
            return None
        if best[2] < MIN_UNIT_EVIDENCE and best[3] < MIN_TERRAIN_FRACTION:
            return None
        return best[1]

    # -- integration --------------------------------------------------------

    def integrate(self, obs: FrameObservation, offset: Cell) -> None:
        """Fold a localised frame into the map at `offset`: unit support with
        px refinement, terrain fingerprints, coverage, and first-seen boundary
        registration."""
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
        for cell, fp in obs.fingerprints.items():
            col, row = cell
            gcell = (col + dcol, row + drow)
            self._terrain[gcell] = fp
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
        for side in SIDES:
            line = obs.edges[side]
            if line is not None and self._reg[side] is None:
                axis = 0 if side in ("west", "east") else 1
                self._reg[side] = line + (dcol if axis == 0 else drow)

    # -- frontier -----------------------------------------------------------

    def _covered_bbox(self) -> tuple[int, int, int, int]:
        cols = [c[0] for c in self._covered]
        rows = [c[1] for c in self._covered]
        return min(cols), max(cols), min(rows), max(rows)

    def frontier(self) -> Cell | None:
        """The next internal cell worth steering toward, or None when the scan
        is complete (all four edges seen and no uncovered cell inside them).
        Priority (plan 5): an unseen edge (extrapolate outward) over the largest
        uncovered region inside the known frame."""
        if not self._covered:
            return None
        cmin, cmax, rmin, rmax = self._covered_bbox()
        mid_col, mid_row = (cmin + cmax) // 2, (rmin + rmax) // 2
        outward = {
            "east": (cmax + 1, mid_row),
            "south": (mid_col, rmax + 1),
            "west": (cmin - 1, mid_row),
            "north": (mid_col, rmin - 1),
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

    # -- reporting / export -------------------------------------------------

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
        cols, rows = self.size()
        bounds: dict[str, float | None] = {
            "west": 0.0,
            "north": 0.0,
            "east": float(cols) * col_pitch if cols is not None else None,
            "south": float(rows) * row_pitch if rows is not None else None,
        }
        return tac, bounds
