"""SCREEN_CENTRE calibration from `verdict reason=recentred` frames.

The selected unit carries a bright-blue halo ring; its centre is located by
annulus correlation (robust to the sprite occluding part of the stroke).
The enclosing grid cell is then read from raw ridge positions.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, "/home/poyu/workspace/project/ggge_ai/src")
from ggge_ai.runtime import board  # noqa: E402

ROOT = Path("/tmp/claude-1000/-home-poyu-workspace-project-ggge-ai/4e7a46d6-0ea7-445f-be34-5bf07944dd7a/scratchpad/persp")
RUNS = {
    "run_031256": Path("/home/poyu/workspace/project/ggge_ai/data/runs/20260809-031256"),
    "run_011740": ROOT / "20260809-011740",
}

SEARCH = (400, 300, 1800, 620)  # x, y, w, h


def blue_mask(frame: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    return ((h >= 100) & (h <= 122) & (s > 90) & (v > 180)).astype(np.float32)


def annulus(radius: int, thick: int = 5) -> np.ndarray:
    size = 2 * radius + thick + 4
    c = size // 2
    yy, xx = np.mgrid[0:size, 0:size]
    d = np.hypot(yy - c, xx - c)
    ker = ((d >= radius - thick) & (d <= radius + thick)).astype(np.float32)
    return ker / ker.sum()


def find_ring(frame: np.ndarray) -> tuple[float, float, int, float] | None:
    mask = blue_mask(frame)
    x, y, w, h = SEARCH
    best = None
    for r in range(46, 74, 2):
        resp = cv2.filter2D(mask, -1, annulus(r))
        sub = resp[y : y + h, x : x + w]
        idx = int(np.argmax(sub))
        py, px = divmod(idx, w)
        score = float(sub[py, px])
        if best is None or score > best[3]:
            best = (float(x + px), float(y + py), r, score)
    return best


def raw_lines(frame: np.ndarray) -> tuple[list[int], list[int]]:
    x0, x1, y0, y1 = 500, 2280, 250, 960
    hp = board._highpass(frame[y0:y1, x0:x1])
    return board._ridges(hp.mean(axis=0), x0, 55), board._ridges(hp.mean(axis=1), y0, 45)


def bracket(value: float, lines: list[int]) -> tuple[float, float] | None:
    for a, b in zip(lines, lines[1:], strict=False):
        if a <= value <= b:
            return (float(a), float(b))
    return None


def main() -> None:
    rows = []
    for run, base in RUNS.items():
        for line in (base / "sweep.jsonl").open():
            d = json.loads(line)
            if d.get("kind") != "verdict" or d.get("reason") != "recentred":
                continue
            p = base / d["frame"]
            frame = cv2.imread(str(p))
            if frame is None:
                continue
            ring = find_ring(frame)
            cols, rws = raw_lines(frame)
            rec = {
                "run": run,
                "seq": d["seq"],
                "cell": d["cell"],
                "frame": str(p),
                "ring": None if ring is None else [ring[0], ring[1], ring[2], round(ring[3], 4)],
                "cols": cols,
                "rows": rws,
            }
            if ring is not None:
                bx = bracket(ring[0], cols)
                by_lo = bracket(ring[1], rws)
                rec["col_span"] = bx
                rec["row_span_at_ring"] = by_lo
            rows.append(rec)
            print(run, d["seq"], rec["ring"], rec.get("col_span"), rec.get("row_span_at_ring"), flush=True)
    (ROOT / "centre_raw.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
