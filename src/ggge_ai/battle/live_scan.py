"""Live serpentine acquisition behind the FrameSource seam (#26 批3a).

The controller's corner-anchored sweep, moved out whole: LiveScanSource
navigates (swipes, steers around eaten drags, closes stray modals),
measures every leg from what the frames show, and emits the MapFrame
series map_grid.read_board consumes. Navigation keeps a private,
factionless landmark pool for relocalization -- steering may read the
screen freely, but interpretation only ever sees the emitted series
(the frame_source contract). The controller's arc census keeps running
on its own copy of this walk until the phase-2 identify cutover
replaces its downstream in the same batch (roadmap 07-20: the old
census consumers have no substitute until inspect_unit lands).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from . import vision
from .frame_source import MapFrame
from .scout_intel import UNIT_DETAIL_CLOSE
from .tacmap import TacticalMap

log = logging.getLogger(__name__)

Point = tuple[float, float]

# panning works on the our-turn hub with no unit selected: dragging an
# empty map spot shifts the camera. drag opposite to the look direction,
# split evenly around the center so both endpoints stay inside the map
# area (vertical half-travel is shorter to clear the HUD and card strip)
PAN_CENTER = (1170, 500)
PAN_HALF = {"x": 300, "y": 200}
# a swipe starting on a unit sprite / UI element gets eaten instead of
# panning (20260719: row legs measuring ~0 with healthy response while the
# map clearly had room) -- an ineffective-but-measurable leg retries from
# these alternates before an edge verdict is accepted
PAN_ORIGINS = (PAN_CENTER, (940, 430), (1380, 610), (1170, 620))
# swipes land more reliably slow: 500ms drags got eaten in stretches on the
# 20260719 star map (post-action camera easing + adb drop flakiness)
PAN_SWIPE_MS = 700
PAN_SETTLE_S = 1.5
# a drag STARTING on a unit gets eaten -- in dense views (the event map's
# east cluster fills mid-screen) every static origin can sit on a unit at
# once, which froze whole scan stretches in both directions (runs 4/7/8/9).
# Origins are therefore picked per swipe from this candidate lattice by
# max-min distance to the visible arcs.
PAN_ORIGIN_GRID = tuple(
    (x, y) for y in (360, 470, 580, 660) for x in (760, 940, 1170, 1400, 1580)
)
PAN_DIRS = (("east", (1, 0)), ("west", (-1, 0)), ("north", (0, -1)), ("south", (0, 1)))
# serpentine full-map scan (turn 1): a pan whose measured travel is under
# this fraction of the gesture means the camera hit the map edge; leg
# budgets bound worst-case scan time on huge maps
SCAN_EDGE_RATIO = 0.3
SCAN_CORNER_MAX_LEGS = 8
SCAN_MAX_LEGS = 28

# MapFrame hints name the camera's travel direction; measured_shift is the
# content displacement, i.e. the negated camera delta (frame_source.py)
_HINT_BY_DIR = {(1, 0): "right", (-1, 0): "left", (0, -1): "up", (0, 1): "down"}


@dataclass
class LiveScanSource:
    """FrameSource over the live device: one collect() drives the corner
    phase plus the full serpentine and returns the anchored frame series.
    Ghost-sentencing bounds, the final camera and the anchoring verdict
    stay readable on the instance afterwards."""

    capture: Callable[[], np.ndarray]
    swipe: Callable[..., None]
    tap: Callable[[int, int], None]
    ledger_log: Callable[..., None] | None = None
    sleep: Callable[[float], None] = time.sleep
    start_frame: np.ndarray | None = None

    bounds: dict | None = None
    camera: Point = (0.0, 0.0)
    legs: int = 0
    corner_anchored: bool = False
    _pool: TacticalMap = field(default_factory=TacticalMap, repr=False)

    def collect(self) -> list[MapFrame]:
        frame = self.start_frame if self.start_frame is not None else self.capture()
        frame = self._clear_obstruction(frame)
        camera: Point = (0.0, 0.0)
        self._pool.reset()
        self._observe(frame, camera)
        legs = 0
        prev = frame
        pending = {"west": (-1, 0), "north": (0, -1)}
        while pending and legs < SCAN_CORNER_MAX_LEGS:
            for name in list(pending):
                camera, prev, actual, requested = self._pan_leg(
                    camera, prev, pending[name], label=f"corner_{name}"
                )
                legs += 1
                axis = 0 if name == "west" else 1
                if self._at_edge(actual, requested, axis):
                    del pending[name]
                if legs >= SCAN_CORNER_MAX_LEGS:
                    break
        corner = not pending
        bounds: dict | None = None
        if corner:
            # the corner IS the origin: everything measured on the way there
            # was in the drift-prone start frame, so pool and camera restart
            # in corner coordinates (the sweep below revisits it all anyway)
            camera = (0.0, 0.0)
            self._pool.reset()
            bounds = {"west": 0.0, "north": 0.0, "east": None, "south": None}
        else:
            log.warning("corner budget exhausted before the NW corner; unanchored series")
        self._observe(prev, camera)
        frames = [MapFrame(image=prev, label="corner" if corner else "start")]
        heading = (1, 0)
        bottom_row = False
        while legs < SCAN_MAX_LEGS:
            camera, prev, actual, requested = self._pan_leg(camera, prev, heading, label="row")
            legs += 1
            if self._at_edge(actual, requested, 0) and bounds is not None:
                side = "east" if heading[0] > 0 else "west"
                camera = (self._snap_bound(bounds, side, camera[0]), camera[1])
            self._observe(prev, camera)
            frames.append(self._emit(prev, heading, actual, "row"))
            if self._at_edge(actual, requested, 0):
                if bottom_row:
                    break
                camera, prev, actual, requested = self._pan_leg(
                    camera, prev, (0, 1), label="south_step"
                )
                legs += 1
                if self._at_edge(actual, requested, 1) and bounds is not None:
                    camera = (camera[0], self._snap_bound(bounds, "south", camera[1]))
                self._observe(prev, camera)
                frames.append(self._emit(prev, (0, 1), actual, "south_step"))
                if self._at_edge(actual, requested, 1):
                    # bottom edge: one last row still needs walking, or the
                    # far bottom corner is never in the series
                    bottom_row = True
                heading = (-heading[0], 0)
        self.bounds = bounds
        self.camera = camera
        self.legs = legs
        self.corner_anchored = corner
        if bounds is not None:
            self._log(
                "map_bounds",
                **{k: (round(v, 1) if v is not None else None) for k, v in bounds.items()},
            )
        return frames

    def _emit(self, image, direction, actual, label: str) -> MapFrame:
        return MapFrame(
            image=image,
            hint=_HINT_BY_DIR.get(tuple(direction)),
            label=label,
            measured_shift=(-actual[0], -actual[1]),
        )

    def _log(self, kind: str, **data) -> None:
        if self.ledger_log is not None:
            self.ledger_log(kind, **data)

    def _find_units(self, frame) -> list[tuple[int, int]]:
        # factionless by design (定案 5): navigation only needs "a unit is
        # here", the dock-side identify pass owns faction later
        return (
            vision.find_enemy_units(frame, region=vision.HUB_SCAN_REGION)
            + vision.find_ally_units(frame, region=vision.HUB_SCAN_REGION)
            + vision.find_third_party_units(frame, region=vision.HUB_SCAN_REGION)
        )

    def _observe(self, frame, camera: Point) -> None:
        self._pool.observe(camera, self._find_units(frame), [], [])

    def _clear_obstruction(self, frame):
        """Close whatever a stray scan tap opened over the map -- the unit
        detail modal freezes panning wholesale (drags slide fine on screen
        while measured movement reads zero: the 'frozen' stretches were a
        modal, not eaten gestures)."""
        if vision.is_unit_detail_modal(frame):
            self._log("scan_modal_closed", frame=frame)
            self.tap(*UNIT_DETAIL_CLOSE)
            self.sleep(1.2)
            return self.capture()
        return frame

    def _pan_origins(self, frame, hx, hy, count: int = 4) -> list[tuple[int, int]]:
        """Swipe origins for this frame, best first: the drag START point
        (origin + half-gesture) must sit on empty map or the game eats the
        drag, so candidates rank by their start point's distance to every
        visible arc. Falls back to the static list when the frame cannot be
        read (tests, degenerate frames)."""
        try:
            arcs = self._find_units(frame)
        except Exception:
            return list(PAN_ORIGINS[:count])
        if not arcs:
            return list(PAN_ORIGINS[:count])

        def clearance(candidate: tuple[int, int]) -> float:
            sx, sy = candidate[0] + hx, candidate[1] + hy
            return min(((sx - ax) ** 2 + (sy - ay) ** 2) ** 0.5 for ax, ay in arcs)

        ranked = sorted(PAN_ORIGIN_GRID, key=clearance, reverse=True)
        return ranked[:count]

    def _pan_leg(self, camera: Point, prev, direction, label: str = "pan"):
        """One measured pan. Returns (camera, frame, actual, requested);
        actual << requested means the camera hit the map edge. Every
        attempt measures the CUMULATIVE shift against the leg's base frame
        (never chained frame-to-frame): a blind first swipe -- weak phase
        response, no arc consensus -- is recovered by the next attempt's
        measurement instead of being guessed at, and an
        ineffective-but-measurable swipe retries from the alternate
        origins before an edge verdict stands (a swipe starting on a
        unit gets eaten and reads exactly like an edge). Only when every
        attempt stays blind does the gesture assumption fire, once."""
        dx, dy = direction
        hx, hy = dx * PAN_HALF["x"], dy * PAN_HALF["y"]
        requested = (2 * hx, 2 * hy)
        goal = (abs(requested[0]) + abs(requested[1])) * SCAN_EDGE_RATIO
        base = prev
        cur = prev
        cumulative: tuple[float, float] | None = None
        attempts = []
        for cx, cy in self._pan_origins(prev, hx, hy):
            self.swipe(cx + hx, cy + hy, cx - hx, cy - hy, PAN_SWIPE_MS)
            self.sleep(PAN_SETTLE_S)
            cur = self._clear_obstruction(self.capture())
            # landmark relocalization first (定案 3: adb gesture delivery is
            # inherently laggy and lossy, so position must come from what
            # the frame SHOWS): known units visible in the overlap fix the
            # camera absolutely, eaten and late-arriving swipes alike
            visible = self._find_units(cur)
            located = self._pool.locate(visible) if visible else None
            response = 0.0
            source = None
            if located is not None:
                delta = (located[0] - camera[0], located[1] - camera[1])
                # physical bound: one leg cannot out-travel its own gesture
                # (plus easing slack) -- a bigger jump is a false lock on an
                # aliased constellation, not a pan
                limit = abs(requested[0]) + abs(requested[1]) + 250
                if abs(delta[0]) + abs(delta[1]) <= limit:
                    cumulative, source = delta, "landmarks"
            if source is None:
                shift, response = vision.measure_camera_shift(base, cur)
                if response >= 0.05:
                    cumulative, source = shift, "phase"
                else:
                    arc = vision.measure_arc_shift(base, cur)
                    if arc is not None:
                        cumulative, source = arc, "arcs"
                    else:
                        source = "blind"
            attempts.append(
                {
                    "origin": [cx, cy],
                    "cumulative": (
                        [round(cumulative[0], 1), round(cumulative[1], 1)]
                        if cumulative is not None
                        else None
                    ),
                    "response": round(float(response), 4),
                    "source": source,
                }
            )
            if cumulative is not None and (
                abs(cumulative[0]) + abs(cumulative[1]) >= goal
            ):
                break
        if cumulative is None:
            # every attempt blind (featureless open space with no arcs in
            # view): assume one gesture's travel, flagged for downstream
            # correction by bounds snapping / hint arbitration
            cumulative = requested
        actual = (cumulative[0], cumulative[1])
        new_camera = (camera[0] + actual[0], camera[1] + actual[1])
        self._log(
            "scan_leg",
            leg=label,
            direction=list(direction),
            requested=list(requested),
            measured=[round(actual[0], 1), round(actual[1], 1)],
            attempts=attempts,
            camera=[round(new_camera[0], 1), round(new_camera[1], 1)],
        )
        return new_camera, cur, actual, requested

    @staticmethod
    def _at_edge(actual, requested, axis: int) -> bool:
        return abs(actual[axis]) < abs(requested[axis]) * SCAN_EDGE_RATIO

    @staticmethod
    def _snap_bound(bounds: dict, name: str, value: float, tolerance: float = 150.0) -> float:
        """First touch of a map edge records its coordinate; later touches
        within tolerance snap the camera back onto it (dead-reckoning
        drift dies at every edge instead of accumulating). A touch beyond
        tolerance is a different boundary segment on an irregular map --
        recorded coordinates stay honest, no snap."""
        known = bounds.get(name)
        if known is None:
            bounds[name] = value
            return value
        if abs(value - known) <= tolerance:
            return known
        return value
