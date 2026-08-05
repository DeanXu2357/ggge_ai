"""候選過濾的漏報評估：拿一個全格點完掃 run 當真值，離線重跑候選檢測。

go/no-go 工具——`--filter-mode candidates` 上實機當預設之前，總召回必須是
100%：漏一台就是那一格被推斷成空，帳本記進一筆假事實，而假帳沒有下游可以救。
誤報只是多點一次，所以報表把兩者分開看。

真值來源＝run 裡每一筆點擊裁決（sweep.jsonl 的 verdict 事件），窗幀＝window 事件
指到的 frames/ 檔。舊 run 的 window 事件沒有 frame 欄位，評不了，要重跑一輪
`--filter-mode full` 產真值。

評不到的窗一律擋住 GO，但原因要分得開：`no_frame`＝流水帳沒記幀路徑（舊 run），
`frame_unreadable`＝路徑記了但檔案讀不出來。後者多半是拿還在被 rotate_runs 壓縮
／刪除的 run 目錄來評——先解開 tar.gz 再評。

usage:
  uv run python scripts/eval_candidate_recall.py data/runs/20260805-003753
  uv run python scripts/eval_candidate_recall.py <run> --halo 1.0 --min-count 60
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from ggge_ai.runtime import sweep
from ggge_ai.runtime.coverage import WorldGrid

UNITS: tuple[str, ...] = (sweep.ENEMY, sweep.ALLY)

Detector = Callable[["Window"], "frozenset[sweep.Cell] | str"]


@dataclass(frozen=True)
class Window:
    index: int
    offset: sweep.Point
    bounds: tuple[sweep.Cell, sweep.Cell]
    frame: str | None


@dataclass
class WindowScore:
    window: Window
    units: tuple[sweep.Cell, ...] = ()
    candidates: frozenset[sweep.Cell] = frozenset()
    missed: tuple[sweep.Cell, ...] = ()
    false_positives: tuple[sweep.Cell, ...] = ()
    skipped: str | None = None

    @property
    def hits(self) -> int:
        return len(self.units) - len(self.missed)

    @property
    def recall(self) -> float | None:
        return None if not self.units else self.hits / len(self.units)


@dataclass
class Report:
    scores: list[WindowScore] = field(default_factory=list)

    @property
    def units(self) -> int:
        return sum(len(score.units) for score in self.scores)

    @property
    def missed(self) -> int:
        return sum(len(score.missed) for score in self.scores)

    @property
    def false_positives(self) -> int:
        return sum(len(score.false_positives) for score in self.scores)

    @property
    def skipped(self) -> int:
        return sum(1 for score in self.scores if score.skipped)

    @property
    def recall(self) -> float | None:
        return None if not self.units else (self.units - self.missed) / self.units

    @property
    def go(self) -> bool:
        """評不到的窗不算過：那一窗的漏報只是沒被看見，不是不存在。"""
        return bool(self.units) and self.missed == 0 and self.skipped == 0


def entries_of(run_dir: Path, name: str = "sweep.jsonl") -> list[dict]:
    path = run_dir / name
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def grid_of(entries: Iterable[dict]) -> WorldGrid | None:
    for entry in entries:
        if entry.get("kind") == "world_anchored":
            phase = entry["phase"]
            pitch = entry["pitch"]
            return WorldGrid((float(phase[0]), float(phase[1])), float(pitch[0]), float(pitch[1]))
    return None


def truth_of(entries: Iterable[dict]) -> dict[sweep.Cell, str]:
    """點擊裁決過的格 → 裁決。UNIT 級事實只認這一份。"""
    out: dict[sweep.Cell, str] = {}
    for entry in entries:
        if entry.get("kind") != "verdict":
            continue
        cell = (int(entry["cell"][0]), int(entry["cell"][1]))
        out[cell] = entry["verdict"]
    return out


def windows_of(entries: Iterable[dict]) -> list[Window]:
    out: list[Window] = []
    for entry in entries:
        if entry.get("kind") != "window" or not entry.get("window"):
            continue
        first, last = entry["window"]
        out.append(
            Window(
                index=len(out),
                offset=(float(entry["offset"][0]), float(entry["offset"][1])),
                bounds=((int(first[0]), int(first[1])), (int(last[0]), int(last[1]))),
                frame=entry.get("frame"),
            )
        )
    return out


def inside(window: Window, cell: sweep.Cell) -> bool:
    (x0, y0), (x1, y1) = window.bounds
    return x0 <= cell[0] <= x1 and y0 <= cell[1] <= y1


def score_window(
    window: Window,
    truth: dict[sweep.Cell, str],
    detect: Detector,
) -> WindowScore:
    units = tuple(sorted(cell for cell, verdict in truth.items()
                         if verdict in UNITS and inside(window, cell)))
    candidates = detect(window)
    if isinstance(candidates, str):
        return WindowScore(window=window, units=units, skipped=candidates)
    missed = tuple(cell for cell in units if cell not in candidates)
    empties = tuple(
        sorted(
            cell
            for cell in candidates
            if truth.get(cell) == sweep.EMPTY and inside(window, cell)
        )
    )
    return WindowScore(
        window=window,
        units=units,
        candidates=candidates,
        missed=missed,
        false_positives=empties,
    )


def detector(
    run_dir: Path, grid: WorldGrid, *, halo: float, min_count: int, min_dist: float
) -> Detector:
    def detect(window: Window) -> frozenset[sweep.Cell] | str:
        if window.frame is None:
            return "no_frame"
        image = cv2.imread(str(run_dir / window.frame), cv2.IMREAD_COLOR)
        if image is None:
            return "frame_unreadable"
        points = sweep.candidate_points(
            np.asarray(image), min_count=min_count, min_dist=min_dist
        )
        return sweep.candidate_cells(grid, window.offset, points, halo=halo)

    return detect


def evaluate(
    windows: Sequence[Window],
    truth: dict[sweep.Cell, str],
    detect: Detector,
) -> Report:
    return Report([score_window(window, truth, detect) for window in windows])


def render(report: Report, run_dir: Path) -> str:
    lines = [f"run: {run_dir}", ""]
    for score in report.scores:
        window = score.window
        head = (
            f"window {window.index:>2} offset=({window.offset[0]:.0f},{window.offset[1]:.0f}) "
            f"bounds={window.bounds[0]}-{window.bounds[1]}"
        )
        if score.skipped:
            lines.append(f"{head}  skipped={score.skipped} frame={window.frame}")
            continue
        recall = "n/a" if score.recall is None else f"{score.recall:.0%}"
        lines.append(
            f"{head}  units={len(score.units)} hit={score.hits} recall={recall} "
            f"candidates={len(score.candidates)} false_positives={len(score.false_positives)}"
        )
        for cell in score.missed:
            lines.append(f"    MISS cell={cell} frame={window.frame}")
    total = "n/a" if report.recall is None else f"{report.recall:.2%}"
    lines += [
        "",
        f"units={report.units} missed={report.missed} recall={total} "
        f"false_positives={report.false_positives} skipped_windows={report.skipped}",
        "GO：召回 100%" if report.go else "NO-GO：有漏報、有評不到的窗，或根本沒有真值",
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--journal", default="sweep.jsonl")
    parser.add_argument("--halo", type=float, default=sweep.CANDIDATE_HALO_PITCH)
    parser.add_argument("--min-count", type=int, default=sweep.CANDIDATE_MIN_COUNT)
    parser.add_argument("--min-dist", type=float, default=sweep.CANDIDATE_MIN_DIST)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    entries = entries_of(args.run_dir, args.journal)
    grid = grid_of(entries)
    if grid is None:
        print("這個 run 沒有 world_anchored 事件：沒有世界格網就對不上真值")
        return 1
    windows = windows_of(entries)
    if not windows:
        print("這個 run 沒有 window 事件")
        return 1
    report = evaluate(
        windows,
        truth_of(entries),
        detector(
            args.run_dir,
            grid,
            halo=args.halo,
            min_count=args.min_count,
            min_dist=args.min_dist,
        ),
    )
    print(render(report, args.run_dir))
    return 0 if report.go else 1


if __name__ == "__main__":
    sys.exit(main())
