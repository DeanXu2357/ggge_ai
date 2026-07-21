"""In-battle settings driver: the 顯示方格 (battle grid) toggle.

Calibrated live 2026-07-19 on the event stage (scratchpad captures
menu_2_open / settings_0 / settings_battle_tab; docs/battle-settings-ui.md):
☰ (2170,52) opens the 戰鬥選單, 設定 (1604,865) the settings panel, the
戰鬥 tab (1613,173) hosts 顯示方格 as row 3 with a single flip toggle at
(1898,591). Toggle state reads off the slider-knob pixel at (1963,591):
teal (G,B high) = ON, dark body = OFF.

Safety: the same tab hosts the AUTO戰鬥 tri-state at y≈295 -- switching it
hands units to the built-in AI, the project's hardest red line -- so every
step verifies its OFF hexagon stays filled and the flow escapes through the
close buttons on any mismatch. The driver is fail-soft: callers scan
without the grid rather than abort when a step does not verify.
"""

from __future__ import annotations

import logging
import time

import numpy as np

log = logging.getLogger(__name__)

BATTLE_MENU_BTN = (2170, 52)
BATTLE_MENU_SETTINGS = (1604, 865)
BATTLE_MENU_CLOSE = (1172, 992)
SETTINGS_BATTLE_TAB = (1613, 173)
SETTINGS_CLOSE = (1180, 992)
GRID_TOGGLE = (1898, 591)
GRID_PROBE = (1963, 591)
AUTO_BATTLE_OFF_PROBE = (1179, 295)
# the settings panel reopens on whichever tab was used last, so the battle
# tab is probed by its selected-state underline before trusting row probes
BATTLE_TAB_UNDERLINE = (1613, 201)


def _pixel(frame: np.ndarray, xy: tuple[int, int]) -> tuple[int, int, int] | None:
    x, y = xy
    if frame is None or frame.shape[0] <= y or frame.shape[1] <= x:
        return None
    b, g, r = (int(v) for v in frame[y, x])
    return b, g, r


def read_grid_setting(frame: np.ndarray) -> str | None:
    """"on"/"off" from the 顯示方格 toggle's right-slot pixel, None when the
    pixel matches neither state (settings page not on screen / wrong tab).

    Pure recognition over the passed frame -- never captures -- so every
    confirmation point is replayable offline against a fixture (design
    principle 5)."""
    px = _pixel(frame, GRID_PROBE)
    if px is None:
        return None
    b, g, r = px
    if g > 160 and b > 160 and r < 150:
        return "on"
    if r < 120 and g < 120 and b < 120:
        return "off"
    return None


def is_auto_battle_off(frame: np.ndarray) -> bool:
    """The AUTO戰鬥 OFF hexagon stays teal-filled while OFF is selected.
    Pure frame recognition; the red-line guard re-reads it every step."""
    px = _pixel(frame, AUTO_BATTLE_OFF_PROBE)
    if px is None:
        return False
    b, g, r = px
    return g > 180 and b > 180


def is_battle_tab_selected(frame: np.ndarray) -> bool:
    """Salmon underline under the 戰鬥 tab text marks it selected.
    Pure frame recognition; the panel reopens on the last-used tab."""
    px = _pixel(frame, BATTLE_TAB_UNDERLINE)
    if px is None:
        return False
    b, g, r = px
    return r > 190 and r > b + 30


def set_battle_grid(capture, tap, desired_on: bool, *, sleep=time.sleep) -> bool:
    """Drive 顯示方格 to `desired_on` through the battle menu and leave the
    menus closed. True when the toggle was verified in the desired state;
    False on any unverified step (the flow still escapes through the close
    buttons so the battle screen comes back either way).

    The flow alternates operation steps (menu taps) with pure recognition
    confirmations (the module's read_* probes over the captured frame):
      1. operate: open the battle menu -> settings -> 戰鬥 tab.
      2. confirm: on the 戰鬥 tab AND AUTO戰鬥 still OFF (the red line);
         bail to close otherwise -- never flip a toggle off this page.
      3. confirm: read the current 顯示方格 state.
      4. operate: flip it only when it differs from `desired_on`.
      5. confirm: re-read the state AND re-assert AUTO戰鬥 OFF.
      6. operate: close settings and the menu (always, fail-soft)."""
    want = "on" if desired_on else "off"

    def close() -> None:
        tap(*SETTINGS_CLOSE)
        sleep(1.2)
        tap(*BATTLE_MENU_CLOSE)
        sleep(1.2)

    tap(*BATTLE_MENU_BTN)
    sleep(1.5)
    tap(*BATTLE_MENU_SETTINGS)
    sleep(1.8)
    tap(*SETTINGS_BATTLE_TAB)
    sleep(1.2)
    frame = capture()

    ok = False
    on_battle_tab = is_battle_tab_selected(frame) and is_auto_battle_off(frame)
    if on_battle_tab:
        state = read_grid_setting(frame)
        if state == want:
            ok = True
        elif state is not None:
            tap(*GRID_TOGGLE)
            sleep(1.0)
            frame = capture()
            ok = read_grid_setting(frame) == want and is_auto_battle_off(frame)

    if not ok:
        log.warning(
            "battle-grid toggle unverified (desired %s); scanning without it", want
        )
    close()
    return ok


def ensure_battle_grid(capture, tap, keyguard, desired_on: bool, *, clear=None, attempts: int = 3) -> bool:
    """Drive 顯示方格 to ``desired_on`` and confirm against the map's ground
    truth: a lattice readable by vision.read_grid_lattice means the grid is
    really on AND we are back on the map (not a stray menu the toggle left
    open). Retries because the menu taps land intermittently. ``clear`` (an
    optional no-arg callable) returns an obstruction-free frame before the
    lattice is read; without it the raw capture is used. Shared by the
    zoom/grid probe scripts (design principle 5)."""
    from . import vision

    for _ in range(attempts):
        keyguard.ensure_unlocked()
        set_battle_grid(capture, tap, desired_on)
        frame = clear() if clear is not None else capture()
        if (vision.read_grid_lattice(frame) is not None) == desired_on:
            return True
    return False
