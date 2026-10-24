from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pytest

from ggge_ai_2.interpreter.contract import Screen, Situation
from ggge_ai_2.interpreter.power_save_cue import (
    LOCK_ICON_REGION,
    LOCK_ICON_TEMPLATE,
    PowerSaveCueInterpreter,
    power_save_screen,
)
from ggge_ai_2.stream.contract import Frame

RUNS = Path(__file__).resolve().parents[4] / "data" / "runs"
LOCK_FRAME = RUNS / "20261024-180258" / "frames" / "000130.png"
DIM_FRAME = RUNS / "20261024-181550" / "frames" / "000006.png"


@dataclass
class _FakeInner:
    situation: Situation | None
    calls: list[int] = field(default_factory=list[int])

    def interpret(self, frame: Frame, candidates: frozenset[Screen]) -> Situation | None:
        self.calls.append(frame.seq)
        return self.situation


def _uniform(gray: int) -> np.ndarray:
    return np.full((1080, 2340, 3), gray, dtype=np.uint8)


def _load(path: Path) -> np.ndarray:
    if not path.exists():
        pytest.skip(f"run frame is missing: {path}")
    image = cv2.imread(str(path))
    assert image is not None
    return np.asarray(image)


def test_run_1_lock_frame_reads_lock() -> None:
    assert power_save_screen(_load(LOCK_FRAME)) is Screen.POWER_SAVE_LOCK


def test_run_2_dim_frame_reads_dim() -> None:
    assert power_save_screen(_load(DIM_FRAME)) is Screen.POWER_SAVE_DIM


def test_bright_frame_goes_to_the_inner() -> None:
    inner = _FakeInner(Situation(7, Screen.SERIES_LIST))
    frame = Frame(_uniform(100), captured_at=1.0, seq=7)

    situation = PowerSaveCueInterpreter(inner).interpret(frame, frozenset())

    assert power_save_screen(frame.image) is None
    assert situation == Situation(7, Screen.SERIES_LIST)
    assert inner.calls == [7]


def test_dark_frame_reads_dim_without_the_inner() -> None:
    inner = _FakeInner(Situation(7, Screen.SERIES_LIST))
    frame = Frame(_uniform(10), captured_at=1.0, seq=7)

    situation = PowerSaveCueInterpreter(inner).interpret(frame, frozenset())

    assert situation == Situation(7, Screen.POWER_SAVE_DIM, None)
    assert inner.calls == []


def test_lock_icon_in_a_dark_frame_reads_lock() -> None:
    template = cv2.imread(str(LOCK_ICON_TEMPLATE))
    assert template is not None
    image = _uniform(10)
    x, y, _, _ = LOCK_ICON_REGION
    h, w = template.shape[:2]
    image[y + 10 : y + 10 + h, x + 10 : x + 10 + w] = template
    inner = _FakeInner(None)
    frame = Frame(image, captured_at=1.0, seq=3)

    situation = PowerSaveCueInterpreter(inner).interpret(frame, frozenset())

    assert situation == Situation(3, Screen.POWER_SAVE_LOCK, None)
    assert inner.calls == []
