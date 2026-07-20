"""Offline map stitching: replay an ordered series of battle-hub frames
(manual or scripted pans) into one world-coordinate, factionless unit
pool -- stage one of the two-stage survey (map-scan 定案 5). Faction is
decided later by per-unit banner docking, so arc color is only an
existence signal here (the density detector unions the three bands).

Pure frame functions, zero device coupling: the caller supplies frames in
pan order and gets per-frame cameras plus merged unit positions back.
Placement is vote-based and screen-derived (定案 3): every candidate shift
comes from constellation votes or pool landmarks, and an optional per-pan
direction hint only arbitrates BETWEEN screen-derived hypotheses -- it is
never dead-reckoned into a position. Phase correlation is deliberately
absent: the periodic grid texture makes it lock, with high confidence, on
near-zero shifts whenever a pan lands close to a whole number of cells
(response 0.17-0.42 on 300-500px pans of the 20260719 ex2if series), and
one silently wrong camera poisons the whole pool."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import vision
from .tacmap import TacticalMap

Point = tuple[float, float]

# a detection recurring at the same screen position across MANY frames is
# HUD furniture (measured 6-8 of 9 frames for the real buttons). The bar
# sits at 4: at 2 the filter ate real units -- with 25+ units on the map,
# two different units landing on the same screen spot in two different
# frames is common (measured 8 such collisions on the ex2if series)
STATIC_SCREEN_RADIUS = 30.0
STATIC_SCREEN_MIN_HITS = 4
# peaks jitter along a wide button block (~200px spread measured), so the
# drop radius around a confirmed static center is much wider than the
# clustering radius
STATIC_DROP_RADIUS = 100.0

# pool merge must sit well under the min-zoom cell pitch (~95px) or two
# adjacent real units merge; stitch residual drift measures a few tens of
# px, so half a cell absorbs it without eating neighbors
POOL_MERGE_RADIUS = 55.0

# one manual or scripted swipe cannot move the camera much more than a
# screen; a fit jumping further than this is an aliased match
MAX_STEP = 1000.0

# vote bucket for pairwise constellation shifts; wider than the arc-shift
# tolerance because min-zoom peak centroids wobble with partial rings
VOTE_TOLERANCE = 30.0
# a candidate camera must land this close to pooled world points to count
# as support; under half the ~95px cell pitch so a one-cell alias of a
# grid-regular formation cannot claim a neighbor's landmark
SUPPORT_RADIUS = 45.0
MIN_SUPPORT = 2

# a hinted pan must actually travel: the game clamps at map edges, but a
# clamped pan that moved less than this is indistinguishable from an
# aliased zero-lock, so the caller decides by trying the next stop
HINT_MIN_TRAVEL = 120.0

# peaks pinned to the scan-region top/bottom rim are boundary-clamped
# reads: at the bottom they are half-cut units read 30-70px off center,
# at the top they are above-region HUD/unit mass bleeding in through the
# box filter. Both still anchor placement votes; entering the pool they
# spawn ~70px ghost twins of the clean observation from a neighboring
# frame
CLAMP_BAND = 6.0

# refinement matches observations to pool units within this radius: under
# half the ~95px cell pitch, so the ICP pull can never latch onto a
# neighboring unit and jump an alias; iterations stop once every camera
# moves under a pixel
REFINE_MATCH_RADIUS = 45.0
REFINE_ITERATIONS = 8

# a weak-frame relocate is a correction, never a re-decision: candidates
# further than this from the placed camera are aliases by construction
# (the observed pt5 correction was 78px; an unconstrained global fit once
# jumped 890px onto a look-alike constellation across the map)
RELOCATE_MAX_SHIFT = 250.0


class StitchError(RuntimeError):
    """A frame could not be placed by any measurement; the caller must
    treat the series as unusable rather than continue on a guess."""


@dataclass
class FramePlacement:
    index: int
    camera: Point
    method: str
    support: int
    arcs: int


@dataclass
class PoolUnit:
    pos: Point
    observations: list[tuple[int, Point]] = field(default_factory=list)

    @property
    def frames(self) -> list[int]:
        return sorted({i for i, _ in self.observations})

    @property
    def support(self) -> int:
        return len(self.frames)

    @property
    def spread(self) -> float:
        if len(self.observations) < 2:
            return 0.0
        xs = [p[0] for _, p in self.observations]
        ys = [p[1] for _, p in self.observations]
        return float(((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2) ** 0.5)


@dataclass
class StitchResult:
    units: list[PoolUnit]
    placements: list[FramePlacement]
    static_screen: list[Point]
    col_pitch: float | None = None
    row_pitch: float | None = None
    lattices: list[tuple[tuple[int, ...], tuple[int, ...]] | None] = field(
        default_factory=list
    )


def clean_series_detections(frames: list[np.ndarray]) -> list[list[tuple[int, int]]]:
    """Per-frame unit peaks with the series-level noise removed: static
    HUD recurrences dropped, rim-clamped (positionally biased) peaks
    excluded. Shared by the pixel stitcher and the cell integrator."""
    detections = [vision.find_unit_density_peaks(f) for f in frames]
    static = _static_screen_points(detections)
    cleaned = [_drop_near(pts, static, STATIC_DROP_RADIUS) for pts in detections]
    _, y0, _, h = vision.UNIT_DENSITY_REGION
    clamp_top, clamp_bottom = y0 + CLAMP_BAND, y0 + h - CLAMP_BAND
    return [[p for p in pts if clamp_top < p[1] < clamp_bottom] for pts in cleaned]


def _static_screen_points(per_frame: list[list[tuple[int, int]]]) -> list[Point]:
    r2 = STATIC_SCREEN_RADIUS * STATIC_SCREEN_RADIUS
    clusters: list[tuple[Point, set[int]]] = []
    for index, points in enumerate(per_frame):
        for p in points:
            for i, (center, frames_seen) in enumerate(clusters):
                if (p[0] - center[0]) ** 2 + (p[1] - center[1]) ** 2 < r2:
                    frames_seen.add(index)
                    clusters[i] = (
                        ((center[0] + p[0]) / 2, (center[1] + p[1]) / 2),
                        frames_seen,
                    )
                    break
            else:
                clusters.append(((float(p[0]), float(p[1])), {index}))
    return [c for c, seen in clusters if len(seen) >= STATIC_SCREEN_MIN_HITS]


def _drop_near(
    points: list[tuple[int, int]], centers: list[Point], radius: float
) -> list[tuple[int, int]]:
    r2 = radius * radius
    return [
        p
        for p in points
        if all((p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 >= r2 for c in centers)
    ]


def _vote_shifts(
    prev_points: list[tuple[int, int]], cur_points: list[tuple[int, int]]
) -> list[tuple[Point, int]]:
    """Candidate camera deltas between two frames: every point pairing
    hypothesizes a translation. Singleton hypotheses stay in -- on sparse
    frames (2-3 detections) perspective drift spreads the true shift's
    votes across buckets, so requiring a two-vote mode starves placement;
    pool support downstream is the real filter, votes only rank. All modes
    are returned (not just the winner) because grid-regular unit blocks
    produce one-cell aliases that only pool support and the direction hint
    can tell apart."""
    votes: dict[tuple[int, int], list[Point]] = {}
    for px, py in prev_points:
        for cx, cy in cur_points:
            d = (float(px - cx), float(py - cy))
            key = (round(d[0] / VOTE_TOLERANCE), round(d[1] / VOTE_TOLERANCE))
            votes.setdefault(key, []).append(d)
    modes = [
        (
            (
                sum(d[0] for d in ds) / len(ds),
                sum(d[1] for d in ds) / len(ds),
            ),
            len(ds),
        )
        for ds in votes.values()
    ]
    modes.sort(key=lambda m: -m[1])
    return modes[:24]


def _matches_hint(delta: Point, hint: str | None) -> bool:
    if not hint:
        return True
    dx, dy = delta
    primary, cross = {
        "up": (-dy, abs(dx)),
        "down": (dy, abs(dx)),
        "left": (-dx, abs(dy)),
        "right": (dx, abs(dy)),
    }[hint]
    return primary >= HINT_MIN_TRAVEL and cross < primary


def _support(
    points: list[tuple[int, int]], camera: Point, pool: list[Point]
) -> int:
    r2 = SUPPORT_RADIUS * SUPPORT_RADIUS
    count = 0
    for p in points:
        wx, wy = p[0] + camera[0], p[1] + camera[1]
        if any((wx - q[0]) ** 2 + (wy - q[1]) ** 2 < r2 for q in pool):
            count += 1
    return count


def _mean_residual(
    points: list[tuple[int, int]], camera: Point, pool: list[Point]
) -> float:
    r2 = SUPPORT_RADIUS * SUPPORT_RADIUS
    matched = []
    for p in points:
        wx, wy = p[0] + camera[0], p[1] + camera[1]
        d2 = min(((wx - q[0]) ** 2 + (wy - q[1]) ** 2 for q in pool), default=None)
        if d2 is not None and d2 < r2:
            matched.append(d2**0.5)
    return sum(matched) / len(matched) if matched else float("inf")


def _merge_pool(observations: list[tuple[int, Point]]) -> list[PoolUnit]:
    """Greedy merge, then re-merged to a fixpoint: sequential averaging is
    order-dependent, so two clusters of one unit can settle just past the
    radius on the first pass and only collapse when cluster centers are
    themselves merged."""
    r2 = POOL_MERGE_RADIUS * POOL_MERGE_RADIUS
    units: list[PoolUnit] = []
    for frame_index, p in observations:
        for unit in units:
            if (p[0] - unit.pos[0]) ** 2 + (p[1] - unit.pos[1]) ** 2 < r2:
                unit.pos = ((p[0] + unit.pos[0]) / 2, (p[1] + unit.pos[1]) / 2)
                unit.observations.append((frame_index, p))
                break
        else:
            units.append(PoolUnit(pos=p, observations=[(frame_index, p)]))
    while True:
        merged: list[PoolUnit] = []
        for unit in units:
            for other in merged:
                if (unit.pos[0] - other.pos[0]) ** 2 + (
                    unit.pos[1] - other.pos[1]
                ) ** 2 < r2:
                    other.observations.extend(unit.observations)
                    xs = [p[0] for _, p in other.observations]
                    ys = [p[1] for _, p in other.observations]
                    other.pos = (sum(xs) / len(xs), sum(ys) / len(ys))
                    break
            else:
                merged.append(unit)
        if len(merged) == len(units):
            return merged
        units = merged


def _mean_pitch(gap_lists: list[tuple[int, ...]]) -> float | None:
    gaps = [b - a for lattice in gap_lists for a, b in zip(lattice, lattice[1:])]
    if not gaps:
        return None
    return float(sum(gaps)) / len(gaps)


def _step_ok(camera: Point, reference: Point) -> bool:
    dx, dy = camera[0] - reference[0], camera[1] - reference[1]
    return dx * dx + dy * dy <= MAX_STEP * MAX_STEP


def _icp(cameras: list[Point], poolable: list[list[tuple[int, int]]]) -> None:
    r2 = REFINE_MATCH_RADIUS * REFINE_MATCH_RADIUS
    for _ in range(REFINE_ITERATIONS):
        pool = _merge_pool(
            [
                (i, (p[0] + cameras[i][0], p[1] + cameras[i][1]))
                for i in range(len(cameras))
                for p in poolable[i]
            ]
        )
        moved = 0.0
        for i in range(1, len(cameras)):
            residuals = []
            for p in poolable[i]:
                wx, wy = p[0] + cameras[i][0], p[1] + cameras[i][1]
                best: tuple[float, Point] | None = None
                for unit in pool:
                    d2 = (wx - unit.pos[0]) ** 2 + (wy - unit.pos[1]) ** 2
                    if d2 < r2 and (best is None or d2 < best[0]):
                        best = (d2, unit.pos)
                if best is not None:
                    residuals.append((best[1][0] - wx, best[1][1] - wy))
            if len(residuals) < 2:
                continue
            dx = sum(d[0] for d in residuals) / len(residuals)
            dy = sum(d[1] for d in residuals) / len(residuals)
            cameras[i] = (cameras[i][0] + dx, cameras[i][1] + dy)
            moved = max(moved, (dx * dx + dy * dy) ** 0.5)
        if moved < 1.0:
            return


def stitch(
    frames: list[np.ndarray], hints: list[str | None] | None = None
) -> StitchResult:
    """`hints[i]` is the recorded pan direction that produced frame i
    ("up"/"down"/"left"/"right", None for unknown; hints[0] is ignored)."""
    if not frames:
        raise StitchError("empty frame series")
    if hints is not None and len(hints) != len(frames):
        raise StitchError("hints length must match frames")
    detections = [vision.find_unit_density_peaks(f) for f in frames]
    static = _static_screen_points(detections)
    cleaned = [_drop_near(pts, static, STATIC_DROP_RADIUS) for pts in detections]
    lattices = [vision.read_grid_lattice(f) for f in frames]
    _, y0, _, h = vision.UNIT_DENSITY_REGION
    clamp_top = y0 + CLAMP_BAND
    clamp_bottom = y0 + h - CLAMP_BAND
    poolable = [
        [p for p in pts if clamp_top < p[1] < clamp_bottom] for pts in cleaned
    ]

    tac = TacticalMap()
    world_points: list[Point] = []
    camera: Point = (0.0, 0.0)
    placements: list[FramePlacement] = []
    for i, points in enumerate(cleaned):
        if i == 0:
            method, support = "origin", len(points)
        else:
            hint = hints[i] if hints else None
            candidates: list[tuple[Point, str]] = []
            for shift, _ in _vote_shifts(cleaned[i - 1], points):
                if _step_ok(shift, (0.0, 0.0)):
                    candidates.append(
                        ((camera[0] + shift[0], camera[1] + shift[1]), "vote")
                    )
            fit = tac.locate(points)
            if fit is not None and _step_ok(fit, camera):
                candidates.append((fit, "locate"))
            scored: list[tuple[int, Point, str]] = []
            for cam, origin in candidates:
                delta = (cam[0] - camera[0], cam[1] - camera[1])
                if not _matches_hint(delta, hint):
                    continue
                if any(
                    (cam[0] - s[1][0]) ** 2 + (cam[1] - s[1][1]) ** 2 < 20**2
                    for s in scored
                ):
                    continue
                scored.append((_support(points, cam, world_points), cam, origin))
            scored.sort(key=lambda s: -s[0])
            if not scored or scored[0][0] < MIN_SUPPORT:
                raise StitchError(
                    f"frame {i}: no supported camera fit "
                    f"(candidates {len(candidates)}, hint {hint})"
                )
            support, camera, method = scored[0]
        tac.observe(camera, poolable[i])
        for p in poolable[i]:
            world_points.append((p[0] + camera[0], p[1] + camera[1]))
        placements.append(
            FramePlacement(
                index=i, camera=camera, method=method, support=support, arcs=len(points)
            )
        )

    # ICP refinement: the initial chain accumulates residual drift (a few
    # tens of px per hop, measured 50-90px by pt5/pt9 on the ex2if series)
    # that splits one unit into neighboring twins across distant frames.
    # Each round rebuilds the pool and pulls every camera by the mean
    # residual of its matched observations; frame 0 stays put as the
    # origin anchor. Mean residual, not coincidence count: counts saturate
    # inside the match radius and cannot tell a sloppy fit from a tight one.
    cameras = [pl.camera for pl in placements]
    _icp(cameras, poolable)

    # weak-frame relocate: a frame placed on 2-point support from screen-
    # edge-biased peaks (pt5 on the ex2if series) can sit a whole 77px off
    # -- beyond the ICP pull radius, so its observations orbit the pool as
    # ghost twins. Re-fit such frames wholesale against units the OTHER
    # frames corroborate (multi-frame only, so the frame's own ghosts
    # cannot anchor it back), then let ICP tighten again.
    relocated = False
    for i in range(1, len(frames)):
        if placements[i].support > MIN_SUPPORT or len(poolable[i]) < 2:
            continue
        pool = _merge_pool(
            [
                (j, (p[0] + cameras[j][0], p[1] + cameras[j][1]))
                for j in range(len(frames))
                if j != i
                for p in poolable[j]
            ]
        )
        anchors = [u.pos for u in pool if u.support >= 2]
        if len(anchors) < 2:
            continue
        max_d2 = RELOCATE_MAX_SHIFT * RELOCATE_MAX_SHIFT
        best: tuple[int, float, Point] | None = None
        for p in poolable[i]:
            for a in anchors:
                cand = (a[0] - p[0], a[1] - p[1])
                dx, dy = cand[0] - cameras[i][0], cand[1] - cameras[i][1]
                if dx * dx + dy * dy > max_d2:
                    continue
                sup = _support(poolable[i], cand, anchors)
                if sup < MIN_SUPPORT:
                    continue
                res = _mean_residual(poolable[i], cand, anchors)
                if best is None or (sup, -res) > (best[0], -best[1]):
                    best = (sup, res, cand)
        if best is not None and best[0] >= _support(poolable[i], cameras[i], anchors):
            cameras[i] = best[2]
            placements[i].method += "+relocate"
            relocated = True
    if relocated:
        _icp(cameras, poolable)
    for i, placement in enumerate(placements):
        if placement.camera != cameras[i]:
            placement.camera = cameras[i]
            if not placement.method.endswith("+relocate"):
                placement.method += "+icp"

    observations = [
        (i, (p[0] + cameras[i][0], p[1] + cameras[i][1]))
        for i in range(len(frames))
        for p in poolable[i]
    ]
    return StitchResult(
        units=_merge_pool(observations),
        placements=placements,
        static_screen=static,
        col_pitch=_mean_pitch([lat[0] for lat in lattices if lat is not None]),
        row_pitch=_mean_pitch([lat[1] for lat in lattices if lat is not None]),
        lattices=lattices,
    )
