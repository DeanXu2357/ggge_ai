"""Manual tool: zoom the battle map out to its furthest and print the grid
pitch measured at every pinch.

Turns the in-battle 顯示方格 on, runs zoom_out_max through the injection-API
gesture backend (sendevent to /dev/input is SELinux-blocked on the live
device -- see actuation/pinch.py), then turns the grid back off. Zoom is left
at maximum; the battle is otherwise untouched.

usage: uv run python scripts/zoom_probe.py
"""

from __future__ import annotations

import logging
import os
import time

from ggge_ai.actuation.keyguard import Keyguard
from ggge_ai.actuation.pinch import GesturePincher, PitchStep, zoom_out_fingers, zoom_out_max
from ggge_ai.app import connect
from ggge_ai.battle import map_view, vision
from ggge_ai.battle.scout_intel import UNIT_DETAIL_CLOSE
from ggge_ai.battle.settings import set_battle_grid

logging.basicConfig(
    level=logging.DEBUG if os.environ.get("GGGE_DEBUG") else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("zoom_probe")

SURFACE = "com.bandainamcoent.gget_WW:id/unitySurfaceView"


def _ensure_grid(capture, tap, keyguard, desired_on: bool, attempts: int = 3) -> bool:
    """Drive 顯示方格 and confirm against ground truth: a lattice readable on the
    live map means the grid is on AND we are back on the map (not a stray menu
    the toggle left open). Retries because the menu taps land intermittently."""
    for _ in range(attempts):
        keyguard.ensure_unlocked()
        set_battle_grid(capture, tap, desired_on)
        has_lattice = vision.read_grid_lattice(capture()) is not None
        if has_lattice == desired_on:
            return True
    return False


def main() -> None:
    perception, actuator = connect()
    device = actuator.device
    capture = perception.capture
    keyguard = Keyguard(device, capture=capture)
    keyguard.ensure_unlocked()

    # user's call: only zoom from the top-level hub with the unit list
    # collapsed -- a selected unit's overlay both shrinks the view and risks
    # committing an action. back out first for the widest, safe map.
    at_top = map_view.ensure_max_view(perception, actuator, keyguard=keyguard)
    log.info("view = %s", "top hub (max view)" if at_top else "NOT hub (fail-soft)")

    grid_on = _ensure_grid(capture, actuator.tap, keyguard, True)
    log.info(
        "battle grid %s",
        "ON (lattice confirmed on map)" if grid_on else "unverified (fail-soft: frame-diff)",
    )

    fa, fb = zoom_out_fingers()
    pincher = GesturePincher(
        gesture=lambda s1, s2, e1, e2, steps: device(resourceId=SURFACE).gesture(
            s1, s2, e1, e2, steps
        ),
        steps=40,
    )

    def obstruction(frame):
        keyguard.ensure_unlocked()
        if vision.is_unit_detail_modal(frame):
            log.warning("stray unit-detail modal; closing")
            actuator.tap(*UNIT_DETAIL_CLOSE)
            time.sleep(1.2)
            return capture()
        return frame

    def report(step: PitchStep) -> None:
        col = f"{step.col_pitch:.1f}" if step.col_pitch is not None else "  -  "
        row = f"{step.row_pitch:.1f}" if step.row_pitch is not None else "  -  "
        chg = f"{step.change:.2f}" if step.change is not None else "  -  "
        log.info(
            "pinch %2d | col=%s row=%s | frame_diff=%s | via %s",
            step.index, col, row, chg, step.source,
        )

    steps = zoom_out_max(
        capture=capture,
        pinch_step=lambda: pincher.pinch(fa, fb),
        obstruction=obstruction,
        on_step=report,
    )

    cols = [s.col_pitch for s in steps if s.col_pitch is not None]
    print("\n=== zoom_out_max summary ===")
    print("col pitch series:", [round(c, 1) for c in cols])
    if len(cols) >= 2:
        print(f"start {cols[0]:.1f}px -> final {cols[-1]:.1f}px over {len(steps) - 1} pinch(es)")
    print("(grid restored OFF; zoom left at maximum)")

    restored = _ensure_grid(capture, actuator.tap, keyguard, False)
    log.info("battle grid restored %s", "OFF" if restored else "unverified")


if __name__ == "__main__":
    main()
