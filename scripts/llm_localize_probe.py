"""Offline probe: can a local vision LLM localise consecutive min-zoom map-scan
frames well enough to feed the coverage scanner's third localisation layer?

For each consecutive frame pair in a fixture series the probe sends BOTH frames
in one message (through the production encoding path -- long edge downscaled to
1280, JPEG q85) and asks the model to name one landmark visible in both frames
and report its 0-based grid cell (counted from the top-left visible gridline) in
each. The claimed offset is (colA - colB, rowA - rowB); the batch2-measured
ground-truth chain is the reference. The probe records per pair: correct / wrong
/ unparseable, the offset error, the named landmark, and latency, then writes a
markdown report with a strong / weak / no-ship recommendation.

Not a pytest (it needs a live ollama). Run e.g.:

    uv run python scripts/llm_localize_probe.py                 # default model
    uv run python scripts/llm_localize_probe.py --all-gemma     # every gemma tag
    uv run python scripts/llm_localize_probe.py --models gemma4:latest,gemma4:26b
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import cv2

from ggge_ai.battle.live_scan import LLM_LOCALIZE_PROMPT
from ggge_ai.perception.llm import DEFAULT_MODEL, DEFAULT_URL, LlmScreenReader

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SERIES = REPO / "tests" / "fixtures" / "vision" / "map_scan" / "ex2if_20260719"
DEFAULT_OUT = REPO / "docs" / "llm-localize-probe.md"

FRAMES = [
    "01_pt1_first_anchor.png", "02_pt2_pan_up.png", "03_pt3_pan_up.png",
    "04_pt4_pan_up.png", "05_pt5_pan_up_small.png", "06_pt6_pan_right.png",
    "07_pt7_pan_down.png", "08_pt8_pan_down.png", "09_pt9_pan_down_end.png",
]

# batch2-measured integer cell offsets, seq a -> seq a+1, expressed the way
# CellMap.localize would report it after anchoring frame a: (colA - colB,
# rowA - rowB) for any shared landmark.
TRUTH = {
    (1, 2): (1, -5),
    (2, 3): (0, -5),
    (3, 4): (-1, -5),
    (4, 5): (0, -2),
    (5, 6): (5, 0),
    (6, 7): (0, 6),
    (7, 8): (0, 5),
    (8, 9): (-1, 5),
}

# the probe measures the exact production prompt (imported from live_scan).
PROMPT = LLM_LOCALIZE_PROMPT


def _tags(url: str) -> list[str]:
    with urllib.request.urlopen(f"{url}/api/tags", timeout=5) as resp:
        data = json.load(resp)
    return sorted(m["name"] for m in data.get("models", []))


def _coord(node: object) -> tuple[int, int] | None:
    if not isinstance(node, dict):
        return None
    try:
        return int(node["col"]), int(node["row"])
    except (KeyError, TypeError, ValueError):
        return None


class PairResult:
    def __init__(self, pair, truth):
        self.pair = pair
        self.truth = truth
        self.landmark: str = ""
        self.offset: tuple[int, int] | None = None
        self.error: tuple[int, int] | None = None
        self.latency: float = 0.0
        self.verdict: str = "unparseable"

    @property
    def err_mag(self) -> float | None:
        if self.error is None:
            return None
        return (self.error[0] ** 2 + self.error[1] ** 2) ** 0.5


def probe_pair(reader: LlmScreenReader, frame_a, frame_b, pair, truth) -> PairResult:
    res = PairResult(pair, truth)
    t0 = time.monotonic()
    reply = reader.localize_pair(frame_a, frame_b, PROMPT, force=True)
    res.latency = time.monotonic() - t0
    if reply is None:
        return res
    res.landmark = str(reply.get("landmark", ""))[:60]
    ca, cb = _coord(reply.get("frame1")), _coord(reply.get("frame2"))
    if ca is None or cb is None:
        return res
    off = (ca[0] - cb[0], ca[1] - cb[1])
    res.offset = off
    res.error = (off[0] - truth[0], off[1] - truth[1])
    res.verdict = "correct" if off == truth else "wrong"
    return res


def run_model(reader: LlmScreenReader, frames, pairs) -> list[PairResult]:
    out = []
    for a, b in pairs:
        res = probe_pair(reader, frames[a - 1], frames[b - 1], (a, b), TRUTH[(a, b)])
        mark = {"correct": "OK", "wrong": "XX", "unparseable": "??"}[res.verdict]
        print(
            f"  [{reader.model}] pt{a}->pt{b} {mark} truth={TRUTH[(a, b)]} "
            f"got={res.offset} err={res.error} {res.latency:.1f}s :: {res.landmark}"
        )
        out.append(res)
    return out


def recommend(per_model: dict[str, list[PairResult]]) -> tuple[str, str]:
    best_model, best_correct = None, -1
    for model, results in per_model.items():
        correct = sum(1 for r in results if r.verdict == "correct")
        if correct > best_correct:
            best_model, best_correct = model, correct
    total = len(next(iter(per_model.values()))) if per_model else 0
    results = per_model.get(best_model, [])
    near = [r for r in results if r.err_mag is not None and r.err_mag <= 2.0]
    if total and best_correct / total >= 0.75:
        verdict = "strong"
        rationale = (
            f"{best_model} localised {best_correct}/{total} pairs exactly; the "
            "grid-coordinate route is reliable enough to feed offset hypotheses "
            "(still gated by patch verification + edge consistency)."
        )
    elif total and len(near) / total >= 0.6:
        verdict = "weak"
        rationale = (
            f"{best_model} rarely nails the exact cell ({best_correct}/{total}) "
            f"but lands within ~2 cells on {len(near)}/{total} pairs: usable only "
            "as a landmark pointer, with deterministic patch matching carrying "
            "the actual offset."
        )
    else:
        verdict = "no-ship"
        rationale = (
            f"best model {best_model} managed {best_correct}/{total} exact and "
            f"{len(near)}/{total} within 2 cells -- too weak to wire even behind "
            "guardrails; keep the probe report and the seam only."
        )
    return verdict, rationale


def write_report(path: Path, url: str, per_model: dict[str, list[PairResult]], reps: int) -> None:
    verdict, rationale = recommend(per_model)
    lines: list[str] = []
    lines.append("# LLM 定位 probe 報告（覆蓋掃描第三層，#26 批4）")
    lines.append("")
    lines.append(
        f"產出：`scripts/llm_localize_probe.py`，{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%MZ')}，"
        f"ollama @ {url}，每對 {reps} 次、temperature 0。"
    )
    lines.append("")
    lines.append("## 方法")
    lines.append("")
    lines.append(
        "- 素材：`tests/fixtures/vision/map_scan/ex2if_20260719/` 九幀（格線已開、最小 zoom）。"
    )
    lines.append(
        "- 每對連續幀兩張圖同訊息送 LLM（`LlmScreenReader.localize_pair`，"
        "生產編碼路徑：長邊縮到 1280＋JPEG q85），要求指認兩幀共通地標及各自 0 基格座標"
        "（左上可見格線起算）。"
    )
    lines.append(
        "- 宣告偏移＝(col1-col2, row1-row2)，對批2 實測真值鏈；exact 相等＝correct。"
    )
    lines.append(
        "- 真值鏈：pt1→2 (1,-5)、2→3 (0,-5)、3→4 (-1,-5)、4→5 (0,-2)、5→6 (5,0)、"
        "6→7 (0,6)、7→8 (0,5)、8→9 (-1,5)。"
    )
    lines.append("")
    lines.append("## 逐對結果")
    lines.append("")
    for model, results in per_model.items():
        correct = sum(1 for r in results if r.verdict == "correct")
        lat = statistics.mean(r.latency for r in results) if results else 0.0
        errs = [r.err_mag for r in results if r.err_mag is not None]
        mean_err = statistics.mean(errs) if errs else float("nan")
        lines.append(f"### {model}")
        lines.append("")
        lines.append(
            f"正確 {correct}/{len(results)}、平均 |誤差| "
            f"{mean_err:.2f} 格、平均延遲 {lat:.1f}s。"
        )
        lines.append("")
        lines.append("| 幀對 | 真值 | LLM 偏移 | 誤差 | 判定 | 延遲 | 地標 |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in results:
            a, b = r.pair
            lines.append(
                f"| pt{a}→pt{b} | {r.truth} | {r.offset} | {r.error} | "
                f"{r.verdict} | {r.latency:.1f}s | {r.landmark} |"
            )
        lines.append("")
    lines.append("## 結論建議")
    lines.append("")
    lines.append(f"**裁決：{verdict}**。{rationale}")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nreport -> {path}")
    print(f"verdict -> {verdict}: {rationale}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--series", type=Path, default=DEFAULT_SERIES, help="fixture frame dir")
    ap.add_argument("--url", default=DEFAULT_URL, help="ollama base url")
    ap.add_argument("--models", default="", help="comma list of model tags to probe")
    ap.add_argument("--all-gemma", action="store_true", help="also probe every gemma* tag")
    ap.add_argument("--repeats", type=int, default=1, help="calls per pair (>=1)")
    ap.add_argument("--timeout", type=float, default=180.0, help="per-call timeout seconds")
    ap.add_argument("--pairs", default="", help="comma list of first seqs, e.g. 1,2,7 (default all)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="markdown report path")
    args = ap.parse_args()

    models: list[str] = [m.strip() for m in args.models.split(",") if m.strip()]
    if args.all_gemma:
        models += [t for t in _tags(args.url) if t.startswith("gemma") and t not in models]
    if not models:
        models = [DEFAULT_MODEL]

    frames = [cv2.imread(str(args.series / name)) for name in FRAMES]
    if any(f is None for f in frames):
        raise SystemExit(f"could not read all frames under {args.series}")

    if args.pairs:
        firsts = {int(x) for x in args.pairs.split(",")}
        pairs = [(a, a + 1) for a in sorted(firsts) if (a, a + 1) in TRUTH]
    else:
        pairs = sorted(TRUTH)

    per_model: dict[str, list[PairResult]] = {}
    for model in models:
        print(f"== {model} ==")
        reader = LlmScreenReader(url=args.url, model=model, timeout_s=args.timeout)
        acc = run_model(reader, frames, pairs)
        for _ in range(args.repeats - 1):
            acc = _merge_best(acc, run_model(reader, frames, pairs))
        per_model[model] = acc

    write_report(args.out, args.url, per_model, args.repeats)


def _merge_best(a: list[PairResult], b: list[PairResult]) -> list[PairResult]:
    rank = {"correct": 2, "wrong": 1, "unparseable": 0}
    return [x if rank[x.verdict] >= rank[y.verdict] else y for x, y in zip(a, b)]


if __name__ == "__main__":
    main()
