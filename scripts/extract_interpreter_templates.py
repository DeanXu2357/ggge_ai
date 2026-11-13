"""Make the templates of the OpenCV interpreter elements from named labeled cases.

Usage: uv run python scripts/extract_interpreter_templates.py data/labeled assets/templates/interpreter

Titles: the white mask of each case, averaged, kept where more than half of the cases
are white. The menu key, the fast-forward glyph, "- TAP TO NEXT -", the round button texts,
the parts of the unit list button and the keys on the arc of the action wheel: the HSV value
channel of one case.

Unit detail summary: the title is the HSV value channel of one case. Each shape holds the
direction edges that all cases share, and 0 elsewhere.
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np

from ggge_ai_2.interpreter.elements.fast_forward import FAST_FORWARD_GLYPH_REGION
from ggge_ai_2.interpreter.elements.menu_key import MENU_GLYPH_REGION
from ggge_ai_2.interpreter.elements.region import Region, crop, value
from ggge_ai_2.interpreter.elements.round_button import ROUND_TEXT_REGION, RoundButton
from ggge_ai_2.interpreter.elements.shape import SHAPE_DIRECTIONS, direction_edges
from ggge_ai_2.interpreter.elements.tap_to_next import TAP_TO_NEXT_REGION
from ggge_ai_2.interpreter.elements.top_left_title import TopLeftTitle, title_mask
from ggge_ai_2.interpreter.elements.unit_list import (
    UNIT_LIST_ARROW_REGIONS,
    UNIT_LIST_LABEL_REGIONS,
    UnitListButton,
)
from ggge_ai_2.interpreter.elements.unit_detail import (
    BLOCK_REGIONS,
    BUTTON_REGIONS,
    TITLE_REGION,
)

TITLE_CASES = {
    TopLeftTitle.PLAYER_PHASE: ["rec20261014-639", "rec20261014-670", "rec20261014-672"],
    TopLeftTitle.UNIT_MOVE: ["rec20261014-536", "rec20261014-755", "rec20261014-1053"],
    TopLeftTitle.SELECT_WEAPON: ["rec20261014-637", "rec20261014-728", "rec20261014-779"],
    TopLeftTitle.BATTLE_PREP_ATTACK: ["rec20261014-648", "rec20261014-774", "rec20261014-851"],
    TopLeftTitle.BATTLE_PREP_RESPONSE: ["rec20261014-882", "rec20261014-901", "rec20261014-1072"],
    TopLeftTitle.ENEMY_PHASE: ["rec20261014-913", "rec20261014-1082"],
    TopLeftTitle.SKILL: ["rec20261014-1237"],
}
MENU_KEY_CASE = "map20261026-51"
TAP_TO_NEXT_CASE = "rec20261014-503"
FAST_FORWARD_CASE = "map20261026-51"
ROUND_TEXT_CASES = {
    RoundButton.SELECT_WEAPON: "rec20261014-536",
    RoundButton.ATTACK: "rec20261014-728",
    RoundButton.ATTACK_OUT_OF_RANGE: "run20261025-165717-31",
    RoundButton.SELECT_ACTION: "rec20261014-927",
    RoundButton.ACTIVATE: "rec20261014-1237",
    RoundButton.START_BATTLE: "rec20261014-648",
}
UNIT_DETAIL_CASES = [f"map20261112-{index}" for index in range(35, 40)]
# The shapes keep only the edges near the outline, so the content inside a block cannot change
# the score. The close button is a hexagon: it keeps the whole button except its label.
UNIT_DETAIL_OUTLINE_BAND = 16
UNIT_DETAIL_CLOSE_LABEL: Region = (0.4744, 0.8889, 0.5342, 0.9444)
UNIT_LIST_CASES = {
    UnitListButton.OPEN: "map20261112-32",
    UnitListButton.CLOSED: "map20261112-31",
}
# The icon and the label of each key, in pixels.
ARC_CASE = "rec20261014-637"
ARC_KEYS = {"arc_skill": (1912, 615, 1984, 735), "arc_switch_target": (1772, 718, 1892, 832)}


def main(labeled: Path, out: Path) -> None:
    files = {}
    for line in (labeled / "cases.jsonl").read_text(encoding="utf-8").splitlines():
        if line:
            row = json.loads(line)
            files[row["id"]] = labeled / "frames" / row["file"]

    def load(case: str) -> np.ndarray:
        image = cv2.imread(str(files[case]))
        assert image is not None, case
        return image

    out.mkdir(parents=True, exist_ok=True)
    for title, case_ids in TITLE_CASES.items():
        masks = [title_mask(load(case)) for case in case_ids]
        proto = np.mean(masks, axis=0) > 0.5
        cv2.imwrite(str(out / f"title_{title.value}.png"), proto.astype(np.uint8) * 255)
    cv2.imwrite(str(out / "key_menu.png"), value(crop(load(MENU_KEY_CASE), MENU_GLYPH_REGION)))
    cv2.imwrite(
        str(out / "fast_forward_glyph.png"),
        value(crop(load(FAST_FORWARD_CASE), FAST_FORWARD_GLYPH_REGION)),
    )
    cv2.imwrite(
        str(out / "tap_to_next.png"), value(crop(load(TAP_TO_NEXT_CASE), TAP_TO_NEXT_REGION))
    )
    for kind, case in ROUND_TEXT_CASES.items():
        cv2.imwrite(
            str(out / f"round_{kind.value}.png"), value(crop(load(case), ROUND_TEXT_REGION))
        )
    open_case = load(UNIT_LIST_CASES[UnitListButton.OPEN])
    cv2.imwrite(
        str(out / "unit_list_label.png"),
        value(crop(open_case, UNIT_LIST_LABEL_REGIONS[UnitListButton.OPEN])),
    )
    for state, case in UNIT_LIST_CASES.items():
        cv2.imwrite(
            str(out / f"unit_list_arrow_{state.value}.png"),
            value(crop(load(case), UNIT_LIST_ARROW_REGIONS[state])),
        )
    arc = load(ARC_CASE)
    for name, (left, top, right, bottom) in ARC_KEYS.items():
        cv2.imwrite(str(out / f"{name}.png"), value(arc[top:bottom, left:right]))
    unit_detail = [load(case) for case in UNIT_DETAIL_CASES]
    cv2.imwrite(str(out / "unit_detail_title.png"), value(crop(unit_detail[0], TITLE_REGION)))
    for name, region in {**BUTTON_REGIONS, **BLOCK_REGIONS}.items():
        shape = _common_edges([direction_edges(crop(image, region)) for image in unit_detail])
        keep = _outline_mask(unit_detail[0], region, name)
        cv2.imwrite(str(out / f"unit_detail_{name}.png"), np.where(keep, shape, 0).astype(np.uint8))
    for path in sorted(out.glob("*.png")):
        print(path.name, np.asarray(cv2.imread(str(path))).shape)


def _common_edges(labels: list[np.ndarray]) -> np.ndarray:
    """Keep the edges of the first case that every case has within 1 pixel, in the same direction."""
    kernel = np.ones((3, 3), np.uint8)
    common = labels[0].copy()
    for other in labels[1:]:
        for direction in range(1, SHAPE_DIRECTIONS + 1):
            near = cv2.dilate((other == direction).astype(np.uint8), kernel) > 0
            common[(common == direction) & ~near] = 0
    return common


def _outline_mask(frame: np.ndarray, region: Region, name: str) -> np.ndarray:
    if name == "close_button":
        keep = np.ones(frame.shape[:2], bool)
        crop(keep, UNIT_DETAIL_CLOSE_LABEL)[:] = False
        return crop(keep, region)
    keep = np.zeros(crop(frame, region).shape[:2], bool)
    band = UNIT_DETAIL_OUTLINE_BAND
    keep[:band, :] = keep[-band:, :] = True
    keep[:, :band] = keep[:, -band:] = True
    return keep


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
