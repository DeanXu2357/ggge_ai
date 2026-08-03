"""把 `board.read_lattice` 的回傳畫在原圖上：偵測到的每一條縱線與橫線。

外掛的觀察工具，不改既有邏輯。取樣窗預設是 `board.GRID_REGION`（`read_lattice`
的預設值），`--region` 可改成別的窗做對照。

    uv run python scripts/overlay_lattice.py <png> [--region grid|map|screen]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ggge_ai.runtime import board  # noqa: E402

LINE_COLOUR = (0, 255, 255)
WINDOW_COLOUR = (255, 128, 0)
TEXT_COLOUR = (255, 255, 255)

REGIONS = {
    "grid": board.GRID_REGION,
    "map": board.MAP_REGION,
    "screen": (0, 0, 2340, 1080),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frames", nargs="+", type=Path)
    parser.add_argument("--region", choices=sorted(REGIONS), default="grid")
    parser.add_argument("--out-dir", type=Path, default=Path("assets/screenshots"))
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    region = REGIONS[args.region]
    x, y, w, h = region

    for path in args.frames:
        frame = cv2.imread(str(path))
        if frame is None:
            print(f"讀不到 {path}")
            continue
        lattice = board.read_lattice(frame, region)
        canvas = frame.copy()
        cv2.rectangle(canvas, (x, y), (x + w, y + h), WINDOW_COLOUR, 2)
        cv2.putText(canvas, f"sample window {args.region} {region}", (x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, WINDOW_COLOUR, 2)
        if lattice is None:
            note = "read_lattice -> None"
            print(f"{path.name}: read_lattice({args.region}) → None")
        else:
            for col in lattice.cols:
                cv2.line(canvas, (int(col), y), (int(col), y + h), LINE_COLOUR, 2)
            for row in lattice.rows:
                cv2.line(canvas, (x, int(row)), (x + w, int(row)), LINE_COLOUR, 2)
            note = f"read_lattice -> {len(lattice.cols)} cols / {len(lattice.rows)} rows"
            print(f"{path.name}: read_lattice({args.region}) → "
                  f"縱線 {lattice.cols} 橫線 {lattice.rows}")
        cv2.putText(canvas, note, (x, y + h + 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, TEXT_COLOUR, 2)
        out = args.out_dir / f"{path.stem}-lattice-{args.region}.png"
        cv2.imwrite(str(out), canvas)
        print(f"  → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
