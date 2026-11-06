"""Make the templates of the OpenCV interpreter elements from named labeled cases.

Usage: uv run python scripts/extract_interpreter_templates.py data/labeled assets/templates/interpreter

Titles: the white mask of each case, averaged, kept where more than half of the cases
are white. The menu key, the fast-forward glyph, "- TAP TO NEXT -" and the round button texts: the HSV value channel of
one case.
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np

from ggge_ai_2.interpreter.elements.fast_forward import FAST_FORWARD_GLYPH_REGION
from ggge_ai_2.interpreter.elements.menu_key import MENU_GLYPH_REGION
from ggge_ai_2.interpreter.elements.region import crop, value
from ggge_ai_2.interpreter.elements.round_button import ROUND_TEXT_REGION, RoundButton
from ggge_ai_2.interpreter.elements.tap_to_next import TAP_TO_NEXT_REGION
from ggge_ai_2.interpreter.elements.top_left_title import TopLeftTitle, title_mask

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
    for path in sorted(out.glob("*.png")):
        print(path.name, np.asarray(cv2.imread(str(path))).shape)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
