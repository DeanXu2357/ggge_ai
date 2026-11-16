from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType

import cv2

from ggge_ai_2.stream.contract import Frame, Instant, Observation, Stream

log = logging.getLogger(__name__)

INDEX = "frames.csv"
# Level 1 writes a frame in about 75 ms. Higher levels save little space on game frames.
PNG_COMPRESSION = 1


@dataclass
class KeptStream:
    """Keep each frame that 'latest' or 'settled' returns as '<seq>.png', and its time in
    'frames.csv'.

    One worker thread writes the files, so neither method waits for the disk and the
    files come out in the order of 'seq'. Leave the 'with' block to write the remaining
    frames.
    """

    inner: Stream
    directory: Path
    _writer: ThreadPoolExecutor = field(
        default_factory=lambda: ThreadPoolExecutor(max_workers=1), init=False
    )

    def __enter__(self) -> KeptStream:
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / INDEX).write_text("seq,captured_at\n")
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        self._writer.shutdown(wait=True)

    def latest(self) -> Frame:
        frame = self.inner.latest()
        self._writer.submit(self._write, frame)
        return frame

    def settled(self, after: Instant, deadline: Instant) -> Observation:
        # Warning: only the returned frame is kept. The frames that the inner stream compares
        # before it are not kept.
        observation = self.inner.settled(after, deadline)
        self._writer.submit(self._write, observation.frame)
        return observation

    def _write(self, frame: Frame) -> None:
        # The worker keeps an exception in a future that nobody reads, so the failure is
        # logged here.
        try:
            if not cv2.imwrite(
                str(self.directory / f"{frame.seq:06d}.png"),
                frame.image,
                [cv2.IMWRITE_PNG_COMPRESSION, PNG_COMPRESSION],
            ):
                raise OSError("cv2.imwrite returned False")
            with (self.directory / INDEX).open("a") as index:
                index.write(f"{frame.seq},{frame.captured_at}\n")
        except Exception:
            log.exception("frame not kept", extra={"frame_seq": frame.seq})
