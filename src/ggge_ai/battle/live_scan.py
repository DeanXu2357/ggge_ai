"""Coverage-driven live scan (#26 批3): replaces the serpentine walk.

The 2026-07-23 red lines (coverage-scan-plan 定案 2): a gesture is only a
request to push the camera -- a stalled, truncated or eaten swipe costs time
and nothing else, it never enters a coordinate. Position comes solely from
what a frame SHOWS against the accumulated CellMap (unit constellation +
per-cell terrain fingerprints + seen boundaries); boundaries count only when
seen and never get inferred from "the camera would not move" (the old
_at_edge -> false south界, the 07-23 failure). The loop is coverage-driven:
a cell-space ledger says what is still unseen, the frontier picks the next
region, a conservative nudge steers toward it, and the frame is re-localised.

CoverageScanSource keeps a factionless TacticalMap `pool` for the survey's
bring_to_view relocalisation, exports the walk's census as `census`
(to_tacmap: world-px units, NW-origin gridline = 0) plus px `bounds`, and
fails loud with SurveyIncomplete when coverage cannot close.

PAN_CENTER / PAN_HALF / PAN_DIRS stay exported: the controller's cheap
turn-2+ local scan (_scout_local, battle zoom, unchanged this batch) imports
them.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from . import vision
from .coverage_map import (
    SIDES,
    CellMap,
    Detector,
    FrameObservation,
    observe_frame,
)
from .scout_intel import UNIT_DETAIL_CLOSE, SurveyIncomplete
from .tacmap import TacticalMap
from .vision import HUB_SCAN_REGION, find_unit_density_peaks

log = logging.getLogger(__name__)

Point = tuple[float, float]
Direction = tuple[int, int]

# retained for the unchanged turn-2+ local scan (_scout_local): a four-leg
# out-and-back around the hub view, not part of the coverage walk.
PAN_CENTER = (1170, 500)
PAN_HALF = {"x": 300, "y": 200}
PAN_DIRS = (("east", (1, 0)), ("west", (-1, 0)), ("north", (0, -1)), ("south", (0, 1)))

# a drag STARTING on a unit sprite gets eaten by the game (reads like an edge
# without moving the camera); origins are picked per nudge from this lattice by
# max-min distance to the injected detector's peaks so the drag start lands on
# empty map. 20260719 dense views could put a unit under every static origin at
# once, freezing whole scan stretches -- hence the per-frame choice.
PAN_ORIGIN_GRID = tuple(
    (x, y) for y in (360, 470, 580, 660) for x in (760, 940, 1170, 1400, 1580)
)
# a nudge trades reach for localisability: a short push keeps a wide overlap
# band with the previous frame so terrain voting always has its >= 5 cells.
NUDGE_HALF = {"x": 250, "y": 170}
# swipes land more reliably slow (500ms drags got eaten in stretches on the
# 20260719 star map: post-action camera easing + adb drop flakiness).
PAN_SWIPE_MS = 700
PAN_SETTLE_S = 1.5

# nudge budgets. ANCHOR reaches the NW corner (west+north seen), SCAN drives
# the fill loop, RELOC bounds one recovery sortie, STUCK is the zero-progress
# streak that condemns a frontier target as unreachable. Deliberately generous:
# coverage may revisit cells, and localisability beats leg efficiency.
ANCHOR_MAX_NUDGES = 8
SCAN_MAX_NUDGES = 48
RELOC_MAX_NUDGES = 6
STUCK_LIMIT = 3

# bring_to_view (post-scan survey navigation) budget and its in-region safety
# band (a target this far inside the tappable region is safe to survey-tap).
BRING_MAX_NUDGES = 8
BRING_MARGIN = 60

_DIR_NAME = {(1, 0): "east", (-1, 0): "west", (0, -1): "north", (0, 1): "south"}
# the cardinal push that brings a given map edge INTO view: to see the west
# edge the camera must travel west, etc.
_EDGE_DIR = {"west": (-1, 0), "east": (1, 0), "north": (0, -1), "south": (0, 1)}


@dataclass
class CoverageScanSource:
    """One collect() drives the whole first-turn full-map scan: anchor at the
    NW corner, then fill by frontier until the coverage ledger closes. After a
    successful collect() the census (a factionless world-px TacticalMap), px
    bounds and nudge count are readable on the instance; failure raises
    SurveyIncomplete (fail loud, no fabricated bounds)."""

    capture: Callable[[], np.ndarray]
    swipe: Callable[..., None]
    tap: Callable[[int, int], None]
    ledger_log: Callable[..., None] | None = None
    # resolved at construction, not class-definition time, so a test that
    # patches time.sleep before building the source is honoured
    sleep: Callable[[float], None] = field(default_factory=lambda: time.sleep)
    start_frame: np.ndarray | None = None
    # the min-zoom full-scan detector (find_unit_density_peaks). Injected so the
    # domain matches the work point -- the 07-23 failure was the controller
    # feeding a battle-zoom arc detector to the min-zoom scan.
    detect: Detector = find_unit_density_peaks
    # the frame -> FrameObservation seam. Default composes observe_frame with
    # the injected detector; a synthetic-world test injects its own so `frame`
    # is an opaque token (the loop never touches pixels itself).
    observe: Callable[[np.ndarray], FrameObservation | None] | None = None
    # batch4 placeholder: the LLM third localisation layer is not wired here.
    llm: object | None = None
    # factionless relocalisation pool for bring_to_view (shared with the
    # controller's adopted census).
    pool: TacticalMap = field(default_factory=TacticalMap, repr=False)

    # -- outputs (set by a successful collect) ------------------------------
    census: TacticalMap | None = field(default=None, repr=False)
    bounds: dict | None = None
    nudges: int = 0

    def __post_init__(self) -> None:
        if self.observe is None:
            self.observe = lambda frame: observe_frame(frame, detect=self.detect)

    # -- public loop --------------------------------------------------------

    def collect(self) -> TacticalMap:
        """Scan the whole map and return the census, or raise SurveyIncomplete.
        Phase A anchors the NW corner; Phase B fills by frontier until the
        ledger closes (all edges seen and every hole either covered or condemned
        unreachable) or the budget runs out."""
        frame = self.start_frame if self.start_frame is not None else self.capture()
        frame = self._clear_obstruction(frame)
        self._map = CellMap()
        self._nudges = 0
        self._unreachable: set[tuple[int, int]] = set()
        self._stuck = 0
        self._last_offset: tuple[int, int] = (0, 0)
        self._last_nudge: Direction = (0, 0)

        obs = self.observe(frame)
        if obs is None:
            raise SurveyIncomplete("coverage scan: anchor frame carried no lattice")
        self._map.anchor(obs)
        # a confirming second look at the start view before moving: real units
        # appear in both captures (support >= 2, MIN_SUPPORT), transient
        # detector noise usually does not, and a map that fits the viewport
        # whole would otherwise leave every unit at support 1 (dropped by
        # to_tacmap) since the scan never revisits it.
        frame, obs = self._confirm(frame, obs)
        frame, obs = self._anchor_phase(frame, obs)
        # the NW-corner frame is the origin reference and its corner units are
        # otherwise single-visit -- confirm it once reached
        frame, obs = self._confirm(frame, obs)

        outcome = "budget"
        for _ in range(SCAN_MAX_NUDGES):
            edges_seen = self._all_edges_seen()
            target = self._map.frontier()
            if target is None:
                outcome = "complete"
                break
            if edges_seen and target in self._unreachable:
                # frontier only surfaces holes we have already condemned: the
                # reachable board is done, only unreachable (恆遮擋) holes remain
                outcome = "unreachable_only"
                break
            before = self._map.coverage()[0]
            self.nudge(self._direction_to(target, obs), frame)
            frame, obs = self._capture_observe()
            off = self._map.localize(obs) if obs is not None else None
            if off is None:
                frame, obs = self._recover(frame, obs)
                continue
            self._map.integrate(obs, off)
            self._last_offset = off
            after = self._map.coverage()[0]
            self._log(
                "frame_localized",
                offset=[off[0], off[1]],
                margin=None,
                source="cell_map",
                edges={s: obs.edges[s] for s in SIDES},
                new_cells=after - before,
            )
            if after > before:
                self._stuck = 0
            else:
                self._stuck += 1
                if self._stuck >= STUCK_LIMIT:
                    self._unreachable.add(target)
                    self._stuck = 0
        return self._finish(outcome)

    # -- phases -------------------------------------------------------------

    def _anchor_phase(
        self, frame: np.ndarray, obs: FrameObservation
    ) -> tuple[np.ndarray, FrameObservation | None]:
        """Drive to the NW corner: nudge toward whichever of west/north is not
        yet seen until both register (map smaller than the viewport finishes at
        once). Best effort -- if the corner resists, Phase B's frontier keeps
        seeking the unseen edges and the budget is the backstop."""
        for _ in range(ANCHOR_MAX_NUDGES):
            need = [s for s in ("west", "north") if self._map.bounds[s] is None]
            if not need:
                break
            self.nudge(_EDGE_DIR[need[0]], frame)
            frame, obs = self._capture_observe()
            off = self._map.localize(obs) if obs is not None else None
            if off is None:
                frame, obs = self._recover(frame, obs)
                continue
            self._map.integrate(obs, off)
            self._last_offset = off
            self._log(
                "frame_localized",
                offset=[off[0], off[1]],
                margin=None,
                source="cell_map",
                edges={s: obs.edges[s] for s in SIDES},
                new_cells=None,
            )
        return frame, obs

    def _confirm(
        self, frame: np.ndarray, obs: FrameObservation | None
    ) -> tuple[np.ndarray, FrameObservation | None]:
        """Re-observe the current view without moving and fold it in again, so
        the reference frame's units clear MIN_SUPPORT on a genuine second
        sighting (not a doubled single read)."""
        cframe, cobs = self._capture_observe()
        if cobs is not None:
            coff = self._map.localize(cobs)
            if coff is not None:
                self._map.integrate(cobs, coff)
                self._last_offset = coff
                return cframe, cobs
        return frame, obs

    def _recover(
        self, frame: np.ndarray, obs: FrameObservation | None
    ) -> tuple[np.ndarray, FrameObservation | None]:
        """Localisation refused (isolated pairing / over-move / ambiguous
        frame): undo the move that lost the lock -- reversing the last nudge
        heads straight back into the covered mass (which holds the registered
        edges), re-overlapping known terrain so localize or an edge pin
        re-anchors us. With no prior nudge (lost at the very anchor) steer
        toward the nearest registered edge. The direction is fixed for the whole
        sortie so recovery nudges cannot oscillate. Budgeted; on exhaustion
        returns with obs unplaced so the caller counts it as no progress."""
        recover_dir = self._recovery_direction(obs)
        self._log("scan_recovery", reason="localize_refused", nudges=0)
        for i in range(1, RELOC_MAX_NUDGES + 1):
            self.nudge(recover_dir, frame)
            frame, obs = self._capture_observe()
            off = self._map.localize(obs) if obs is not None else None
            if off is not None:
                self._map.integrate(obs, off)
                self._last_offset = off
                self._log("scan_recovery", reason="relocated", nudges=i)
                return frame, obs
        self._log("scan_recovery", reason="exhausted", nudges=RELOC_MAX_NUDGES)
        return frame, obs

    def _finish(self, outcome: str) -> TacticalMap:
        covered, total = self._map.coverage()
        self._log(
            "coverage_report",
            cells=total,
            covered=covered,
            holes=(total - covered) if total else None,
            unreachable=len(self._unreachable),
            bounds=dict(self._map.bounds),
            nudges=self._nudges,
        )
        if outcome in ("complete", "unreachable_only") and self._all_edges_seen():
            self.census, self.bounds = self._map.to_tacmap()
            self.nudges = self._nudges
            return self.census
        raise SurveyIncomplete(
            f"coverage scan did not close: covered {covered}/{total}, "
            f"unreachable {len(self._unreachable)}, edges {dict(self._map.bounds)}"
        )

    # -- steering (belief picks direction only, never a coordinate) ---------

    def _direction_to(self, target: tuple[int, int], obs: FrameObservation | None) -> Direction:
        """The cardinal push from the last localised frame toward `target`. The
        offset supplies a direction only -- it never enters the swipe geometry
        (定案 1)."""
        n_cols = (len(obs.lattice.cols) - 1) if obs is not None else 6
        n_rows = (len(obs.lattice.rows) - 1) if obs is not None else 4
        vc = self._last_offset[0] + n_cols // 2
        vr = self._last_offset[1] + n_rows // 2
        dcol, drow = target[0] - vc, target[1] - vr
        if dcol == 0 and drow == 0:
            return (1, 0)
        if abs(dcol) >= abs(drow):
            return (1, 0) if dcol > 0 else (-1, 0)
        return (0, 1) if drow > 0 else (0, -1)

    def _recovery_direction(self, obs: FrameObservation | None) -> Direction:
        lx, ly = self._last_nudge
        if lx or ly:
            return (-lx, -ly)
        # lost at the very anchor with no prior push: steer toward the nearest
        # registered edge so its hard axis pin can re-anchor the free axis
        reg = self._map.bounds
        registered = [(s, reg[s]) for s in SIDES if reg[s] is not None]
        if registered:
            n_cols = (len(obs.lattice.cols) - 1) if obs is not None else 6
            n_rows = (len(obs.lattice.rows) - 1) if obs is not None else 4
            vc = self._last_offset[0] + n_cols // 2
            vr = self._last_offset[1] + n_rows // 2
            best: tuple[float, str] | None = None
            for side, line in registered:
                dist = abs(vc - line) if side in ("west", "east") else abs(vr - line)
                if best is None or dist < best[0]:
                    best = (dist, side)
            return _EDGE_DIR[best[1]]
        return (1, 0)

    def _all_edges_seen(self) -> bool:
        return all(self._map.bounds[s] is not None for s in SIDES)

    # -- operation (dumb: pushes the camera, measures nothing) --------------

    def nudge(self, direction: Direction, frame: np.ndarray) -> None:
        """One conservative swipe in `direction` from an obstruction-clear
        origin. Measures nothing and reads nothing back (定案 1); the next
        observe/localise sees where it landed."""
        cx, cy = self._pick_origin(frame, direction)
        hx = direction[0] * NUDGE_HALF["x"]
        hy = direction[1] * NUDGE_HALF["y"]
        self.swipe(cx + hx, cy + hy, cx - hx, cy - hy, PAN_SWIPE_MS)
        self.sleep(PAN_SETTLE_S)
        self._nudges += 1
        self._last_nudge = direction
        self._log("nudge", dir=_DIR_NAME.get(tuple(direction)), origin=[int(cx), int(cy)])

    def _pick_origin(self, frame: np.ndarray, direction: Direction) -> tuple[int, int]:
        """Origin whose drag START point sits furthest from every detected
        unit peak (max-min clearance), so the game does not eat the swipe.
        Clearance is against the injected detector's peaks, fixing the old
        arc-only choice that was blind to min-zoom units."""
        hx = direction[0] * NUDGE_HALF["x"]
        hy = direction[1] * NUDGE_HALF["y"]
        try:
            peaks = self.detect(frame)
        except Exception:
            peaks = []
        if not peaks:
            return PAN_CENTER

        def clearance(cand: tuple[int, int]) -> float:
            sx, sy = cand[0] + hx, cand[1] + hy
            return min(((sx - px) ** 2 + (sy - py) ** 2) ** 0.5 for px, py in peaks)

        return max(PAN_ORIGIN_GRID, key=clearance)

    def _capture_observe(self) -> tuple[np.ndarray, FrameObservation | None]:
        frame = self._clear_obstruction(self.capture())
        return frame, self.observe(frame)

    def _clear_obstruction(self, frame: np.ndarray) -> np.ndarray:
        """Close whatever a stray scan tap opened over the map -- the unit
        detail modal freezes panning wholesale (drags slide on screen while the
        camera does not move)."""
        if vision.is_unit_detail_modal(frame):
            self._log("scan_modal_closed", frame=frame)
            self.tap(*UNIT_DETAIL_CLOSE)
            self.sleep(1.2)
            return self.capture()
        return frame

    # -- survey navigation --------------------------------------------------

    def bring_to_view(
        self, world: Point, start_camera: Point | None = None
    ) -> Point | None:
        """Pan until a census world point sits safely inside the tappable map
        area and return its screen point, or None when it cannot be reached.
        Content-only: pool.locate re-anchors the camera each step from the
        visible constellation (no gesture量測, killing the 07-23 335px false
        jump); the nudge just pushes toward the target. Budgeted, fail-loud."""
        x0, y0, w, h = HUB_SCAN_REGION
        camera = start_camera
        for _ in range(BRING_MAX_NUDGES):
            frame = self._clear_obstruction(self.capture())
            try:
                arcs = self.detect(frame)
            except Exception:
                arcs = []
            located = self.pool.locate(arcs) if arcs else None
            if located is not None:
                camera = located
            if camera is None:
                return None
            screen = (world[0] - camera[0], world[1] - camera[1])
            if (
                x0 + BRING_MARGIN <= screen[0] <= x0 + w - BRING_MARGIN
                and y0 + BRING_MARGIN <= screen[1] <= y0 + h - BRING_MARGIN
            ):
                return screen
            dx = (screen[0] > x0 + w - BRING_MARGIN) - (screen[0] < x0 + BRING_MARGIN)
            dy = (screen[1] > y0 + h - BRING_MARGIN) - (screen[1] < y0 + BRING_MARGIN)
            step: Direction = (dx, 0) if (abs(dx) >= abs(dy) or dy == 0) else (0, dy)
            if step == (0, 0):
                return None
            self.nudge(step, frame)
        return None

    def _log(self, kind: str, **data) -> None:
        if self.ledger_log is not None:
            self.ledger_log(kind, **data)
