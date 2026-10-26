from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ggge_ai_2.interpreter.contract import AutoMode

LABELED = Path(__file__).resolve().parents[2] / "data" / "labeled"
CASES = LABELED / "cases.jsonl"
FRAMES = LABELED / "frames"


@dataclass(frozen=True)
class Case:
    id: str
    source: str
    index: int
    file: str
    t: float | None
    sha256: str
    screen: str
    transition: bool
    auto: AutoMode | None
    power_save: str | None


@functools.cache
def cases() -> tuple[Case, ...]:
    rows = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line]
    return tuple(_case(row) for row in rows)


def _case(row: dict[str, object]) -> Case:
    auto = row["auto"]
    return Case(
        id=str(row["id"]),
        source=str(row["source"]),
        index=int(str(row["index"])),
        file=str(row["file"]),
        t=None if row["t"] is None else float(str(row["t"])),
        sha256=str(row["sha256"]),
        screen=str(row["screen"]),
        transition=row["transition"] is True,
        auto=None if auto is None else AutoMode(str(auto)),
        power_save=None if row["power_save"] is None else str(row["power_save"]),
    )


def load_image(case: Case) -> np.ndarray:
    path = FRAMES / case.file
    image = cv2.imread(str(path))
    if image is None:
        raise FileNotFoundError(path)
    return np.asarray(image)
