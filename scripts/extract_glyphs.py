"""Rebuild assets/templates/glyphs/panel from the panel fixtures.

Each SOURCES entry names a fixture field whose text was transcribed by hand,
plus which atom range of that field carries each glyph. Atom indices come from
the same splitter the reader uses, so `--list` prints them when a fixture is
re-shot and the ranges need re-checking.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from ggge_ai.runtime import glyphs

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "vision"
OUT = glyphs.TEMPLATE_ROOT / "panel"

SOURCES: tuple[tuple[str, glyphs.Region, glyphs.Ink, str, dict[tuple[int, int], str]], ...] = (
    (
        "stage_panels/enemy_detail_weapons_gearadoga",
        (596, 254, 148, 32),
        glyphs.Ink.DARK,
        "29265",
        {(0, 0): "2", (1, 1): "9", (3, 3): "6", (4, 4): "5"},
    ),
    (
        "stage_panels/enemy_detail_weapons_gearadoga",
        (596, 350, 148, 32),
        glyphs.Ink.DARK,
        "4",
        {(0, 0): "4"},
    ),
    (
        "stage_panels/enemy_detail_weapons_gearadoga",
        (596, 398, 148, 32),
        glyphs.Ink.DARK,
        "4078",
        {(1, 1): "0", (2, 2): "7", (3, 3): "8"},
    ),
    (
        "stage_panels/enemy_detail_weapons_gearadoga",
        (596, 446, 148, 32),
        glyphs.Ink.DARK,
        "3637",
        {(0, 0): "3"},
    ),
    (
        "stage_panels/enemy_detail_weapons_gearadoga",
        (596, 840, 148, 32),
        glyphs.Ink.DARK,
        "15",
        {(0, 0): "1"},
    ),
    (
        "stage_panels/enemy_detail_weapons_gearadoga",
        (1120, 400, 157, 36),
        glyphs.Ink.DARK,
        "1-3",
        {(0, 0): "1__s", (1, 1): "minus", (2, 2): "3__s"},
    ),
    (
        "stage_panels/enemy_detail_weapons_gearadoga",
        (1291, 400, 190, 36),
        glyphs.Ink.DARK,
        "3600",
        {(1, 1): "6__s", (2, 2): "0__s"},
    ),
    (
        "stage_panels/enemy_detail_weapons_gearadoga",
        (1495, 400, 124, 36),
        glyphs.Ink.DARK,
        "29",
        {(0, 0): "2__s", (1, 1): "9__s"},
    ),
    (
        "stage_panels/enemy_detail_weapons_gearadoga",
        (1632, 400, 157, 36),
        glyphs.Ink.DARK,
        "100%",
        {(3, 4): "percent"},
    ),
    (
        "stage_panels/enemy_detail_weapons_gearadoga",
        (1495, 569, 124, 36),
        glyphs.Ink.DARK,
        "25",
        {(1, 1): "5__s"},
    ),
    (
        "stage_panels/enemy_detail_weapons_kshatriya",
        (1291, 569, 190, 36),
        glyphs.Ink.DARK,
        "4100",
        {(0, 0): "4__s"},
    ),
    (
        "stage_panels/enemy_detail_weapons_kshatriya",
        (1291, 740, 190, 36),
        glyphs.Ink.DARK,
        "3800",
        {(1, 1): "8__s"},
    ),
    (
        "roster_panels/unit_weapons_theo_top",
        (1495, 567, 124, 36),
        glyphs.Ink.DARK,
        "37",
        {(1, 1): "7__s"},
    ),
    (
        "stage_panels/enemy_detail_weapons_kshatriya",
        (1632, 399, 157, 38),
        glyphs.Ink.DARK,
        "105%",
        {(0, 0): "1__b", (2, 2): "5__b", (3, 4): "percent__b"},
    ),
    (
        "roster_panels/unit_weapons_map_icon_nu_gundam",
        (1632, 636, 157, 38),
        glyphs.Ink.DARK,
        "105%",
        {(1, 1): "0__b"},
    ),
    (
        "stage_panels/ally_detail_abilities_ntgundam",
        (596, 254, 148, 32),
        glyphs.Ink.DARK,
        "+11010",
        {(0, 0): "plus"},
    ),
    (
        "stage_panels/ally_detail_weapons_ntgundam",
        (596, 254, 148, 32),
        glyphs.Ink.DARK,
        "▲39955",
        {(0, 0): "arrow"},
    ),
    (
        "stage_panels/ally_detail_basicinfo_ntgundam",
        (1780, 608, 95, 44),
        glyphs.Ink.LIGHT,
        "0/12",
        {(1, 1): "slash"},
    ),
    (
        "roster_panels/unit_weapons_map_icon_nu_gundam",
        (1096, 397, 135, 38),
        glyphs.Ink.DARK,
        "MAP",
        {(0, 1): "letter-m", (2, 3): "letter-a", (4, 4): "letter-p"},
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="print atom spans instead of writing")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    written = 0
    for name, region, ink, transcription, picks in SOURCES:
        frame = cv2.imread(str(FIXTURES / f"{name}.png"))
        if frame is None:
            raise SystemExit(f"missing fixture {name}")
        field = glyphs._field(glyphs.crop(frame, region), ink)
        if field is None:
            raise SystemExit(f"no ink in {name} {region}")
        if args.list:
            print(f"{name} {region} {transcription!r} atoms={field.atoms}")
            continue
        for (first, last), char in picks.items():
            image = glyphs._atom_image(field, field.atoms[first][0], field.atoms[last][1])
            if image is None:
                raise SystemExit(f"empty atom {first}..{last} in {name}")
            cv2.imwrite(str(OUT / f"{char}.png"), image)
            written += 1
    if not args.list:
        print(f"wrote {written} glyphs to {OUT}")


if __name__ == "__main__":
    main()
