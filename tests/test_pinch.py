"""Offline tests for the pinch gesture layer: raw mapping, protocol-B event
series (slot/tracking lifecycle, release, interpolation), the single-command
renderer, and the zoom_out_max convergence logic. No device."""

from __future__ import annotations

from ggge_ai.actuation import pinch
from ggge_ai.actuation.pinch import (
    ABS_MT_POSITION_X,
    ABS_MT_POSITION_Y,
    ABS_MT_SLOT,
    ABS_MT_TRACKING_ID,
    BTN_TOUCH,
    EV_KEY,
    EV_SYN,
    RELEASE_ID,
    SYN_REPORT,
    GesturePincher,
    PitchStep,
    SendeventPincher,
    pinch_events,
    render_sendevent,
    screen_to_raw,
    zoom_out_fingers,
    zoom_out_max,
)

IDENTITY = lambda x, y: (int(round(x)), int(round(y)))  # noqa: E731


# --- raw coordinate mapping (direction is the derived ROTATION_90 default) ---

def test_screen_to_raw_center_maps_to_center():
    assert screen_to_raw(1170, 540) == (2048, 2048)


def test_screen_to_raw_corners_rotation90_default():
    # screen top-left -> panel (raw_x=0 from y=0, raw_y flipped to max from x=0)
    assert screen_to_raw(0, 0) == (0, 4095)
    # screen bottom-right -> the opposite raw corner
    assert screen_to_raw(2340, 1080) == (4095, 0)


def test_screen_to_raw_axis_swap_directions():
    # raw_x is driven by screen Y; raw_y by screen X (the 90deg swap)
    only_y = screen_to_raw(0, 1080)
    only_x = screen_to_raw(2340, 0)
    assert only_y == (4095, 4095)  # y max -> raw_x max, x=0 -> raw_y max (flip)
    assert only_x == (0, 0)  # x max -> raw_y min (flip), y=0 -> raw_x min


def test_screen_to_raw_monotonic_with_flips():
    # raw_x grows with screen y
    assert screen_to_raw(500, 200)[0] < screen_to_raw(500, 800)[0]
    # raw_y shrinks as screen x grows (default flip_panel_y)
    assert screen_to_raw(200, 500)[1] > screen_to_raw(800, 500)[1]
    # flipping the knob reverses that axis
    left = screen_to_raw(200, 500, flip_panel_y=False)[1]
    right = screen_to_raw(800, 500, flip_panel_y=False)[1]
    assert left < right


def test_screen_to_raw_clamps_into_range():
    rx, ry = screen_to_raw(5000, -50)
    assert 0 <= rx <= 4095 and 0 <= ry <= 4095


# --- protocol-B event series ---

def _events():
    return pinch_events(
        ((100, 100), (200, 100)),
        ((900, 100), (800, 100)),
        steps=4,
        map_fn=IDENTITY,
        tracking_ids=(100, 101),
    )


def test_pinch_opens_both_slots_with_distinct_tracking_ids():
    ev = _events()
    # the contact block: slot 0 then slot 1, each with its own tracking id
    slot_then_id = [
        (e[2], n[2])
        for e, n in zip(ev, ev[1:])
        if e[:2] == (pinch.EV_ABS, ABS_MT_SLOT) and n[:2] == (pinch.EV_ABS, ABS_MT_TRACKING_ID)
    ]
    # first two such pairings are the opens (slot0->100, slot1->101)
    assert slot_then_id[0] == (0, 100)
    assert slot_then_id[1] == (1, 101)


def test_pinch_touch_button_latches_once_each_way():
    ev = _events()
    touch_vals = [e[2] for e in ev if e[0] == EV_KEY and e[1] == BTN_TOUCH]
    assert touch_vals == [1, 0]  # down at contact, up at release, nothing between


def test_pinch_releases_both_slots_with_release_id():
    ev = _events()
    releases = [e for e in ev if e[:2] == (pinch.EV_ABS, ABS_MT_TRACKING_ID) and e[2] == RELEASE_ID]
    assert len(releases) == 2  # one per slot
    # release happens after the last SYN of travel and before BTN_TOUCH up
    last_touch_up = max(i for i, e in enumerate(ev) if e[0] == EV_KEY and e[1] == BTN_TOUCH and e[2] == 0)
    assert all(ev.index(r) < last_touch_up for r in releases)


def test_pinch_syn_frame_count():
    ev = _events()
    syns = [e for e in ev if e[0] == EV_SYN and e[1] == SYN_REPORT]
    # 1 contact frame + steps travel frames + 1 release frame
    assert len(syns) == 1 + 4 + 1


def test_pinch_trajectory_reaches_endpoints():
    ev = _events()
    # collect the x position emitted per slot across the whole series
    slot = None
    a_xs, b_xs = [], []
    for e in ev:
        if e[:2] == (pinch.EV_ABS, ABS_MT_SLOT):
            slot = e[2]
        elif e[:2] == (pinch.EV_ABS, ABS_MT_POSITION_X):
            (a_xs if slot == 0 else b_xs).append(e[2])
    assert a_xs[0] == 100 and a_xs[-1] == 200  # finger A start->end
    assert b_xs[0] == 900 and b_xs[-1] == 800  # finger B start->end (closing in)


def test_pinch_omits_unchanged_axis_during_travel():
    # horizontal pinch: Y never changes during travel, so no POS_Y after contact
    ev = _events()
    contact_syn = next(i for i, e in enumerate(ev) if e[0] == EV_SYN)
    travel = ev[contact_syn + 1 :]
    assert not any(e[:2] == (pinch.EV_ABS, ABS_MT_POSITION_Y) for e in travel)


def test_pinch_rejects_bad_args():
    import pytest

    with pytest.raises(ValueError):
        pinch_events(((0, 0), (0, 0)), ((1, 1), (1, 1)), steps=0, map_fn=IDENTITY)
    with pytest.raises(ValueError):
        pinch_events(((0, 0), (0, 0)), ((1, 1), (1, 1)), tracking_ids=(5, 5), map_fn=IDENTITY)


# --- single-command renderer ---

def test_render_is_one_command_with_paced_syn():
    ev = pinch_events(((0, 0), (10, 0)), ((20, 0), (10, 0)), steps=2, map_fn=IDENTITY)
    cmd = render_sendevent(ev, device="/dev/input/event7", frame_pause_s=0.005)
    calls = cmd.split("; ")
    # every event becomes exactly one sendevent line
    sendevents = [c for c in calls if c.startswith("sendevent ")]
    assert len(sendevents) == len(ev)
    # a sleep is inserted after each SYN frame
    syns = sum(1 for e in ev if e[0] == EV_SYN and e[1] == SYN_REPORT)
    assert sum(1 for c in calls if c.startswith("sleep ")) == syns
    assert all(c.startswith("sendevent /dev/input/event7 ") for c in sendevents)


def test_render_no_sleep_when_pause_zero():
    ev = pinch_events(((0, 0), (10, 0)), ((20, 0), (10, 0)), steps=2, map_fn=IDENTITY)
    cmd = render_sendevent(ev, frame_pause_s=0.0)
    assert "sleep" not in cmd


# --- executors (dependency-injected seams) ---

def test_sendevent_pincher_runs_single_shell_call():
    calls = []
    p = SendeventPincher(run_shell=calls.append, steps=3, map_fn=IDENTITY)
    p.pinch(((0, 0), (10, 0)), ((20, 0), (10, 0)))
    assert len(calls) == 1  # one adb round-trip
    assert calls[0].count("sendevent ") == len(
        pinch_events(((0, 0), (10, 0)), ((20, 0), (10, 0)), steps=3, map_fn=IDENTITY)
    )


def test_gesture_pincher_maps_finger_pairs_to_gesture_call():
    seen = []
    p = GesturePincher(gesture=lambda *a: seen.append(a), steps=40)
    p.pinch(((760, 540), (1120, 540)), ((1580, 540), (1220, 540)))
    # gesture(start1, start2, end1, end2, steps)
    assert seen == [((760, 540), (1580, 540), (1120, 540), (1220, 540), 40)]


def test_zoom_out_fingers_pinch_in_geometry():
    a, b = zoom_out_fingers((1170, 500), start_span=1000, end_span=120)
    # start far apart, end close together (a pinch-in => zoom out)
    assert abs(b[0][0] - a[0][0]) == 1000
    assert abs(b[1][0] - a[1][0]) == 120
    assert a[0][1] == 500 and b[0][1] == 500  # horizontal by default


# --- zoom_out_max convergence ---

def test_zoom_out_max_stops_after_two_non_shrinking_pinches():
    seq = [128.0, 118.0, 108.0, 100.0, 99.0, 99.0, 99.0]
    frames = iter(range(len(seq)))
    pinches = []

    steps = zoom_out_max(
        capture=lambda: next(frames),
        pinch_step=lambda: pinches.append(1),
        measure=lambda f: (seq[f], seq[f]),
        frame_change=lambda a, b: 5.0,
        sleep=lambda s: None,
        shrink_tol=1.5,
        max_pinches=10,
    )
    # 100 -> 99 (step4, <1.5) then 99 -> 99 (step5) are the two plateau steps
    assert steps[-1].index == 5
    assert len(pinches) == 5
    assert steps[-1].source == "grid"


def test_zoom_out_max_failsoft_uses_frame_change_when_no_lattice():
    changes = iter([50.0, 10.0, 8.0, 1.0, 1.0, 1.0])
    frames = iter(range(10))
    steps = zoom_out_max(
        capture=lambda: next(frames),
        pinch_step=lambda: None,
        measure=lambda f: (None, None),
        frame_change=lambda a, b: next(changes),
        sleep=lambda s: None,
        change_tol=2.5,
        max_pinches=10,
    )
    assert steps[-1].source == "frame"
    # two frames that barely change (1.0 < 2.5) end it
    assert steps[-1].change == 1.0


def test_zoom_out_max_reports_every_step_via_hook():
    seq = [120.0, 100.0, 100.0, 100.0]
    frames = iter(range(len(seq)))
    seen: list[PitchStep] = []
    zoom_out_max(
        capture=lambda: next(frames),
        pinch_step=lambda: None,
        measure=lambda f: (seq[f], None),
        frame_change=lambda a, b: 0.0,
        sleep=lambda s: None,
        on_step=seen.append,
        max_pinches=10,
    )
    # 120->100 shrinks, then 100->100 twice: two non-shrinking pinches = done
    assert [s.index for s in seen] == [0, 1, 2, 3]
    assert seen[0].col_pitch == 120.0


def test_zoom_out_max_source_reports_wide_band_reader():
    """A 3-tuple measure (the default's shape) carries its reader tag into
    PitchStep.source, so a step read through the full-frame fallback logs
    "map_lattice" while a narrow-band step logs "grid" -- the 批6 ledger split."""
    seq = [
        (128.0, 120.0, "grid"),
        (100.0, 95.0, "map_lattice"),  # narrow band buried; wide band read it
        (99.0, 95.0, "map_lattice"),
        (99.0, 95.0, "map_lattice"),
    ]
    frames = iter(range(len(seq)))
    steps = zoom_out_max(
        capture=lambda: next(frames),
        pinch_step=lambda: None,
        measure=lambda f: seq[f],
        frame_change=lambda a, b: 0.0,
        sleep=lambda s: None,
        max_pinches=10,
    )
    assert [s.source for s in steps] == ["grid", "map_lattice", "map_lattice", "map_lattice"]


# --- pick_pinch_center (dynamic pinch center) ---

def _four_point_clearance(center, peaks):
    a, b = zoom_out_fingers(center)
    pts = (a[0], a[1], b[0], b[1])
    return min(((px - ux) ** 2 + (py - uy) ** 2) ** 0.5 for px, py in pts for ux, uy in peaks)


def test_pick_pinch_center_no_peaks_returns_default():
    assert pinch.pick_pinch_center([]) == pinch.PINCH_CENTER_DEFAULT


def test_pick_pinch_center_beats_fixed_on_a_cluster():
    """A cluster under the fixed center's left finger: the picker must find a
    center whose four points clear it better than (1170,500) does."""
    peaks = [(660, 500), (700, 480), (680, 520), (1170, 500), (1230, 500)]
    chosen = pinch.pick_pinch_center(peaks)
    assert chosen != pinch.PINCH_CENTER_DEFAULT
    assert _four_point_clearance(chosen, peaks) > _four_point_clearance(
        pinch.PINCH_CENTER_DEFAULT, peaks
    )


def test_pick_pinch_center_keeps_all_points_in_region():
    """Every chosen center's four finger points stay inside the safe map
    rectangle even when units blanket the interior."""
    peaks = [(x, y) for x in range(500, 1900, 110) for y in range(340, 640, 90)]
    a, b = zoom_out_fingers(pinch.pick_pinch_center(peaks))
    rx, ry, rw, rh = pinch.PINCH_SAFE_REGION
    for px, py in (a[0], a[1], b[0], b[1]):
        assert rx <= px <= rx + rw and ry <= py <= ry + rh
