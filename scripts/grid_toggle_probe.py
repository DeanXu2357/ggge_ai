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
from ggge_ai.battle import map_view, vision
from ggge_ai.battle.map_view import UNIT_DETAIL_CLOSE
from ggge_ai.battle.settings import ensure_battle_grid

logging.basicConfig(
    level=logging.DEBUG if os.environ.get("GGGE_DEBUG") else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("grid_toggle_probe")


def _clear_obstruction(capture, tap, keyguard):
    """Keep the map clear before reading ground truth: re-unlock and dismiss a
    stray unit-detail modal."""
    keyguard.ensure_unlocked()
    frame = capture()
    if vision.is_unit_detail_modal(frame):
        log.warning("stray unit-detail modal; closing")
        tap(*UNIT_DETAIL_CLOSE)
        time.sleep(1.2)
        frame = capture()
    return frame


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

    def clear():
        return _clear_obstruction(capture, tap, keyguard)

    initial_on = vision.read_grid_lattice(clear()) is not None
    log.info("initial grid (map ground truth) = %s", "ON" if initial_on else "OFF")

    on_ok = off_ok = restored = False
    try:
        on_ok = ensure_battle_grid(capture, tap, keyguard, True, clear=clear)
        log.info("step ON  -> lattice %s", "appeared (OK)" if on_ok else "NOT confirmed")

        off_ok = ensure_battle_grid(capture, tap, keyguard, False, clear=clear)
        log.info("step OFF -> lattice %s", "vanished (OK)" if off_ok else "NOT confirmed")
    finally:
        restored = ensure_battle_grid(capture, tap, keyguard, initial_on, clear=clear)
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
