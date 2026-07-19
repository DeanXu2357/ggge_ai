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


def _grid_state(frame: np.ndarray) -> str | None:
    """"on"/"off" from the toggle's right-slot pixel, None when the pixel
    matches neither state (settings page not on screen / wrong tab)."""
    px = _pixel(frame, GRID_PROBE)
    if px is None:
        return None
    b, g, r = px
    if g > 160 and b > 160 and r < 150:
        return "on"
    if r < 120 and g < 120 and b < 120:
        return "off"
    return None


def _auto_battle_is_off(frame: np.ndarray) -> bool:
    """The AUTO戰鬥 OFF hexagon stays teal-filled while OFF is selected."""
    px = _pixel(frame, AUTO_BATTLE_OFF_PROBE)
    if px is None:
        return False
    b, g, r = px
    return g > 180 and b > 180


def _battle_tab_selected(frame: np.ndarray) -> bool:
    """Salmon underline under the 戰鬥 tab text marks it selected."""
    px = _pixel(frame, BATTLE_TAB_UNDERLINE)
    if px is None:
        return False
    b, g, r = px
    return r > 190 and r > b + 30


def set_battle_grid(capture, tap, desired_on: bool, *, sleep=time.sleep) -> bool:
    """Drive 顯示方格 to `desired_on` through the battle menu and leave the
    menus closed. True when the toggle was verified in the desired state;
    False on any unverified step (the flow still escapes through the close
    buttons so the battle screen comes back either way)."""
    ok = False
    tap(*BATTLE_MENU_BTN)
    sleep(1.5)
    tap(*BATTLE_MENU_SETTINGS)
    sleep(1.8)
    tap(*SETTINGS_BATTLE_TAB)
    sleep(1.2)
    frame = capture()
    if _battle_tab_selected(frame) and _auto_battle_is_off(frame):
        state = _grid_state(frame)
        if state == ("on" if desired_on else "off"):
            ok = True
        elif state is not None:
            tap(*GRID_TOGGLE)
            sleep(1.0)
            frame = capture()
            ok = (
                _grid_state(frame) == ("on" if desired_on else "off")
                and _auto_battle_is_off(frame)
            )
    if not ok:
        log.warning(
            "battle-grid toggle unverified (desired %s); scanning without it",
            "on" if desired_on else "off",
        )
    tap(*SETTINGS_CLOSE)
    sleep(1.2)
    tap(*BATTLE_MENU_CLOSE)
    sleep(1.2)
    return ok
