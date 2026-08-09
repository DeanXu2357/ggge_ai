"""逐 run 透視參數 + 實際作業 x 範圍下的縱線偏差。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path("/tmp/claude-1000/-home-poyu-workspace-project-ggge-ai/4e7a46d6-0ea7-445f-be34-5bf07944dd7a/scratchpad/persp")
YREF = 650.0


def longest_run(pos, lo, hi, jump):
    best, cur = [], []
    for a, b in zip(pos, pos[1:], strict=False):
        gap = b - a
        if not (lo <= gap <= hi):
            cur = []
            continue
        if cur and abs(gap - (cur[-1] - cur[-2])) > jump:
            cur = [a, b]
        elif cur:
            cur.append(b)
        else:
            cur = [a, b]
        if len(cur) > len(best):
            best = list(cur)
    return best


def main() -> None:
    recs = [json.loads(l) for l in (ROOT / "measurements.jsonl").open()]
    per = {}
    for r in recs:
        d = per.setdefault(r["run"], {"row": [], "col": [], "slope": []})
        rows = longest_run(r["rows"], 65, 115, 12)
        for a, b in zip(rows, rows[1:], strict=False):
            d["row"].append(((a + b) / 2.0, b - a))
        prev = None
        for band in r["bands"]:
            lo, hi = band["y"]
            yc = (lo + hi) / 2.0
            cols = longest_run(band["cols"], 70, 120, 12)
            if len(cols) < 5:
                prev = None
                continue
            d["col"].append((yc, float(np.median(np.diff(cols)))))
            if prev:
                py, pc = prev
                for x in pc:
                    near = min(cols, key=lambda c: abs(c - x))
                    if abs(near - x) < 25:
                        d["slope"].append(((x + near) / 2.0, (near - x) / (yc - py)))
            prev = (yc, cols)

    summary = {}
    for run, d in sorted(per.items()):
        row = np.array(d["row"])
        col = np.array(d["col"])
        sl = np.array(d["slope"])
        A = np.stack([row[:, 0] - YREF, np.ones(len(row))], 1)
        rc, *_ = np.linalg.lstsq(A, row[:, 1], rcond=None)
        A = np.stack([col[:, 0] - YREF, np.ones(len(col))], 1)
        cc, *_ = np.linalg.lstsq(A, col[:, 1], rcond=None)
        A = np.stack([sl[:, 0], np.ones(len(sl))], 1)
        sc, *_ = np.linalg.lstsq(A, sl[:, 1], rcond=None)
        vp = -sc[1] / sc[0]
        summary[run] = {
            "n_row": len(row), "n_col": len(col), "n_slope": len(sl),
            "row_pitch_650": rc[1], "row_slope": rc[0], "row_rel": rc[0] / rc[1],
            "col_pitch_650": cc[1], "col_slope": cc[0], "col_rel": cc[0] / cc[1],
            "K_from_slope": sc[0], "VP_X": vp,
        }
        print(f"{run}: row650={rc[1]:.2f} slope={rc[0]:.5f} rel={rc[0] / rc[1]:.3e} | "
              f"col650={cc[1]:.2f} slope={cc[0]:.5f} rel={cc[0] / cc[1]:.3e} | "
              f"K_slope={sc[0]:.3e} VP_X={vp:.0f} | rel_row/rel_col={rc[0] / rc[1] / (cc[0] / cc[1]):.2f}")

    print("\n縱線 uniform 模型偏差（單位＝格），逐作業 x 範圍：")
    for x0, x1 in [(150, 1750), (500, 1750), (500, 2280), (150, 2280)]:
        xs = np.arange(x0, x1 + 1, 5.0)
        for y0, y1 in [(250, 780), (250, 960)]:
            ys = np.arange(y0, y1 + 1, 5.0)
            X, Y = np.meshgrid(xs, ys)
            s = 1.0 + 1.110e-4 * (Y - YREF)
            Xr = 1164.1 + (X - 1164.1) / s
            d = (X - Xr) / 92.639
            d -= d.mean()
            print(f"  x{x0}-{x1} y{y0}-{y1}: p2p={d.max() - d.min():.3f} maxabs={np.abs(d).max():.3f}")

    (ROOT / "per_run.json").write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
