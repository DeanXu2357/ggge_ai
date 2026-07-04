"""Capture a screenshot from the connected device into assets/screenshots/.

usage: uv run python scripts/capture.py [name]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np
import uiautomator2 as u2

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOT_DIR = PROJECT_ROOT / "assets" / "screenshots"


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%Y%m%d-%H%M%S")
    device = u2.connect()
    img = cv2.cvtColor(np.array(device.screenshot()), cv2.COLOR_RGB2BGR)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}.png"
    cv2.imwrite(str(path), img)
    h, w = img.shape[:2]
    print(f"saved {path} ({w}x{h})")


if __name__ == "__main__":
    main()
