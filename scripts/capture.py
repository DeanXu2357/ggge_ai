"""Capture a screenshot from the connected device into assets/screenshots/.

usage: uv run python scripts/capture.py [name] [--serial SERIAL]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from ggge_ai.runtime.device import Adb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOT_DIR = PROJECT_ROOT / "assets" / "screenshots"


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    serial = None
    if "--serial" in sys.argv:
        serial = sys.argv[sys.argv.index("--serial") + 1]
    name = args[0] if args else time.strftime("%Y%m%d-%H%M%S")
    png = Adb(serial=serial).screencap()
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}.png"
    path.write_bytes(png)
    print(f"saved {path} ({len(png)} bytes)")


if __name__ == "__main__":
    main()
