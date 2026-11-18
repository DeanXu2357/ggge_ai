from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ggge_ai_2.agent.contract import MapReadingRecord
from ggge_ai_2.interpreter.contract import Phase
from ggge_ai_2.mapparser.contract import MapReading
from ggge_ai_2.stream.contract import StillWindow


@dataclass
class MapReadingHistory:
    _records: list[MapReadingRecord] = field(default_factory=list[MapReadingRecord])

    def insert(
        self, still: StillWindow, reading: MapReading, phase: Phase | None, turn: int | None
    ) -> None:
        self._records.append(MapReadingRecord(still, reading, phase, turn))

    @property
    def records(self) -> Sequence[MapReadingRecord]:
        return tuple(self._records)
