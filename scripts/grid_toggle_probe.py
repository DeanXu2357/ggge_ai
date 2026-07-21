"""Manual tool: independently verify the 顯示方格 (battle grid) toggle flow on
the live device, decoupled from the full battle loop (design principle 5).

Ground truth is the map itself: a lattice readable by vision.read_grid_lattice
means the grid is really ON and we are back on the map (not a stray menu the
toggle left open). The probe records the initial toggle state, drives it ON
(lattice must appear), drives it OFF (lattice must vanish), then restores the
initial state -- logging every step. The battle is otherwise untouched.

Red line: set_battle_grid refuses to flip anything unless AUTO戰鬥 reads OFF,
and always escapes through the close buttons; this probe never taps the
AUTO戰鬥 tri-state region itself.

usage: uv run python scripts/grid_toggle_probe.py
"""

from __future__ import annotations

import logging
import os
import time

from ggge_ai.actuation.keyguard import Keyguard
from ggge_ai.app import connect
from ggge_ai.battle import map_view, settings, vision
from ggge_ai.battle.scout_intel import UNIT_DETAIL_CLOSE
from ggge_ai.battle.settings import set_battle_grid

logging.basicConfig(
    level=logging.DEBUG if os.environ.get("GGGE_DEBUG") else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("grid_toggle_probe")


def _clear_obstruction(capture, tap, keyguard):
    """Keep the map clear before reading ground truth: re-unlock and dismiss a
    stray unit-detail modal the way zoom_probe does."""
    keyguard.ensure_unlocked()
    frame = capture()
    if vision.is_unit_detail_modal(frame):
        log.warning("stray unit-detail modal; closing")
        tap(*UNIT_DETAIL_CLOSE)
        time.sleep(1.2)
        frame = capture()
    return frame


def _ensure_grid(capture, tap, keyguard, desired_on: bool, attempts: int = 3) -> bool:
    """Drive 顯示方格 and confirm against ground truth: a lattice on the live map
    iff the grid is meant to be on. Retries because the menu taps land
    intermittently (mirrors zoom_probe._ensure_grid)."""
    for _ in range(attempts):
        keyguard.ensure_unlocked()
        set_battle_grid(capture, tap, desired_on)
        frame = _clear_obstruction(capture, tap, keyguard)
        has_lattice = vision.read_grid_lattice(frame) is not None
        if has_lattice == desired_on:
            return True
    return False


def _log_settings_page_state(perception, tap, keyguard) -> None:
    """Open the settings 戰鬥 tab and log the project-wide page-level state
    (classify_frame should read "settings" here), then close back out. Pure
    logging: set_battle_grid's own toggle-pixel confirmations stay the in-page
    authority; classify_frame is only the cross-flow page vocabulary, so this
    step never gates the toggle flow. Fail-soft -- always escapes the menus."""
    keyguard.ensure_unlocked()
    tap(*settings.BATTLE_MENU_BTN)
    time.sleep(1.5)
    tap(*settings.BATTLE_MENU_SETTINGS)
    time.sleep(1.8)
    tap(*settings.SETTINGS_BATTLE_TAB)
    time.sleep(1.2)
    log.info("settings page classify_frame -> %s", map_view.classify_view(perception))
    tap(*settings.SETTINGS_CLOSE)
    time.sleep(1.2)
    tap(*settings.BATTLE_MENU_CLOSE)
    time.sleep(1.2)


def main() -> None:
    perception, actuator = connect()
    capture = perception.capture
    tap = actuator.tap
    keyguard = Keyguard(actuator.device, capture=capture)
    keyguard.ensure_unlocked()

    # the lattice reader assumes the top-level hub view; back out of any
    # selected unit / expanded card strip first so ground truth is trustworthy.
    at_top = map_view.ensure_max_view(perception, actuator, keyguard=keyguard)
    log.info("view = %s", "top hub (max view)" if at_top else "NOT hub (fail-soft)")

    frame = _clear_obstruction(capture, tap, keyguard)
    initial_on = vision.read_grid_lattice(frame) is not None
    log.info("initial grid (map ground truth) = %s", "ON" if initial_on else "OFF")

    _log_settings_page_state(perception, tap, keyguard)

    on_ok = _ensure_grid(capture, tap, keyguard, True)
    log.info("step ON  -> lattice %s", "appeared (OK)" if on_ok else "NOT confirmed")

    off_ok = _ensure_grid(capture, tap, keyguard, False)
    log.info("step OFF -> lattice %s", "vanished (OK)" if off_ok else "NOT confirmed")

    restored = _ensure_grid(capture, tap, keyguard, initial_on)
    log.info(
        "restore -> initial %s %s",
        "ON" if initial_on else "OFF",
        "(OK)" if restored else "NOT confirmed",
    )

    print("\n=== grid_toggle_probe summary ===")
    print(f"initial state : {'ON' if initial_on else 'OFF'}")
    print(f"toggle ON      : {'lattice appeared' if on_ok else 'UNVERIFIED'}")
    print(f"toggle OFF     : {'lattice vanished' if off_ok else 'UNVERIFIED'}")
    print(f"restored       : {'yes' if restored else 'UNVERIFIED'}")
    if on_ok and off_ok and restored:
        print("result: PASS (toggle recognition tracks the map lattice, state restored)")
    else:
        print("result: CHECK LOG (a step did not verify against ground truth)")


if __name__ == "__main__":
    main()
