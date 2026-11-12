"""Make the terrain icon templates from the user's rulings of the tap mark.

Usage: uv run python scripts/extract_terrain_templates.py data/labeled assets/templates/mapparser/terrain

Each ruled terrain box gives one gray crop of ICON_SIZE for each icon, at the icon
slots of 'tap_mark.py' from the tip that the parser finds. The template of a terrain
is the mean of its crops.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

from ggge_ai_2.mapparser.border import read_border
from ggge_ai_2.mapparser.hud import hud_rects
from ggge_ai_2.mapparser.lattice import read_lattice
from ggge_ai_2.mapparser.region import read_region
from ggge_ai_2.mapparser.tap_mark import ICON_CENTER_Y, ICON_PITCH, ICON_SIZE, find_tip
from ggge_ai_2.mapparser.topview import top_view


def main(labeled: Path, out: Path) -> None:
    crops: dict[str, list[np.ndarray]] = defaultdict(list)
    for line in (labeled / "cases.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        mark = row.get("tap_mark")
        if not mark or mark["terrain"] is None:
            continue
        read = cv2.imread(str(labeled / "frames" / row["file"]))
        assert read is not None, row["id"]
        image = np.asarray(read)
        lattice = read_lattice(image)
        assert lattice is not None, row["id"]
        rects = hud_rects(image)
        region = read_region(lattice, rects, read_border(top_view(image, lattice, rects)))
        tip = find_tip(image, lattice, region)
        if tip is None:
            print(f"{row['id']}: no tip, skipped")
            continue
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        count = len(mark["terrain"])
        width, height = ICON_SIZE
        for slot, terrain in enumerate(mark["terrain"]):
            x = tip[0] + (slot - (count - 1) / 2) * ICON_PITCH
            y = tip[1] + ICON_CENTER_Y
            left, top = int(round(x - width / 2)), int(round(y - height / 2))
            crops[terrain].append(gray[top : top + height, left : left + width].astype(np.float32))
    out.mkdir(parents=True, exist_ok=True)
    for terrain, items in sorted(crops.items()):
        cv2.imwrite(str(out / f"{terrain}.png"), np.rint(np.mean(items, axis=0)).astype(np.uint8))
        print(f"{terrain}: {len(items)} crops")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
