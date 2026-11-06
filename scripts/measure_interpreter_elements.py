"""Print the OpenCV interpreter element scores on the labeled frames.

Usage: uv run python scripts/measure_interpreter_elements.py data/labeled [screen ...]
Without screens: one min/max row for each screen. With screens: one row for each
frame of those screens. The last block lists the quick checks that pass on each frame.
"""

import collections
import json
import sys
from pathlib import Path

import cv2

from ggge_ai_2.interpreter.elements.fast_forward import (
    fast_forward_glyph_score,
    fast_forward_outline_coverage,
)
from ggge_ai_2.interpreter.elements.menu_key import menu_key_white_share
from ggge_ai_2.interpreter.elements.round_button import round_button
from ggge_ai_2.interpreter.elements.tap_to_next import tap_to_next_score
from ggge_ai_2.interpreter.elements.top_left_title import title_ious
from ggge_ai_2.interpreter.elements.turn_box import turn_box_white_share
from ggge_ai_2.interpreter.screens import QUICK_CHECKS


def scores(image):
    ious = sorted(((v, k.value) for k, v in title_ious(image).items()), reverse=True)
    return {
        "turn": turn_box_white_share(image),
        "title": ious[0][1],
        "iou1": ious[0][0],
        "iou2": ious[1][0],
        "menu": menu_key_white_share(image),
        "round": str(round_button(image)),
        "ff_outline": fast_forward_outline_coverage(image),
        "ff_glyph": fast_forward_glyph_score(image),
        "tap": tap_to_next_score(image),
    }


def fmt(value):
    return value if isinstance(value, str) else f"{value:.2f}"


def main(labeled: Path, focus: set[str]) -> None:
    rows = [json.loads(line) for line in (labeled / "cases.jsonl").read_text().splitlines() if line]
    groups = collections.defaultdict(list)
    passes = []
    for row in rows:
        if row["power_save"]:
            continue
        image = cv2.imread(str(labeled / "frames" / row["file"]))
        assert image is not None, row["id"]
        groups[row["screen"]].append((row, scores(image)))
        passed = [screen.value for screen, check in QUICK_CHECKS.items() if check(image)]
        own = row["screen"] in {screen.value for screen in QUICK_CHECKS}
        if passed != ([row["screen"]] if own else []):
            passes.append((row["id"], row["screen"], passed))
    for screen in sorted(groups):
        members = groups[screen]
        if screen in focus:
            for row, s in members:
                print(
                    screen[:28].ljust(29),
                    row["id"].ljust(24),
                    str(row["auto"]).ljust(7),
                    " ".join(f"{k}={fmt(v)}" for k, v in s.items()),
                )
        elif not focus:
            keys = [k for k, v in members[0][1].items() if not isinstance(v, str)]
            print(
                screen[:28].ljust(29),
                str(len(members)).rjust(3),
                " ".join(
                    f"{k}={min(s[k] for _, s in members):.2f}/{max(s[k] for _, s in members):.2f}"
                    for k in keys
                ),
            )
    print("frames whose passed quick checks differ from the own screen (false pass or miss):")
    for case_id, screen, passed in passes:
        print(" ", case_id, screen, passed)


if __name__ == "__main__":
    main(Path(sys.argv[1]), set(sys.argv[2:]))
