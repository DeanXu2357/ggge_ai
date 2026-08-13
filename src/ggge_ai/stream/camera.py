"""串流組合層：把 StreamSource 組成 sweep 流程要的 camera 介面。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from ggge_ai.stream.source import StreamSource


@dataclass
class StreamCamera:
    """唯一幀源的串流版：grab 當下就編碼，keep 存下的就是判定用的那一張。"""

    source: StreamSource
    journal: Any
    raw: bytes | None = field(default=None, init=False)
    shots: int = field(default=0, init=False)

    def grab(self) -> np.ndarray:
        frame = self.source.latest()
        self.raw = cv2.imencode(".png", frame)[1].tobytes()
        self.shots += 1
        return frame

    def screenshot(self) -> bytes:
        self.grab()
        return self.raw

    def keep(self, label: str) -> str | None:
        path = self.journal.save_frame(self.raw, self.shots)
        self.journal.record("frame", label=label, frame=path)
        return path

    def close(self) -> None:
        self.source.stop()
