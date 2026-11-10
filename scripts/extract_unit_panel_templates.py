"""Make the templates of the selected unit's panel from the user's rulings.

Usage: uv run python scripts/extract_unit_panel_templates.py data/labeled assets/templates/mapparser/unit_panel

Glyphs: the white glyphs of HP, EN, MP and the 'CHANCE STEP' count of every ruled panel,
averaged for each label. A field whose glyph count differs from its ruled text is skipped.
State words, 'DAMAGE +x%', overlay texts and names: one crop of the first case that
shows each value.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

from ggge_ai_2.mapparser.contract import PilotState
from ggge_ai_2.mapparser.unit_panel import (
    CHANCE_COUNT,
    DAMAGE,
    EN,
    GLYPH_LABELS,
    HP,
    MECH_NAME,
    MP,
    OVERLAY_AREA,
    PILOT_NAME,
    STATE,
    color_mask,
    crop,
    glyph_boxes,
    glyph_image,
    text_crop,
    white_mask,
)

FILE_NAMES = {label: name for name, label in GLYPH_LABELS.items()}
DAMAGE_MARGIN = 3
# The overlay text of the ruled cases shows below the pilot block, inside these rows and
# columns of the overlay area.
OVERLAY_ROWS = (140, 172)
OVERLAY_COLUMNS = (424, 506)


def main(labeled: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    glyphs: dict[str, list[np.ndarray]] = defaultdict(list)
    states: dict[str, np.ndarray] = {}
    damages: dict[int, np.ndarray] = {}
    names: dict[str, str] = {}
    overlays: dict[str, str] = {}
    seen: dict[tuple[str, str], str] = {}
    for line in (labeled / "cases.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        panel = row.get("unit_panel")
        if not panel:
            continue
        image = cv2.imread(str(labeled / "frames" / row["file"]))
        assert image is not None, row["id"]
        mech, pilot = panel["mech"], panel["pilot"]
        texts = [
            (HP, str(mech["hp"])),
            (EN, str(mech["en"])),
            (MP, f"{pilot['mp']}/{pilot['mp_max']}"),
        ]
        if pilot["chance_step"] is not None:
            texts.append((CHANCE_COUNT, f"x{pilot['chance_step']}"))
        for box, text in texts:
            mask = white_mask(crop(image, box))
            boxes = glyph_boxes(mask)
            if len(boxes) != len(text):
                print("skip", row["id"], text, len(boxes))
                continue
            for label, glyph_box in zip(text, boxes):
                glyphs[label].append(glyph_image(mask, glyph_box))
        if pilot["state"] not in states:
            mask = color_mask(crop(image, STATE))
            ys, xs = np.nonzero(mask)
            states[pilot["state"]] = mask[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
        if pilot["damage"] is not None and pilot["damage"] not in damages:
            mask = white_mask(crop(image, DAMAGE))
            damages[pilot["damage"]] = mask[
                DAMAGE_MARGIN:-DAMAGE_MARGIN, DAMAGE_MARGIN:-DAMAGE_MARGIN
            ]
        if mech["overlay"] is not None and mech["overlay"] not in overlays.values():
            mask = color_mask(crop(image, OVERLAY_AREA))
            ys, xs = np.nonzero(
                mask[OVERLAY_ROWS[0] : OVERLAY_ROWS[1], OVERLAY_COLUMNS[0] : OVERLAY_COLUMNS[1]]
            )
            file = f"overlay_{len(overlays):02d}.png"
            top, left = OVERLAY_ROWS[0], OVERLAY_COLUMNS[0]
            cv2.imwrite(
                str(out / file),
                mask[top + ys.min() : top + ys.max() + 1, left + xs.min() : left + xs.max() + 1],
            )
            overlays[file] = mech["overlay"]
        for kind, box in (("mech", MECH_NAME), ("pilot", PILOT_NAME)):
            name = panel[kind]["name"]
            if (kind, name) in seen:
                continue
            found = text_crop(crop(image, box))
            assert found is not None, row["id"]
            file = f"name_{kind}_{sum(1 for k, _ in seen if k == kind):02d}.png"
            seen[(kind, name)] = file
            names[file] = name
            cv2.imwrite(str(out / file), found)
    for label, samples in sorted(glyphs.items()):
        mean = np.mean(np.stack(samples).astype(np.float32), axis=0)
        cv2.imwrite(
            str(out / f"glyph_{FILE_NAMES.get(label, label)}.png"),
            ((mean > 127) * 255).astype(np.uint8),
        )
    for word, mask in states.items():
        cv2.imwrite(str(out / f"state_{PilotState(word).name.lower()}.png"), mask)
    for value, mask in damages.items():
        cv2.imwrite(str(out / f"damage_{value}.png"), mask)
    (out / "overlays.json").write_text(
        json.dumps(overlays, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    (out / "names.json").write_text(
        json.dumps(names, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(
        {label: len(samples) for label, samples in sorted(glyphs.items())},
        sorted(states),
        sorted(damages),
        len(names),
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
