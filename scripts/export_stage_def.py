"""Export a map-scan standard answer into a schema-2 stage definition:
the factionless first stage of the two-stage survey (定案 5), positions
and footprints only. Faction, stats and weapons arrive when the second
stage (per-unit banner docking + panel reads) runs on-device, so the
file is written with status "positions_only" -- the warm-start path only
adopts "complete" definitions, this one is inert until then.

usage: uv run python scripts/export_stage_def.py "<stage_id>" [series_dir] [--root DIR]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ggge_ai.content import stage_def

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SERIES = PROJECT_ROOT / "tests" / "fixtures" / "vision" / "map_scan" / "ex2if_20260719"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage_id")
    parser.add_argument("series_dir", nargs="?", default=str(DEFAULT_SERIES))
    parser.add_argument("--root", default=None)
    args = parser.parse_args()

    answer = json.loads(
        (Path(args.series_dir) / "standard_answer.json").read_text(encoding="utf-8")
    )
    units = []
    for entry in answer["units"]:
        cells = entry.get("cells") or [entry["map_cell"]]
        anchor = (min(c[0] for c in cells), min(c[1] for c in cells))
        units.append(
            stage_def.StageUnit(
                uid="",
                cell=anchor,
                faction="unknown",
                footprint=tuple(entry.get("footprint", (1, 1))),
            )
        )
    pitch = answer["pitch"]
    defn = stage_def.StageDefinition(
        stage_id=args.stage_id,
        layout=stage_def.assign_uids(units),
        status="positions_only",
        cell_size=round(sum(pitch) / len(pitch), 1),
    )
    root = Path(args.root) if args.root else None
    path = stage_def.save_stage_def(defn, root)
    print(f"stage definition written: {path} ({len(defn.layout)} units)")


if __name__ == "__main__":
    main()
