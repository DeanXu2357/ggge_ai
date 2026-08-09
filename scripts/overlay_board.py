"""把一幀的盤面解讀畫回原圖：認得的空格畫正方形、有單位的格畫圈、沒認出來的不畫。

外掛的觀察工具，不改任何既有邏輯——格線、終止邊、單位目擊、逐格四態全部走
`runtime/board.py` 與 `runtime/coverage.py` 現行的函式，這裡只負責把回傳畫出來。

    uv run python scripts/overlay_board.py <png> [<png> ...] [--out-dir DIR]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ggge_ai.runtime import board, coverage  # noqa: E402

EMPTY_COLOUR = (0, 255, 0)
UNIT_COLOUR = (0, 165, 255)
SIGHTING_COLOUR = (255, 0, 255)
SPAN_COLOUR = (255, 255, 0)


def interpret(frame: np.ndarray) -> tuple[coverage.KnowledgeMap | None, coverage.FrameView, Any]:
    """走一次程式現行的盤面解讀，回傳它的知識圖、畫面觀測與格線覆蓋。"""
    span = board.read_span(frame)
    found = board.find_lattice_band(frame)
    view = coverage.Survey()._view(frame, (0.0, 0.0))
    if span is None or found is None:
        return (None, view, span)
    grid = coverage.WorldGrid.anchor(found[0], found[1])
    if grid is None:
        return (None, view, span)
    chart = coverage.KnowledgeMap(grid=grid)
    chart.absorb(view)
    return (chart, view, span)


def draw(frame: np.ndarray, chart: coverage.KnowledgeMap | None, view: coverage.FrameView, span: Any) -> np.ndarray:
    canvas = frame.copy()
    if span is not None:
        x, y, w, h = span.box
        cv2.rectangle(canvas, (int(x), int(y)), (int(x + w), int(y + h)), SPAN_COLOUR, 2)
        for side in sorted(span.edges):
            cv2.putText(canvas, f"edge:{side}", (int(x), int(y) - 8), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, SPAN_COLOUR, 2)
    for sighting in view.units:
        cv2.drawMarker(canvas, (int(sighting.point[0]), int(sighting.point[1])), SIGHTING_COLOUR,
                       cv2.MARKER_TILTED_CROSS, 26, 2)
    if chart is None:
        return canvas
    for cell, known in sorted(chart.state.items()):
        x0, y0, x1, y1 = chart.grid.box_of(cell)
        if known is coverage.Knowledge.UNIT:
            cx, cy = chart.grid.centre_of(cell)
            radius = int(min(x1 - x0, y1 - y0) * 0.42)
            cv2.circle(canvas, (int(cx), int(cy)), radius, UNIT_COLOUR, 3)
        elif known is coverage.Knowledge.EMPTY:
            cv2.rectangle(canvas, (int(x0) + 3, int(y0) + 3), (int(x1) - 3, int(y1) - 3),
                          EMPTY_COLOUR, 2)
    return canvas


def report(path: Path, chart: coverage.KnowledgeMap | None, view: coverage.FrameView, span: Any) -> None:
    print(f"\n=== {path.name} ===")
    if span is None:
        print("  read_span → None（這一幀讀不出格線，一格都不畫）")
    else:
        print(f"  read_span → 框{span.box} 終止邊{sorted(span.edges) or '無'} "
              f"縱線{len(span.lattice.cols)}條 橫線{len(span.lattice.rows)}條")
    print(f"  find_sightings → {len(view.units)} 個目擊")
    for sighting in view.units:
        print(f"      {sighting.point} hint={sighting.hint}")
    if chart is None:
        print("  無世界格網，逐格四態無從產生")
        return
    census = chart.census()
    print(f"  逐格四態 → 空格(正方形) {census[coverage.Knowledge.EMPTY.value]} "
          f"／有單位(圈) {census[coverage.Knowledge.UNIT.value]}")
    for cell, known in sorted(chart.state.items()):
        if known is coverage.Knowledge.UNIT:
            print(f"      單位格 {cell} 中心 {tuple(round(v) for v in chart.grid.centre_of(cell))}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frames", nargs="+", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("assets/screenshots"))
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for path in args.frames:
        frame = cv2.imread(str(path))
        if frame is None:
            print(f"讀不到 {path}")
            continue
        chart, view, span = interpret(frame)
        report(path, chart, view, span)
        out = args.out_dir / f"{path.stem}-overlay.png"
        cv2.imwrite(str(out), draw(frame, chart, view, span))
        print(f"  → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
