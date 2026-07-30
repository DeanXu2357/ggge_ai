"""Rebuild assets/templates/panels from the panel fixtures.

Titles discriminate the panel families, category badges the weapon type, and
the CHANCE STEP badge is counted rather than matched once.
"""

from __future__ import annotations

from pathlib import Path

import cv2

from ggge_ai.runtime import panels

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "vision"

SOURCES: tuple[tuple[str, str, tuple[int, int, int, int]], ...] = (
    ("title_stage_unit.png", "stage_panels/enemy_detail_weapons_gearadoga", (1050, 80, 262, 34)),
    ("title_roster_unit.png", "roster_panels/unit_weapons_theo_top", (1050, 80, 220, 34)),
    ("title_roster_pilot.png", "roster_panels/pilot_detail_amuro_info", (1050, 80, 220, 34)),
    ("badge_shooting.png", "stage_panels/enemy_detail_weapons_gearadoga", (1832, 303, 160, 40)),
    ("badge_melee.png", "stage_panels/enemy_detail_weapons_kshatriya", (1832, 303, 160, 40)),
    ("badge_awakening.png", "stage_panels/enemy_detail_weapons_kshatriya", (1832, 643, 160, 40)),
    (
        "badge_chance_step.png",
        "stage_panels/enemy_detail_basicinfo_unicorngundam",
        (2010, 182, 26, 26),
    ),
)


def main() -> None:
    panels.TEMPLATE_ROOT.mkdir(parents=True, exist_ok=True)
    for name, fixture, (x, y, w, h) in SOURCES:
        frame = cv2.imread(str(FIXTURES / f"{fixture}.png"))
        if frame is None:
            raise SystemExit(f"missing fixture {fixture}")
        patch = cv2.cvtColor(frame[y : y + h, x : x + w], cv2.COLOR_BGR2GRAY)
        cv2.imwrite(str(panels.TEMPLATE_ROOT / name), patch)
    print(f"wrote {len(SOURCES)} templates to {panels.TEMPLATE_ROOT}")


if __name__ == "__main__":
    main()
