"""Cell-relative map integration (定案 6): every frame is read into
integer cell coordinates against its OWN visible lattice, frames join by
integer cell offsets, and the map anchors on boundary lines confirmed by
starfield beyond. Pixel positions exist only inside a single frame's
snap; nothing accumulates across frames, so the half-cell drift of pixel
stitching (11 units landed one row off on the ex2if series) cannot
happen -- a disagreement surfaces as an integer conflict instead of a
silent rounding.

Frame joins are arbitrated per axis across three channels, so the
positioning backbone is the map itself and units are pure content (a
board with two units huddled in one corner integrates fine):
- shared boundary: two frames trimmed to the same map edge join exactly
  (定案 1 -- edges are the positioning authority and never move);
- lattice-phase unwrapping: the navigator's measured pan shift picks the
  integer number of lines crossed by matching the frames' measured line
  positions -- the shift only has to be right to within a third of a
  pitch, the lattice supplies the exact phase;
- unit-correspondence votes: the original channel, demoted to content
  corroboration (it needs >=2 shared units and pool support).
Channels that fire must agree; any disagreement raises instead of
guessing. A frame no channel can place is dropped when it carries no
units and raises when it does.

The scan must start anchored (階段 0): the first frame is required to
show at least one real map boundary, so the whole chain hangs off the
corner that never moves (定案 1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:
    from .frame_source import MapFrame


Cell = tuple[int, int]

# column ridges are sampled in a band below the left-button HUD block and
# above the bottom prompt strip; rows are sampled clear of the banner and
# the collapsed-list button
COL_SEED_SPAN = (600, 1700)
COL_BAND = (450, 900)
ROW_SEED_SPAN = (0, 1080)
ROW_BAND = (500, 1900)
LINE_MIN_SPACING = 80
WALK_LIMIT = 40
# the search window must stay wide (pitch drifts 89-111 across a frame,
# ±0.2 stalled every walk immediately) but the accepted step needs a
# spacing floor: ±0.3 once admitted a line 0.7 pitch out, shifting a
# whole frame's row indexing by one. The ridge only needs to top the
# search window modestly because boundary-adjacent lines render dim;
# phantom terminal lines are removed by the edge trim
WALK_TOLERANCE = 0.3
WALK_MIN_STEP = 0.8
WALK_QUALITY = 1.18
# how far past the outermost detected line a unit may still be snapped
# (virtual lines at the local pitch); kept short so slant and pitch drift
# cannot push a snap across a cell
SNAP_EXTRAPOLATE_LINES = 2


@dataclass
class FrameGrid:
    cols: list[int]
    rows: list[int]
    west_bound: bool = False
    east_bound: bool = False
    north_bound: bool = False
    south_bound: bool = False

    def bounds(self) -> dict[str, bool]:
        return {
            "west": self.west_bound,
            "east": self.east_bound,
            "north": self.north_bound,
            "south": self.south_bound,
        }


class GridUnreadable(RuntimeError):
    """The frame offers no trustworthy lattice (dense formations can bury
    the seed band); the caller skips the frame for cell work."""


def _highpass(frame: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return np.abs(gray - cv2.GaussianBlur(gray, (0, 0), 6))


def _profile(hp: np.ndarray, axis: str, span: tuple[int, int], band: tuple[int, int]):
    if axis == "cols":
        return hp[band[0] : band[1], span[0] : span[1]].mean(axis=0)
    return hp[span[0] : span[1], band[0] : band[1]].mean(axis=1)


def _seed_peaks(profile: np.ndarray, offset: int) -> list[int]:
    centered = profile - profile.mean()
    gate = centered.std() * 1.2
    out: list[int] = []
    for i in range(2, len(centered) - 2):
        if (
            centered[i] >= centered[i - 1]
            and centered[i] >= centered[i + 1]
            and centered[i] > gate
        ):
            if not out or i - (out[-1] - offset) >= LINE_MIN_SPACING:
                out.append(offset + i)
            elif centered[i] > centered[out[-1] - offset]:
                out[-1] = offset + i
    return out


def _band_profile(hp: np.ndarray, axis: str, band: tuple[int, int], lo: int, hi: int):
    if axis == "cols":
        return hp[band[0] : band[1], lo:hi].mean(axis=0)
    return hp[lo:hi, band[0] : band[1]].mean(axis=1)


def _walk(
    hp: np.ndarray,
    chain: list[int],
    axis: str,
    band: tuple[int, int],
    direction: int,
    limit: int,
) -> list[int]:
    out = sorted(chain)
    for _ in range(WALK_LIMIT):
        if direction < 0:
            pitch = out[1] - out[0]
            predicted = out[0] - pitch
        else:
            pitch = out[-1] - out[-2]
            predicted = out[-1] + pitch
        window = int(pitch * WALK_TOLERANCE)
        lo, hi = predicted - window, predicted + window + 1
        if lo < 0 or hi > limit:
            break
        profile = _band_profile(hp, axis, band, lo, hi)
        peak = int(profile.argmax())
        if profile[peak] < float(np.median(profile)) * WALK_QUALITY:
            break
        position = lo + peak
        end = out[0] if direction < 0 else out[-1]
        if abs(position - end) < pitch * WALK_MIN_STEP:
            break
        if direction < 0:
            out.insert(0, position)
        else:
            out.append(position)
    return out


# a gridline ridge dies at the map edge: past it lies starfield measuring
# well under this floor, while the ridge itself measures 5-70 depending on
# terrain brightness. The run length keeps a single dark patch (shadowed
# terrain, unit sprite) from faking a termination
EDGE_DEAD_FLOOR = 1.6
EDGE_DEAD_RUN = 0.5


def _ridge_termination(
    hp: np.ndarray, line: int, axis: str, start: int, direction: int, pitch: int, limit: int
) -> int | None:
    """Where a perpendicular line's ridge dies while walking outward from
    the map interior; None when it runs past the screen edge (map
    continues off-screen). This is how the map boundary is actually
    drawn: gridlines terminate on the boundary line, starfield beyond."""
    if axis == "cols":
        ridge = hp[max(0, line - 2) : line + 3, :].mean(axis=0)
    else:
        ridge = hp[:, max(0, line - 2) : line + 3].mean(axis=1)
    kernel = np.ones(15, np.float32) / 15
    smooth = np.convolve(ridge, kernel, mode="same")
    dead_run = int(pitch * EDGE_DEAD_RUN)
    run = 0
    pos = start
    while 0 <= pos < limit:
        if smooth[pos] < EDGE_DEAD_FLOOR:
            run += 1
            if run >= dead_run:
                return pos - direction * (run - 1)
        else:
            run = 0
        pos += direction
    return None


def _edge_estimate(
    hp: np.ndarray,
    perpendicular: list[int],
    axis: str,
    start: int,
    direction: int,
    pitch: int,
    limit: int,
) -> int | None:
    """Map edge on one side: the median termination of the perpendicular
    gridline ridges. None when most ridges run off-screen (no edge in
    view)."""
    ends = [
        _ridge_termination(hp, line, axis, start, direction, pitch, limit)
        for line in perpendicular
    ]
    seen = sorted(e for e in ends if e is not None)
    if len(seen) < max(3, len(ends) // 2):
        return None
    return seen[len(seen) // 2]


def _trim_to_edges(
    chain: list[int], low_edge: int | None, high_edge: int | None, pitch: int
) -> list[int]:
    margin = int(pitch * 0.45)
    out = list(chain)
    if low_edge is not None:
        out = [x for x in out if x >= low_edge - margin]
    if high_edge is not None:
        out = [x for x in out if x <= high_edge + margin]
    return out


def _near_edge(chain_end: int, edge: int | None, pitch: int) -> bool:
    return edge is not None and abs(chain_end - edge) < pitch * 0.5


def _trim_ends(chain: list[int]) -> list[int]:
    """端點種子的間距不合理就丟端點：貼界視角下頂帶／盤外常漏一條線或多抓一條
    HUD 假線，只污染鏈的頭尾。中段不合理不修——那是整張讀壞，交給後面整張拒讀。"""
    out = list(chain)
    while len(out) >= 2 and not LINE_MIN_SPACING <= out[1] - out[0] <= 160:
        out.pop(0)
    while len(out) >= 2 and not LINE_MIN_SPACING <= out[-1] - out[-2] <= 160:
        out.pop()
    return out


def read_frame_grid(frame: np.ndarray) -> FrameGrid:
    hp = _highpass(frame)
    col_seed = _seed_peaks(
        _profile(hp, "cols", COL_SEED_SPAN, COL_BAND), COL_SEED_SPAN[0]
    )
    row_seed = _seed_peaks(
        _profile(hp, "rows", ROW_SEED_SPAN, ROW_BAND), ROW_SEED_SPAN[0]
    )
    if len(col_seed) < 4 or len(row_seed) < 4:
        raise GridUnreadable(f"seed too sparse (cols {len(col_seed)}, rows {len(row_seed)})")

    def plausible(chain: list[int]) -> bool:
        gaps = [b - a for a, b in zip(chain, chain[1:])]
        return all(LINE_MIN_SPACING <= g <= 160 for g in gaps)

    col_seed = _trim_ends(col_seed)
    row_seed = _trim_ends(row_seed)
    if len(col_seed) < 4 or len(row_seed) < 4:
        raise GridUnreadable(f"seed too sparse (cols {len(col_seed)}, rows {len(row_seed)})")
    if not plausible(col_seed) or not plausible(row_seed):
        raise GridUnreadable("seed spacing implausible")

    cols = _walk(hp, _walk(hp, col_seed, "cols", COL_BAND, -1, 2340), "cols", COL_BAND, +1, 2340)
    rows = _walk(hp, _walk(hp, row_seed, "rows", ROW_BAND, -1, 1080), "rows", ROW_BAND, +1, 1080)
    col_pitch = round((cols[-1] - cols[0]) / (len(cols) - 1))
    row_pitch = round((rows[-1] - rows[0]) / (len(rows) - 1))
    # interior rows only: rows running under the top banner or into the
    # bottom prompt strip would terminate on HUD, not on the map edge
    mid_rows = [y for y in rows if 250 <= y <= 940]
    mid_cols = [x for x in cols if 550 <= x <= 1750]
    center_x = (cols[0] + cols[-1]) // 2
    center_y = (rows[0] + rows[-1]) // 2
    west = _edge_estimate(hp, mid_rows, "cols", center_x, -1, col_pitch, 2340)
    east = _edge_estimate(hp, mid_rows, "cols", center_x, +1, col_pitch, 2340)
    north = _edge_estimate(hp, mid_cols, "rows", center_y, -1, row_pitch, 1080)
    south = _edge_estimate(hp, mid_cols, "rows", center_y, +1, row_pitch, 1080)
    cols = _trim_to_edges(cols, west, east, col_pitch)
    rows = _trim_to_edges(rows, north, south, row_pitch)
    # ridges outside the unit-scan region are HUD or starfield artifacts
    # (a phantom at x61 once inflated a frame's east-boundary claim by a
    # whole column); the map is only ever read inside the scan region
    cols = [x for x in cols if 140 <= x <= 2260]
    rows = [y for y in rows if 0 <= y <= 1030]
    if len(cols) < 4 or len(rows) < 4:
        raise GridUnreadable("lattice collapsed after edge trim")
    return FrameGrid(
        cols=cols,
        rows=rows,
        west_bound=_near_edge(cols[0], west, col_pitch),
        east_bound=_near_edge(cols[-1], east, col_pitch),
        north_bound=_near_edge(rows[0], north, row_pitch),
        south_bound=_near_edge(rows[-1], south, row_pitch),
    )


def _snap_axis(value: float, lines: list[int], bounded_low: bool, bounded_high: bool) -> int | None:
    """Index of the cell (between lines i and i+1) containing `value`;
    a short virtual extension covers units just past the detected span,
    but never past a confirmed boundary."""
    if lines[0] <= value < lines[-1]:
        for i, (a, b) in enumerate(zip(lines, lines[1:])):
            if a <= value < b:
                return i
    if value < lines[0] and not bounded_low:
        pitch = lines[1] - lines[0]
        for step in range(1, SNAP_EXTRAPOLATE_LINES + 1):
            if lines[0] - step * pitch <= value:
                return -step
        return None
    if value >= lines[-1] and not bounded_high:
        pitch = lines[-1] - lines[-2]
        for step in range(1, SNAP_EXTRAPOLATE_LINES + 1):
            if value < lines[-1] + step * pitch:
                return len(lines) - 2 + step
        return None
    if value < lines[0] or value >= lines[-1]:
        return None
    return None


def snap_cell(grid: FrameGrid, point: tuple[float, float]) -> Cell | None:
    col = _snap_axis(point[0], grid.cols, grid.west_bound, grid.east_bound)
    row = _snap_axis(point[1], grid.rows, grid.north_bound, grid.south_bound)
    if col is None or row is None:
        return None
    return (col, row)


@dataclass
class FrameCells:
    index: int
    grid: FrameGrid | None
    units: list[Cell] = field(default_factory=list)
    pixels: dict[Cell, tuple[float, float]] = field(default_factory=dict)


@dataclass
class BoardUnit:
    cell: Cell
    frames: list[int] = field(default_factory=list)

    @property
    def support(self) -> int:
        return len(self.frames)


@dataclass
class CellBoard:
    units: list[BoardUnit]
    size: tuple[int | None, int | None]
    offsets: list[Cell | None]
    conflicts: list[str] = field(default_factory=list)


class IntegrationError(RuntimeError):
    """The frame chain cannot be joined or anchored; partial cell maps
    must never be presented as a board."""


def _offset_votes(prev_units: list[Cell], cur_units: list[Cell]) -> list[tuple[Cell, int]]:
    votes: dict[Cell, int] = {}
    for a in prev_units:
        for b in cur_units:
            d = (a[0] - b[0], a[1] - b[1])
            votes[d] = votes.get(d, 0) + 1
    return sorted(votes.items(), key=lambda kv: -kv[1])


# the offset between two frames' cell indexings reflects their CHAIN
# ORIGINS, not the camera: two frames both anchored on the same map edge
# legitimately join at offset (0,0) across a real pan. The pan hint is
# therefore checked against the PIXEL displacement of the matched units
# (camera up -> the same unit renders lower), which is physical
# regardless of what each chain anchored on.
HINT_MIN_PIXELS = 80.0
PAIR_PIXEL_SPREAD = 70.0


def _matched_pixel_delta(
    prev: FrameCells, cur: FrameCells, delta: Cell
) -> tuple[float, float] | None:
    """Mean screen displacement of units matched under a candidate cell
    offset; None when matches are missing or mutually inconsistent (an
    aliased offset pairs unrelated units, whose pixel deltas scatter)."""
    deltas = []
    for cell in cur.units:
        shifted = (cell[0] + delta[0], cell[1] + delta[1])
        if shifted in prev.pixels and cell in cur.pixels:
            a, b = prev.pixels[shifted], cur.pixels[cell]
            deltas.append((b[0] - a[0], b[1] - a[1]))
    if len(deltas) < 2:
        return None
    mx = sum(d[0] for d in deltas) / len(deltas)
    my = sum(d[1] for d in deltas) / len(deltas)
    if any(abs(d[0] - mx) > PAIR_PIXEL_SPREAD or abs(d[1] - my) > PAIR_PIXEL_SPREAD for d in deltas):
        return None
    return (mx, my)


def _pixel_matches_hint(pixel_delta: tuple[float, float], hint: str | None) -> bool:
    if not hint:
        return True
    dx, dy = pixel_delta
    primary, cross = {
        "up": (dy, abs(dx)),
        "down": (-dy, abs(dx)),
        "left": (dx, abs(dy)),
        "right": (-dx, abs(dy)),
    }[hint]
    return primary >= HINT_MIN_PIXELS and cross < max(primary, 300.0)


# a line pair votes when the shifted position lands within a third of a
# pitch: far enough under the half-pitch aliasing threshold to absorb
# navigator noise plus the perspective drift a translation model ignores
# (row pitch runs 84-102 across a frame), tight enough that a wrong
# integer cannot collect votes. Three agreeing pairs with a 2x lead over
# the runner-up keep a coincidental alignment from deciding a join.
LINE_VOTE_TOLERANCE = 3.0
LINE_VOTE_MIN = 3


def _line_delta(prev_lines: list[int], cur_lines: list[int], shift: float) -> int | None:
    """Cell-index offset by matching the two frames' measured line
    positions under the navigator's coarse shift: the lattice supplies
    the exact phase, the shift only picks the integer multiple."""
    if len(prev_lines) < 2 or len(cur_lines) < 2:
        return None
    pitch = (prev_lines[-1] - prev_lines[0]) / (len(prev_lines) - 1)
    tolerance = pitch / LINE_VOTE_TOLERANCE
    votes: dict[int, int] = {}
    for i, lp in enumerate(prev_lines):
        for j, lc in enumerate(cur_lines):
            if abs(lp + shift - lc) <= tolerance:
                votes[i - j] = votes.get(i - j, 0) + 1
    ranked = sorted(votes.items(), key=lambda kv: -kv[1])
    if not ranked or ranked[0][1] < LINE_VOTE_MIN:
        return None
    if len(ranked) > 1 and ranked[1][1] * 2 > ranked[0][1]:
        return None
    return ranked[0][0]


def _accumulated_shift(
    shifts: list[tuple[float, float] | None] | None, lo: int, hi: int
) -> tuple[float, float] | None:
    """Content displacement between two readable frames: the vector sum
    of every hop over (lo, hi], None as soon as one hop is unmeasured."""
    if shifts is None:
        return None
    total = (0.0, 0.0)
    for i in range(lo + 1, hi + 1):
        hop = shifts[i]
        if hop is None:
            return None
        total = (total[0] + hop[0], total[1] + hop[1])
    return total


def integrate(
    frames: list[FrameCells],
    hints: list[str | None] | None = None,
    shifts: list[tuple[float, float] | None] | None = None,
) -> CellBoard:
    if hints is not None and len(hints) != len(frames):
        raise IntegrationError("hints length must match frames")
    if shifts is not None and len(shifts) != len(frames):
        raise IntegrationError("shifts length must match frames")
    readable = [f for f in frames if f.grid is not None]
    if not readable:
        raise IntegrationError("no readable frames")
    first = readable[0]
    if not any(first.grid.bounds().values()):
        raise IntegrationError(
            "階段 0 failed: the first readable frame shows no map boundary"
        )

    # placement is PER AXIS: a frame whose column offset cannot be
    # resolved still serves as the row bridge for its neighbours (a
    # dropped bridge once disconnected everything behind it), and unit
    # cells only ever integrate from fully placed frames
    conflicts: list[str] = []
    placed_x: dict[int, int] = {first.index: 0}
    placed_y: dict[int, int] = {first.index: 0}
    pool_cells: set[Cell] = set(first.units)
    # map edges are ABSOLUTE registration, not pairwise joins: once any
    # placed frame fixes an edge's chain coordinate, every later frame
    # trimmed to that edge places against the map itself (定案 1); later
    # disagreements surface through the anchor audit below
    edge_reg: dict[str, int | None] = {
        "west": None, "east": None, "north": None, "south": None,
    }

    def register_edges(f: FrameCells) -> None:
        b = f.grid.bounds()
        if f.index in placed_x:
            if b["west"] and edge_reg["west"] is None:
                edge_reg["west"] = placed_x[f.index]
            if b["east"] and edge_reg["east"] is None:
                edge_reg["east"] = placed_x[f.index] + len(f.grid.cols) - 1
        if f.index in placed_y:
            if b["north"] and edge_reg["north"] is None:
                edge_reg["north"] = placed_y[f.index]
            if b["south"] and edge_reg["south"] is None:
                edge_reg["south"] = placed_y[f.index] + len(f.grid.rows) - 1

    register_edges(first)

    def merged_hint(lo: int, hi: int) -> str | None:
        if hints is None:
            return None
        merged = [hints[i] for i in range(lo + 1, hi + 1) if hints[i] is not None]
        return merged[0] if merged and len(set(merged)) == 1 else None

    def line_channel(cur: FrameCells, axis: int, placed: dict[int, int]) -> int | None:
        refs = [f for f in readable if f.index < cur.index and f.index in placed]
        if not refs:
            return None
        ref = refs[-1]
        shift = _accumulated_shift(shifts, ref.index, cur.index)
        if shift is None:
            return None
        hint = merged_hint(ref.index, cur.index)
        if hint and not _pixel_matches_hint(shift, hint):
            conflicts.append(
                f"frame {cur.index}: measured shift {shift} contradicts hint"
                f" {hint}, shift channel skipped"
            )
            return None
        if axis == 0:
            delta = _line_delta(ref.grid.cols, cur.grid.cols, shift[0])
        else:
            delta = _line_delta(ref.grid.rows, cur.grid.rows, shift[1])
        if delta is None:
            return None
        return placed[ref.index] + delta

    def units_channel(cur: FrameCells) -> tuple[int, int, Cell] | None:
        # a grid-regular formation aliases both the cell vote AND the
        # pixel-consistency check (shifting the pairing by a cell keeps
        # displacements uniform); support against the accumulated pool is
        # what an alias cannot fake, so a units-only placement keeps the
        # pool gate
        refs = [
            f
            for f in readable
            if f.index < cur.index
            and f.index in placed_x
            and f.index in placed_y
            and f.units
        ]
        if not refs or not cur.units:
            return None
        ref = refs[-1]
        hint = merged_hint(ref.index, cur.index)
        base = (placed_x[ref.index], placed_y[ref.index])
        best: tuple[int, int, Cell] | None = None
        for delta, support in _offset_votes(ref.units, cur.units):
            if support < 2:
                break
            pixel_delta = _matched_pixel_delta(ref, cur, delta)
            if pixel_delta is None:
                continue
            if not _pixel_matches_hint(pixel_delta, hint):
                continue
            candidate = (base[0] + delta[0], base[1] + delta[1])
            pool_support = sum(
                1
                for cell in cur.units
                if (cell[0] + candidate[0], cell[1] + candidate[1]) in pool_cells
            )
            if best is None or (pool_support, support) > (best[0], best[1]):
                best = (pool_support, support, candidate)
        return best

    for cur in readable[1:]:
        b = cur.grid.bounds()
        best = units_channel(cur)
        cand_x: dict[str, int] = {}
        cand_y: dict[str, int] = {}
        if b["west"] and edge_reg["west"] is not None:
            cand_x["edge_west"] = edge_reg["west"]
        if b["east"] and edge_reg["east"] is not None:
            cand_x["edge_east"] = edge_reg["east"] - (len(cur.grid.cols) - 1)
        if b["north"] and edge_reg["north"] is not None:
            cand_y["edge_north"] = edge_reg["north"]
        if b["south"] and edge_reg["south"] is not None:
            cand_y["edge_south"] = edge_reg["south"] - (len(cur.grid.rows) - 1)
        line_x = line_channel(cur, 0, placed_x)
        if line_x is not None:
            cand_x["shift"] = line_x
        line_y = line_channel(cur, 1, placed_y)
        if line_y is not None:
            cand_y["shift"] = line_y
        if best is not None:
            cand_x["units"] = best[2][0]
            cand_y["units"] = best[2][1]

        for axis, cand in (("col", cand_x), ("row", cand_y)):
            if len(set(cand.values())) > 1:
                raise IntegrationError(
                    f"frame {cur.index}: {axis} offset channels disagree: {cand}"
                )
        if cand_x and cand_y:
            units_only = {"units"} in (set(cand_x), set(cand_y))
            if units_only and (best is None or best[0] < 2):
                raise IntegrationError(
                    f"frame {cur.index}: no supported cell offset (units channel"
                    " alone lacks pool support)"
                )
            placed_x[cur.index] = next(iter(cand_x.values()))
            placed_y[cur.index] = next(iter(cand_y.values()))
            pool_cells.update(
                (cell[0] + placed_x[cur.index], cell[1] + placed_y[cur.index])
                for cell in cur.units
            )
        elif cur.units:
            raise IntegrationError(
                f"frame {cur.index}: no channel joins it"
                f" (col candidates {sorted(cand_x)}, row candidates {sorted(cand_y)})"
            )
        else:
            if cand_x:
                placed_x[cur.index] = next(iter(cand_x.values()))
            if cand_y:
                placed_y[cur.index] = next(iter(cand_y.values()))
            axes = ("col" if cand_x else "") + ("row" if cand_y else "")
            conflicts.append(
                f"frame {cur.index}: unit-free, dropped from cell pool"
                f" (axes placed: {axes or 'none'})"
            )
        register_edges(cur)

    pool: dict[Cell, BoardUnit] = {}
    for f in readable:
        if f.index not in placed_x or f.index not in placed_y:
            continue
        off = (placed_x[f.index], placed_y[f.index])
        for cell in f.units:
            g = (cell[0] + off[0], cell[1] + off[1])
            unit = pool.setdefault(g, BoardUnit(cell=g))
            if f.index not in unit.frames:
                unit.frames.append(f.index)

    def anchor(side: str, placed: dict[int, int], pick) -> int | None:
        seen: dict[int, list[int]] = {}
        for f in readable:
            if f.index not in placed or not f.grid.bounds()[side]:
                continue
            seen.setdefault(pick(f, placed[f.index]), []).append(f.index)
        if not seen:
            return None
        if len(seen) > 1:
            conflicts.append(f"{side} boundary disagrees across frames: {seen}")
        return min(seen)

    west = anchor("west", placed_x, lambda f, off: off)
    north = anchor("north", placed_y, lambda f, off: off)
    east = anchor("east", placed_x, lambda f, off: off + len(f.grid.cols) - 1)
    south = anchor("south", placed_y, lambda f, off: off + len(f.grid.rows) - 1)
    if west is None or north is None:
        raise IntegrationError("map NW corner never anchored (no west/north boundary seen)")

    units = [
        BoardUnit(cell=(u.cell[0] - west, u.cell[1] - north), frames=sorted(u.frames))
        for u in pool.values()
    ]
    units.sort(key=lambda u: (u.cell[1], u.cell[0]))
    size = (
        east - west if east is not None else None,
        south - north if south is not None else None,
    )
    return CellBoard(
        units=units,
        size=size,
        offsets=[
            (placed_x[f.index], placed_y[f.index])
            if f.index in placed_x and f.index in placed_y
            else None
            for f in frames
        ],
        conflicts=conflicts,
    )


def read_board(frames: list["MapFrame"]) -> CellBoard:
    """The interpretation half of the full-map scan: consume a collected
    frame series (any FrameSource) and produce the board. Pure -- no
    capture, no gestures; acquisition failures never reach here and
    integration failures raise instead of guessing."""
    series = read_series([f.image for f in frames])
    return integrate(
        series,
        hints=[f.hint for f in frames],
        shifts=[f.measured_shift for f in frames],
    )


def read_series(frames: list[np.ndarray]) -> list[FrameCells]:
    from .map_stitch import clean_series_detections

    per_frame = clean_series_detections(frames)
    out: list[FrameCells] = []
    for i, (frame, peaks) in enumerate(zip(frames, per_frame)):
        try:
            grid = read_frame_grid(frame)
        except GridUnreadable:
            out.append(FrameCells(index=i, grid=None))
            continue
        cells: list[Cell] = []
        pixels: dict[Cell, tuple[float, float]] = {}
        for p in peaks:
            cell = snap_cell(grid, (float(p[0]), float(p[1])))
            if cell is not None and cell not in cells:
                cells.append(cell)
                pixels[cell] = (float(p[0]), float(p[1]))
        out.append(FrameCells(index=i, grid=grid, units=cells, pixels=pixels))
    return out
