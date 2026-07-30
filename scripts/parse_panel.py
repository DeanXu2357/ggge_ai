"""Parse one panel screenshot and print the result as JSON.

    uv run python scripts/parse_panel.py <png> [--no-llm] [--unit-id UID]

--no-llm keeps the run offline: numbers still come out, free text does not.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path

import cv2

from ggge_ai.runtime import panels
from ggge_ai.runtime.glyphs import crop
from ggge_ai.runtime.panel_text import OllamaPanelTextReader, PanelTextReader
from ggge_ai.stage.intel_panels import unit_intel_from_panels


def _plain(value):
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _plain(item) for key, item in asdict(value).items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, set | frozenset):
        return sorted(str(item) for item in value)
    return value


def _weapon_texts(frame, rows, reader: PanelTextReader | None):
    if reader is None:
        return tuple((row, None) for row in rows)
    pairs = []
    for row in rows:
        region = row.name_region
        if row.note_region is not None:
            region = (
                region[0],
                region[1],
                region[2],
                row.note_region[1] + row.note_region[3] - region[1],
            )
        pairs.append(
            (row, reader.weapon(crop(frame, region), has_note=row.note_region is not None))
        )
    return tuple(pairs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--unit-id", default="unknown")
    parser.add_argument("--pick", choices=("shooting", "melee", "awakening"))
    args = parser.parse_args()

    frame = cv2.imread(str(args.image))
    if frame is None:
        raise SystemExit(f"cannot read {args.image}")

    kind = panels.classify(frame)
    reader = None if args.no_llm else OllamaPanelTextReader.from_env()
    column = panels.read_stat_column(frame, kind)
    basic = panels.read_basic_view(frame, kind)
    rows = panels.read_weapon_rows(frame, kind)
    weapons = _weapon_texts(frame, rows, reader)
    abilities = (
        reader.abilities(crop(frame, panels.CONTENT_REGION))
        if reader is not None and kind in panels.ABILITY_KINDS
        else None
    )
    assembled = unit_intel_from_panels(
        args.unit_id,
        column=column,
        basic=basic,
        weapons=weapons,
        abilities=abilities,
        pick=args.pick,
    )
    print(
        json.dumps(
            {
                "image": str(args.image),
                "kind": kind.value,
                "llm": reader is not None,
                "stat_column": _plain(column),
                "basic_view": _plain(basic),
                "weapon_rows": _plain(rows),
                "weapon_texts": _plain([text for _, text in weapons]),
                "abilities": _plain(abilities),
                "intel": _plain(assembled),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
