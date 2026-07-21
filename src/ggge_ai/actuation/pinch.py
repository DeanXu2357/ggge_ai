"""Two-finger pinch gestures for map zoom (定案 4: 縮放地圖).

Two layers, both dependency-injected the way ``battle/live_scan.py`` injects
its swipe/tap/capture seams:

1. Pure event-sequence generation. ``pinch_events`` turns two finger
   trajectories into a Linux MT protocol-B ``(type, code, value)`` tuple
   series; ``render_sendevent`` folds that series into a single chained
   ``sendevent`` shell command. Both are side-effect-free and unit-tested
   offline -- no device, no adb.
2. Execution. ``SendeventPincher`` runs the rendered command through an
   injected shell callable. ``GesturePincher`` is the injection-API backend
   (below). ``zoom_out_max`` is backend-agnostic: it takes a ``pinch_step``
   callable and a ``capture`` callable and pinches until the grid pitch
   stops shrinking.

DEVICE REALITY (2026-07-20, R5CRC37JBYJ / SM-G9900, measured this session):
sendevent to /dev/input/event7 is REFUSED -- SELinux is Enforcing, there is
no ``su`` and ``adb root`` is rejected on this production build (ro.secure=1),
so the shell domain cannot write the touch node. The SendeventPincher path is
therefore kept as the portable/root-capable design (and is the layer the unit
tests pin), but ON THIS DEVICE the working backend is GesturePincher, which
injects a two-pointer MotionEvent through the uiautomator server (the same
non-root injection path ``adb shell input`` uses). A live pinch through it was
verified to zoom the battle map out this session.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

log = logging.getLogger(__name__)

Point = tuple[float, float]
Event = tuple[int, int, int]

# --- Linux input event codes (decimal), confirmed via getevent -lp event7 ---
EV_SYN = 0
EV_KEY = 1
EV_ABS = 3

SYN_REPORT = 0

BTN_TOUCH = 330  # 0x14a
BTN_TOOL_FINGER = 325  # 0x145

ABS_MT_SLOT = 47  # 0x2f
ABS_MT_TOUCH_MAJOR = 48  # 0x30
ABS_MT_POSITION_X = 53  # 0x35
ABS_MT_POSITION_Y = 54  # 0x36
ABS_MT_TRACKING_ID = 57  # 0x39

# a slot releases its contact by setting the tracking id to -1; sendevent
# takes an unsigned value, so -1 is written as 0xffffffff
RELEASE_ID = 0xFFFFFFFF

TOUCH_DEVICE = "/dev/input/event7"
LANDSCAPE_SCREEN = (2340, 1080)  # the game runs landscape; window_size() agrees
RAW_MAX = 4095  # ABS_MT_POSITION_X/Y both report 0..4095 on this panel


def screen_to_raw(
    x: float,
    y: float,
    *,
    screen: tuple[int, int] = LANDSCAPE_SCREEN,
    raw_max: int = RAW_MAX,
    swap_axes: bool = True,
    flip_panel_x: bool = False,
    flip_panel_y: bool = True,
) -> tuple[int, int]:
    """Landscape screen pixel -> raw touch coordinate (both raw axes 0..4095).

    The panel is physically portrait (1080x2340); the touch driver always
    reports in that native frame while the display sits at SurfaceOrientation
    ROTATION_90 (measured: ``dumpsys input`` SurfaceOrientation=1). So a 90deg
    axis swap is needed: the screen's vertical extent (1080) spans the panel's
    short raw-X edge, the screen's horizontal extent (2340) spans the panel's
    long raw-Y edge.

    DIRECTION IS DERIVED, NOT MEASURED. The usual empirical check -- drive one
    sendevent drag and read the content-shift direction -- is impossible here:
    /dev/input writes are SELinux-blocked (above), and injected events bypass
    the driver so getevent never observes them either. The defaults encode the
    standard ROTATION_90 (90deg CCW) convention: raw_x grows with screen y,
    raw_y grows as screen x decreases. ``flip_panel_x``/``flip_panel_y`` are the
    calibration knobs to flip either axis once a rooted device can confirm.
    """
    ws, hs = screen
    if swap_axes:
        u, u_span = float(y), float(hs)  # panel horizontal <- screen vertical
        v, v_span = float(x), float(ws)  # panel vertical   <- screen horizontal
    else:
        u, u_span = float(x), float(ws)
        v, v_span = float(y), float(hs)
    if flip_panel_x:
        u = u_span - u
    if flip_panel_y:
        v = v_span - v
    raw_x = round(u / u_span * raw_max)
    raw_y = round(v / v_span * raw_max)
    return (_clamp(raw_x, raw_max), _clamp(raw_y, raw_max))


def _clamp(value: int, hi: int, lo: int = 0) -> int:
    return max(lo, min(hi, value))


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _trajectory(
    start: Point, end: Point, steps: int, map_fn: Callable[[float, float], tuple[int, int]]
) -> list[tuple[int, int]]:
    """steps+1 raw waypoints from start to end inclusive (index 0 = contact)."""
    out = []
    for i in range(steps + 1):
        t = i / steps if steps else 1.0
        out.append(map_fn(_lerp(start[0], end[0], t), _lerp(start[1], end[1], t)))
    return out


def pinch_events(
    finger_a: tuple[Point, Point],
    finger_b: tuple[Point, Point],
    steps: int = 24,
    *,
    map_fn: Callable[[float, float], tuple[int, int]] = screen_to_raw,
    tracking_ids: tuple[int, int] = (100, 101),
    tool_finger: bool = True,
) -> list[Event]:
    """Protocol-B ``(type, code, value)`` series for a two-finger gesture.

    ``finger_a``/``finger_b`` are ``(start_screen, end_screen)`` point pairs;
    both fingers travel together over ``steps`` frames. Pass
    ``map_fn=lambda x, y: (int(x), int(y))`` to feed raw coordinates directly
    (the tests do this to check trajectory/lifecycle without the mapping).

    Lifecycle: slot 0 and slot 1 each open with a fresh tracking id, BTN_TOUCH
    (and optionally BTN_TOOL_FINGER) latch once on first contact, every frame
    ends with SYN_REPORT, and both slots release with tracking id -1 before
    BTN_TOUCH drops.
    """
    if steps < 1:
        raise ValueError("steps must be >= 1")
    id_a, id_b = tracking_ids
    if id_a == id_b:
        raise ValueError("the two fingers need distinct tracking ids")
    path_a = _trajectory(finger_a[0], finger_a[1], steps, map_fn)
    path_b = _trajectory(finger_b[0], finger_b[1], steps, map_fn)

    ev: list[Event] = []

    # contact: open both slots, latch the touch buttons once
    ev.append((EV_ABS, ABS_MT_SLOT, 0))
    ev.append((EV_ABS, ABS_MT_TRACKING_ID, id_a))
    ev.append((EV_KEY, BTN_TOUCH, 1))
    if tool_finger:
        ev.append((EV_KEY, BTN_TOOL_FINGER, 1))
    ev.append((EV_ABS, ABS_MT_POSITION_X, path_a[0][0]))
    ev.append((EV_ABS, ABS_MT_POSITION_Y, path_a[0][1]))
    ev.append((EV_ABS, ABS_MT_SLOT, 1))
    ev.append((EV_ABS, ABS_MT_TRACKING_ID, id_b))
    ev.append((EV_ABS, ABS_MT_POSITION_X, path_b[0][0]))
    ev.append((EV_ABS, ABS_MT_POSITION_Y, path_b[0][1]))
    ev.append((EV_SYN, SYN_REPORT, 0))

    # travel: one SYN-terminated frame per step, only emitting moved axes
    prev_a, prev_b = path_a[0], path_b[0]
    for i in range(1, steps + 1):
        ax, ay = path_a[i]
        bx, by = path_b[i]
        ev.append((EV_ABS, ABS_MT_SLOT, 0))
        if ax != prev_a[0]:
            ev.append((EV_ABS, ABS_MT_POSITION_X, ax))
        if ay != prev_a[1]:
            ev.append((EV_ABS, ABS_MT_POSITION_Y, ay))
        ev.append((EV_ABS, ABS_MT_SLOT, 1))
        if bx != prev_b[0]:
            ev.append((EV_ABS, ABS_MT_POSITION_X, bx))
        if by != prev_b[1]:
            ev.append((EV_ABS, ABS_MT_POSITION_Y, by))
        ev.append((EV_SYN, SYN_REPORT, 0))
        prev_a, prev_b = (ax, ay), (bx, by)

    # release: lift both slots, then drop the touch buttons
    ev.append((EV_ABS, ABS_MT_SLOT, 0))
    ev.append((EV_ABS, ABS_MT_TRACKING_ID, RELEASE_ID))
    ev.append((EV_ABS, ABS_MT_SLOT, 1))
    ev.append((EV_ABS, ABS_MT_TRACKING_ID, RELEASE_ID))
    ev.append((EV_KEY, BTN_TOUCH, 0))
    if tool_finger:
        ev.append((EV_KEY, BTN_TOOL_FINGER, 0))
    ev.append((EV_SYN, SYN_REPORT, 0))
    return ev


def render_sendevent(
    events: Iterable[Event],
    *,
    device: str = TOUCH_DEVICE,
    frame_pause_s: float = 0.008,
) -> str:
    """Fold the event series into ONE shell command: ``sendevent`` per event,
    a short ``sleep`` inserted after each SYN_REPORT so the frames land as a
    smooth drag rather than one teleport. One adb round-trip for the whole
    gesture, not one per event."""
    parts: list[str] = []
    for etype, code, value in events:
        parts.append(f"sendevent {device} {etype} {code} {value}")
        if etype == EV_SYN and code == SYN_REPORT and frame_pause_s > 0:
            parts.append(f"sleep {frame_pause_s:g}")
    return "; ".join(parts)


@dataclass
class SendeventPincher:
    """Executes a pinch by rendering the protocol-B series into a single
    ``sendevent`` shell command and handing it to the injected ``run_shell``.

    NOTE: blocked on R5CRC37JBYJ (SELinux denies writing /dev/input/event7,
    no root). Kept for rooted devices and as the tuple series the tests pin.
    """

    run_shell: Callable[[str], object]
    device: str = TOUCH_DEVICE
    steps: int = 24
    frame_pause_s: float = 0.008
    map_fn: Callable[[float, float], tuple[int, int]] = screen_to_raw

    def pinch(self, finger_a: tuple[Point, Point], finger_b: tuple[Point, Point]) -> None:
        events = pinch_events(
            finger_a, finger_b, self.steps, map_fn=self.map_fn
        )
        self.run_shell(render_sendevent(events, device=self.device, frame_pause_s=self.frame_pause_s))


@dataclass
class GesturePincher:
    """Injection-API backend: one call performs a two-pointer gesture in
    landscape screen pixels (no raw mapping -- the uiautomator server injects
    at the display layer). ``gesture`` is the injected seam, matching u2's
    ``d(...).gesture(start1, start2, end1, end2, steps)`` signature, so tests
    can pass a recorder and the live tool passes the real device element.
    This is the backend that actually works on the SELinux-locked device."""

    gesture: Callable[[Point, Point, Point, Point, int], object]
    steps: int = 40

    def pinch(self, finger_a: tuple[Point, Point], finger_b: tuple[Point, Point]) -> None:
        self.gesture(finger_a[0], finger_b[0], finger_a[1], finger_b[1], self.steps)


def zoom_out_fingers(
    center: Point = (1170.0, 500.0),
    *,
    start_span: float = 1000.0,
    end_span: float = 120.0,
    horizontal: bool = True,
) -> tuple[tuple[Point, Point], tuple[Point, Point]]:
    """Two symmetric fingers that start ``start_span`` apart and close to
    ``end_span`` -- a pinch-IN, i.e. zoom OUT. Default center (1170,500) sits
    mid-map, clear of the end-turn (275,182) / AUTO (1815,52) buttons up top
    and the unit-card strip along the bottom."""
    cx, cy = center
    h0, h1 = start_span / 2.0, end_span / 2.0
    if horizontal:
        a = ((cx - h0, cy), (cx - h1, cy))
        b = ((cx + h0, cy), (cx + h1, cy))
    else:
        a = ((cx, cy - h0), (cx, cy - h1))
        b = ((cx, cy + h0), (cx, cy + h1))
    return a, b


@dataclass
class PitchStep:
    index: int
    col_pitch: float | None
    row_pitch: float | None
    change: float | None  # frame mean-abs-diff vs the previous frame
    source: str  # "grid" when pitch read, "frame" when the fail-soft fired


def _col_row_pitch(frame) -> tuple[float | None, float | None]:
    """Median column/row gridline spacing via the vision lattice reader, or
    (None, None) when no lattice is on screen."""
    from ..battle import vision

    lattice = vision.read_grid_lattice(frame)
    if lattice is None:
        return (None, None)
    cols, rows = lattice

    def median_gap(pos: Sequence[int]) -> float | None:
        gaps = sorted(b - a for a, b in zip(pos, pos[1:]))
        if not gaps:
            return None
        n = len(gaps)
        return float(gaps[n // 2] if n % 2 else (gaps[n // 2 - 1] + gaps[n // 2]) / 2)

    return (median_gap(cols), median_gap(rows))


def _mean_abs_diff(prev, cur) -> float:
    import numpy as np

    from ..battle import vision

    x0, y0, w, h = vision.MAP_REGION
    a = prev[y0 : y0 + h, x0 : x0 + w].astype("float32")
    b = cur[y0 : y0 + h, x0 : x0 + w].astype("float32")
    return float(np.abs(a - b).mean())


def zoom_out_max(
    capture: Callable[[], object],
    pinch_step: Callable[[], None],
    *,
    measure: Callable[[object], tuple[float | None, float | None]] = _col_row_pitch,
    frame_change: Callable[[object, object], float] = _mean_abs_diff,
    obstruction: Callable[[object], object] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    settle_s: float = 1.3,
    max_pinches: int = 10,
    shrink_tol: float = 1.5,
    change_tol: float = 2.5,
    on_step: Callable[[PitchStep], None] | None = None,
) -> list[PitchStep]:
    """Pinch repeatedly until the map stops zooming out.

    Convergence primarily on the grid pitch: two pinches in a row that fail to
    shrink the column pitch by more than ``shrink_tol`` px means the camera hit
    minimum zoom. Fail-soft when the lattice cannot be read (grid off, pitch
    below the detector's floor): fall back to the frame mean-abs-diff over the
    map region -- two near-identical frames (change < ``change_tol``) count as
    settled. Every step is reported through ``on_step`` and in the return list.

    ``obstruction`` (optional) is handed each frame to close a stray unit-detail
    modal, mirroring live_scan._clear_obstruction; it returns the frame to keep.
    """
    frame = capture()
    if obstruction is not None:
        frame = obstruction(frame)
    col, row = measure(frame)
    steps = [PitchStep(0, col, row, None, "grid" if col is not None else "frame")]
    if on_step:
        on_step(steps[0])

    stable = 0
    prev_frame, prev_col = frame, col
    for i in range(1, max_pinches + 1):
        pinch_step()
        sleep(settle_s)
        frame = capture()
        if obstruction is not None:
            frame = obstruction(frame)
        col, row = measure(frame)
        change = frame_change(prev_frame, frame)

        if col is not None and prev_col is not None:
            shrank = (prev_col - col) > shrink_tol
            source = "grid"
        else:
            # no clean pitch this step: lean on whether anything moved at all
            shrank = change > change_tol
            source = "frame"
        stable = 0 if shrank else stable + 1

        rec = PitchStep(i, col, row, round(change, 3), source)
        steps.append(rec)
        if on_step:
            on_step(rec)
        if stable >= 2:
            break
        prev_frame, prev_col = frame, (col if col is not None else prev_col)
    return steps
