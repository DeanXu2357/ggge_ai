"""Replay a captured map-scan fixture series through the offline
stitcher and print the would-be sim sync result for human comparison.

usage: uv run python scripts/replay_map_scan.py [series_dir] [--out composite.png]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from ggge_ai.battle import map_stitch, vision

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SERIES = PROJECT_ROOT / "tests" / "fixtures" / "vision" / "map_scan" / "ex2if_20260719"

HINT_KEYS = ("up", "down", "left", "right")


def hint_from_label(label: str) -> str | None:
    for key in HINT_KEYS:
        if f"pan_{key}" in label:
            return key
    return None


def load_series(series_dir: Path) -> tuple[list[np.ndarray], list[dict]]:
    manifest = json.loads((series_dir / "manifest.json").read_text(encoding="utf-8"))
    entries = sorted(manifest["frames"], key=lambda f: f["seq"])
    frames = []
    for entry in entries:
        frame = cv2.imread(str(series_dir / entry["image"]))
        if frame is None:
            raise SystemExit(f"unreadable frame: {entry['image']}")
        frames.append(frame)
    return frames, entries


def unit_cells(
    result: map_stitch.StitchResult,
) -> list[tuple[str, map_stitch.PoolUnit, tuple[int, int] | None]]:
    units = sorted(result.units, key=lambda u: (u.pos[1], u.pos[0]))
    if not units:
        return []
    origin = (min(u.pos[0] for u in units), min(u.pos[1] for u in units))
    out = []
    for i, u in enumerate(units, start=1):
        cell = None
        if result.col_pitch and result.row_pitch:
            cell = (
                round((u.pos[0] - origin[0]) / result.col_pitch),
                round((u.pos[1] - origin[1]) / result.row_pitch),
            )
        out.append((f"u{i:02d}", u, cell))
    return out


def render_composite(
    frames: list[np.ndarray],
    result: map_stitch.StitchResult,
    path: Path,
) -> None:
    x0, y0, w, h = vision.UNIT_DENSITY_REGION
    cams = [p.camera for p in result.placements]
    min_x = min(c[0] for c in cams) + x0
    min_y = min(c[1] for c in cams) + y0
    max_x = max(c[0] for c in cams) + x0 + w
    max_y = max(c[1] for c in cams) + y0 + h
    canvas = np.zeros((int(max_y - min_y) + 1, int(max_x - min_x) + 1, 3), np.uint8)
    for frame, placement in zip(frames, result.placements):
        crop = frame[y0 : y0 + h, x0 : x0 + w]
        px = int(placement.camera[0] + x0 - min_x)
        py = int(placement.camera[1] + y0 - min_y)
        canvas[py : py + h, px : px + w] = crop
    for label, unit, _ in unit_cells(result):
        cx, cy = int(unit.pos[0] - min_x), int(unit.pos[1] - min_y)
        cv2.circle(canvas, (cx, cy), 46, (0, 0, 255), 3)
        cv2.putText(
            canvas, label, (cx - 30, cy - 54), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 255), 3
        )
    cv2.imwrite(str(path), canvas)
    print(f"composite saved: {path} ({canvas.shape[1]}x{canvas.shape[0]})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("series_dir", nargs="?", default=str(DEFAULT_SERIES))
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    series_dir = Path(args.series_dir)

    frames, entries = load_series(series_dir)
    hints = [hint_from_label(e["label"]) for e in entries]
    result = map_stitch.stitch(frames, hints=hints)

    print("frame placements:")
    for placement, entry in zip(result.placements, entries):
        cx, cy = placement.camera
        print(
            f"  #{entry['seq']:02d} {entry['label']:<22} camera ({cx:+8.1f}, {cy:+8.1f})"
            f"  method {placement.method:<7} support {placement.support:2d}"
            f"  arcs {placement.arcs}"
        )
    print(f"static screen points dropped as HUD: {len(result.static_screen)}")
    for p in result.static_screen:
        print(f"  screen ({p[0]:7.1f}, {p[1]:7.1f})")
    pitch_c = f"{result.col_pitch:.1f}" if result.col_pitch else "?"
    pitch_r = f"{result.row_pitch:.1f}" if result.row_pitch else "?"
    print(f"grid pitch: col {pitch_c}px, row {pitch_r}px (mean over readable lattices)")

    cells = unit_cells(result)
    print(f"units ({len(cells)}), row-major, world origin = min corner:")
    for label, unit, cell in cells:
        cell_text = f"cell ({cell[0]:2d},{cell[1]:2d})" if cell else "cell ?"
        frames_text = ",".join(str(i + 1) for i in unit.frames)
        print(
            f"  {label}  world ({unit.pos[0]:+8.1f}, {unit.pos[1]:+8.1f})  {cell_text}"
            f"  seen x{unit.support} (frames {frames_text})  spread {unit.spread:5.1f}px"
        )

    if args.out:
        render_composite(frames, result, Path(args.out))


if __name__ == "__main__":
    main()
