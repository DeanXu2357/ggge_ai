"""Build the page where the user rules, frame by frame, whether an interpreter element is present.

Usage: uv run python scripts/build_element_label_page.py data/labeled <template html> <out dir>

The page shows the area around the element on every labeled frame, ordered by the
element score, without the score. The full frames go to <out dir>/full/.
"""

import base64
import json
import sys
from pathlib import Path

import cv2

from ggge_ai_2.interpreter.elements.turn_box import TURN_BOX_REGION, turn_box_white_share

CONTEXT_REGION = (0.0, 0.0, 0.26, 0.15)
CONTEXT_SCALE = 0.8
FULL_SIZE = (1170, 540)


def pixels(region, w, h):
    left, top, right, bottom = region
    return int(left * w), int(top * h), int(right * w), int(bottom * h)


def jpeg(image, quality):
    return cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()


def context(image):
    h, w = image.shape[:2]
    x0, y0, x1, y1 = pixels(CONTEXT_REGION, w, h)
    out = image[y0:y1, x0:x1].copy()
    bx0, by0, bx1, by1 = pixels(TURN_BOX_REGION, w, h)
    cv2.rectangle(out, (bx0 - x0 - 4, by0 - y0 - 4), (bx1 - x0 + 3, by1 - y0 + 3), (0, 220, 255), 2)
    out = cv2.resize(out, None, fx=CONTEXT_SCALE, fy=CONTEXT_SCALE, interpolation=cv2.INTER_AREA)
    return base64.b64encode(jpeg(out, 82)).decode()


def main(labeled: Path, template: Path, out: Path) -> None:
    rows = [
        json.loads(line)
        for line in (labeled / "cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    (out / "full").mkdir(parents=True, exist_ok=True)
    cases = []
    for row in rows:
        image = cv2.imread(str(labeled / "frames" / row["file"]))
        assert image is not None, row["id"]
        (out / "full" / f"{row['id']}.jpg").write_bytes(
            jpeg(cv2.resize(image, FULL_SIZE, interpolation=cv2.INTER_AREA), 78)
        )
        cases.append(
            {
                "id": row["id"],
                "screen": row["screen"],
                "auto": row["auto"],
                "power_save": row["power_save"],
                "transition": row["transition"],
                "score": turn_box_white_share(image),
                "crop": context(image),
            }
        )
    cases.sort(key=lambda c: (-c["score"], c["id"]))
    for rank, case in enumerate(cases):
        case["rank"] = rank
        del case["score"]
    page = template.read_text(encoding="utf-8").replace(
        "/*CASES*/[]", json.dumps(cases, ensure_ascii=False)
    )
    (out / "index.html").write_text(page, encoding="utf-8")
    print(out / "index.html", (out / "index.html").stat().st_size, len(cases))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
