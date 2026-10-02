from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ggge_ai_2.stream.contract import Frame, FramePoint


class SightingKind(StrEnum):
    UNIT = "unit"
    FILL = "fill"
    BORDER = "border"


@dataclass(frozen=True)
class Sighting:
    kind: SightingKind
    point: FramePoint


@dataclass(frozen=True)
class MapReading:
    frame_seq: int
    row_lines: tuple[float, ...]
    column_lines: tuple[float, ...]
    sightings: tuple[Sighting, ...]


class MapParser(Protocol):
    def parse(self, frame: Frame) -> MapReading: ...
