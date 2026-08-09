"""Offline lattice measurement over sweep window frames.

Reuses ggge_ai.runtime.board primitives (_highpass / _ridges / find_lattice);
the uniformity gates (_trim/_plausible) are deliberately bypassed for the raw
pass so perspective distortion is not filtered out of the sample.
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

# 量測窗：避開左側按鈕欄（x<500）、頂部 AUTO 列（y<250）與底部訊息條（y>960）。
MEAS_X0, MEAS_X1 = 500, 2280
MEAS_Y0, MEAS_Y1 = 250, 960

# 縱線量測帶（螢幕 y），刻意重疊以便同一條線跨帶追蹤。
COL_BANDS = [(260, 400), (380, 520), (500, 640), (620, 760), (740, 880), (820, 955)]


def ridges(profile: np.ndarray, offset: int, spacing: int) -> list[int]:
    return board._ridges(profile, offset, spacing)


def measure_frame(path: Path) -> dict | None:
    frame = cv2.imread(str(path))
    if frame is None:
        return None
    patch = frame[MEAS_Y0:MEAS_Y1, MEAS_X0:MEAS_X1]
    hp = board._highpass(patch)

    rows = ridges(hp.mean(axis=1), MEAS_Y0, 45)
    cols_full = ridges(hp.mean(axis=0), MEAS_X0, 55)

    bands: list[dict] = []
    for lo, hi in COL_BANDS:
        sl = hp[lo - MEAS_Y0 : hi - MEAS_Y0, :]
        if sl.shape[0] < 20:
            continue
        bands.append(
            {
                "y": [lo, hi],
                "cols": ridges(sl.mean(axis=0), MEAS_X0, 55),
            }
        )

    lat = board.find_lattice(frame)
    return {
        "frame": str(path),
        "rows": rows,
        "cols_full": cols_full,
        "bands": bands,
        "lattice": None
        if lat is None
        else {"cols": list(lat.cols), "rows": list(lat.rows),
              "col_pitch": lat.col_pitch, "row_pitch": lat.row_pitch},
    }


def main() -> None:
    out = (ROOT / "measurements.jsonl").open("w")
    total = 0
    for run, base in RUNS.items():
        journal = base / "sweep.jsonl"
        frames: list[tuple[int, str, list[float]]] = []
        for line in journal.open():
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("kind") == "window" and d.get("frame"):
                frames.append((d["seq"], d["frame"], d.get("offset")))
        seen = set()
        for seq, rel, offset in frames:
            if rel in seen:
                continue
            seen.add(rel)
            p = base / rel
            if not p.exists():
                continue
            m = measure_frame(p)
            if m is None:
                continue
            m["run"] = run
            m["seq"] = seq
            m["offset"] = offset
            out.write(json.dumps(m) + "\n")
            total += 1
            if total % 50 == 0:
                print(total, flush=True)
    out.close()
    print("done", total)


if __name__ == "__main__":
    main()
