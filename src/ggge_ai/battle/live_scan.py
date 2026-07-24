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
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import cv2
import numpy as np

from . import map_view, vision
from .coverage_map import (
    SIDES,
    TERRAIN_MIN_OVERLAP,
    CellMap,
    Detector,
    FrameObservation,
    LocalizeReport,
    MapStateInconsistent,
    observe_frame,
)
from .scout_intel import SurveyIncomplete
from .tacmap import TacticalMap
from .vision import HUB_SCAN_REGION, find_unit_density_peaks

if TYPE_CHECKING:
    from ..perception.llm import LlmScreenReader

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
# localisation-starving brake (輪七): K consecutive primary-direction refusals
# with zero coverage progress -- regardless of whether recovery relocated --
# is a starving scan. The 輪七 failure took 110 nudges / ~9 min to hit the outer
# budget; K=6 fails honestly in <90s with the refused/relocated tally. Only a
# new early-stop exit on a path that WOULD have burned the budget; frontier/
# integrate/localize/recovery-direction semantics are untouched.
STARVE_LIMIT = 6

# 輪十 anchor-evidence gate: the anchor reference must carry localisation
# evidence before the map commits to it. localize() votes on two sources -- a
# unit constellation and distinctive per-cell terrain -- so a frame with at
# least ANCHOR_MIN_UNITS unit peaks OR at least TERRAIN_MIN_OVERLAP distinctive
# cells is re-findable once the camera moves and is a valid anchor. The 輪十
# void (camera parked in the empty north-east corner: 0 units + uniform starfield
# past only the east/north cut-off edges) has neither; anchoring on it strands
# the scan at margin=null forever (98 nudges, every recovery exhausted). When the
# start view is that void the loop seeks toward the map interior instead, reusing
# the ANCHOR_MAX_NUDGES budget, until a unit appears. The terrain half of the
# gate is why a 0-unit-but-distinctive frame (the 輪七/輪八 starving worlds, the
# north==south inconsistency frame) is NOT diverted -- it localises on terrain
# alone and its downstream handling (fill-loop starve, frontier inconsistency)
# must stay reachable.
ANCHOR_MIN_UNITS = 1

# bring_to_view (post-scan survey navigation) budget and its in-region safety
# band (a target this far inside the tappable region is safe to survey-tap).
BRING_MAX_NUDGES = 8
BRING_MARGIN = 60

_DIR_NAME = {(1, 0): "east", (-1, 0): "west", (0, -1): "north", (0, 1): "south"}
# the cardinal push that brings a given map edge INTO view: to see the west
# edge the camera must travel west, etc.
_EDGE_DIR = {"west": (-1, 0), "east": (1, 0), "north": (0, -1), "south": (0, 1)}

# LLM localisation layer 3 (plan 4). The prompt is the production one; the
# offline probe (scripts/llm_localize_probe.py) imports it verbatim so it
# measures exactly what the live loop sends. FRAME 1 is the last localised frame,
# FRAME 2 the current (refused) frame.
LLM_LOCALIZE_PROMPT = (
    "You are given TWO screenshots from the same tactical map in the mobile "
    "game SD Gundam G Generation ETERNAL. The camera panned a little between "
    "them, so they overlap. A square grid is drawn over the map in both. The "
    "FIRST image is FRAME 1, the SECOND image is FRAME 2.\n"
    "Pick ONE distinctive landmark (a unit, terrain feature or structure) that "
    "is clearly visible in BOTH frames. Report which grid cell it sits in, in "
    "each frame, using 0-based integer coordinates: col counts grid columns "
    "from the LEFTMOST visible vertical gridline (0) increasing rightward; row "
    "counts grid rows from the TOPMOST visible horizontal gridline (0) "
    "increasing downward.\n"
    'Answer strictly as JSON: {"landmark": "<short description>", '
    '"frame1": {"col": <int>, "row": <int>}, '
    '"frame2": {"col": <int>, "row": <int>}}'
)
# an LLM offset hypothesis is trusted only if a patch cropped at its claimed cell
# in each frame cross-correlates this high (absolute floor); TM_CCOEFF_NORMED is
# unreliable on flat regions (CLAUDE.md), so a patch below this texture floor
# (std) is refused outright rather than matched against empty starfield.
LLM_PATCH_HALF = 40
LLM_PATCH_SEARCH = 22
LLM_PATCH_MIN = 0.55
LLM_PATCH_MIN_STD = 10.0


def _reply_cell(node: object) -> tuple[int, int] | None:
    if not isinstance(node, dict):
        return None
    try:
        return int(node["col"]), int(node["row"])
    except (KeyError, TypeError, ValueError):
        return None


def _cell_patch(
    frame: np.ndarray, lat: "vision.MapLattice", cell: tuple[int, int], half: int
) -> np.ndarray | None:
    """A square crop centred on cell (col, row) using the frame's own lattice, or
    None when the cell is off-lattice or too close to a frame edge to crop a full
    window."""
    col, row = cell
    if not (0 <= col < len(lat.cols) - 1 and 0 <= row < len(lat.rows) - 1):
        return None
    cx = (lat.cols[col] + lat.cols[col + 1]) // 2
    cy = (lat.rows[row] + lat.rows[row + 1]) // 2
    h, w = frame.shape[:2]
    x0, x1 = max(0, cx - half), min(w, cx + half)
    y0, y1 = max(0, cy - half), min(h, cy + half)
    if x1 - x0 < half or y1 - y0 < half:
        return None
    return frame[y0:y1, x0:x1]


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
    # localisation layer 3 (plan 4): an injected screen reader whose landmark
    # hypotheses are gated by patch verification + edge consistency before they
    # touch a coordinate. None (the default, and every machine without ollama)
    # makes _place skip the tier so the loop is bit-identical to the pure
    # deterministic version.
    llm: LlmScreenReader | None = None
    # factionless relocalisation pool for bring_to_view (shared with the
    # controller's adopted census).
    pool: TacticalMap = field(default_factory=TacticalMap, repr=False)
    # (cols, rows) expected extent from a cached stage definition. A planning
    # hint fed to CellMap: the frontier reaches toward where the cache says the
    # edge is and the nudge budget scales to the known size. NEVER an edge (the
    # scan still has to SEE each boundary); dropped + logged the moment the seen
    # geometry contradicts it. None makes the loop bit-identical to a cold scan.
    bounds_hint: tuple[int, int] | None = None
    # native-resolution diagnostic sink for refused-localisation forensics
    # (輪七): (frame, tag) -> ledger-relative path, independent of the ledger's
    # downscaled thumbnail pipeline. None (tests, no ledger) just records no path.
    diag_save: Callable[[np.ndarray, str], str | None] | None = None
    # Round 1.11 keyguard defence: the controller wires keyguard.ensure_unlocked
    # here. The game's battery-saver touch lock can dim the frame between the
    # controller's 15s keyguard checks -- mid-scan, at the exact read that anchors
    # the survey -- and 批7's brightness filter then starves the darkened frame of
    # gridline votes (observe -> None). Poked ONLY on a failed observation
    # (failure-response, not per-frame, to bound adb cost) so the caller can
    # re-capture and retry once. None (legacy, no keyguard) is a no-op and leaves
    # every path bit-identical; it never counts as a nudge (spends no scan budget).
    guard: Callable[[], None] | None = None

    # -- outputs (set by a successful collect) ------------------------------
    census: TacticalMap | None = field(default=None, repr=False)
    bounds: dict | None = None
    size: tuple[int | None, int | None] | None = None
    nudges: int = 0

    def __post_init__(self) -> None:
        if self.observe is None:
            self.observe = lambda frame: observe_frame(frame, detect=self.detect)
        # the walk state nudge()/bring_to_view() write: _navigator() builds a
        # fresh source purely for the survey's bring_to_view and never runs
        # collect(), so both must exist from construction. collect() re-sets
        # them to the same values (behaviour unchanged).
        self._nudges = 0
        self._last_nudge: Direction = (0, 0)

    # -- public loop --------------------------------------------------------

    def collect(self) -> TacticalMap:
        """Scan the whole map and return the census, or raise SurveyIncomplete.
        Phase A anchors the NW corner; Phase B fills by frontier until the
        ledger closes (all edges seen and every hole either covered or condemned
        unreachable) or the budget runs out."""
        frame = self.start_frame if self.start_frame is not None else self.capture()
        self._refused = 0
        self._relocated = 0
        self._starve = 0
        frame = self._clear_full(frame)
        self._map = CellMap(size_hint=self.bounds_hint)
        self._hint_drop_logged = False
        self._nudges = 0
        self._unreachable: set[tuple[int, int]] = set()
        self._stuck = 0
        self._last_offset: tuple[int, int] = (0, 0)
        self._last_nudge: Direction = (0, 0)
        self._inconsistency: str | None = None

        obs = self.observe(frame)
        if obs is None:
            # 輪十一: a no-lattice anchor read is the last frame the batch7
            # brightness filter starved -- most likely the battery-saver touch
            # lock dimming mid-scan. Stash the native frame BEFORE any recovery
            # (the entry path had no forensics -- only downscaled thumbnails --
            # so the hypothesis could not be settled offline), poke the guard to
            # dismiss a lock, then re-capture and re-observe once.
            diag_path = self._save_diag(frame, "anchor_no_lattice")
            self._guard()
            frame, obs = self._capture_observe()
            if obs is None:
                detail = f" (diag {diag_path})" if diag_path else ""
                raise SurveyIncomplete(
                    f"coverage scan: anchor frame carried no lattice{detail}"
                )
        # 輪十 anchor-evidence gate: refuse to anchor on an un-re-findable void.
        # Seeks toward the interior when the start view carries no localisation
        # evidence; returns a units-bearing frame or fails loud (anchor_starved).
        frame, obs = self._anchor_seek(frame, obs)
        self._map.anchor(obs)
        self._note_hint_drop()
        # the last frame that localised (pixels + its observation): the LLM assist
        # pairs the current refused frame against this one and crops verification
        # patches from it. The anchor frame is the first.
        self._anchor_frame = frame
        self._anchor_obs = obs
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
        for _ in range(self._scan_budget(obs)):
            edges_seen = self._all_edges_seen()
            try:
                target = self._map.frontier()
            except MapStateInconsistent as exc:
                # empty coverage with observations integrated is upstream
                # breakage, not a finished scan -- fail honestly, never "complete"
                self._inconsistency = str(exc)
                outcome = "inconsistent"
                break
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
            report = self._place(frame, obs)
            if report.offset is None:
                self._refused += 1
                self._save_refused(frame, report, obs)
                # 輪十一: a refusal can be the battery-saver touch lock dimming
                # the frame between the controller's 15s keyguard checks. Poke
                # the guard and re-capture ONCE before spending clear/recovery
                # budget on it. Gated on a wired guard so the legacy path is
                # bit-identical; the re-capture is not a nudge.
                if self.guard is not None:
                    self._guard()
                    frame, obs = self._capture_observe()
                    report = self._place(frame, obs)
                if report.offset is None:
                    # a docked enemy-selection HUD poisons the whole-frame vote;
                    # clear it and retry placement before spending recovery
                    # budget (輪七). No residue -> same frame, straight to
                    # recovery (old behaviour bit-for-bit).
                    cleared = self._clear_full(frame)
                    if cleared is not frame:
                        frame = cleared
                        obs = self.observe(frame)
                        report = self._place(frame, obs)
                    if report.offset is None:
                        frame, obs = self._recover(frame, obs, report)
                        if self._map.coverage()[0] > before:
                            self._starve = 0
                        else:
                            self._starve += 1
                            if self._starve >= STARVE_LIMIT:
                                outcome = "starved"
                                break
                        continue
            conflict = self._integrate(frame, obs, report)
            after = self._map.coverage()[0]
            self._log_localized(obs, report, after - before, conflict)
            self._starve = 0
            if after > before:
                self._stuck = 0
            else:
                self._stuck += 1
                if self._stuck >= STUCK_LIMIT:
                    self._unreachable.add(target)
                    self._stuck = 0
        return self._finish(outcome)

    # -- localisation seam --------------------------------------------------

    def _place(self, frame: np.ndarray, obs: FrameObservation | None) -> LocalizeReport:
        """Localise obs against the map: the deterministic report (edge_pin /
        vote), and on a deterministic refusal the LLM assist tier when one is
        wired (self.llm). The single seam every localisation flows through so the
        frame_localized ledger carries the real margin and source, and the assist
        (source='llm_assist') sits exactly where plan 4 puts it -- after localize
        refuses, before the recovery protocol. Returns a refused report when obs
        is None (caller runs recovery)."""
        if obs is None:
            return LocalizeReport(
                offset=None, source=None, margin=None, unit_hits=0, terrain_fraction=0.0
            )
        report = self._map.localize_report(obs)
        if report.offset is None and self.llm is not None:
            assist = self._llm_assist(frame, obs)
            if assist is not None:
                return assist
        return report

    def _integrate(
        self, frame: np.ndarray, obs: FrameObservation, report: LocalizeReport
    ) -> int:
        """Fold the localised frame in and return CellMap.integrate's
        terrain_conflict count so the caller can log it (輪八 mislocalisation
        warning)."""
        conflict = self._map.integrate(obs, report.offset)
        self._note_hint_drop()
        self._last_offset = report.offset
        self._anchor_frame = frame
        self._anchor_obs = obs
        return conflict

    def _note_hint_drop(self) -> None:
        """Log cache_bounds_dropped once, the first time CellMap discards the
        cache size hint because the SEEN geometry contradicted it (紅線: hint
        never survives a conflicting real edge)."""
        if self._hint_drop_logged or not self._map.hint_dropped:
            return
        self._hint_drop_logged = True
        self._log(
            "cache_bounds_dropped",
            hint=list(self.bounds_hint) if self.bounds_hint else None,
            reason=self._map.hint_drop_reason,
            bounds=dict(self._map.bounds),
        )

    def _scan_budget(self, obs: FrameObservation | None) -> int:
        """The fill-loop nudge ceiling. SCAN_MAX_NUDGES with no cache hint; with
        one, scaled to the known map size (a serpentine-ish cover of cols x rows
        at this viewport takes far more than the cold default on a large stage)
        so a warm rescan does not fail-fast spuriously. Capped, and only ever
        raises the ceiling -- a wrong hint that inflates it is still bounded and
        gets dropped mid-scan anyway."""
        if self.bounds_hint is None or obs is None:
            return SCAN_MAX_NUDGES
        cols, rows = self.bounds_hint
        vc = max(1, len(obs.lattice.cols) - 2)
        vr = max(1, len(obs.lattice.rows) - 2)
        frames = math.ceil(cols / vc) * math.ceil(rows / vr)
        return min(max(SCAN_MAX_NUDGES, frames * 3), SCAN_MAX_NUDGES * 8)

    def _llm_assist(
        self, frame: np.ndarray, obs: FrameObservation
    ) -> LocalizeReport | None:
        """Localisation layer 3: consult the injected LlmScreenReader for a
        landmark shared by the last localised frame (FRAME 1) and the current
        refused one (FRAME 2), turn its two grid cells into an offset hypothesis,
        then trust NOTHING until two deterministic guards pass -- (a) a patch
        cropped at each claimed cell cross-correlates over LLM_PATCH_MIN (proof
        the two positions are the same content, so the offset is a real
        correspondence), and (b) the offset is edge-consistent
        (CellMap.verify_offset: nothing covered may sit past a visible boundary).
        Only then is the offset returned (source='llm_assist'); any miss returns
        None and the caller falls through to the recovery protocol. force=True
        bypasses the reader's 60s rate limit so these sparse refusal events are
        not swallowed."""
        anchor_frame = getattr(self, "_anchor_frame", None)
        anchor_obs = getattr(self, "_anchor_obs", None)
        if anchor_frame is None or anchor_obs is None:
            return None
        reply = self.llm.localize_pair(anchor_frame, frame, LLM_LOCALIZE_PROMPT, force=True)
        if reply is None:
            return None
        a_cell = _reply_cell(reply.get("frame1"))
        b_cell = _reply_cell(reply.get("frame2"))
        if a_cell is None or b_cell is None:
            return None
        offset = (
            self._last_offset[0] + a_cell[0] - b_cell[0],
            self._last_offset[1] + a_cell[1] - b_cell[1],
        )
        score = self._patch_certainty(
            anchor_frame, anchor_obs.lattice, a_cell, frame, obs.lattice, b_cell
        )
        accepted = score >= LLM_PATCH_MIN and self._map.verify_offset(obs, offset)
        self._log(
            "llm_assist",
            accepted=accepted,
            offset=[offset[0], offset[1]],
            patch=round(score, 3),
            landmark=str(reply.get("landmark", ""))[:60],
        )
        if not accepted:
            return None
        return LocalizeReport(
            offset=offset, source="llm_assist", margin=score, unit_hits=0, terrain_fraction=0.0
        )

    def _patch_certainty(
        self,
        a_frame: np.ndarray,
        a_lat: "vision.MapLattice",
        a_cell: tuple[int, int],
        b_frame: np.ndarray,
        b_lat: "vision.MapLattice",
        b_cell: tuple[int, int],
    ) -> float:
        """Peak TM_CCOEFF_NORMED of the FRAME 1 landmark patch searched in a
        slightly larger FRAME 2 window (the search band absorbs sub-cell camera
        drift). A patch flatter than LLM_PATCH_MIN_STD is refused with 0.0: on
        near-uniform starfield TM_CCOEFF aliases high against any other empty
        region (CLAUDE.md), so it cannot verify a correspondence there."""
        tpl = _cell_patch(a_frame, a_lat, a_cell, LLM_PATCH_HALF)
        win = _cell_patch(b_frame, b_lat, b_cell, LLM_PATCH_HALF + LLM_PATCH_SEARCH)
        if tpl is None or win is None:
            return 0.0
        if float(tpl.std()) < LLM_PATCH_MIN_STD:
            return 0.0
        if win.shape[0] < tpl.shape[0] or win.shape[1] < tpl.shape[1]:
            return 0.0
        return float(cv2.matchTemplate(win, tpl, cv2.TM_CCOEFF_NORMED).max())

    def _log_localized(
        self,
        obs: FrameObservation,
        report: LocalizeReport,
        new_cells: int | None,
        terrain_conflict: int,
    ) -> None:
        self._log(
            "frame_localized",
            offset=[report.offset[0], report.offset[1]],
            margin=report.margin,
            source=report.source,
            edges={s: obs.edges[s] for s in SIDES},
            new_cells=new_cells,
            terrain_conflict=terrain_conflict,
        )

    @staticmethod
    def _edges_visibility(obs: FrameObservation | None) -> dict[str, int | None]:
        """The per-side edge line index this frame sees (None = off-screen), or
        all-None when the frame carried no observation. Refused telemetry (輪八):
        an outward-extrapolation refusal with no visible edge reads differently
        from one that saw an edge and still could not clear the margin."""
        return {s: obs.edges[s] for s in SIDES} if obs is not None else {s: None for s in SIDES}

    # -- phases -------------------------------------------------------------

    @staticmethod
    def _anchorable(obs: FrameObservation | None) -> bool:
        """Does this frame carry enough evidence to be a localisation anchor?
        localize() places later frames by a unit constellation and by distinctive
        per-cell terrain; a frame strong in EITHER is re-findable once the camera
        moves. The 輪十 void has neither (0 units + uniform starfield), so it is
        the only shape the anchor gate diverts. TERRAIN_MIN_OVERLAP is the exact
        distinctive-cell count localize() needs before it trusts a terrain vote,
        so it is the honest 'terrain alone can localise this' threshold."""
        if obs is None:
            return False
        return (
            len(obs.units) >= ANCHOR_MIN_UNITS
            or len(obs.distinctive) >= TERRAIN_MIN_OVERLAP
        )

    def _seek_direction(
        self, frame: np.ndarray, obs: FrameObservation | None, step: int
    ) -> tuple[Direction, str]:
        """Which cardinal push brings the map interior (and its units) into view.
        Frame evidence only (定案 1 -- never a coordinate):
        1. a visible cut-off edge means the interior lies the opposite way (see
           the east edge -> go west, see north -> go south); when both a
           horizontal and a vertical edge show, alternate the two single-axis
           pushes by step parity (合成單向輪替) so neither axis stalls;
        2. no edge to lean on -> steer toward the density-peak centroid if the
           detector still finds peaks the observation dropped (rim-clamped /
           off-lattice);
        3. nothing at all -> a fixed probe order so the seek still explores.
        Returns (direction, basis) for the anchor_seek ledger event."""
        cx = cy = 0
        if obs is not None:
            if obs.edges["east"] is not None:
                cx -= 1
            if obs.edges["west"] is not None:
                cx += 1
            if obs.edges["north"] is not None:
                cy += 1
            if obs.edges["south"] is not None:
                cy -= 1
        if cx and cy:
            return ((cx, 0), "edge") if step % 2 == 0 else ((0, cy), "edge")
        if cx:
            return (cx, 0), "edge"
        if cy:
            return (0, cy), "edge"
        try:
            peaks = self.detect(frame)
        except Exception:
            peaks = []
        if peaks:
            mx = sum(p[0] for p in peaks) / len(peaks)
            my = sum(p[1] for p in peaks) / len(peaks)
            dcol, drow = mx - PAN_CENTER[0], my - PAN_CENTER[1]
            if abs(dcol) >= abs(drow):
                return ((1, 0) if dcol > 0 else (-1, 0)), "peak"
            return ((0, 1) if drow > 0 else (0, -1)), "peak"
        probe = ((-1, 0), (0, 1), (1, 0), (0, -1))
        return probe[step % 4], "probe"

    def _anchor_seek(
        self, frame: np.ndarray, obs: FrameObservation | None
    ) -> tuple[np.ndarray, FrameObservation]:
        """輪十 anchor-evidence gate. When the start view already carries
        localisation evidence (_anchorable) this is a no-op -- returns the frame
        untouched, zero behaviour change for a healthy start. Otherwise seek the
        interior: pick a direction from frame evidence, nudge, re-observe, and
        exit the moment a localisable frame appears. Budgeted by ANCHOR_MAX_NUDGES
        (an obs=None seek frame still spends a step and continues -- never an
        infinite wait); the budget spent without a localisable anchor fails loud
        (anchor_starved) rather than committing to the void."""
        if self._anchorable(obs):
            return frame, obs
        for step in range(ANCHOR_MAX_NUDGES):
            direction, basis = self._seek_direction(frame, obs, step)
            self._log(
                "anchor_seek",
                dir=_DIR_NAME.get(direction),
                basis=basis,
                peaks=(len(obs.units) if obs is not None else 0),
            )
            self.nudge(direction, frame)
            frame, obs = self._capture_observe()
            # 輪十一: a seek step that reads no lattice may be the battery-saver
            # touch lock dimming the frame -- poke the guard and re-capture once
            # before spending another seek step (or condemning the anchor void).
            # Gated on a wired guard so the legacy seek is bit-identical; the
            # re-capture is not a nudge.
            if obs is None and self.guard is not None:
                self._guard()
                frame, obs = self._capture_observe()
            if self._anchorable(obs):
                return frame, obs
        self._finish("anchor_starved")

    def _anchor_phase(
        self, frame: np.ndarray, obs: FrameObservation
    ) -> tuple[np.ndarray, FrameObservation | None]:
        """Drive to the NW corner: nudge toward whichever of west/north is not
        yet seen until both register (map smaller than the viewport finishes at
        once). Best effort -- if the corner resists, Phase B's frontier keeps
        seeking the unseen edges and the budget is the backstop.

        輪十 brake: the same zero-progress streak the fill loop carries
        (STARVE_LIMIT). A corner push that refuses AND whose recovery cannot
        relocate is a starving anchor phase; K such in a row fails loud rather
        than burning the whole ANCHOR_MAX_NUDGES x RELOC_MAX_NUDGES budget on a
        camera that will not re-anchor (the void the evidence gate already guards
        the START frame against -- this guards the drive to the corner)."""
        starve = 0
        for _ in range(ANCHOR_MAX_NUDGES):
            need = [s for s in ("west", "north") if self._map.bounds[s] is None]
            if not need:
                break
            self.nudge(_EDGE_DIR[need[0]], frame)
            frame, obs = self._capture_observe()
            report = self._place(frame, obs)
            if report.offset is None:
                before = self._relocated
                frame, obs = self._recover(frame, obs, report)
                if self._relocated > before:
                    starve = 0
                else:
                    starve += 1
                    if starve >= STARVE_LIMIT:
                        self._finish("anchor_phase_starved")
                continue
            conflict = self._integrate(frame, obs, report)
            self._log_localized(obs, report, None, conflict)
            starve = 0
        return frame, obs

    def _confirm(
        self, frame: np.ndarray, obs: FrameObservation | None
    ) -> tuple[np.ndarray, FrameObservation | None]:
        """Re-observe the current view without moving and fold it in again, so
        the reference frame's units clear MIN_SUPPORT on a genuine second
        sighting (not a doubled single read)."""
        cframe, cobs = self._capture_observe()
        if cobs is not None:
            creport = self._map.localize_report(cobs)
            if creport.offset is not None:
                self._integrate(cframe, cobs, creport)
                return cframe, cobs
        return frame, obs

    def _recover(
        self,
        frame: np.ndarray,
        obs: FrameObservation | None,
        refused: LocalizeReport,
    ) -> tuple[np.ndarray, FrameObservation | None]:
        """Localisation refused (isolated pairing / over-move / ambiguous
        frame): undo the move that lost the lock -- reversing the last nudge
        heads straight back into the covered mass (which holds the registered
        edges), re-overlapping known terrain so localize or an edge pin
        re-anchors us. With no prior nudge (lost at the very anchor) steer
        toward the nearest registered edge. The direction is fixed for the whole
        sortie so recovery nudges cannot oscillate. Budgeted; on exhaustion
        returns with obs unplaced so the caller counts it as no progress.

        `refused` is the report that triggered recovery; its margin / unit_hits /
        terrain_fraction and the frame's edge visibility ride the
        localize_refused event so a refused frame's evidence is on record (輪八
        遙測), and the relocated event carries the relocation's terrain_conflict
        count."""
        recover_dir = self._recovery_direction(obs)
        self._log(
            "scan_recovery",
            reason="localize_refused",
            nudges=0,
            margin=refused.margin,
            unit_hits=refused.unit_hits,
            terrain_fraction=refused.terrain_fraction,
            edges=self._edges_visibility(obs),
        )
        for i in range(1, RELOC_MAX_NUDGES + 1):
            self.nudge(recover_dir, frame)
            frame, obs = self._capture_observe()
            report = (
                self._map.localize_report(obs)
                if obs is not None
                else LocalizeReport(None, None, None, 0, 0.0)
            )
            if report.offset is not None:
                conflict = self._integrate(frame, obs, report)
                self._relocated += 1
                self._log(
                    "scan_recovery", reason="relocated", nudges=i, terrain_conflict=conflict
                )
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
            refused=self._refused,
            relocated=self._relocated,
            outcome=outcome,
        )
        stats = (
            f"{self._refused} refused / {self._relocated} relocated, "
            f"bounds {dict(self._map.bounds)}"
        )
        if outcome == "inconsistent":
            raise SurveyIncomplete(
                f"map state inconsistent: {self._inconsistency}"
            )
        if outcome == "starved":
            raise SurveyIncomplete(
                f"localization starving: {self._starve} consecutive refused "
                f"with no integration progress; {stats}"
            )
        if outcome == "anchor_starved":
            raise SurveyIncomplete(
                f"anchor without units: {self._nudges} seek nudges found no "
                f"localizable reference (0 units, no distinctive terrain); {stats}"
            )
        if outcome == "anchor_phase_starved":
            raise SurveyIncomplete(
                f"anchor phase starving: {STARVE_LIMIT} consecutive corner "
                f"pushes refused with no relocation; {stats}"
            )
        if outcome in ("complete", "unreachable_only") and self._all_edges_seen():
            self.census, self.bounds = self._map.to_tacmap()
            self.size = self._map.size()
            self.nudges = self._nudges
            return self.census
        raise SurveyIncomplete(
            f"coverage scan did not close: covered {covered}/{total}, "
            f"unreachable {len(self._unreachable)}, edges {dict(self._map.bounds)}; "
            f"{stats}"
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
        """Modal-only obstruction clearing on every capture -- the unit detail
        modal freezes panning wholesale (drags slide on screen while the camera
        does not move). Delegates to map_view.clear_obstruction, the single
        source of truth; this source's capture/tap/sleep fields satisfy the
        perception/actuator/sleep seams directly. The selection-residue leg is
        deliberately NOT wired here (no detect passed): it belongs only at the
        two defence points (_clear_full) so the recovery-capture path keeps its
        pristine, empty-tap-free semantics (批7 red line)."""
        return map_view.clear_obstruction(
            self,
            self,
            frame,
            sleep=self.sleep,
            on_close=lambda f: self._log("scan_modal_closed", frame=f),
        )

    def _clear_full(self, frame: np.ndarray) -> np.ndarray:
        """Full obstruction chain (輪七): modal THEN enemy-selection residue,
        fail-loud. Wired at exactly two points -- the scan pre-anchor and the
        fill-loop refused branch -- where a docked comparison HUD would poison
        localisation. Returns a fresh frame when something was cleared, the same
        frame object when nothing was (lets the caller cheaply detect a clear).
        An undismissable residue becomes a loud SurveyIncomplete rather than
        anchoring on a poisoned frame."""
        try:
            return map_view.clear_obstruction(
                self,
                self,
                frame,
                sleep=self.sleep,
                detect=self.detect,
                on_close=lambda f: self._log("scan_modal_closed", frame=f),
                on_clear_selection=lambda f, pt, i: self._log(
                    "scan_selection_cleared", point=list(pt), attempt=i
                ),
            )
        except map_view.SelectionResidueStuck as exc:
            raise SurveyIncomplete(str(exc)) from exc

    def _guard(self) -> None:
        """Round 1.11 failure-response keyguard defence. Poke the injected guard
        (the controller wires keyguard.ensure_unlocked) so the game's
        battery-saver touch lock -- which dims the frame and starves 批7's
        brightness filter of gridline votes, invisible to the controller's 15s
        keyguard cadence -- is dismissed before the caller re-captures and retries.
        A no-op when no guard is wired (legacy, bit-identical). Never a nudge: it
        spends no scan budget."""
        if self.guard is not None:
            self.guard()

    def _save_diag(self, frame: np.ndarray, tag: str) -> str | None:
        """Stash a NATIVE-resolution diagnostic frame via the diag_save seam
        (outside the ledger's downscaled thumbnail pipeline) and return its
        ledger-relative path, or None when no sink is wired or the save fails.
        The single seam for scan forensics (refused frames + the 輪十一 entry
        no-lattice存證)."""
        if self.diag_save is None:
            return None
        try:
            return self.diag_save(frame, tag)
        except Exception:
            return None

    def _save_refused(
        self, frame: np.ndarray, report: LocalizeReport, obs: FrameObservation | None
    ) -> None:
        """Round 1.7 forensics: dump the first 3 refused frames and every 20th
        after at NATIVE resolution (outside the ledger's downscaled thumbnail
        pipeline) and record the path in a refused_frame event, so a poisoned
        localisation can be re-probed offline. self._refused is already bumped.

        輪八 telemetry: the refused report already carries margin / unit_hits /
        terrain_fraction (read but never logged) -- record them plus the frame's
        edge visibility so a refused frame's evidence is on the ledger without a
        re-probe (a low-margin miss vs a no-overlap miss read differently)."""
        n = self._refused
        if not (n <= 3 or n % 20 == 0):
            return
        path = self._save_diag(frame, f"refused{n:03d}")
        self._log(
            "refused_frame",
            n=n,
            path=path,
            margin=report.margin,
            unit_hits=report.unit_hits,
            terrain_fraction=report.terrain_fraction,
            edges=self._edges_visibility(obs),
        )

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
