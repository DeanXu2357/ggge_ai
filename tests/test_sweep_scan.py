"""點擊清算掃描主迴圈的組裝：本窗點完 → 沒得推就停 → 帳本收斂。

裝置整支換成假件（幀是全黑合成圖），完全不碰 adb。
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from ggge_ai.runtime import sweep
from ggge_ai.runtime.coverage import WorldGrid
from ggge_ai.runtime.journal import Journal
from scripts.sweep_scan import SweepRun

GRID = WorldGrid(phase=(0.0, 0.0), col_pitch=100.0, row_pitch=100.0)


def _blank() -> np.ndarray:
    return np.zeros((1080, 2340, 3), np.uint8)


def build_run(tmp_path, outcomes: dict) -> SweepRun:
    journal = Journal(tmp_path / "sweep.jsonl")
    camera = SimpleNamespace(grab=_blank, keep=lambda label: None, shots=0)
    run = SweepRun(
        device=SimpleNamespace(tap=lambda x, y: None),
        camera=camera,
        journal=journal,
        executor=None,
        driver=None,
        perceiver=None,
        gate=None,
        identifier=None,
        sleep=lambda seconds: None,
    )
    run.ledger = sweep.SweepLedger(grid=GRID)
    run.ledger.boundary.update(west=2, east=4, north=4, south=5)
    run.settled = _blank
    run.witness = lambda frame: None
    run.pan = lambda direction, frame: None
    run.relocate = lambda candidate=None: None
    run.escape = lambda: None
    run.on_hub = lambda: True
    run.tap_cell = lambda target, before: outcomes.get(
        target.cell, sweep.TapOutcome(sweep.TAP_EMPTY, marker=target.point)
    )
    return run


def test_the_loop_sentences_every_in_bounds_cell_and_then_stops(tmp_path):
    run = build_run(tmp_path, {})

    run.tour()

    assert run.ledger.complete
    assert run.ledger.taps == 0  # tap_cell 被假件接管，計數在它裡面
    assert set(run.ledger.cells_of(sweep.EMPTY)) == {
        (col, row) for col in (2, 3, 4) for row in (4, 5)
    }


def test_a_cell_with_no_feedback_twice_is_left_blank_as_unsure(tmp_path):
    silent = sweep.TapOutcome(sweep.TAP_NONE)
    run = build_run(tmp_path, {(3, 4): silent})

    run.tour()

    assert run.ledger.verdict((3, 4)) == sweep.UNSURE
    assert run.ledger.reasons[(3, 4)] == "no_feedback"
    assert run.ledger.complete


def test_a_card_interrupts_the_window_and_the_cell_is_sentenced_from_the_card(tmp_path):
    run = build_run(tmp_path, {(3, 4): sweep.TapOutcome(sweep.TAP_CARD)})
    seen: list[tuple[int, int]] = []
    run.sentence_card = lambda target: (
        seen.append(target.cell),
        run.ledger.record(target.cell, sweep.ENEMY, name="sig-a"),
    )

    run.tour()

    assert seen == [(3, 4)]
    assert run.ledger.verdict((3, 4)) == sweep.ENEMY
    assert run.ledger.complete


def test_the_tap_fuse_stops_the_loop_before_the_ledger_is_complete(tmp_path):
    run = build_run(tmp_path, {})
    run.max_taps = 0

    run.tour()

    assert not run.ledger.complete
    assert run.ledger.pending()
