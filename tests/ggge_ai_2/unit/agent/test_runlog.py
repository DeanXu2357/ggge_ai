from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from ggge_ai_2.agent.runlog import RunLog, StepRecord
from ggge_ai_2.stream.contract import Frame


def entry(frame_seq: int) -> StepRecord:
    return StepRecord(
        frame_seq=frame_seq,
        interpreted="sortie_prep",
        believed="story_stage_list",
        caller=None,
        auto=True,
        passing=None,
        expected=("sortie_prep", "ap_recovery_overlay"),
        matched=False,
        outside_candidates=True,
        step="open_info",
    )


def test_record_appends_one_json_line_per_entry(tmp_path: Path):
    runlog = RunLog(tmp_path / "run")

    runlog.record(entry(1))
    runlog.record(entry(2))

    lines = (tmp_path / "run" / "steps.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [
        {**asdict(entry(seq)), "expected": ["sortie_prep", "ap_recovery_overlay"]} for seq in (1, 2)
    ]


def test_save_frame_writes_the_frame_under_its_sequence_number(tmp_path: Path):
    runlog = RunLog(tmp_path / "run")
    image = np.full((4, 6, 3), 200, np.uint8)

    runlog.save_frame(Frame(image, 1.0, 42))

    saved = cv2.imread(str(tmp_path / "run" / "frames" / "000042.png"))
    assert saved is not None
    assert np.array_equal(saved, image)
