"""Export a map-scan standard answer into a schema-3 stage definition:
the factionless first stage of the two-stage survey (定案 5), positions
and footprints only. Units the user identified as the sortie squad
(`deployed` entries) become deploy_slots -- fixed stage cells whose
occupant is per-sortie content -- instead of layout units. Faction,
stats and weapons arrive when the second stage (per-unit banner docking
+ panel reads) runs on-device, so the file is written with status
"positions_only" -- the warm-start path only adopts "complete"
definitions, this one is inert until then.

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

    series_dir = Path(args.series_dir)
    answer = json.loads((series_dir / "standard_answer.json").read_text(encoding="utf-8"))
    units = []
    slots = []
    for entry in answer["units"]:
        cells = entry.get("cells") or [entry["map_cell"]]
        anchor = (min(c[0] for c in cells), min(c[1] for c in cells))
        deployed = entry.get("deployed")
        if deployed:
            slots.append(
                stage_def.DeploySlot(
                    cell=anchor,
                    observed=[{**deployed, "source": series_dir.name}],
                )
            )
        else:
            units.append(
                stage_def.StageUnit(
                    uid="",
                    cell=anchor,
                    faction="unknown",
                    footprint=tuple(entry.get("footprint", (1, 1))),
                )
            )
    slots.sort(key=lambda s: (s.observed[0]["team"], s.observed[0]["slot"]))
    pitch = answer["pitch"]
    defn = stage_def.StageDefinition(
        stage_id=args.stage_id,
        layout=stage_def.assign_uids(units),
        deploy_slots=slots,
        status="positions_only",
        cell_size=round(sum(pitch) / len(pitch), 1),
    )
    root = Path(args.root) if args.root else None
    path = stage_def.save_stage_def(defn, root)
    print(
        f"stage definition written: {path} "
        f"({len(defn.layout)} units, {len(defn.deploy_slots)} deploy slots)"
    )


if __name__ == "__main__":
    main()
