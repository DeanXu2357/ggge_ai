"""離線重放：把已封存的窗幀重新量一次格線，比較「等距純平移」與「單應性投影」
兩個模型在**位置空間**的殘差。

只讀資料、不碰裝置、不改任何運行時行為。素材＝`data/runs/<run>/` 或
`data/runs/<run>.tar.gz` 裡的 window 事件幀，鏡位取那筆事件記的 offset。

三個模型並排：
  old     等距格網＋純平移（現行 `WorldGrid` 的幾何假設）
  new     `runtime/projection` 的單應性，格距仍取 `WorldGrid` 錨定當時的值
  scaled  同 new，但格距換成本 run 逐幀量出來的中位（診斷用：把「模型形狀錯」
          與「錨定的格距量錯」分開；scaled 不是提案，正式流程沒有這個數）

另外附一節 shadow：完全照 `SweepRun.aimed` 的取樣路徑（`find_lattice_band` 的線位）
算 `aim_drift`（舊）與 `projection.shadow_drift`（新），用來預估影子入帳會記到什麼。

usage:
  uv run python scripts/validate_projection.py                       # 兩批全跑
  uv run python scripts/validate_projection.py --limit 20            # 冒煙
  uv run python scripts/validate_projection.py data/runs/20260809-152222

輸出：總表印到 stdout，明細存
`docs/reviews/projection-shadow/replay-residuals.json`。
"""

from __future__ import annotations

import argparse
import json
import sys
import tarfile
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from ggge_ai.runtime import board, projection, sweep
from ggge_ai.runtime.coverage import WorldGrid

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS = (
    PROJECT_ROOT / "data" / "runs" / "20260809-152222",
    PROJECT_ROOT / "data" / "runs" / "20260809-133305.tar.gz",
)
DEFAULT_OUT = PROJECT_ROOT / "docs" / "reviews" / "projection-shadow" / "replay-residuals.json"

# 量測窗：左避按鈕欄、上避 AUTO 列、下停在訊息條之上（同 perspective-measurement 的窗）。
MEAS_X = (500, 2280)
MEAS_Y = (250, 960)
# 縱線是斜的，全高投影會把線攤成寬丘——逐帶各自投影，線位就是該帶中線上的 x。
BANDS: tuple[tuple[int, int], ...] = ((250, 450), (450, 700), (700, 870))
ROW_SPACING = 45
COL_SPACING = 55
# 脊列清理的間距帶：模型格距的 ±25%。假脊（單位精靈、HUD 邊）進不了連續段。
PITCH_SLACK = 0.25
# 一條線要能定出格距的最少線數。
MIN_LINES = 6
# 驗收線：新模型全帶 p95 要在這個格數以下。
ACCEPT_P95 = 0.10
# harness 自檢：舊模型應落在量測報告的量級（0.1-0.5 格），太漂亮＝這支腳本自己算錯。
SANE_OLD = (0.05, 1.0)

ENDORSED_SOURCES = ("edge", "mixed")
MODELS = ("old", "new", "scaled")


@dataclass(frozen=True)
class Reading:
    """一幀的量測。`cols` 逐帶各一組（帶中線高度上的 x）；`lattice` 是運行時看得到的那組。"""

    rows: tuple[int, ...]
    cols: dict[tuple[int, int], tuple[int, ...]]
    lattice: board.Lattice | None
    band: tuple[int, int, int, int] | None


@dataclass
class Sample:
    """一條線的一次比對。`pitch` ＝該處的模型格距，px 換格用它。"""

    band: tuple[int, int]
    axis: str
    model: str
    px: float
    pitch: float


@dataclass
class Bucket:
    px: list[float] = field(default_factory=list)
    grid: list[float] = field(default_factory=list)


def read_frame(frame: np.ndarray) -> Reading:
    """刻意繞過 `_trim`／`_plausible` 兩個均勻性閘：它們會整幀丟掉「間距不均勻」的
    證據，而那正是要量的東西。清理另外用連續段做（見 `_clean`）。
    """
    patch = frame[MEAS_Y[0] : MEAS_Y[1], MEAS_X[0] : MEAS_X[1]]
    highpass = board._highpass(patch)
    rows = tuple(board._ridges(highpass.mean(axis=1), MEAS_Y[0], ROW_SPACING))
    cols: dict[tuple[int, int], tuple[int, ...]] = {}
    for low, high in BANDS:
        slab = highpass[low - MEAS_Y[0] : high - MEAS_Y[0], :]
        if slab.shape[0] < 20:
            continue
        cols[(low, high)] = tuple(board._ridges(slab.mean(axis=0), MEAS_X[0], COL_SPACING))
    found = board.find_lattice_band(frame)
    return Reading(rows, cols, None if found is None else found[0], None if found is None else found[1])


def _clean(lines: Sequence[int], pitch: float) -> tuple[float, ...]:
    low = int(pitch * (1.0 - PITCH_SLACK))
    high = int(pitch * (1.0 + PITCH_SLACK))
    return tuple(float(value) for value in board._longest_run(lines, low, high))


def _pitch_of(lines: Sequence[float]) -> float | None:
    """線位對序號的最小平方斜率＝次像素格距（整數線位取中位差只有 1px 解析度）。"""
    if len(lines) < MIN_LINES:
        return None
    return float(np.polyfit(np.arange(len(lines)), np.asarray(lines, dtype=float), 1)[0])


def measured_pitches(
    reading: Reading, grid: WorldGrid, shape: projection.Projection
) -> tuple[float | None, float | None]:
    """這一幀量到的格距，換算到世界座標的參考高度上（跟 `WorldGrid` 同一把尺）。"""
    heights: list[float] = []
    pitches: list[float] = []
    for band, raw in reading.cols.items():
        pitch = _pitch_of(_clean(raw, grid.col_pitch))
        if pitch is not None:
            heights.append((band[0] + band[1]) / 2.0)
            pitches.append(pitch)
    col = None
    if len(heights) >= 2:
        fit = np.polyfit(heights, pitches, 1)
        col = float(np.polyval(fit, shape.grid_ref_y))
    rows = _clean(reading.rows, grid.row_pitch)
    row = None
    if len(rows) >= 3:
        centres = [(a + b) / 2.0 for a, b in zip(rows, rows[1:], strict=False)]
        gaps = [b - a for a, b in zip(rows, rows[1:], strict=False)]
        if centres[0] <= shape.grid_ref_y <= centres[-1]:
            row = float(np.interp(shape.grid_ref_y, centres, gaps))
    return (col, row)


def _flat_lines(
    phase: float, pitch: float, offset: float, span: tuple[float, float]
) -> tuple[float, ...]:
    """舊模型的期望線位：等距、純平移，與螢幕位置無關。"""
    return tuple(
        line - offset
        for line in projection.lines_between(phase, pitch, span[0] + offset, span[1] + offset)
    )


def _row_pitch_at(grid: WorldGrid, y: float, shape: projection.Projection) -> float:
    scale = shape.row_scale(y) / shape.row_scale(shape.grid_ref_y)
    return grid.row_pitch * scale * scale


def _col_pitch_at(grid: WorldGrid, y: float, shape: projection.Projection) -> float:
    return grid.col_pitch * shape.col_scale(y) / shape.col_scale(shape.grid_ref_y)


def _band_of(y: float) -> tuple[int, int] | None:
    for low, high in BANDS:
        if low <= y < high:
            return (low, high)
    return None


def compare(
    reading: Reading,
    grids: dict[str, WorldGrid],
    offset: tuple[float, float],
    shape: projection.Projection,
) -> list[Sample]:
    samples: list[Sample] = []
    base = grids["new"]
    rows = _clean(reading.rows, base.row_pitch)
    for model, grid in grids.items():
        if not rows:
            break
        # 坑：預測窗各外擴一格。貼著窗邊的實測線沒有預測線可配就會配到窗內最後一條，
        # 留下一整格的假殘差（p95 因此虛胖到 0.95 格）。
        span = (MEAS_Y[0] - grid.row_pitch, MEAS_Y[1] + grid.row_pitch)
        guess = (
            _flat_lines(grid.phase[1], grid.row_pitch, offset[1], span)
            if model == "old"
            else projection.expected_rows(grid, offset, span, projection=shape)
        )
        residual = projection.line_residual(guess, rows)
        for line, value in zip(rows, residual.offsets, strict=True):
            band = _band_of(line)
            if band is not None:
                samples.append(Sample(band, "row", model, value, _row_pitch_at(grid, line, shape)))
    for band, raw in reading.cols.items():
        eval_y = (band[0] + band[1]) / 2.0
        cols = _clean(raw, _col_pitch_at(base, eval_y, shape))
        if not cols:
            continue
        for model, grid in grids.items():
            span = (MEAS_X[0] - grid.col_pitch, MEAS_X[1] + grid.col_pitch)
            guess = (
                _flat_lines(grid.phase[0], grid.col_pitch, offset[0], span)
                if model == "old"
                else projection.expected_columns(grid, offset, eval_y, span, projection=shape)
            )
            residual = projection.line_residual(guess, cols)
            pitch = _col_pitch_at(grid, eval_y, shape)
            for value in residual.offsets:
                samples.append(Sample(band, "col", model, value, pitch))
    return samples


def centred(samples: Sequence[Sample]) -> list[Sample]:
    """每幀每軸每模型准一個世界平移自由度：扣掉該幀的格數中位。

    這一版看的是**模型形狀**對不對；不扣的那一版還含著鏡位本身的誤差與座標系換算的
    常數偏差，兩個要分開看才讀得懂。
    """
    out: list[Sample] = []
    for axis in ("row", "col"):
        for model in MODELS:
            picked = [item for item in samples if item.axis == axis and item.model == model]
            if not picked:
                continue
            shift = float(np.median([item.px / item.pitch for item in picked]))
            out.extend(
                Sample(item.band, item.axis, item.model, item.px - shift * item.pitch, item.pitch)
                for item in picked
            )
    return out


def summarise(buckets: dict[tuple, Bucket]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for key, bucket in buckets.items():
        px = np.abs(np.asarray(bucket.px, dtype=float))
        grid = np.abs(np.asarray(bucket.grid, dtype=float))
        if not px.size:
            continue
        out["|".join(str(part) for part in key)] = {
            "n": int(px.size),
            "px": {
                "median": round(float(np.median(px)), 2),
                "p95": round(float(np.percentile(px, 95)), 2),
                "max": round(float(px.max()), 2),
            },
            "grid": {
                "median": round(float(np.median(grid)), 4),
                "p95": round(float(np.percentile(grid, 95)), 4),
                "max": round(float(grid.max()), 4),
            },
        }
    return out


def shadow_pair(
    reading: Reading, grid: WorldGrid, offset: tuple[float, float], shape: projection.Projection
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """照 `SweepRun.aimed` 的取樣路徑算兩個模型的漂移，預估影子入帳會記到什麼。"""
    if reading.lattice is None or reading.band is None:
        return None
    lattice = reading.lattice
    pitch = (lattice.col_pitch, lattice.row_pitch)
    if pitch[0] <= 0 or pitch[1] <= 0:
        return None
    phase = (lattice.cols[0] % pitch[0], lattice.rows[0] % pitch[1])
    old = sweep.aim_drift(phase, grid, offset)
    at = (
        sweep.TAP_REGION[0] + sweep.TAP_REGION[2] / 2.0,
        sweep.TAP_REGION[1] + sweep.TAP_REGION[3] / 2.0,
    )
    new = projection.shadow_drift(lattice, reading.band, grid, offset, at=at, projection=shape)
    return None if new is None else (old, new)


def _journal_grid(entries: Sequence[dict]) -> WorldGrid | None:
    for entry in entries:
        if entry.get("kind") == "world_anchored":
            phase = entry["phase"]
            pitch = entry["pitch"]
            return WorldGrid((float(phase[0]), float(phase[1])), float(pitch[0]), float(pitch[1]))
    return None


def _windows(entries: Sequence[dict]) -> list[dict]:
    """window 事件＋它當下的錨定來源（界線背書的窗要單獨統計）。"""
    out: list[dict] = []
    source: str | None = None
    for entry in entries:
        kind = entry.get("kind")
        if kind in ("anchor_backed", "anchor_unbacked"):
            source = entry.get("source")
        elif kind in ("world_anchored", "rezeroed"):
            source = "edge"
        elif kind == "window" and entry.get("frame"):
            out.append(
                {
                    "seq": entry["seq"],
                    "frame": entry["frame"],
                    "offset": (float(entry["offset"][0]), float(entry["offset"][1])),
                    "endorsed": source in ENDORSED_SOURCES,
                }
            )
    return out


def _load_directory(path: Path, limit: int | None) -> Iterator[tuple[dict, Reading]]:
    entries = [json.loads(line) for line in (path / "sweep.jsonl").open(encoding="utf-8")]
    grid = _journal_grid(entries)
    if grid is None:
        return
    yield ({"grid": grid}, Reading((), {}, None, None))
    for window in _windows(entries)[:limit]:
        frame = cv2.imread(str(path / window["frame"]))
        if frame is not None:
            yield (window, read_frame(frame))


def _load_tar(path: Path, limit: int | None) -> Iterator[tuple[dict, Reading]]:
    """單趟串流：流水帳排在壓縮檔尾端，所以先把每張幀量完再與事件對帳。"""
    readings: dict[str, Reading] = {}
    entries: list[dict] = []
    with tarfile.open(path, "r|gz") as stream:
        for member in stream:
            handle = stream.extractfile(member)
            if handle is None:
                continue
            if member.name.endswith("sweep.jsonl"):
                # 串流 tar 的成員不可 seek，TextIOWrapper 包不上去——整份讀進來再切行。
                entries = [
                    json.loads(line)
                    for line in handle.read().decode("utf-8").splitlines()
                    if line.strip()
                ]
                continue
            if not member.name.endswith(".png"):
                continue
            frame = cv2.imdecode(np.frombuffer(handle.read(), np.uint8), cv2.IMREAD_COLOR)
            if frame is not None:
                readings[Path(member.name).name] = read_frame(frame)
    grid = _journal_grid(entries)
    if grid is None:
        return
    yield ({"grid": grid}, Reading((), {}, None, None))
    for window in _windows(entries)[:limit]:
        found = readings.get(Path(window["frame"]).name)
        if found is not None:
            yield (window, found)


def replay(path: Path, limit: int | None, shape: projection.Projection) -> dict:
    source = _load_tar(path, limit) if path.suffix == ".gz" else _load_directory(path, limit)
    header = next(source, None)
    if header is None:
        return {"run": path.name, "frames": 0, "note": "journal has no world_anchored"}
    grid: WorldGrid = header[0]["grid"]
    frames = [(window, reading) for window, reading in source]
    fitted = [measured_pitches(reading, grid, shape) for _, reading in frames]
    col = [value for value, _ in fitted if value is not None]
    row = [value for _, value in fitted if value is not None]
    scaled = WorldGrid(
        grid.phase,
        float(np.median(col)) if col else grid.col_pitch,
        float(np.median(row)) if row else grid.row_pitch,
    )
    grids = {"old": grid, "new": grid, "scaled": scaled}

    buckets: dict[tuple, Bucket] = {}
    shadows: dict[tuple[str, str], list[float]] = {}
    counted = 0
    endorsed = 0
    for window, reading in frames:
        samples = compare(reading, grids, window["offset"], shape)
        if not samples:
            continue
        counted += 1
        endorsed += bool(window["endorsed"])
        scopes = ("all", "endorsed") if window["endorsed"] else ("all",)
        for variant, group in (("absolute", samples), ("centred", centred(samples))):
            for sample in group:
                for scope in scopes:
                    band = f"{sample.band[0]}-{sample.band[1]}"
                    key = (scope, variant, sample.model, sample.axis, band)
                    bucket = buckets.setdefault(key, Bucket())
                    bucket.px.append(sample.px)
                    bucket.grid.append(sample.px / sample.pitch)
        pair = shadow_pair(reading, grid, window["offset"], shape)
        if pair is not None:
            for model, drift in zip(("old", "new"), pair, strict=True):
                for scope in scopes:
                    shadows.setdefault((scope, model, "dx"), []).append(abs(drift[0]))
                    shadows.setdefault((scope, model, "dy"), []).append(abs(drift[1]))
    return {
        "run": path.name,
        "frames": counted,
        "endorsed_frames": endorsed,
        "grid": {
            "phase": list(grid.phase),
            "col_pitch": grid.col_pitch,
            "row_pitch": grid.row_pitch,
        },
        "replay_pitch": {"col": round(scaled.col_pitch, 2), "row": round(scaled.row_pitch, 2)},
        "bands": summarise(buckets),
        "shadow": {
            "|".join(key): {
                "n": len(values),
                "median": round(float(np.median(values)), 2),
                "p95": round(float(np.percentile(values, 95)), 2),
            }
            for key, values in shadows.items()
        },
    }


def verdict(report: dict, scope: str = "endorsed") -> dict:
    out: dict[str, dict] = {}
    for variant in ("absolute", "centred"):
        worst: dict[str, float] = {}
        for key, stats in report.get("bands", {}).items():
            parts = key.split("|")
            if parts[0] != scope or parts[1] != variant:
                continue
            worst[parts[2]] = max(worst.get(parts[2], 0.0), stats["grid"]["p95"])
        if not worst:
            continue
        out[variant] = {
            **{f"{model}_worst_p95_grid": round(value, 4) for model, value in worst.items()},
            "new_passes": bool(worst.get("new") and worst["new"] < ACCEPT_P95),
            "scaled_passes": bool(worst.get("scaled") and worst["scaled"] < ACCEPT_P95),
            "harness_sane": bool(SANE_OLD[0] <= worst.get("old", 0.0) <= SANE_OLD[1]),
        }
    return out


def _table(report: dict, scope: str, variant: str) -> str:
    head = (
        f"  {'band':<10}{'axis':<5}{'model':<8}{'n':>7}{'med px':>9}{'p95 px':>9}"
        f"{'max px':>9}{'med gu':>9}{'p95 gu':>9}{'max gu':>9}"
    )
    lines = [head]
    for key, stats in sorted(report.get("bands", {}).items()):
        parts = key.split("|")
        if parts[0] != scope or parts[1] != variant:
            continue
        lines.append(
            f"  {parts[4]:<10}{parts[3]:<5}{parts[2]:<8}{stats['n']:>7}"
            f"{stats['px']['median']:>9.2f}{stats['px']['p95']:>9.2f}{stats['px']['max']:>9.2f}"
            f"{stats['grid']['median']:>9.3f}{stats['grid']['p95']:>9.3f}{stats['grid']['max']:>9.3f}"
        )
    return "\n".join(lines)


def report_lines(report: dict) -> str:
    out = [
        f"\n=== {report['run']}  frames={report['frames']} "
        f"endorsed={report.get('endorsed_frames')} "
        f"anchor_pitch={report.get('grid', {}).get('col_pitch')}/"
        f"{report.get('grid', {}).get('row_pitch')} "
        f"replay_pitch={report.get('replay_pitch')} ==="
    ]
    for scope in ("all", "endorsed"):
        for variant in ("absolute", "centred"):
            table = _table(report, scope, variant)
            if table.count("\n"):
                out.append(f"\n-- scope={scope} variant={variant} (gu = 格)")
                out.append(table)
    out.append("\n-- shadow drift |px| (照 SweepRun.aimed 的取樣路徑)")
    out.append(json.dumps(report.get("shadow", {}), indent=2))
    out.append("\n-- verdict (endorsed windows)")
    out.append(json.dumps(report.get("verdict", {}), indent=2))
    return "\n".join(out)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="offline projection replay")
    parser.add_argument("runs", nargs="*", type=Path, default=list(DEFAULT_RUNS))
    parser.add_argument("--limit", type=int, default=None, help="每批只跑前 N 個窗幀（冒煙用）")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    shape = projection.PROJECTION
    reports = []
    for path in args.runs:
        if not path.exists():
            print(f"skip {path}: not found", file=sys.stderr)
            continue
        report = replay(path, args.limit, shape)
        report["verdict"] = verdict(report)
        reports.append(report)
        print(report_lines(report), flush=True)
    payload = {
        "projection": {
            "vp_x": shape.vp_x,
            "col_k": shape.col_k,
            "row_k": shape.row_k,
            "ref_y": shape.ref_y,
            "grid_ref_y": shape.grid_ref_y,
        },
        "accept_p95_grid": ACCEPT_P95,
        "measure_window": {"x": list(MEAS_X), "y": list(MEAS_Y), "bands": [list(b) for b in BANDS]},
        "runs": reports,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
