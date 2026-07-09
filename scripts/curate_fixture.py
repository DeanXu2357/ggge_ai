"""Curate a real screenshot crop into a vision regression fixture.

usage:
  uv run python scripts/curate_fixture.py assets/screenshots/x.png \
      hp_arc/our_turn_hub_pink_bug --box 150,90,1510,780 \
      --check hp_arc_counts \
      --expect '{"enemies": {"max": 0}, "allies": {"min": 10}, "third_party": {"max": 0}}' \
      --note "..." --xfail "..."

Writes tests/fixtures/vision/<case>.{jpg or png,json}. The crop is stored
at full source resolution so the region's pixels line up with vision.py's
hardcoded absolute-coordinate boxes when test_vision_regression.py pastes
it back onto a blank canvas at --box's origin -- cropping trims file size
without breaking those boxes. Omit --box to store the full frame (needed
when a check's regions span most of the screen).

Default format is JPEG q85 (the #15 frame-dump spec) for template-match
checks, which tolerate compression -- their own code comments measure
score gaps of 0.6-0.8 between positive and negative. Pixel-level color/
shape checks (hp_arc_counts) sit much closer to their decision boundary:
JPEG re-encoding measurably flips blob classification at the edges
(verified 2026-07-09, non-monotonic with quality -- q85/q90/q95 all
produced a phantom blob that q92/q98 didn't). Pass --format png for those.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "vision"
JPEG_QUALITY = 85


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("screenshot", type=Path)
    parser.add_argument("case", help="<category>/<case_name>, e.g. hp_arc/our_turn_hub")
    parser.add_argument("--box", help="x,y,w,h crop in source pixel coordinates")
    parser.add_argument("--check", required=True, help="registry key in test_vision_regression.py")
    parser.add_argument("--expect", required=True, help="JSON-encoded expected value")
    parser.add_argument("--note", default="", help="human note: what this pins and why")
    parser.add_argument("--xfail", default=None, help="if set, marks the case as a known failure")
    parser.add_argument(
        "--format",
        choices=["jpg", "png"],
        default="jpg",
        help="png for pixel-level color/shape checks that JPEG noise can flip (e.g. hp_arc_counts)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    img = cv2.imread(str(args.screenshot))
    if img is None:
        raise SystemExit(f"cannot read {args.screenshot}")
    frame_h, frame_w = img.shape[:2]

    if args.box:
        x, y, w, h = (int(v) for v in args.box.split(","))
        crop = img[y : y + h, x : x + w]
        box = [x, y, w, h]
    else:
        crop = img
        box = [0, 0, frame_w, frame_h]

    out_dir = FIXTURE_ROOT / Path(args.case).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(args.case).name
    img_path = FIXTURE_ROOT / f"{args.case}.{args.format}"
    json_path = FIXTURE_ROOT / f"{args.case}.json"

    params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY] if args.format == "jpg" else []
    ok = cv2.imwrite(str(img_path), crop, params)
    if not ok:
        raise SystemExit(f"failed to write {img_path}")

    annotation = {
        "check": args.check,
        "expect": json.loads(args.expect),
        "box": box,
        "canvas_size": [frame_w, frame_h],
        "image": img_path.name,
        "source": str(args.screenshot),
    }
    if args.note:
        annotation["note"] = args.note
    if args.xfail:
        annotation["xfail_reason"] = args.xfail
    json_path.write_text(json.dumps(annotation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    size_kb = img_path.stat().st_size / 1024
    print(f"wrote {img_path} ({size_kb:.0f} KB) + {json_path.name} [{stem}]")


if __name__ == "__main__":
    main()
