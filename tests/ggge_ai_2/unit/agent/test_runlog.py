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
        time=12.5,
        interpreted="sortie_prep",
        believed="story_stage_list",
        caller=None,
        auto=True,
        passing=None,
        expected=("sortie_prep", "ap_recovery_overlay"),
        matched=False,
        outside_candidates=True,
        step="open_info",
        gesture="tap 0.432,0.504",
        frame=f"{frame_seq:06d}.jpg",
    )


def shot(seq: int) -> Frame:
    return Frame(np.full((1080, 2340, 3), 200, np.uint8), 12.5, seq)


def test_record_appends_one_json_line_per_entry(tmp_path: Path):
    runlog = RunLog(tmp_path / "run")

    runlog.record(entry(1), shot(1))
    runlog.record(entry(2), shot(2))

    lines = (tmp_path / "run" / "steps.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [
        {**asdict(entry(seq)), "expected": ["sortie_prep", "ap_recovery_overlay"]} for seq in (1, 2)
    ]
    assert json.loads(lines[0])["time"] == 12.5
    assert json.loads(lines[0])["gesture"] == "tap 0.432,0.504"
    assert json.loads(lines[0])["frame"] == "000001.jpg"


def test_record_writes_a_thumbnail_for_every_entry_and_no_full_size_frame(tmp_path: Path):
    runlog = RunLog(tmp_path / "run")

    runlog.record(entry(1), shot(1))
    runlog.record(entry(2), shot(2))

    frames = tmp_path / "run" / "frames"
    assert sorted(path.name for path in frames.iterdir()) == ["000001.jpg", "000002.jpg"]
    thumbnail = cv2.imread(str(frames / "000001.jpg"))
    assert thumbnail is not None
    assert thumbnail.shape == (360, 780, 3)


def test_save_frame_writes_the_frame_under_its_sequence_number(tmp_path: Path):
    runlog = RunLog(tmp_path / "run")
    image = np.full((4, 6, 3), 200, np.uint8)

    runlog.save_frame(Frame(image, 1.0, 42))

    saved = cv2.imread(str(tmp_path / "run" / "frames" / "000042.png"))
    assert saved is not None
    assert np.array_equal(saved, image)
