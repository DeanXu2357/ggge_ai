"""Write the review pages of one stage run: analysis.html and analysis.json in the run directory.

usage:
  uv run python scripts/analyze_run.py RUN_DIR
  uv run python scripts/run_loop_v2.py --stage STAGE --trace-plans [--keep-frames] 2>&1 \\
      | uv run python scripts/analyze_run.py

Without RUN_DIR the script copies its input to its output and takes the run directory from
the line 'run directory: ...' at the end. The run needs --trace-plans: the analysis replays
the map sync planner on the traced map readings, with the seed and at the code version in the
log. The same run directory and the same code give the same pages.
"""

from __future__ import annotations

import argparse
import html
import json
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from random import Random
from typing import Any

import cv2
import numpy as np

from ggge_ai_2.agent.belief import Belief, UiBasis, UiSource
from ggge_ai_2.agent.contract import Evidence, MapReadingRecord
from ggge_ai_2.agent.trace_json import decode_record, decode_ui, encode_gesture
from ggge_ai_2.mapgeom.contract import MapJudgment
from ggge_ai_2.mapgeom.stitch import StitchMapGeometry
from ggge_ai_2.planner.map_sync import MapSyncPlanner, _targets
from ggge_ai_2.uisim.stage_sim import StageUiSim
from ggge_ai_2.uisim.stages import load_stages

SCREEN = (2340, 1080)
STAGES = Path("assets/ui_stages/stages.json")
THUMB_WIDTH = 585
# A run of this many equal steps, or of this many swipes that each reverse the last one, is
# flagged.
REPEAT_MIN = 3
REVERSAL_MIN = 3

Row = dict[str, Any]


@dataclass(frozen=True)
class NullDomain:
    def absorb(self, intent: object, outcome: object) -> NullDomain:
        return self


@dataclass
class Replay:
    stage: str
    seed: int
    uisim: StageUiSim
    records: list[MapReadingRecord] = field(default_factory=lambda: list[MapReadingRecord]())
    planner: MapSyncPlanner | None = None
    gap: bool = False


def main() -> int:
    parser = argparse.ArgumentParser(description="Write the review pages of a stage run.")
    parser.add_argument("run_dir", nargs="?", type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir if args.run_dir is not None else pass_through()
    if run_dir is None:
        print("analyze_run: the input has no 'run directory:' line", file=sys.stderr)
        return 2
    if not (run_dir / "run.log").is_file():
        print(f"analyze_run: {run_dir} has no run.log", file=sys.stderr)
        return 2
    rows = [
        json.loads(line)
        for line in (run_dir / "run.log").open(encoding="utf-8")
        if line.startswith("{")
    ]
    header = next((row for row in rows if row["message"] == "stage"), None)
    if header is None or "seed" not in header:
        print(f"analyze_run: {run_dir}/run.log has no stage line with a seed", file=sys.stderr)
        return 2
    if not any(row["message"] == "plan input" for row in rows):
        print(f"analyze_run: {run_dir} has no plan trace; run with --trace-plans", file=sys.stderr)
        return 2
    cycles = analyze(run_dir, rows, header)
    summary = {
        "run": run_dir.name,
        "stage": header["stage"],
        "app_version": header["app_version"],
        "run_code_version": header["code_version"],
        "analysis_code_version": code_version(),
        "seed": header["seed"],
        "cycles": len(cycles),
        "flagged": sum(1 for cycle in cycles if cycle["flags"]),
    }
    (run_dir / "analysis.json").write_text(
        json.dumps({"summary": summary, "cycles": cycles}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    (run_dir / "analysis.html").write_text(page(summary, cycles), encoding="utf-8")
    print(f"analysis: {run_dir / 'analysis.html'} ({summary['flagged']} flagged cycles)")
    return 0


def pass_through() -> Path | None:
    # Ctrl-C stops the run before it; this end of the pipe reads on until the run closes it.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    found = None
    for line in sys.stdin:
        sys.stdout.write(line)
        sys.stdout.flush()
        if line.startswith("run directory: "):
            found = Path(line.removeprefix("run directory: ").strip())
    return found


def code_version() -> str:
    def git(*command: str) -> str:
        return subprocess.run(
            ["git", *command], capture_output=True, text=True, check=True
        ).stdout.strip()

    head = git("rev-parse", "HEAD")[:8]
    return f"{head}-dirty" if git("status", "--porcelain", "--untracked-files=no") else head


def analyze(run_dir: Path, rows: list[Row], header: Row) -> list[Row]:
    replay = Replay(header["stage"], header["seed"], StageUiSim(load_stages(STAGES)))
    plans: dict[int, Row] = {}
    pending: Row | None = None
    for row in rows:
        if row["message"] == "plan input" and row["plan"] == MapSyncPlanner.__name__:
            pending = row
        elif row["message"] == "plan output" and pending is not None:
            seq = pending["belief"]["as_of"]["frame_seq"]
            plans[seq] = replay_step(replay, pending, row)
            pending = None
    cycles = [
        cycle_of(row, plans.get(row["frame_seq"])) for row in rows if row["message"].startswith("#")
    ]
    flag(cycles)
    out = run_dir / "analysis"
    out.mkdir(exist_ok=True)
    for cycle in cycles:
        cycle["thumb"] = draw(run_dir, out, cycle)
    return cycles


def replay_step(replay: Replay, given: Row, gave: Row) -> Row:
    count, newest = given["readings"], given["newest"]
    if newest is not None and count == len(replay.records) + 1:
        replay.records.append(decode_record(newest))
    elif newest is not None and count != len(replay.records):
        replay.gap = True
    if replay.planner is None:
        replay.planner = MapSyncPlanner(
            replay.stage, count, StitchMapGeometry(), replay.uisim, SCREEN, Random(replay.seed)
        )
    ui, as_of = decode_ui(given["belief"])
    belief = Belief(
        ui, UiBasis(UiSource.SEEN, None if as_of is None else as_of.frame_seq), NullDomain(), as_of
    )
    evidence = Evidence(tuple(replay.records))
    step = replay.planner.next(belief, evidence)
    judgment = replay.planner.judgment(evidence)
    replayed = {"step": step.name, "gesture": encode_gesture(step.gesture)}
    logged = {"step": gave["step"], "gesture": gave["gesture"]}
    return {
        "judgment": None if judgment is None else summarize(judgment),
        # Warning: '_record_taps' is private to the planner. The analysis reads it only to show
        # the tap number of the newest view.
        "tap": replay.planner._record_taps[-1] if replay.planner._record_taps else None,  # pyright: ignore[reportPrivateUsage]
        "reading": replay.records[-1] if replay.records else None,
        "logged": logged,
        "replay_same": replayed == logged and not replay.gap,
        "replayed": replayed,
    }


def summarize(judgment: MapJudgment) -> Row:
    def axis(length: int, start: bool, end: bool) -> str:
        return f"{'[' if start else '('}{length}{']' if end else ')'}"

    centre = None
    targets: list[list[int]] = []
    if judgment.current:
        xs = [x for x, _ in judgment.current]
        ys = [y for _, y in judgment.current]
        centre = ((min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2)
        targets = [list(cell) for cell in _targets(judgment, centre)[:3]]
    return {
        "columns": axis(
            judgment.columns.length, judgment.columns.start_closed, judgment.columns.end_closed
        ),
        "rows": axis(judgment.rows.length, judgment.rows.start_closed, judgment.rows.end_closed),
        "units": len(judgment.units),
        "uncertain": len(judgment.uncertain),
        "current": None if judgment.current is None else len(judgment.current),
        "centre": None if centre is None else list(centre),
        "targets": targets,
    }


def cycle_of(row: Row, plan: Row | None) -> Row:
    cycle: Row = {
        "cycle": int(row["message"][1:].split()[0]),
        "frame_seq": row["frame_seq"],
        "frame": row["frame"],
        "interpreted": row["interpreted"],
        "believed": row["believed"],
        "expected": row["expected"],
        "matched": row["matched"],
        "outside_candidates": row["outside_candidates"],
        "step": row["step"],
        "gesture": row["gesture"],
        "flags": [],
    }
    if plan is not None:
        reading = plan.pop("reading")
        cycle["map"] = plan
        cycle["_reading"] = reading
    return cycle


def flag(cycles: list[Row]) -> None:
    repeat = 1
    reversals = 0
    last_drag: tuple[int, int] | None = None
    for index, cycle in enumerate(cycles):
        flags: list[str] = cycle["flags"]
        if cycle["matched"] is False:
            flags.append("unexpected screen")
        if cycle["outside_candidates"]:
            flags.append("outside candidates")
        same = index > 0 and (cycles[index - 1]["step"], cycles[index - 1]["gesture"]) == (
            cycle["step"],
            cycle["gesture"],
        )
        repeat = repeat + 1 if same else 1
        if repeat >= REPEAT_MIN:
            flags.append(f"same step {repeat} times")
        plan = cycle.get("map")
        if plan is None:
            continue
        if not plan["replay_same"]:
            flags.append("replay differs")
        judgment = plan["judgment"]
        if judgment is not None and judgment["current"] is None:
            flags.append("view joins nothing")
        gesture = plan["logged"]["gesture"]
        if gesture is not None and gesture["kind"] == "swipe":
            drag = (
                gesture["end"][0] - gesture["start"][0],
                gesture["end"][1] - gesture["start"][1],
            )
            reverses = last_drag is not None and drag[0] * last_drag[0] + drag[1] * last_drag[1] < 0
            reversals = reversals + 1 if reverses else 0
            if reversals >= REVERSAL_MIN:
                flags.append(f"swipe reversed {reversals} times")
            last_drag = drag
        previous = next((c for c in reversed(cycles[:index]) if c.get("map")), None)
        if previous is not None and previous["map"]["logged"]["step"] == "map_sync_tap_empty":
            tapped = previous["map"]["logged"]["gesture"]["cell"]
            reading = cycle["_reading"]
            mark = (
                None
                if reading is None or reading.reading.tap_mark is None
                else list(reading.reading.tap_mark.cell)
            )
            if mark != tapped:
                flags.append(
                    f"tap on {tuple(tapped)} read mark {None if mark is None else tuple(mark)}"
                )


def draw(run_dir: Path, out: Path, cycle: Row) -> str | None:
    """Draw the units, the tap mark and the gesture of the cycle on its frame. The full frame
    of --keep-frames is used when it is there, else the small frame of the cycle line."""
    record: MapReadingRecord | None = cycle.pop("_reading", None)
    image = cv2.imread(str(run_dir / "stream" / f"{cycle['frame_seq']:06d}.png"))
    if image is None:
        image = cv2.imread(str(run_dir / "frames" / cycle["frame"]))
    if image is None:
        return None
    scale = image.shape[1] / SCREEN[0]

    def at(point: tuple[int, int]) -> tuple[int, int]:
        return round(point[0] * scale), round(point[1] * scale)

    def outline(
        corners: tuple[tuple[int, int], ...], color: tuple[int, int, int], width: int
    ) -> None:
        points = np.array([at(corner) for corner in corners], np.int32)
        cv2.polylines(image, [points], True, color, max(1, round(width * scale)))

    if record is not None and record.still.frame_seq == cycle["frame_seq"]:
        reading = record.reading
        for unit in reading.units:
            place = reading.places.get(unit.pos)
            if place is not None:
                outline(place.corners, (0, 200, 0) if unit.controllable else (0, 0, 230), 3)
        if reading.tap_mark is not None and reading.tap_mark.cell in reading.places:
            outline(reading.places[reading.tap_mark.cell].corners, (255, 255, 0), 6)
        gesture = cycle.get("map", {}).get("logged", {}).get("gesture")
        if (
            gesture is not None
            and gesture["kind"] == "map_tap"
            and tuple(gesture["cell"]) in reading.places
        ):
            centre = reading.places[tuple(gesture["cell"])].center
            cv2.circle(
                image,
                at(centre),
                max(1, round(30 * scale)),
                (0, 255, 255),
                max(1, round(5 * scale)),
            )
    draw_gesture(image, cycle["gesture"])
    height, width = image.shape[:2]
    thumb = cv2.resize(
        image, (THUMB_WIDTH, round(height * THUMB_WIDTH / width)), interpolation=cv2.INTER_AREA
    )
    name = f"{cycle['frame_seq']:06d}.jpg"
    cv2.imwrite(str(out / name), thumb, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return f"analysis/{name}"


def draw_gesture(image: np.ndarray, text: str | None) -> None:
    """Draw the gesture of a cycle line, 'tap X,Y' or 'swipe X,Y->X,Y Ds' in screen shares."""
    if not text:
        return
    height, width = image.shape[:2]

    def point(pair: str) -> tuple[int, int]:
        x, y = pair.split(",")
        return round(float(x) * width), round(float(y) * height)

    thick = max(2, round(6 * width / SCREEN[0]))
    kind, _, rest = text.partition(" ")
    if kind == "tap":
        cv2.circle(image, point(rest), max(4, round(24 * width / SCREEN[0])), (0, 0, 255), thick)
    elif kind == "swipe":
        start, end = rest.split()[0].split("->")
        cv2.arrowedLine(image, point(start), point(end), (0, 0, 255), thick, tipLength=0.08)


def page(summary: Row, cycles: list[Row]) -> str:
    head = " · ".join(f"{key} {html.escape(str(value))}" for key, value in summary.items())
    lines = [
        "<!doctype html><meta charset='utf-8'>",
        f"<title>Run {html.escape(summary['run'])}</title>",
        "<style>",
        "body{font:14px system-ui,sans-serif;margin:16px;background:#fff;color:#111}",
        "table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px;vertical-align:top}",
        "tr.flagged{background:#fff3e0}.flag{color:#b00020}code{font-size:12px}",
        "body.only tr.plain{display:none}",
        "@media (prefers-color-scheme:dark){body{background:#121212;color:#eee}",
        "td,th{border-color:#444}tr.flagged{background:#3a2a10}.flag{color:#ff8a80}}",
        "</style>",
        f"<h1>Run {html.escape(summary['run'])}</h1><p>{head}</p>",
        "<label><input type=checkbox onchange=\"document.body.classList.toggle('only',this.checked)\">"
        " flagged cycles only</label>",
        "<table><tr><th>cycle</th><th>frame</th><th>screen</th><th>step</th><th>map</th><th>flags</th></tr>",
    ]
    for cycle in cycles:
        plan = cycle.get("map")
        judgment = None if plan is None else plan["judgment"]
        map_cell = ""
        if plan is not None:
            map_cell = f"tap {plan['tap']}<br>"
            if judgment is not None:
                map_cell += (
                    f"{judgment['columns']}×{judgment['rows']} units {judgment['units']}"
                    f" uncertain {judgment['uncertain']}<br>current {judgment['current']}"
                    f" centre {judgment['centre']}<br>targets {judgment['targets']}"
                )
            if not plan["replay_same"]:
                map_cell += f"<br>replayed <code>{html.escape(json.dumps(plan['replayed']))}</code>"
        thumb = cycle.get("thumb")
        image = f"<img src='{thumb}' width={THUMB_WIDTH} loading=lazy>" if thumb else ""
        flags = "<br>".join(
            f"<span class=flag>{html.escape(item)}</span>" for item in cycle["flags"]
        )
        lines.append(
            f"<tr id=c{cycle['cycle']} class={'flagged' if cycle['flags'] else 'plain'}>"
            f"<td>#{cycle['cycle']}<br>seq {cycle['frame_seq']}</td><td>{image}</td>"
            f"<td>seen {html.escape(str(cycle['interpreted']))}<br>believed {html.escape(str(cycle['believed']))}"
            f"<br>expected {html.escape(', '.join(cycle['expected']))}<br>matched {cycle['matched']}</td>"
            f"<td>{html.escape(str(cycle['step']))}<br><code>{html.escape(str(cycle['gesture']))}</code></td>"
            f"<td>{map_cell}</td><td>{flags}</td></tr>"
        )
    lines.append("</table>")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
