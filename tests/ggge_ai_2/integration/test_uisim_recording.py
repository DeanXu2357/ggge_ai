from __future__ import annotations

import json
from pathlib import Path

import pytest

from ggge_ai_2.uisim.contract import Observed, UiScreen, UiState
from ggge_ai_2.uisim.stage_sim import PASS_THROUGH_KINDS, StageUiSim
from ggge_ai_2.uisim.stages import load_stages

ROOT = Path(__file__).resolve().parents[3]
STAGES = ROOT / "assets" / "ui_stages" / "stages.json"
RECORDING = ROOT / "data" / "ui_recordings" / "20261014-234132" / "discovery"
LABELS = (RECORDING / "run5" / "labels.jsonl", RECORDING / "run6" / "labels.jsonl")

_SKIP_FLOW_GAP = (
    "the skip flow ('略過') is out of scope for #109; "
    "skip_stage_overlay was not sampled as a stable frame before skip_result_list"
)

KNOWN_GAPS: dict[tuple[int, int], str] = {
    (424, 428): (
        "event_stage_list to eternal_stage_list through stage_chosen; "
        "the middle screens exist only as transition frames, "
        "and event stages are out of scope for #109"
    ),
    (1769, 1777): (
        "series_list to story_stage_list; series_stage_info was not sampled as a stable frame"
    ),
    (1778, 1782): _SKIP_FLOW_GAP,
    (1785, 1787): _SKIP_FLOW_GAP,
    (1792, 1799): _SKIP_FLOW_GAP,
    (1802, 1804): _SKIP_FLOW_GAP,
}

Step = tuple[int, int, str, str]


def _rows() -> list[tuple[int, str]]:
    merged: dict[int, dict[str, object]] = {}
    for path in LABELS:
        if not path.exists():
            pytest.skip(f"recording labels are missing: {path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                merged[row["index"]] = row
    return [
        (index, str(row["screen"]))
        for index, row in sorted(merged.items())
        if not row["transition"]
    ]


def _disallowed_steps(sim: StageUiSim, rows: list[tuple[int, str]]) -> list[Step]:
    screen_values = {screen.value for screen in UiScreen}
    disallowed: list[Step] = []
    state: UiState | None = None
    previous_index = -1
    for index, name in rows:
        screen_def = sim.stages.screens.get(name)
        if screen_def is not None and screen_def.kind in PASS_THROUGH_KINDS:
            continue
        if name not in screen_values:
            state = None
            continue
        screen = UiScreen(name)
        if state is None:
            state = UiState(screen)
        elif screen != state.screen:
            following = next(
                (
                    outcome.then
                    for operation in sim.successors(state)
                    for outcome in operation.outcomes
                    if outcome.then.screen == screen
                ),
                None,
            )
            if following is None:
                disallowed.append((previous_index, index, state.screen.value, name))
                following = sim.sync(state, Observed(screen))
            state = following
        previous_index = index
    return disallowed


def test_recorded_visit_sequence_is_allowed_by_uisim():
    sim = StageUiSim(load_stages(STAGES))

    disallowed = _disallowed_steps(sim, _rows())

    unknown = [step for step in disallowed if step[:2] not in KNOWN_GAPS]
    lines = [
        f"{before} -> {after}: {source} -> {target}" for before, after, source, target in unknown
    ]
    assert not unknown, f"{len(unknown)} disallowed steps:\n" + "\n".join(lines)
    occurring = {step[:2] for step in disallowed}
    stale = [pair for pair in KNOWN_GAPS if pair not in occurring]
    stale_lines = [f"{before} -> {after}" for before, after in stale]
    assert not stale, f"{len(stale)} known gaps no longer occur:\n" + "\n".join(stale_lines)
