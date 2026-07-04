"""Run template recognition against a screenshot and print the results.

usage: uv run python scripts/verify_match.py assets/screenshots/x.png
       uv run python scripts/verify_match.py x.png --annotate out.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from ggge_ai.vision.manifest import TemplateManifest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_ROOT = PROJECT_ROOT / "assets" / "templates"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("screenshot", type=Path)
    parser.add_argument("--annotate", type=Path, help="write annotated image here")
    args = parser.parse_args()

    img = cv2.imread(str(args.screenshot))
    if img is None:
        raise SystemExit(f"cannot read {args.screenshot}")

    manifest = TemplateManifest.load(TEMPLATE_ROOT)
    if not manifest.screens and not manifest.elements:
        raise SystemExit("manifest is empty, crop some templates first")
    recognizer = manifest.build_recognizer()

    print("== screen classification ==")
    candidates = recognizer.classify_screen(img)
    for c in candidates[:5]:
        print(f"  {c.screen:20s} {c.confidence:.3f}")

    best_screen = candidates[0].screen if candidates else None
    element_ids = manifest.element_ids_by_screen().get(best_screen, [])
    elements = recognizer.detect_elements(img, element_ids) if element_ids else []
    if elements:
        print(f"== elements on '{best_screen}' ==")
        for e in elements:
            print(f"  {e.id:20s} {e.confidence:.3f} center={e.bbox.center}")

    if args.annotate:
        for e in elements:
            b = e.bbox
            cv2.rectangle(img, (b.x, b.y), (b.x + b.w, b.y + b.h), (0, 255, 0), 3)
            cv2.putText(
                img,
                f"{e.id} {e.confidence:.2f}",
                (b.x, b.y - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )
        cv2.imwrite(str(args.annotate), img)
        print(f"annotated image written to {args.annotate}")


if __name__ == "__main__":
    main()
