"""Distortion summary + three-model residuals over the measured window frames."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path("/tmp/claude-1000/-home-poyu-workspace-project-ggge-ai/4e7a46d6-0ea7-445f-be34-5bf07944dd7a/scratchpad/persp")
YREF = 650.0
BANDS = [("top 250-450", 250, 450), ("mid 450-700", 450, 700), ("bot 700-870", 700, 870)]


def longest_run(pos: list[int], lo: float, hi: float, jump: float) -> list[int]:
    """最長的一段「相鄰間距落在 [lo,hi] 且逐差變化不超過 jump」的線位。"""
    best: list[int] = []
    cur: list[int] = []
    for a, b in zip(pos, pos[1:], strict=False):
        gap = b - a
        if not (lo <= gap <= hi):
            cur = []
            continue
        if cur:
            if abs(gap - (cur[-1] - cur[-2])) > jump:
                cur = [a, b]
            else:
                cur.append(b)
        else:
            cur = [a, b]
        if len(cur) > len(best):
            best = list(cur)
    return best


def load() -> list[dict]:
    out = []
    for line in (ROOT / "measurements.jsonl").open():
        out.append(json.loads(line))
    return out


# ---------------------------------------------------------------- scatter data
def gather(records: list[dict]) -> dict:
    row_pts: list[tuple[float, float, str]] = []
    col_pts: list[tuple[float, float, str]] = []
    slopes: list[tuple[float, float, str]] = []
    frames_rows: list[tuple[str, list[int]]] = []

    for rec in records:
        run = rec["run"]
        rows = longest_run(rec["rows"], 65, 115, 12)
        if len(rows) >= 5:
            frames_rows.append((run, rows))
            for a, b in zip(rows, rows[1:], strict=False):
                row_pts.append(((a + b) / 2.0, float(b - a), run))
        for band in rec["bands"]:
            lo, hi = band["y"]
            cols = longest_run(band["cols"], 70, 120, 12)
            if len(cols) >= 5:
                pitch = float(np.median(np.diff(cols)))
                col_pts.append(((lo + hi) / 2.0, pitch, run))
        # 縱線斜率：同一條線在相鄰帶之間的位移。
        prev = None
        for band in rec["bands"]:
            lo, hi = band["y"]
            yc = (lo + hi) / 2.0
            cols = longest_run(band["cols"], 70, 120, 12)
            if len(cols) < 5:
                prev = None
                continue
            if prev is not None:
                py, pcols = prev
                for x in pcols:
                    near = min(cols, key=lambda c: abs(c - x))
                    if abs(near - x) < 25:
                        slopes.append(((x + near) / 2.0, (near - x) / (yc - py), run))
            prev = (yc, cols)
    return {"row_pts": row_pts, "col_pts": col_pts, "slopes": slopes, "frames_rows": frames_rows}


# ------------------------------------------------------------------- V(y) maps
def v_uniform(y: np.ndarray, p: float) -> np.ndarray:
    return y / p


def v_affine(y: np.ndarray, p0: float, k: float) -> np.ndarray:
    """row pitch(y) = p0 + k (y - YREF) 的世界列座標。"""
    return np.log(p0 + k * (y - YREF)) / k


def v_homography(y: np.ndarray, p0: float, k2: float) -> np.ndarray:
    """row pitch(y) = p0 (1 + k2 (y - YREF))^2 ＝ 平面單應性。"""
    return -1.0 / (p0 * k2 * (1.0 + k2 * (y - YREF)))


def residuals(frames: list[tuple[str, list[int]]], vfun, args) -> np.ndarray:
    """每幀扣掉自己的平移之後，V 與整數列序的殘差（單位＝格）。"""
    out = []
    for _run, rows in frames:
        y = np.asarray(rows, float)
        v = vfun(y, *args)
        idx = np.arange(len(y), dtype=float)
        r = v - idx
        out.append((y, r - r.mean()))
    return out


def score(frames, vfun, args) -> float:
    res = residuals(frames, vfun, args)
    allr = np.concatenate([r for _, r in res])
    return float(np.sqrt((allr**2).mean()))


def fit(frames, vfun, grid_a, grid_b) -> tuple[float, float]:
    best = None
    for a in grid_a:
        for b in grid_b:
            s = score(frames, vfun, (a, b))
            if best is None or s < best[0]:
                best = (s, a, b)
    return (best[1], best[2])


def band_stats(res, pitch_at) -> dict:
    out = {}
    for name, lo, hi in BANDS:
        vals = []
        for y, r in res:
            m = (y >= lo) & (y < hi)
            vals.extend(np.abs(r[m]).tolist())
        if not vals:
            out[name] = None
            continue
        a = np.array(vals)
        out[name] = {
            "n": int(a.size),
            "med_cell": float(np.median(a)),
            "p95_cell": float(np.percentile(a, 95)),
            "max_cell": float(a.max()),
            "med_px": float(np.median(a) * pitch_at(lo, hi)),
            "p95_px": float(np.percentile(a, 95) * pitch_at(lo, hi)),
        }
    return out


def main() -> None:
    recs = load()
    g = gather(recs)
    frames = g["frames_rows"]
    print(f"frames measured={len(recs)} usable row runs={len(frames)}")

    rp = np.array([(y, p) for y, p, _ in g["row_pts"]])
    cp = np.array([(y, p) for y, p, _ in g["col_pts"]])
    sl = np.array([(x, s) for x, s, _ in g["slopes"]])
    print("row gap samples", len(rp), "col band samples", len(cp), "slope samples", len(sl))

    # 間距 vs y 的線性趨勢
    for name, arr in (("row", rp), ("col", cp)):
        A = np.stack([arr[:, 0] - YREF, np.ones(len(arr))], 1)
        coef, *_ = np.linalg.lstsq(A, arr[:, 1], rcond=None)
        print(f"{name}: pitch(y) = {coef[1]:.3f} + {coef[0]:.5f}*(y-650)"
              f"  rel-slope={coef[0] / coef[1]:.3e}/px")

    # 縱線斜率 vs x → 消失點
    A = np.stack([sl[:, 0], np.ones(len(sl))], 1)
    coef, *_ = np.linalg.lstsq(A, sl[:, 1], rcond=None)
    vp = -coef[1] / coef[0]
    print(f"col slope dx/dy = {coef[0]:.3e}*x + {coef[1]:.4f} -> VP_X={vp:.1f}, K={coef[0]:.3e}")

    # 分帶間距表
    print("\n-- row pitch by screen-y band --")
    for lo in range(250, 950, 50):
        m = (rp[:, 0] >= lo) & (rp[:, 0] < lo + 50)
        if m.sum() >= 20:
            print(f"  y {lo:4d}-{lo + 50:4d}  n={int(m.sum()):5d}  "
                  f"median={np.median(rp[m, 1]):6.2f}  p10={np.percentile(rp[m, 1], 10):5.1f} "
                  f"p90={np.percentile(rp[m, 1], 90):5.1f}")
    print("-- col pitch by band --")
    for lo in range(250, 950, 50):
        m = (cp[:, 0] >= lo) & (cp[:, 0] < lo + 50)
        if m.sum() >= 5:
            print(f"  y {lo:4d}-{lo + 50:4d}  n={int(m.sum()):5d}  median={np.median(cp[m, 1]):6.2f}")

    # ---- 三個模型
    pit = float(np.median(rp[:, 1]))
    uni_p = min(np.arange(80.0, 95.0, 0.05),
                key=lambda p: score(frames, v_uniform, (p,)) if True else 0)
    print(f"\nuniform best pitch = {uni_p:.2f} (journal 86-87, median gap {pit:.2f})")

    aff = fit(frames, v_affine, np.arange(84.0, 92.0, 0.25), np.arange(0.008, 0.026, 0.0005))
    hom = fit(frames, v_homography, np.arange(84.0, 92.0, 0.25), np.arange(0.6e-4, 1.7e-4, 0.02e-4))
    print(f"affine   p0={aff[0]:.2f} k={aff[1]:.5f}  rms={score(frames, v_affine, aff):.4f} cell")
    print(f"homog    p0={hom[0]:.2f} k2={hom[1]:.3e} rms={score(frames, v_homography, hom):.4f} cell")
    print(f"uniform  p={uni_p:.2f}  rms={score(frames, v_uniform, (uni_p,)):.4f} cell")

    models = {
        "uniform": (v_uniform, (uni_p,)),
        "affine": (v_affine, aff),
        "homography": (v_homography, hom),
    }

    def pitch_at(lo, hi):
        m = (rp[:, 0] >= lo) & (rp[:, 0] < hi)
        return float(np.median(rp[m, 1])) if m.sum() else pit

    report = {}
    print("\n== row-line residual (|cell| units) ==")
    for name, (f, a) in models.items():
        st = band_stats(residuals(frames, f, a), pitch_at)
        report[name] = {"params": list(map(float, a)), "bands": st}
        for b, s in st.items():
            if s:
                print(f"  {name:11s} {b:12s} n={s['n']:6d} med={s['med_cell']:.4f} "
                      f"p95={s['p95_cell']:.4f} max={s['max_cell']:.4f} "
                      f"(px med={s['med_px']:.2f} p95={s['p95_px']:.2f})")

    # 全域（不分帶）
    for name, (f, a) in models.items():
        allr = np.abs(np.concatenate([r for _, r in residuals(frames, f, a)]))
        report[name]["all"] = {
            "n": int(allr.size),
            "med": float(np.median(allr)),
            "p95": float(np.percentile(allr, 95)),
            "max": float(allr.max()),
            "frac_over_0.25": float((allr > 0.25).mean()),
        }
        print(f"  ALL {name:11s} med={report[name]['all']['med']:.4f} "
              f"p95={report[name]['all']['p95']:.4f} max={report[name]['all']['max']:.4f} "
              f">0.25: {report[name]['all']['frac_over_0.25'] * 100:.2f}%")

    # 逐 run
    print("\n== per-run row pitch(y) ==")
    for run in sorted({r for _, _, r in g["row_pts"]}):
        arr = np.array([(y, p) for y, p, rr in g["row_pts"] if rr == run])
        A = np.stack([arr[:, 0] - YREF, np.ones(len(arr))], 1)
        c, *_ = np.linalg.lstsq(A, arr[:, 1], rcond=None)
        fr = [(rn, rows) for rn, rows in frames if rn == run]
        print(f"  {run}: n={len(arr)} pitch650={c[1]:.2f} slope={c[0]:.5f} "
              f"rel={c[0] / c[1]:.3e}  homog-rms={score(fr, v_homography, hom):.4f}")

    (ROOT / "analysis.json").write_text(json.dumps(
        {"models": report, "vp_x": vp, "k_col": float(coef[0]),
         "row_fit": None, "n_frames": len(recs), "n_runs_rows": len(frames)}, indent=1))

    np.save(ROOT / "row_pts.npy", rp)
    np.save(ROOT / "col_pts.npy", cp)
    np.save(ROOT / "slopes.npy", sl)
    with (ROOT / "frames_rows.json").open("w") as fh:
        json.dump(frames, fh)


if __name__ == "__main__":
    main()
