"""串流幀源的離線驗證：scrcpy 子程序與 v4l2 讀取端整組換成假件。"""

from __future__ import annotations

import time

import numpy as np
import pytest

from ggge_ai.runtime.journal import Journal
from ggge_ai.runtime.perceive import decode
from ggge_ai.stream import StreamCamera, StreamSource, StreamStarved


class FakeProcess:
    def __init__(self) -> None:
        self.stopped = False

    def terminate(self) -> None:
        self.stopped = True

    def kill(self) -> None:
        self.stopped = True

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def poll(self) -> int | None:
        return None


class FakeCapture:
    def __init__(self, frame: np.ndarray | None, ready: bool = True) -> None:
        self.current = frame
        self.released = False
        self.ready = ready

    def isOpened(self) -> bool:  # noqa: N802
        return self.ready

    def read(self):
        if self.current is None:
            return False, None
        return True, self.current

    def release(self) -> None:
        self.released = True


class Spawner:
    def __init__(self, capture: FakeCapture) -> None:
        self.capture_stub = capture
        self.processes: list[FakeProcess] = []
        self.opened: list[FakeCapture] = []

    def process(self, serial, video_device) -> FakeProcess:
        self.processes.append(FakeProcess())
        return self.processes[-1]

    def capture(self, video_device) -> FakeCapture:
        self.opened.append(self.capture_stub)
        return self.capture_stub


class FakeJournal:
    def __init__(self) -> None:
        self.frames: list[tuple[bytes | None, int]] = []
        self.records: list[tuple[str, dict]] = []

    def save_frame(self, frame: bytes | None, tick: int) -> str:
        self.frames.append((frame, tick))
        return "frames/000.png"

    def record(self, kind: str, **fields) -> None:
        self.records.append((kind, fields))


def frame_of(value: int) -> np.ndarray:
    return np.full((4, 4, 3), value, np.uint8)


def source_with(capture: FakeCapture, **kwargs) -> tuple[StreamSource, Spawner]:
    spawner = Spawner(capture)
    source = StreamSource(
        process_factory=spawner.process,
        capture_factory=spawner.capture,
        sleep=lambda seconds: None,
        **kwargs,
    )
    return source, spawner


def wait_for(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


def test_latest_returns_the_newest_frame_and_the_earlier_one_is_not_overwritten():
    capture = FakeCapture(frame_of(1))
    source, _ = source_with(capture)
    source.start()

    first = source.latest()
    capture.current = frame_of(2)
    assert wait_for(lambda: int(source.latest()[0, 0, 0]) == 2)
    source.stop()

    assert int(first[0, 0, 0]) == 1


def test_a_stale_frame_rebuilds_the_whole_stream():
    now = [100.0]
    source, spawner = source_with(FakeCapture(frame_of(3)), stale_after_s=1.0)
    source.clock = lambda: now[0]
    source.start()
    assert len(spawner.processes) == 1

    now[0] += 5.0
    frame = source.latest()
    source.stop()

    assert int(frame[0, 0, 0]) == 3
    assert len(spawner.processes) == 2
    assert spawner.opened[0].released


def test_a_source_that_never_yields_frames_starves():
    source, spawner = source_with(
        FakeCapture(None), first_frame_timeout_s=0.05, reconnect_tries=2
    )

    with pytest.raises(StreamStarved) as boom:
        source.start()
    source.stop()

    assert "/dev/video0" in str(boom.value)
    assert len(spawner.processes) == 3


def test_capture_is_reopened_until_the_v4l2_sink_is_ready():
    spawner = Spawner(FakeCapture(frame_of(5)))
    early = [FakeCapture(None, ready=False), FakeCapture(None, ready=False)]

    def capture(video_device):
        stub = early.pop(0) if early else spawner.capture_stub
        spawner.opened.append(stub)
        return stub

    source = StreamSource(
        process_factory=spawner.process,
        capture_factory=capture,
        sleep=lambda seconds: None,
    )
    source.start()
    frame = source.latest()
    source.stop()

    assert int(frame[0, 0, 0]) == 5
    assert len(spawner.processes) == 1
    assert [stub.released for stub in spawner.opened] == [True, True, True]


def test_starvation_cleans_up_the_process_and_the_capture():
    source, spawner = source_with(
        FakeCapture(None), first_frame_timeout_s=0.05, reconnect_tries=2
    )

    with pytest.raises(StreamStarved):
        source.start()

    assert all(process.stopped for process in spawner.processes)
    assert spawner.capture_stub.released


def test_screenshot_round_trips_through_decode_and_bumps_the_counters(tmp_path):
    source, _ = source_with(FakeCapture(frame_of(7)))
    source.start()
    camera = StreamCamera(source=source, journal=Journal(tmp_path / "sweep.jsonl"))

    raw = camera.screenshot()
    source.stop()

    assert camera.raw is raw
    assert camera.shots == 1
    assert decode(raw).shape == (4, 4, 3)
    assert int(decode(raw)[0, 0, 0]) == 7


def test_keep_writes_the_judging_frame_into_the_journal():
    source, _ = source_with(FakeCapture(frame_of(9)))
    source.start()
    journal = FakeJournal()
    camera = StreamCamera(source=source, journal=journal)
    camera.grab()

    path = camera.keep("card")
    camera.close()

    assert path == "frames/000.png"
    assert journal.frames == [(camera.raw, 1)]
    assert journal.records == [("frame", {"label": "card", "frame": "frames/000.png"})]


def test_stop_is_reentrant():
    source, spawner = source_with(FakeCapture(frame_of(1)))
    source.start()

    source.stop()
    source.stop()

    assert spawner.processes[0].stopped


def test_sweep_scan_knows_the_stream_flag(monkeypatch):
    from scripts import sweep_scan

    monkeypatch.setattr("sys.argv", ["sweep_scan", "--stage-node", "1,2", "--stream"])
    assert sweep_scan.parse_args().stream is True

    monkeypatch.setattr("sys.argv", ["sweep_scan", "--stage-node", "1,2"])
    assert sweep_scan.parse_args().stream is False
