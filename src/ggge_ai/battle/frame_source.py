"""Frame acquisition boundary for the full-map scan (定案 1-4 的取圖段).

A FrameSource produces the frame series the board reader consumes;
acquisition (live serpentine, fixture replay, future zoom variants)
swaps freely behind the one contract. Navigation may read the screen to
steer itself, but interpretation only ever sees the emitted series:
frames, pan-direction hints, and the navigator's measured pan shifts.

`measured_shift` is the screen displacement of map content from the
previous frame to this one (a fixed map point at screen p appears at
p + shift), i.e. the negated camera delta. Panning "up" moves content
down, so hint "up" pairs with a positive-y shift. Shifts are what the
live navigator already measures per leg (定案 3: gestures are requests,
positions come from the screen); fixtures may omit them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

HINT_KEYS = ("up", "down", "left", "right")


def hint_from_label(label: str) -> str | None:
    for key in HINT_KEYS:
        if f"pan_{key}" in label:
            return key
    return None


@dataclass
class MapFrame:
    image: np.ndarray
    hint: str | None = None
    label: str = ""
    measured_shift: tuple[float, float] | None = None


class FrameSource(Protocol):
    def collect(self) -> list[MapFrame]: ...


class FixtureFrameSource:
    """Replays a captured manifest series (offline tests and replay
    tooling); hints come from the manifest labels, shifts are absent."""

    def __init__(self, series_dir: Path | str):
        self.series_dir = Path(series_dir)

    def collect(self) -> list[MapFrame]:
        manifest = json.loads(
            (self.series_dir / "manifest.json").read_text(encoding="utf-8")
        )
        entries = sorted(manifest["frames"], key=lambda f: f["seq"])
        out: list[MapFrame] = []
        for entry in entries:
            image = cv2.imread(str(self.series_dir / entry["image"]))
            if image is None:
                raise FileNotFoundError(f"unreadable frame: {entry['image']}")
            out.append(
                MapFrame(
                    image=image,
                    hint=hint_from_label(entry["label"]),
                    label=entry["label"],
                )
            )
        return out
