"""Offline probe B: measure the form the user asked for after probe A's no-ship.

Probe A tested the hardest shape -- two frames in one message, LLM reporting
absolute grid coordinates across frames -- and found local gemma models reply a
systematic (0,0). That does not test "point at a landmark in ONE image, let the
program carry the precision". Probe B measures exactly that, plus a deterministic
baseline that uses no LLM, plus a gap scenario with units masked out.

Three modes, each localising every consecutive frame pair of a fixture series
and scoring the recovered cell offset against the batch2 truth chain:

  llm   -- weak form: the LLM is a patch SELECTOR. For each frame it is asked
           (single image, single message) to list up to 3 salient landmarks with
           an approximate percentage position. Each landmark's point in frame A
           becomes a full-resolution patch searched by TM_CCOEFF_NORMED across
           frame B; the per-landmark screen displacements vote a cell offset. The
           LLM never emits a coordinate that touches the answer -- the program's
           template match does, so a roughly-pointed landmark is enough.
  auto  -- deterministic baseline, no LLM: the program picks patches itself on a
           candidate grid, scored by texture variance x intra-frame uniqueness,
           then runs the identical search + vote. This measures the patch-search
           layer ALONE, isolating whatever the LLM adds over variance selection.
  gap   -- reruns llm and auto with the units masked (ground-truth footprints
           painted over with the frame's median terrain colour). The real gap is
           "no units in the overlap band"; this measures whether bare min-zoom
           terrain carries a lock at all.

LLM input goes through the production encoding path (long edge 1280, JPEG q85,
LlmScreenReader._encode); template matching runs on the full-resolution frame
(the program's own precision). Only responsive models are probed (gemma4:latest,
gemma3:27b), 90s timeout, temperature 0; a timeout is missing data, not a 0.

Not a pytest (llm/gap-llm modes need a live ollama; auto/gap-auto do not). Run:

    uv run python -u scripts/llm_localize_probe_b.py                # all modes
    uv run python -u scripts/llm_localize_probe_b.py --modes auto   # no ollama
    uv run python -u scripts/llm_localize_probe_b.py --models gemma4:latest
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from ggge_ai.battle import vision
from ggge_ai.battle.live_scan import LLM_PATCH_MIN, LLM_PATCH_MIN_STD
from ggge_ai.perception.llm import DEFAULT_URL, LlmScreenReader

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SERIES = REPO / "tests" / "fixtures" / "vision" / "map_scan" / "ex2if_20260719"
DEFAULT_OUT = REPO / "docs" / "llm-localize-probe-b.md"

FRAMES = [
    "01_pt1_first_anchor.png", "02_pt2_pan_up.png", "03_pt3_pan_up.png",
    "04_pt4_pan_up.png", "05_pt5_pan_up_small.png", "06_pt6_pan_right.png",
    "07_pt7_pan_down.png", "08_pt8_pan_down.png", "09_pt9_pan_down_end.png",
]

# batch2-measured integer cell offsets, seq a -> seq a+1, as (colA-colB,
# rowA-rowB) for any shared landmark (same convention CellMap.localize reports).
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

# patch geometry. A ~1.75-cell window (half 85 -> 170px on the ~96px min-zoom
# lattice) is wide enough to carry a landmark yet offset from the grid period so
# the match does not alias on the lattice itself; the search band absorbs the
# sub-cell drift the vote quantises away.
PATCH_HALF = 85
# deterministic candidate grid: a coarse lattice over the terrain region (minus
# the top banner / bottom prompt strip), each point scored then thinned by
# spatial spread to TOP_K distinct landmarks.
AUTO_REGION = (170, 110, 2010, 900)
AUTO_STEP = 130
TOP_K = 3
AUTO_MIN_DIST = 220
# the uniqueness ranking is coarse (does this patch recur in the frame?), so it
# runs on a half-scale copy: a full-res self-search of every candidate patch cost
# minutes, the half-scale ranking is the same order at a fraction of the price.
UNIQ_SCALE = 0.5
# unit mask: a square footprint painted over each ground-truth unit centre so
# neither selection nor matching can lean on a sprite.
MASK_HALF = 80

LLM_LANDMARK_PROMPT = (
    "You are looking at ONE screenshot from a tactical map in the mobile game SD "
    "Gundam G Generation ETERNAL (landscape). List up to 3 visually distinctive "
    "landmarks that would be easy to find again in a slightly panned view -- a "
    "unit, a terrain feature, a structure or a marking. For each give a short "
    "description and its approximate position as a PERCENTAGE of the image: "
    "x_pct from 0 (left edge) to 100 (right edge), y_pct from 0 (top) to 100 "
    "(bottom).\n"
    'Answer strictly as JSON: {"landmarks": [{"desc": "<short>", '
    '"x_pct": <number>, "y_pct": <number>}]}'
)


# --- pure geometry / matching -------------------------------------------------

def pct_to_px(x_pct: float, y_pct: float, w: int, h: int) -> tuple[int, int]:
    """A percentage point (scale-invariant, so the LLM's downscaled view maps
    straight onto the full-resolution frame) to a full-frame pixel, clamped."""
    x = min(max(x_pct / 100.0, 0.0), 1.0) * (w - 1)
    y = min(max(y_pct / 100.0, 0.0), 1.0) * (h - 1)
    return int(round(x)), int(round(y))


def cell_index(cols: tuple[int, ...], rows: tuple[int, ...], x: float, y: float
               ) -> tuple[int, int] | None:
    """0-based (col, row) of a screen point in the frame's own lattice -- the
    count of gridlines above/left of it, i.e. the coordinate probe A asked the
    LLM to read. None when the point is outside the lattice span."""
    col = _line_cell(cols, x)
    row = _line_cell(rows, y)
    if col is None or row is None:
        return None
    return col, row


def _line_cell(lines: tuple[int, ...], value: float) -> int | None:
    for i in range(len(lines) - 1):
        if lines[i] <= value < lines[i + 1]:
            return i
    return None


def crop_patch(frame: np.ndarray, cx: int, cy: int, half: int
               ) -> tuple[np.ndarray, tuple[int, int]] | None:
    """Square crop centred near (cx, cy) with its true centre, or None when the
    point sits too close to a frame edge to take a full window."""
    h, w = frame.shape[:2]
    x0, y0 = cx - half, cy - half
    x1, y1 = cx + half, cy + half
    if x0 < 0 or y0 < 0 or x1 > w or y1 > h:
        return None
    return frame[y0:y1, x0:x1], (cx, cy)


def patch_std(patch: np.ndarray) -> float:
    return float(patch.std())


def template_search(patch: np.ndarray, target: np.ndarray
                    ) -> tuple[tuple[int, int], float] | None:
    """Peak TM_CCOEFF_NORMED of `patch` over the whole `target`, returning the
    matched patch CENTRE in target coordinates and the peak score. None when the
    patch does not fit."""
    ph, pw = patch.shape[:2]
    th, tw = target.shape[:2]
    if ph > th or pw > tw:
        return None
    resp = cv2.matchTemplate(target, patch, cv2.TM_CCOEFF_NORMED)
    _, peak, _, loc = cv2.minMaxLoc(resp)
    return (loc[0] + pw // 2, loc[1] + ph // 2), float(peak)


def patch_uniqueness(patch: np.ndarray, frame: np.ndarray, self_center: tuple[int, int],
                     suppress: int) -> float:
    """How distinct a patch is within its own frame: 1 minus the strongest match
    ANYWHERE ELSE (a disk of radius `suppress` around the self peak zeroed out).
    Low when the frame repeats the texture (grid, starfield) -- exactly the case
    that aliases a cross-frame search."""
    ph, pw = patch.shape[:2]
    if frame.shape[0] < ph or frame.shape[1] < pw:
        return 0.0
    resp = cv2.matchTemplate(frame, patch, cv2.TM_CCOEFF_NORMED)
    sx, sy = self_center[0] - pw // 2, self_center[1] - ph // 2
    y, x = np.ogrid[: resp.shape[0], : resp.shape[1]]
    resp = resp.copy()
    resp[(x - sx) ** 2 + (y - sy) ** 2 <= suppress * suppress] = -1.0
    return float(1.0 - max(resp.max(), 0.0))


def auto_candidates(frame: np.ndarray, half: int, mask: np.ndarray | None,
                    region=AUTO_REGION, step=AUTO_STEP, top_k=TOP_K,
                    min_dist=AUTO_MIN_DIST) -> list[tuple[int, int, float]]:
    """Deterministic patch picks: score every grid point by variance x
    uniqueness, drop flat / masked ones, then take the strongest that stay
    `min_dist` apart. No LLM, no randomness."""
    rx, ry, rw, rh = region
    small = cv2.resize(frame, None, fx=UNIQ_SCALE, fy=UNIQ_SCALE, interpolation=cv2.INTER_AREA)
    scored: list[tuple[float, int, int]] = []
    for cy in range(ry, ry + rh + 1, step):
        for cx in range(rx, rx + rw + 1, step):
            if _mask_hit(mask, cx, cy, half):
                continue
            crop = crop_patch(frame, cx, cy, half)
            if crop is None:
                continue
            patch, _ = crop
            std = patch_std(patch)  # full-res texture floor, same guard as the search
            if std < LLM_PATCH_MIN_STD:
                continue
            sp = cv2.resize(patch, None, fx=UNIQ_SCALE, fy=UNIQ_SCALE,
                            interpolation=cv2.INTER_AREA)
            s_center = (int(cx * UNIQ_SCALE), int(cy * UNIQ_SCALE))
            uniq = patch_uniqueness(sp, small, s_center, max(1, int(half * UNIQ_SCALE)))
            scored.append((std * uniq, cx, cy))
    scored.sort(key=lambda s: -s[0])
    out: list[tuple[int, int, float]] = []
    for score, cx, cy in scored:
        if all((cx - ox) ** 2 + (cy - oy) ** 2 >= min_dist * min_dist for ox, oy, _ in out):
            out.append((cx, cy, score))
        if len(out) >= top_k:
            break
    return out


def _mask_hit(mask: np.ndarray | None, cx: int, cy: int, half: int) -> bool:
    if mask is None:
        return False
    h, w = mask.shape[:2]
    x0, y0 = max(0, cx - half), max(0, cy - half)
    x1, y1 = min(w, cx + half), min(h, cy + half)
    if x1 <= x0 or y1 <= y0:
        return True
    return bool(mask[y0:y1, x0:x1].any())


def consensus(items: list[tuple[tuple[int, int], float]]
              ) -> tuple[tuple[int, int] | None, int, int]:
    """Vote a single offset from the per-landmark (offset, score) pairs: the
    group with the most votes (score sum breaks ties). Returns (offset, votes,
    total); offset is None when every landmark disagreed (all singletons)."""
    if not items:
        return None, 0, 0
    groups: dict[tuple[int, int], list[float]] = defaultdict(list)
    for off, score in items:
        groups[off].append(score)
    best = max(groups.items(), key=lambda kv: (len(kv[1]), sum(kv[1])))
    votes, total = len(best[1]), len(items)
    if votes == 1 and total >= 2:
        return None, votes, total
    return best[0], votes, total


def build_unit_mask(shape: tuple[int, int], centers: list[tuple[int, int]],
                    half: int = MASK_HALF) -> np.ndarray:
    mask = np.zeros(shape[:2], np.uint8)
    for cx, cy in centers:
        x0, y0 = max(0, cx - half), max(0, cy - half)
        x1, y1 = min(shape[1], cx + half), min(shape[0], cy + half)
        mask[y0:y1, x0:x1] = 1
    return mask


def apply_mask(frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Paint the masked footprints over with the frame's median colour, so the
    holes read as flat terrain (low variance, no correspondence) instead of a
    high-contrast rectangle that would forge a landmark."""
    out = frame.copy()
    fill = np.median(frame.reshape(-1, frame.shape[2]), axis=0)
    out[mask > 0] = fill.astype(frame.dtype)
    return out


# --- offset from one landmark -------------------------------------------------

def landmark_offset(a_frame: np.ndarray, b_frame: np.ndarray, a_lat: vision.MapLattice,
                    b_lat: vision.MapLattice, cx: int, cy: int, half: int
                    ) -> tuple[tuple[int, int], float] | None:
    """Crop the landmark from A, find it in B, and turn the two lattice cells
    into an offset (colA-colB, rowA-rowB). None on any guard miss: off-edge crop,
    flat patch (LLM_PATCH_MIN_STD), match below LLM_PATCH_MIN, or an off-lattice
    endpoint."""
    crop = crop_patch(a_frame, cx, cy, half)
    if crop is None:
        return None
    patch, a_center = crop
    if patch_std(patch) < LLM_PATCH_MIN_STD:
        return None
    hit = template_search(patch, b_frame)
    if hit is None:
        return None
    b_center, score = hit
    if score < LLM_PATCH_MIN:
        return None
    a_cell = cell_index(a_lat.cols, a_lat.rows, a_center[0], a_center[1])
    b_cell = cell_index(b_lat.cols, b_lat.rows, b_center[0], b_center[1])
    if a_cell is None or b_cell is None:
        return None
    return (a_cell[0] - b_cell[0], a_cell[1] - b_cell[1]), score


# --- per-pair runners ---------------------------------------------------------

class PairResult:
    def __init__(self, pair: tuple[int, int], truth: tuple[int, int]) -> None:
        self.pair = pair
        self.truth = truth
        self.offset: tuple[int, int] | None = None
        self.error: tuple[int, int] | None = None
        self.px_error: float | None = None
        self.score: float = 0.0
        self.votes: int = 0
        self.total: int = 0
        self.latency: float = 0.0
        self.landmarks: list[str] = []
        self.verdict: str = "no_data"

    def settle(self, offset, votes, total, scores, lat, a_lat) -> None:
        self.votes, self.total, self.latency = votes, total, lat
        if scores:
            self.score = statistics.mean(scores)
        if offset is None:
            self.verdict = "no_consensus" if total else "no_data"
            return
        self.offset = offset
        self.error = (offset[0] - self.truth[0], offset[1] - self.truth[1])
        self.px_error = (
            (self.error[0] * a_lat.col_pitch) ** 2 + (self.error[1] * a_lat.row_pitch) ** 2
        ) ** 0.5
        self.verdict = "correct" if offset == self.truth else "wrong"


def _points_llm(reader: LlmScreenReader, frame: np.ndarray, timeout: float,
                cache: dict) -> tuple[list[tuple[int, int, str]], float] | None:
    """Landmark points (full-frame px) for one frame, cached per frame id. None
    on timeout / transport failure (missing data). Empty list is a real, non-null
    answer (the model saw the frame and named nothing usable)."""
    key = id(frame)
    if key in cache:
        return cache[key]
    payload = {
        "model": reader.model,
        "messages": [
            {"role": "user", "content": LLM_LANDMARK_PROMPT,
             "images": [LlmScreenReader._encode(frame)]}
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }
    t0 = time.monotonic()
    try:
        content = reader.transport(reader.url, payload, timeout)
        data = json.loads(content)
    except Exception as exc:  # noqa: BLE001 -- timeout / transport / parse = missing data
        print(f"    [{reader.model}] landmark call failed: {type(exc).__name__}")
        cache[key] = None
        return None
    lat = time.monotonic() - t0
    h, w = frame.shape[:2]
    pts: list[tuple[int, int, str]] = []
    for lm in (data or {}).get("landmarks", []) if isinstance(data, dict) else []:
        try:
            px, py = pct_to_px(float(lm["x_pct"]), float(lm["y_pct"]), w, h)
        except (KeyError, TypeError, ValueError):
            continue
        pts.append((px, py, str(lm.get("desc", ""))[:40]))
    cache[key] = (pts, lat)
    return pts, lat


def run_pair_llm(reader, a_frame, b_frame, a_lat, b_lat, pair, cache) -> PairResult:
    res = PairResult(pair, TRUTH[pair])
    got = _points_llm(reader, a_frame, reader.timeout_s, cache)
    if got is None:
        return res
    points, lat = got
    items, scores = [], []
    for px, py, desc in points:
        res.landmarks.append(desc)
        off = landmark_offset(a_frame, b_frame, a_lat, b_lat, px, py, PATCH_HALF)
        if off is not None:
            items.append(off)
            scores.append(off[1])
    offset, votes, total = consensus(items)
    res.settle(offset, votes, total, scores, lat, a_lat)
    return res


def run_pair_auto(a_frame, b_frame, a_lat, b_lat, pair, mask=None) -> PairResult:
    res = PairResult(pair, TRUTH[pair])
    items, scores = [], []
    for cx, cy, _ in auto_candidates(a_frame, PATCH_HALF, mask):
        res.landmarks.append(f"({cx},{cy})")
        off = landmark_offset(a_frame, b_frame, a_lat, b_lat, cx, cy, PATCH_HALF)
        if off is not None:
            items.append(off)
            scores.append(off[1])
    offset, votes, total = consensus(items)
    res.settle(offset, votes, total, scores, 0.0, a_lat)
    return res


# --- report -------------------------------------------------------------------

def _summary(results: list[PairResult]) -> str:
    correct = sum(1 for r in results if r.verdict == "correct")
    wrong = sum(1 for r in results if r.verdict == "wrong")
    noc = sum(1 for r in results if r.verdict == "no_consensus")
    nod = sum(1 for r in results if r.verdict == "no_data")
    graded = [r for r in results if r.px_error is not None]
    mean_px = statistics.mean(r.px_error for r in graded) if graded else float("nan")
    return f"correct {correct}/{len(results)} (wrong {wrong}, no-consensus {noc}, " \
           f"no-data {nod}), 平均 px 誤差 {mean_px:.0f}"


def _table(results: list[PairResult], llm: bool) -> list[str]:
    head = "| 幀對 | 真值 | 偏移 | 誤差 | px誤差 | 分數 | 票數 | 判定 |"
    if llm:
        head = "| 幀對 | 真值 | 偏移 | 誤差 | 分數 | 票數 | 延遲 | 判定 | 地標 |"
    lines = [head, "|" + "---|" * (head.count("|") - 1)]
    for r in results:
        a, b = r.pair
        px = "-" if r.px_error is None else f"{r.px_error:.0f}"
        if llm:
            lm = "; ".join(r.landmarks[:3])
            lines.append(
                f"| pt{a}→pt{b} | {r.truth} | {r.offset} | {r.error} | "
                f"{r.score:.2f} | {r.votes}/{r.total} | {r.latency:.1f}s | "
                f"{r.verdict} | {lm} |"
            )
        else:
            lines.append(
                f"| pt{a}→pt{b} | {r.truth} | {r.offset} | {r.error} | {px} | "
                f"{r.score:.2f} | {r.votes}/{r.total} | {r.verdict} |"
            )
    return lines


def write_report(path: Path, url: str, auto_res, gap_auto_res, per_model, per_model_gap
                 ) -> None:
    lines: list[str] = []
    lines.append("# LLM 定位 probe B 報告（弱版 patch 選擇器 vs 確定性基準，#26 批4後續）")
    lines.append("")
    lines.append(
        f"產出：`scripts/llm_localize_probe_b.py`，"
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%MZ')}，ollama @ {url}，"
        "temperature 0、90s timeout。**本批只量測，不接生產線。**"
    )
    lines.append("")
    lines.append("## 背景與 probe A 對照")
    lines.append("")
    lines.append(
        "probe A 測最難形式（兩圖同訊息、要 LLM 回跨幀絕對格座標），本機 gemma 系統性"
        "回 (0,0)、無位移訊號→裁決 no-ship。使用者質疑成立：那不能證明「單圖分開問＋"
        "程式組合」不可行，且多圖同訊息本身是方法學混淆。probe B 量測使用者提的形式——"
        "LLM 只當 patch 選擇器（弱版），精度由程式的 TM_CCOEFF_NORMED 模板搜尋承載；"
        "另加不用 LLM 的確定性基準線（auto）與單位遮罩缺口情境（gap）。"
    )
    lines.append("")
    lines.append("## 方法")
    lines.append("")
    lines.append(
        "- 素材：`tests/fixtures/vision/map_scan/ex2if_20260719/` 九幀，批2 真值偏移鏈。"
    )
    lines.append(
        "- **llm**：逐幀單圖單訊息要 LLM 列最多 3 個顯著地標＋百分比位置；每地標在 A 幀"
        f"裁 {2 * PATCH_HALF}px patch（避開格線週期），於 B 幀全幅 TM_CCOEFF_NORMED 搜尋，"
        "多地標投票取偏移共識。LLM 輸入走生產編碼（長邊 1280＋JPEG q85）、搜尋用全解析原圖。"
    )
    lines.append(
        "- **auto**：程式在候選網格上以 變異×幀內唯一性 計分選 top-3 patch，同一搜尋＋投票，"
        "不用 LLM——量測「patch 搜尋層本身」。"
    )
    lines.append(
        "- **gap**：以真值單位位置遮罩（塗成幀中位色）後重跑 llm/auto，量測純地形能否扛定位。"
    )
    lines.append(
        f"- 護欄沿用生產值：patch std 下限 {LLM_PATCH_MIN_STD}（平坦拒判）、"
        f"匹配分數下限 {LLM_PATCH_MIN}。偏移＝各幀 lattice 格索引差（同 probe A 語意）。"
    )
    lines.append("")
    lines.append("## 結果矩陣")
    lines.append("")
    lines.append("| 模式 | 模型 | 摘要 |")
    lines.append("|---|---|---|")
    lines.append(f"| auto | （無） | {_summary(auto_res)} |")
    lines.append(f"| gap-auto | （無） | {_summary(gap_auto_res)} |")
    for model, res in per_model.items():
        lines.append(f"| llm | {model} | {_summary(res)} |")
    for model, res in per_model_gap.items():
        lines.append(f"| gap-llm | {model} | {_summary(res)} |")
    lines.append("")
    lines.append("## 逐對明細")
    lines.append("")
    lines.append("### auto（確定性基準線，無 LLM）")
    lines.append("")
    lines += _table(auto_res, llm=False)
    lines.append("")
    lines.append("### gap-auto（單位遮罩）")
    lines.append("")
    lines += _table(gap_auto_res, llm=False)
    lines.append("")
    for model, res in per_model.items():
        lines.append(f"### llm — {model}")
        lines.append("")
        lines += _table(res, llm=True)
        lines.append("")
    for model, res in per_model_gap.items():
        lines.append(f"### gap-llm — {model}")
        lines.append("")
        lines += _table(res, llm=True)
        lines.append("")
    lines.append("## 結論建議")
    lines.append("")
    lines.append("<!-- 由執行者依實跑數據策展填寫：弱版接縫／純確定性 patch 層／皆不可行 -->")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nreport -> {path}")


# --- driver -------------------------------------------------------------------

def _load(series: Path):
    frames = [cv2.imread(str(series / name)) for name in FRAMES]
    if any(f is None for f in frames):
        raise SystemExit(f"could not read all frames under {series}")
    lattices = [vision.read_map_lattice(f) for f in frames]
    if any(lat is None for lat in lattices):
        missing = [FRAMES[i] for i, lat in enumerate(lattices) if lat is None]
        raise SystemExit(f"no lattice on: {missing}")
    gt = json.loads((series / "ground_truth.json").read_text())
    centers = {
        name: [(int(u["pos"][0]), int(u["pos"][1])) for u in units]
        for name, units in gt["frames"].items()
    }
    return frames, lattices, centers


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--series", type=Path, default=DEFAULT_SERIES)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--models", default="gemma4:latest,gemma3:27b")
    ap.add_argument("--modes", default="auto,gap-auto,llm,gap-llm")
    ap.add_argument("--timeout", type=float, default=90.0)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    modes = {m.strip() for m in args.modes.split(",") if m.strip()}
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    pairs = sorted(TRUTH)

    frames, lattices, centers = _load(args.series)
    masks = [build_unit_mask(f.shape, centers.get(FRAMES[i], [])) for i, f in enumerate(frames)]
    masked = [apply_mask(f, masks[i]) for i, f in enumerate(frames)]

    auto_res, gap_auto_res = [], []
    if "auto" in modes:
        print("== auto ==")
        for a, b in pairs:
            r = run_pair_auto(frames[a - 1], frames[b - 1], lattices[a - 1], lattices[b - 1], (a, b))
            print(f"  auto pt{a}->pt{b} {r.verdict} got={r.offset} err={r.error} "
                  f"votes={r.votes}/{r.total} score={r.score:.2f}")
            auto_res.append(r)
    if "gap-auto" in modes:
        print("== gap-auto ==")
        for a, b in pairs:
            r = run_pair_auto(masked[a - 1], masked[b - 1], lattices[a - 1], lattices[b - 1],
                              (a, b), mask=masks[a - 1])
            print(f"  gap-auto pt{a}->pt{b} {r.verdict} got={r.offset} err={r.error} "
                  f"votes={r.votes}/{r.total} score={r.score:.2f}")
            gap_auto_res.append(r)

    per_model, per_model_gap = {}, {}
    for model in models:
        reader = LlmScreenReader(url=args.url, model=model, timeout_s=args.timeout)
        if "llm" in modes:
            print(f"== llm {model} ==")
            cache: dict = {}
            res = []
            for a, b in pairs:
                r = run_pair_llm(reader, frames[a - 1], frames[b - 1], lattices[a - 1],
                                 lattices[b - 1], (a, b), cache)
                print(f"  [{model}] pt{a}->pt{b} {r.verdict} got={r.offset} err={r.error} "
                      f"votes={r.votes}/{r.total} score={r.score:.2f} {r.latency:.1f}s")
                res.append(r)
            per_model[model] = res
        if "gap-llm" in modes:
            print(f"== gap-llm {model} ==")
            cache = {}
            res = []
            for a, b in pairs:
                r = run_pair_llm(reader, masked[a - 1], masked[b - 1], lattices[a - 1],
                                 lattices[b - 1], (a, b), cache)
                print(f"  [gap {model}] pt{a}->pt{b} {r.verdict} got={r.offset} err={r.error} "
                      f"votes={r.votes}/{r.total} score={r.score:.2f} {r.latency:.1f}s")
                res.append(r)
            per_model_gap[model] = res

    write_report(args.out, args.url, auto_res, gap_auto_res, per_model, per_model_gap)


if __name__ == "__main__":
    main()
