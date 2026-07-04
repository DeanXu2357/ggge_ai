"""Crop a template from a screenshot and register it in the manifest.

usage:
  # 畫面錨點（用於畫面分類）
  uv run python scripts/crop.py assets/screenshots/x.png --anchor main_menu

  # 元素（按鈕等，--screen 標記它屬於哪個畫面）
  uv run python scripts/crop.py assets/screenshots/x.png --element btn_battle --screen main_menu

  # 免 GUI：直接給座標
  uv run python scripts/crop.py x.png --anchor main_menu --box 40,2200,300,100

未給 --box 時開啟 OpenCV 視窗以滑鼠框選（Enter 確認、c 取消）。
search_region 預設為裁切框外擴 --margin（預設 40px），比對時只搜尋該區域。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from ggge_ai.vision.manifest import TemplateEntry, TemplateManifest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

TEMPLATE_ROOT = PROJECT_ROOT / "assets" / "templates"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("screenshot", type=Path)
    kind = parser.add_mutually_exclusive_group(required=True)
    kind.add_argument("--anchor", help="register as screen anchor with this ScreenId")
    kind.add_argument("--element", help="register as element with this id")
    parser.add_argument("--screen", help="which screen the element belongs to")
    parser.add_argument("--box", help="x,y,w,h to skip interactive selection")
    parser.add_argument("--margin", type=int, default=40, help="search region margin in px")
    parser.add_argument("--no-search-region", action="store_true")
    return parser.parse_args()


def select_box(img, args) -> tuple[int, int, int, int]:
    if args.box:
        x, y, w, h = (int(v) for v in args.box.split(","))
        return x, y, w, h
    box = cv2.selectROI("crop (Enter=confirm, c=cancel)", img, showCrosshair=True)
    cv2.destroyAllWindows()
    if box[2] == 0 or box[3] == 0:
        raise SystemExit("selection cancelled")
    return box


def main() -> None:
    args = parse_args()
    img = cv2.imread(str(args.screenshot))
    if img is None:
        raise SystemExit(f"cannot read {args.screenshot}")

    x, y, w, h = select_box(img, args)
    crop = img[y : y + h, x : x + w]

    if args.anchor:
        subdir, entry_id = "screens", args.anchor
    else:
        subdir, entry_id = "elements", args.element

    rel_file = f"{subdir}/{entry_id}.png"
    out_path = TEMPLATE_ROOT / rel_file
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), crop)

    search_region = None
    if not args.no_search_region:
        ih, iw = img.shape[:2]
        m = args.margin
        sx, sy = max(0, x - m), max(0, y - m)
        search_region = (sx, sy, min(iw - sx, w + 2 * m), min(ih - sy, h + 2 * m))

    manifest = TemplateManifest.load(TEMPLATE_ROOT)
    entry = TemplateEntry(
        id=entry_id,
        file=rel_file,
        search_region=search_region,
        screen=args.screen if args.element else None,
    )
    if args.anchor:
        manifest.screens[entry_id] = entry
    else:
        manifest.elements[entry_id] = entry
    manifest.save()

    print(f"saved {out_path} box=({x},{y},{w},{h}) search_region={search_region}")
    print(f"manifest updated: {manifest.path}")


if __name__ == "__main__":
    main()
