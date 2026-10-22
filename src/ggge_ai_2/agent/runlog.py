from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2

from ggge_ai_2.stream.contract import Frame


@dataclass(frozen=True)
class StepRecord:
    frame_seq: int
    interpreted: str | None
    believed: str
    caller: str | None
    auto: bool | None
    passing: str | None
    expected: tuple[str, ...]
    matched: bool | None
    outside_candidates: bool
    step: str | None


class RunLog:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        (run_dir / "frames").mkdir(parents=True, exist_ok=True)

    def record(self, entry: StepRecord) -> None:
        with (self.run_dir / "steps.jsonl").open("a", encoding="utf-8") as steps:
            steps.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")

    def save_frame(self, frame: Frame) -> None:
        cv2.imwrite(str(self.run_dir / "frames" / f"{frame.seq:06d}.png"), frame.image)
