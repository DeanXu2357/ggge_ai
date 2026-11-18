"""Draw the stage data that a survey saved over a mosaic of the frames that the survey saw.

usage: uv run python scripts/render_stage_map.py RUN_DIR [--views]

The run needs --trace-plans and --keep-frames. The script replays the map sync planner on the
traced readings as analyze_run.py does, places each view of the output map group as mapgeom
placed it, and pastes the top view of each readable cell, newest view first. It draws the
units of the stage store over the mosaic and writes stage_map.html, stage_map.png and
stage_map_plain.png in the run directory. --views also prints the shift and the units of each
placed view.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from analyze_run import STAGES, Replay, replay_step
from ggge_ai_2.agent.contract import Evidence, MapReadingRecord
from ggge_ai_2.agent.map_reading import map_reading
from ggge_ai_2.agent.stage_survey import stage_data
from ggge_ai_2.interpreter.element_first import ElementFirstInterpreter
from ggge_ai_2.interpreter.elements.detectors import DETECTORS
from ggge_ai_2.mapgeom.stitch import StitchMapGeometry
from ggge_ai_2.mapparser.border import read_border
from ggge_ai_2.mapparser.contract import CellReading, ViewCell
from ggge_ai_2.mapparser.lattice import read_lattice
from ggge_ai_2.mapparser.opencv_parser import OpenCvMapParser
from ggge_ai_2.mapparser.region import read_region
from ggge_ai_2.mapparser.topview import CELL, TopView, top_view
from ggge_ai_2.planner.map_sync import MapSyncPlanner, view_of
from ggge_ai_2.screenmodel.definition_model import DefinitionScreenModel
from ggge_ai_2.stagedata.contract import StageData
from ggge_ai_2.stagedata.store import PostgresStageStore
from ggge_ai_2.stream.contract import Frame, StillWindow
from ggge_ai_2.uisim.stage_sim import StageUiSim
from ggge_ai_2.uisim.stages import load_stages

Row = dict[str, Any]
MODEL = DefinitionScreenModel()
ENEMY = (60, 60, 255)
NPC_ALLY = (255, 160, 0)
CONTROLLED = (0, 220, 0)
UNCERTAIN = (0, 160, 255)


def main() -> int:
    parser = argparse.ArgumentParser(description="Draw the saved stage map of a survey run.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--views", action="store_true")
    args = parser.parse_args()
    run_dir: Path = args.run_dir
    rows = [
        json.loads(line)
        for line in (run_dir / "run.log").open(encoding="utf-8")
        if line.startswith("{")
    ]
    header = next(row for row in rows if row["message"] == "stage")
    replay = Replay(header["stage"], header["seed"], StageUiSim(load_stages(STAGES)))
    pending = None
    for row in rows:
        if row["message"] == "plan input" and row["plan"] == MapSyncPlanner.__name__:
            pending = row
        elif row["message"] == "plan output" and pending is not None:
            replay_step(replay, pending, row)
            pending = None
    planner = replay.planner
    if planner is None:
        print(f"render_stage_map: {run_dir} has no traced survey", file=sys.stderr)
        return 2
    add_last_reading(run_dir, rows, replay.records)
    judgment = planner.judgment(Evidence(tuple(replay.records)))
    records = replay.records[planner.start :]
    # Warning: '_record_taps' is private to the planner. The script reads it only to give each
    # view the tap number that the survey gave it.
    taps = planner._record_taps  # pyright: ignore[reportPrivateUsage]
    views = [view_of(record, replay.stage, tap) for record, tap in zip(records, taps, strict=True)]
    placement = StitchMapGeometry().placement(views)
    if judgment is None or not placement:
        print(f"render_stage_map: the survey of {run_dir} has no map", file=sys.stderr)
        return 2
    width, height = judgment.columns.length, judgment.rows.length
    with PostgresStageStore() as store:
        stored = store.load(replay.stage, header["app_version"])
    replayed = None
    if judgment.columns.size() is not None and judgment.rows.size() is not None:
        replayed = stage_data(judgment, replay.stage, header["app_version"], header["code_version"])

    mosaic, pasted = paste(run_dir, records, placement, width, height)
    drawn = mosaic.copy()
    draw_grid(drawn, width, height)
    for cell, unit_id in judgment.unit_cells.items():
        if judgment.units[unit_id].controllable:
            box(drawn, cell, (1, 1), CONTROLLED, 3, 6)
    for x, y in judgment.uncertain:
        cv2.line(drawn, (x * CELL, y * CELL), ((x + 1) * CELL, (y + 1) * CELL), UNCERTAIN, 1)
    units = () if stored is None else stored.units
    for index, unit in enumerate(units):
        box(drawn, unit.pos, unit.size, ENEMY if unit.faction.value == "enemy" else NPC_ALLY, 4, 3)
        x, y = unit.pos
        label = (x * CELL + 8, (y + 1) * CELL - 10)
        cv2.putText(drawn, f"#{index}", label, cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.imwrite(str(run_dir / "stage_map.png"), drawn)
    cv2.imwrite(str(run_dir / "stage_map_plain.png"), mosaic)
    same = same_units(stored, replayed)
    note = f"{width}x{height} from {len(placement)} of {len(views)} views, {len(pasted)} pasted"
    (run_dir / "stage_map.html").write_text(
        page(run_dir, replay.stage, stored, note, same), encoding="utf-8"
    )
    print(f"stage map: {run_dir / 'stage_map.html'} ({note}, same as the store: {same})")
    if args.views:
        for member in sorted(placement):
            dx, dy = placement[member]
            cells = sorted((u.pos[0] + dx, u.pos[1] + dy) for u in records[member].reading.units)
            print(
                records[member].still.frame_seq,
                "shift",
                (dx, dy),
                "tap",
                taps[member],
                "units",
                cells,
            )
    return 0


def add_last_reading(run_dir: Path, rows: list[Row], records: list[MapReadingRecord]) -> None:
    """Add the reading on which the survey ended. The survey ends in 'still_valid', and no
    'next' call traces that reading, so it is read again from its kept frame."""
    saved = next((i for i, row in enumerate(rows) if row["message"] == "stage data saved"), None)
    if saved is None or not records:
        return
    sense = next(row for row in reversed(rows[:saved]) if row["message"] == "sense")
    seq: int = sense["frame_seq"]
    if seq <= records[-1].still.frame_seq:
        return
    image = cv2.imread(str(run_dir / "stream" / f"{seq:06d}.png"))
    if image is None:
        return
    interpreter = ElementFirstInterpreter(DETECTORS, MODEL, OpenCvMapParser())
    situation = interpreter.interpret(Frame(image, sense["still_until"], seq), frozenset())
    if situation is None or situation.map is None:
        return
    still = StillWindow(sense["still_since"], sense["still_until"], seq)
    records.append(
        MapReadingRecord(still, map_reading(situation.map), situation.phase, situation.turn)
    )


def paste(
    run_dir: Path,
    records: list[MapReadingRecord],
    placement: dict[int, tuple[int, int]],
    width: int,
    height: int,
) -> tuple[np.ndarray, list[int]]:
    mosaic = np.zeros((height * CELL, width * CELL, 3), np.uint8)
    filled = np.zeros((height, width), bool)
    pasted: list[int] = []
    for member in sorted(placement, reverse=True):
        record = records[member]
        image = cv2.imread(str(run_dir / "stream" / f"{record.still.frame_seq:06d}.png"))
        found = None if image is None else frame_view(image)
        if found is None:
            continue
        view, to_lattice = found
        dx, dy = placement[member]
        count = 0
        for cell, seen in record.reading.cells.items():
            x, y = cell[0] + dx, cell[1] + dy
            if (
                seen is CellReading.UNREADABLE
                or not (0 <= x < width and 0 <= y < height)
                or filled[y, x]
            ):
                continue
            tile, _white, shown = view.cell(to_lattice(cell))
            if tile.shape[:2] != (CELL, CELL) or shown.mean() < 0.5:
                continue
            mosaic[y * CELL : (y + 1) * CELL, x * CELL : (x + 1) * CELL] = tile
            filled[y, x] = True
            count += 1
        if count:
            pasted.append(record.still.frame_seq)
    return mosaic, pasted


def frame_view(image: np.ndarray) -> tuple[TopView, Callable[[ViewCell], ViewCell]] | None:
    """Return the top view of the frame and the map from view cells to lattice cells, with the
    occlusion that the screen model gives, as the parser reads them."""
    judgment = MODEL.judge([found for detector in DETECTORS for found in detector.detect(image)])
    lattice = read_lattice(image)
    if lattice is None:
        return None
    view = top_view(image, lattice, judgment.occlusion)
    region = read_region(lattice, judgment.occlusion, read_border(view))
    return view, region.to_lattice


def draw_grid(image: np.ndarray, width: int, height: int) -> None:
    for x in range(width + 1):
        cv2.line(image, (x * CELL, 0), (x * CELL, height * CELL), (90, 90, 90), 1)
    for y in range(height + 1):
        cv2.line(image, (0, y * CELL), (width * CELL, y * CELL), (90, 90, 90), 1)
    for x in range(width):
        cv2.putText(
            image, str(x), (x * CELL + 4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1
        )
    for y in range(height):
        cv2.putText(
            image, str(y), (4, y * CELL + 36), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1
        )


def box(
    image: np.ndarray,
    cell: tuple[int, int],
    size: tuple[int, int],
    color: tuple[int, int, int],
    width: int,
    inset: int,
) -> None:
    x, y = cell
    corner = (x * CELL + inset, y * CELL + inset)
    far = ((x + size[0]) * CELL - inset, (y + size[1]) * CELL - inset)
    cv2.rectangle(image, corner, far, color, width)


def same_units(a: StageData | None, b: StageData | None) -> bool:
    if a is None or b is None:
        return False

    def key(data: StageData) -> list[object]:
        return [
            (u.pos, u.size, u.faction, u.brief.hp, u.brief.en, u.brief.mp, u.brief.mp_max)
            for u in data.units
        ]

    return (a.columns, a.rows, key(a)) == (b.columns, b.rows, key(b))


def mask_png(mask: np.ndarray) -> str:
    ok, data = cv2.imencode(".png", mask)
    assert ok, "a name mask encodes as PNG"
    return "data:image/png;base64," + base64.b64encode(data.tobytes()).decode()


def page(run_dir: Path, stage: str, stored: StageData | None, note: str, same: bool) -> str:
    lines = [
        "<!doctype html><meta charset='utf-8'><title>Stage map</title>",
        "<style>body{font:14px system-ui,sans-serif;margin:16px;background:#fff;color:#111}"
        "table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:3px 6px}"
        "img.map{max-width:100%}"
        "@media (prefers-color-scheme:dark){body{background:#121212;color:#eee}"
        "td,th{border-color:#444}}</style>",
        f"<h1>{html.escape(stage)} stage data</h1>",
    ]
    if stored is None:
        lines.append("<p>The store has no data of this stage.</p>")
    else:
        lines.append(
            f"<p>store: {stored.columns} columns × {stored.rows} rows · app"
            f" {html.escape(stored.app_version)} · code {html.escape(stored.code_version)}"
            f" · {len(stored.units)} units · terrain cells {len(stored.terrain)}"
            f" · deploy cells {len(stored.deploy_cells)} · victory {len(stored.victory)}"
            f" · events {len(stored.events)}</p>"
        )
    lines.append(
        f"<p>replayed survey of run {html.escape(run_dir.name)}: {html.escape(note)}"
        f" · same as the store: {same}</p>"
        "<p>Red boxes: stored units (#index). Green boxes: units that the player controls; the"
        " store does not keep them. Orange diagonal: uncertain cells. Black: no view showed"
        " the cell.</p><p><a href='stage_map_plain.png'>mosaic without marks</a></p>"
        "<img class=map src='stage_map.png'>"
        "<table><tr><th>#</th><th>cell</th><th>size</th><th>faction</th><th>mech</th><th>HP</th>"
        "<th>EN</th><th>pilot</th><th>MP</th><th>state</th><th>roles</th></tr>"
    )
    for index, unit in enumerate(() if stored is None else stored.units):
        brief = unit.brief
        lines.append(
            f"<tr><td>#{index}</td><td>{unit.pos}</td><td>{unit.size}</td>"
            f"<td>{unit.faction.value}</td>"
            f"<td><img src='{mask_png(brief.mech_name.mask)}' height=20></td>"
            f"<td>{brief.hp}</td><td>{brief.en}</td>"
            f"<td><img src='{mask_png(brief.pilot_name.mask)}' height=20></td>"
            f"<td>{brief.mp}/{brief.mp_max}</td><td>{html.escape(brief.state.value)}</td>"
            f"<td>{brief.mech_role.value} / {brief.pilot_role.value}</td></tr>"
        )
    lines.append("</table>")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
