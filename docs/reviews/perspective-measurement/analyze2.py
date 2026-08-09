"""模型偏差函數、find_lattice 格距穩定度、縱線塗抹、journal aim_drift。"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path("/tmp/claude-1000/-home-poyu-workspace-project-ggge-ai/4e7a46d6-0ea7-445f-be34-5bf07944dd7a/scratchpad/persp")
YREF = 650.0
BANDS = [("頂帶 250-450", 250, 450), ("中帶 450-700", 450, 700), ("底帶 700-870", 700, 870)]

# analyze.py 的擬合結果
ROW_P0, ROW_K2 = 88.00, 1.180e-4          # homography: pitch = p0 (1+k2 dy)^2
ROW_AFF_P0, ROW_AFF_K = 88.00, 0.02050    # affine: pitch = p0 + k dy
ROW_UNI = 87.05
COL_P0, COL_K = 92.639, 1.110e-4


def v_uniform(y, p=ROW_UNI):
    return y / p


def v_affine(y, p0=ROW_AFF_P0, k=ROW_AFF_K):
    return np.log(p0 + k * (y - YREF)) / k


def v_hom(y, p0=ROW_P0, k2=ROW_K2):
    return -1.0 / (p0 * k2 * (1.0 + k2 * (y - YREF)))


def col_v_uniform(x, y, p=92.639):
    return x / p


def col_v_hom(x, y, vp=1164.1, k=COL_K, p0=COL_P0):
    """縱線：先反投影到 y=YREF 的校正座標，再除以參考格距。"""
    s = 1.0 + k * (y - YREF)
    return (vp + (x - vp) / s) / p0


def deviation_table(name, fmodel, ftruth, lo, hi):
    y = np.arange(lo, hi + 1, 1.0)
    d = fmodel(y) - ftruth(y)
    d = d - d.mean()
    out = {"span": [lo, hi], "p2p": float(d.max() - d.min()),
           "max_abs": float(np.abs(d).max())}
    for bn, blo, bhi in BANDS:
        m = (y >= blo) & (y < bhi)
        if m.any():
            out[bn] = {"med": float(np.median(np.abs(d[m]))),
                       "p95": float(np.percentile(np.abs(d[m]), 95)),
                       "max": float(np.abs(d[m]).max())}
    return out


def main() -> None:
    recs = [json.loads(l) for l in (ROOT / "measurements.jsonl").open()]

    print("=== 模型偏差函數 D(y)=V_model-V_true，全域去平均，單位＝格 ===")
    dev = {}
    for span in [(250, 960), (250, 870), (250, 780)]:
        print(f"-- 螢幕 y {span[0]}..{span[1]} --")
        for name, f in (("uniform", v_uniform), ("affine", v_affine), ("homography", v_hom)):
            t = deviation_table(name, f, v_hom, *span)
            dev[f"{name}@{span}"] = t
            bands = "  ".join(
                f"{bn.split()[0]} med={t[bn]['med']:.3f} max={t[bn]['max']:.3f}"
                for bn, _, _ in BANDS if bn in t
            )
            print(f"  {name:11s} p2p={t['p2p']:.3f}  {bands}")

    print("\n=== 縱線模型偏差（含 y 依存與斜率），單位＝格 ===")
    xs = np.arange(500, 1900, 5.0)
    for ylo, yhi in [(250, 960), (250, 780)]:
        ys = np.arange(ylo, yhi + 1, 5.0)
        X, Y = np.meshgrid(xs, ys)
        d = col_v_uniform(X, Y) - col_v_hom(X, Y)
        d = d - d.mean()
        print(f"  uniform  y{ylo}-{yhi}: p2p={d.max() - d.min():.3f} maxabs={np.abs(d).max():.3f}")
        # 只修 y 依存、不修斜率的假設模型（縱線視為垂直、格距隨 y）
        d2 = (X / (COL_P0 * (1.0 + COL_K * (Y - YREF)))) - col_v_hom(X, Y)
        d2 = d2 - d2.mean()
        print(f"  y-scaled y{ylo}-{yhi}: p2p={d2.max() - d2.min():.3f} maxabs={np.abs(d2).max():.3f}")

    print("\n=== find_lattice 回報格距的穩定度（758 幀）===")
    rp, cp, r0 = [], [], []
    none_ct = 0
    for r in recs:
        lat = r["lattice"]
        if lat is None:
            none_ct += 1
            continue
        rp.append(lat["row_pitch"])
        cp.append(lat["col_pitch"])
        r0.append(lat["rows"][0])
    rp, cp, r0 = np.array(rp), np.array(cp), np.array(r0)
    print(f"  讀不到格線 {none_ct}/{len(recs)}")
    print(f"  row_pitch  med={np.median(rp):.1f} p5={np.percentile(rp, 5):.1f} "
          f"p95={np.percentile(rp, 95):.1f} min={rp.min():.1f} max={rp.max():.1f}")
    print(f"  col_pitch  med={np.median(cp):.1f} p5={np.percentile(cp, 5):.1f} "
          f"p95={np.percentile(cp, 95):.1f} min={cp.min():.1f} max={cp.max():.1f}")
    print(f"  rows[0]    med={np.median(r0):.0f} min={r0.min():.0f} max={r0.max():.0f}")

    # 相位期望與實測用不同週期造成的系統誤差
    P = 86.5
    drift = []
    for y0, p in zip(r0, rp, strict=True):
        a = y0 % p
        b = y0 % P
        d = (a - b + P / 2) % P - P / 2
        drift.append(d / P)
    drift = np.array(drift)
    print(f"  同一條線用 lattice 格距 vs 世界格距 {P} 取相位的差："
          f"med={np.median(np.abs(drift)):.3f} p95={np.percentile(np.abs(drift), 95):.3f} "
          f"max={np.abs(drift).max():.3f} 格；超過 0.25 格 {(np.abs(drift) > 0.25).mean() * 100:.1f}%")

    print("\n=== 帶內縱線等距性（單應性預測：同一 y 帶內縱線等距）===")
    resid = []
    for r in recs:
        for band in r["bands"]:
            c = band["cols"]
            keep = [c[0]] if c else []
            for a, b in zip(c, c[1:], strict=False):
                if 70 <= b - a <= 120:
                    keep.append(b)
                else:
                    keep = [b]
                if len(keep) >= 6:
                    break
            if len(keep) >= 6:
                arr = np.array(keep, float)
                idx = np.arange(len(arr))
                A = np.stack([idx, np.ones(len(arr))], 1)
                coef, *_ = np.linalg.lstsq(A, arr, rcond=None)
                resid.extend((arr - A @ coef).tolist())
    resid = np.abs(np.array(resid))
    print(f"  n={resid.size} med={np.median(resid):.2f}px p95={np.percentile(resid, 95):.2f}px "
          f"max={resid.max():.2f}px")

    print("\n=== 全域帶 vs 分帶縱線位置差（塗抹偏誤）===")
    diffs = []
    for r in recs:
        full = r["cols_full"]
        if not full:
            continue
        for band in r["bands"]:
            yc = (band["y"][0] + band["y"][1]) / 2.0
            for x in band["cols"]:
                near = min(full, key=lambda c: abs(c - x)) if full else None
                if near is not None and abs(near - x) < 45:
                    diffs.append((yc, x, near - x))
    d = np.array(diffs)
    for ylo in range(250, 950, 100):
        m = (d[:, 0] >= ylo) & (d[:, 0] < ylo + 100)
        if m.sum() > 50:
            print(f"  帶 y{ylo}-{ylo + 100}: n={int(m.sum())} 中位差={np.median(d[m, 2]):+.1f}px "
                  f"|差|p95={np.percentile(np.abs(d[m, 2]), 95):.1f}px")

    print("\n=== journal aim_drift ===")
    for run, base in (("run_031256", ROOT / "j031256/20260809-031256"),
                      ("run_011740", ROOT / "20260809-011740")):
        dx, dy = [], []
        for line in (base / "sweep.jsonl").open():
            e = json.loads(line)
            if e.get("kind") == "aim_drift":
                dx.append(e["drift"][0])
                dy.append(e["drift"][1])
        dx, dy = np.array(dx), np.array(dy)
        print(f"  {run}: n={dx.size}  |dx| med={np.median(np.abs(dx)):.1f}px "
              f"p95={np.percentile(np.abs(dx), 95):.1f}  |dy| med={np.median(np.abs(dy)):.1f}px "
              f"p95={np.percentile(np.abs(dy), 95):.1f}")
        print(f"      x 超 0.25 格(22.8px): {(np.abs(dx) > 0.25 * 91):.0%}"
              if False else
              f"      超閘比例 x={np.mean(np.abs(dx) > 0.25 * 91) * 100:.0f}% "
              f"y={np.mean(np.abs(dy) > 0.25 * 86) * 100:.0f}% （兩軸至少一軸超="
              f"{np.mean((np.abs(dx) > 0.25 * 91) | (np.abs(dy) > 0.25 * 86)) * 100:.0f}%）")

    (ROOT / "deviation.json").write_text(json.dumps(dev, indent=1))


if __name__ == "__main__":
    main()
