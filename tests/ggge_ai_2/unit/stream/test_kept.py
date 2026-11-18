from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from ggge_ai_2.stream.adb import AdbScreencapStream
from ggge_ai_2.stream.kept import KeptStream

IMAGES = [np.full((8, 8, 3), value, np.uint8) for value in (0, 128, 255)]


def test_keeps_each_frame_and_its_capture_time_in_seq_order(tmp_path: Path) -> None:
    images = iter(IMAGES)
    times = iter(range(100))
    inner = AdbScreencapStream(
        serial="SER", clock=lambda: float(next(times)), capture=lambda: next(images)
    )

    with KeptStream(inner, tmp_path) as stream:
        frames = [stream.latest() for _ in IMAGES]

    assert (tmp_path / "frames.csv").read_text().splitlines() == [
        "seq,captured_at",
        *(f"{frame.seq},{frame.captured_at}" for frame in frames),
    ]
    for frame in frames:
        kept = cv2.imread(str(tmp_path / f"{frame.seq:06d}.png"))
        assert kept is not None
        assert np.array_equal(kept, frame.image)


def test_logs_a_frame_that_it_cannot_write(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    inner = AdbScreencapStream(serial="SER", capture=lambda: IMAGES[0])
    stream = KeptStream(inner, tmp_path)
    with stream:
        (tmp_path / "frames.csv").unlink()
        (tmp_path / "frames.csv").mkdir()
        frame = stream.latest()

    assert [record.__dict__["frame_seq"] for record in caplog.records] == [frame.seq]


def test_keeps_the_frame_that_settled_returns(tmp_path: Path) -> None:
    times = iter(range(100))
    inner = AdbScreencapStream(
        serial="SER", clock=lambda: float(next(times)), capture=lambda: IMAGES[1]
    )

    with KeptStream(inner, tmp_path) as stream:
        observation = stream.settled(after=-1.0, deadline=100.0)

    assert (tmp_path / "frames.csv").read_text().splitlines() == [
        "seq,captured_at",
        f"{observation.frame.seq},{observation.frame.captured_at}",
    ]
