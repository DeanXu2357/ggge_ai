"""報告用圖表。"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path("/tmp/claude-1000/-home-poyu-workspace-project-ggge-ai/4e7a46d6-0ea7-445f-be34-5bf07944dd7a/scratchpad/persp")
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#8a8a84"
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
YREF = 650.0


def style(ax, title, xlabel, ylabel):
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    ax.set_title(title, color=INK, fontsize=12, loc="left", pad=12)
    ax.set_xlabel(xlabel, color=INK2, fontsize=10)
    ax.set_ylabel(ylabel, color=INK2, fontsize=10)
    ax.tick_params(colors=INK2, labelsize=9)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
        ax.spines[side].set_linewidth(0.8)
    ax.grid(True, color="#e6e5e0", linewidth=0.8)
    ax.set_axisbelow(True)


def fig1() -> None:
    rp = np.load(ROOT / "row_pts.npy", allow_pickle=True).astype(float)
    cp = np.load(ROOT / "col_pts.npy", allow_pickle=True).astype(float)
    fig, ax = plt.subplots(figsize=(8.4, 4.6), dpi=140)
    style(ax, "格距隨螢幕 y 線性增長（橫線的斜率是縱線的兩倍）",
          "螢幕 y（px）", "格距（px）")

    for arr, color, label in ((rp, S1, "橫線間距 row pitch"), (cp, S2, "縱線間距 col pitch")):
        bins = np.arange(250, 1000, 25)
        idx = np.digitize(arr[:, 0], bins)
        xs, med, lo, hi = [], [], [], []
        for i in range(1, len(bins)):
            m = idx == i
            if m.sum() < 15:
                continue
            xs.append(bins[i - 1] + 12.5)
            med.append(np.median(arr[m, 1]))
            lo.append(np.percentile(arr[m, 1], 10))
            hi.append(np.percentile(arr[m, 1], 90))
        xs, med = np.array(xs), np.array(med)
        ax.fill_between(xs, lo, hi, color=color, alpha=0.16, linewidth=0)
        ax.plot(xs, med, color=color, linewidth=2, marker="o", markersize=5,
                markeredgecolor=SURFACE, markeredgewidth=1.2, label=label)
        A = np.stack([arr[:, 0] - YREF, np.ones(len(arr))], 1)
        c, *_ = np.linalg.lstsq(A, arr[:, 1], rcond=None)
        yy = np.array([250.0, 960.0])
        ax.plot(yy, c[1] + c[0] * (yy - YREF), color=color, linewidth=1,
                linestyle="--", alpha=0.7)
        anchor = (470, 96.2) if color == S2 else (700, 81.2)
        ax.text(anchor[0], anchor[1],
                f"{label.split()[0]}  {c[1]:.1f}px @y650，斜率 {c[0]:.4f} px/px"
                f"（相對 {c[0] / c[1] * 1e4:.2f}e-4/px）",
                color=color, fontsize=9, ha="left")

    for lo_, hi_, name in ((250, 450, "頂帶"), (450, 700, "中帶"), (700, 870, "底帶")):
        ax.axvline(hi_, color=MUTED, linewidth=0.8, linestyle=":", alpha=0.7)
        ax.text((lo_ + hi_) / 2, 78.5, name, color=MUTED, fontsize=9, ha="center")

    ax.set_xlim(250, 960)
    ax.set_ylim(78, 97)
    leg = ax.legend(frameon=False, loc="upper left", fontsize=9, labelcolor=INK2)
    leg.set_title(None)
    fig.tight_layout()
    fig.savefig(ROOT / "fig1_pitch_vs_y.png")


def fig2() -> None:
    sl = np.load(ROOT / "slopes.npy", allow_pickle=True).astype(float)
    fig, ax = plt.subplots(figsize=(8.4, 4.2), dpi=140)
    style(ax, "縱線扇形傾斜：斜率與 x 成正比，交會於 VP_X≈1164",
          "縱線螢幕 x（px）", "縱線斜率 dx/dy")
    bins = np.arange(500, 2300, 40)
    idx = np.digitize(sl[:, 0], bins)
    xs, med, lo, hi = [], [], [], []
    for i in range(1, len(bins)):
        m = idx == i
        if m.sum() < 30:
            continue
        xs.append(bins[i - 1] + 20)
        med.append(np.median(sl[m, 1]))
        lo.append(np.percentile(sl[m, 1], 25))
        hi.append(np.percentile(sl[m, 1], 75))
    ax.fill_between(xs, lo, hi, color=S1, alpha=0.16, linewidth=0)
    ax.plot(xs, med, color=S1, linewidth=2, label="實測中位斜率（帶間位移）")
    A = np.stack([sl[:, 0], np.ones(len(sl))], 1)
    c, *_ = np.linalg.lstsq(A, sl[:, 1], rcond=None)
    xx = np.array([500.0, 2280.0])
    ax.plot(xx, c[0] * xx + c[1], color=S2, linewidth=1.6, linestyle="--",
            label=f"擬合 K(x−VP)，K={c[0]:.3e}, VP_X={-c[1] / c[0]:.0f}")
    ax.axhline(0, color=MUTED, linewidth=0.8)
    ax.axvline(-c[1] / c[0], color=MUTED, linewidth=0.8, linestyle=":")
    ax.annotate("VP_X 1164\n（board.PERSPECTIVE_VP_X = 1166）",
                xy=(-c[1] / c[0], 0), xytext=(12, 26), textcoords="offset points",
                color=INK, fontsize=9)
    ax.legend(frameon=False, loc="upper left", fontsize=9, labelcolor=INK2)
    fig.tight_layout()
    fig.savefig(ROOT / "fig2_col_slope.png")


def fig3() -> None:
    y = np.arange(250, 961, 1.0)
    p0, k2 = 88.00, 1.180e-4
    v_hom = -1.0 / (p0 * k2 * (1.0 + k2 * (y - YREF)))
    v_aff = np.log(88.00 + 0.02050 * (y - YREF)) / 0.02050
    v_uni = y / 87.05
    fig, ax = plt.subplots(figsize=(8.4, 4.2), dpi=140)
    style(ax, "橫線模型偏差 D(y)＝模型列座標 − 實測列座標（全域去平均）",
          "螢幕 y（px）", "偏差（格）")
    for v, color, label in ((v_uni, S2, "均勻格距（現行）"),
                            (v_aff, S1, "affine：格距對 y 一次式"),
                            (v_hom, S3, "單應性：格距 ∝ s(y)²")):
        d = v - v_hom
        d = d - d.mean()
        ax.plot(y, d, color=color, linewidth=2, label=label)
    for lvl in (0.25, -0.25):
        ax.axhline(lvl, color="#e34948", linewidth=1.2, linestyle="--")
    ax.text(255, 0.255, "aim 閘容差 ±0.25 格", color="#e34948", fontsize=9, va="bottom")
    ax.set_ylim(-0.30, 0.30)
    ax.set_xlim(250, 960)
    ax.legend(frameon=False, loc="lower right", fontsize=9, labelcolor=INK2)
    fig.tight_layout()
    fig.savefig(ROOT / "fig3_row_model_deviation.png")


def fig4() -> None:
    fig, ax = plt.subplots(figsize=(8.4, 4.2), dpi=140)
    style(ax, "縱線：把斜格當垂直線的位置誤差（格），是橫線誤差的三倍以上",
          "縱線螢幕 x（px）", "誤差（格）")
    x = np.arange(150, 2281, 5.0)
    for yv, color, label in ((300.0, S1, "螢幕 y=300（頂帶）"),
                             (650.0, S3, "螢幕 y=650（參考列）"),
                             (900.0, S2, "螢幕 y=900（底帶）")):
        s = 1.0 + 1.110e-4 * (yv - YREF)
        xr = 1164.1 + (x - 1164.1) / s
        ax.plot(x, (x - xr) / 92.639, color=color, linewidth=2)
        ax.annotate(label, xy=(x[-1], ((x - xr) / 92.639)[-1]), xytext=(-4, 6),
                    textcoords="offset points", color=INK, fontsize=9, ha="right")
    for lvl in (0.25, -0.25):
        ax.axhline(lvl, color="#e34948", linewidth=1.2, linestyle="--")
    ax.text(160, 0.255, "aim 閘容差 ±0.25 格", color="#e34948", fontsize=9, va="bottom")
    ax.axvspan(150, 1750, color=MUTED, alpha=0.07, linewidth=0)
    ax.text(950, -0.44, "GRID_REGION 取樣範圍 x150–1750", color=MUTED, fontsize=9, ha="center")
    ax.set_xlim(150, 2280)
    ax.set_ylim(-0.5, 0.5)
    fig.tight_layout()
    fig.savefig(ROOT / "fig4_col_error.png")


def fig5() -> None:
    data = json.load((ROOT / "centre_raw.json").open())
    xs = np.array([d["ring"][0] for d in data])
    ys = np.array([d["ring"][1] for d in data])
    runs = [d["run"] for d in data]
    fig, ax = plt.subplots(figsize=(6.2, 5.0), dpi=140)
    style(ax, "置中後選擇環中心：21 筆樣本落在 (1170, 546) ±3px",
          "螢幕 x（px）", "螢幕 y（px）")
    for run, color, label in (("run_031256", S1, "run 20260809-031256"),
                              ("run_011740", S3, "run 20260809-011740")):
        m = np.array([r == run for r in runs])
        ax.plot(xs[m], ys[m], "o", color=color, markersize=9,
                markeredgecolor=SURFACE, markeredgewidth=1.4, label=label)
    ax.plot([950], [540], "X", color="#e34948", markersize=13, label="現行 SCREEN_CENTRE (950,540)")
    ax.annotate("現行 (950,540)", xy=(950, 540), xytext=(6, 12),
                textcoords="offset points", color="#e34948", fontsize=9)
    ax.annotate(f"實測環心 ({xs.mean():.0f}, {ys.mean():.0f})\n格心 (1174, 555)",
                xy=(xs.mean(), ys.mean()), xytext=(-10, 20),
                textcoords="offset points", color=INK, fontsize=9, ha="right")
    ax.set_xlim(900, 1230)
    ax.set_ylim(500, 600)
    ax.invert_yaxis()
    ax.legend(frameon=False, loc="lower left", fontsize=9, labelcolor=INK2)
    fig.tight_layout()
    fig.savefig(ROOT / "fig5_screen_centre.png")


if __name__ == "__main__":
    plt.rcParams["font.family"] = ["Noto Sans CJK TC", "Noto Sans CJK JP", "DejaVu Sans"]
    fig1()
    fig2()
    fig3()
    fig4()
    fig5()
    print("ok")
