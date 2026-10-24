from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2

from ggge_ai_2.stream.contract import Frame

THUMBNAIL_WIDTH = 780
THUMBNAIL_QUALITY = 80


@dataclass(frozen=True)
class StepRecord:
    frame_seq: int
    time: float
    interpreted: str | None
    believed: str
    caller: str | None
    auto: bool | None
    passing: str | None
    expected: tuple[str, ...]
    matched: bool | None
    outside_candidates: bool
    step: str | None
    gesture: str | None
    frame: str


def thumbnail_name(frame_seq: int) -> str:
    return f"{frame_seq:06d}.jpg"


class RunLog:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        (run_dir / "frames").mkdir(parents=True, exist_ok=True)

    def record(self, entry: StepRecord, frame: Frame) -> None:
        height, width = frame.image.shape[:2]
        size = (THUMBNAIL_WIDTH, max(1, round(height * THUMBNAIL_WIDTH / width)))
        thumbnail = cv2.resize(frame.image, size, interpolation=cv2.INTER_AREA)
        cv2.imwrite(
            str(self.run_dir / "frames" / entry.frame),
            thumbnail,
            [cv2.IMWRITE_JPEG_QUALITY, THUMBNAIL_QUALITY],
        )
        with (self.run_dir / "steps.jsonl").open("a", encoding="utf-8") as steps:
            steps.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")

    def save_frame(self, frame: Frame) -> None:
        cv2.imwrite(str(self.run_dir / "frames" / f"{frame.seq:06d}.png"), frame.image)
