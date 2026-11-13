from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ggge_ai_2.interpreter.contract import Phase, Screen, Situation
from ggge_ai_2.interpreter.elements.contract import ElementDetector
from ggge_ai_2.interpreter.seen_map import seen_map
from ggge_ai_2.mapparser.contract import MapParser, MapScope
from ggge_ai_2.screenmodel.contract import ScreenModel
from ggge_ai_2.stream.contract import Frame


@dataclass(frozen=True)
class ElementFirstInterpreter:
    detectors: Sequence[ElementDetector]
    model: ScreenModel
    mapparser: MapParser

    # Warning: the candidates are not used until task I3 of roadmap section 8.14.
    def interpret(self, frame: Frame, candidates: frozenset[Screen]) -> Situation | None:
        elements = [found for detector in self.detectors for found in detector.detect(frame.image)]
        judgment = self.model.judge(elements)
        if judgment.screen is None:
            return None
        reading = (
            None
            if judgment.map is None
            else self.mapparser.parse(frame, MapScope(judgment.occlusion, judgment.map.chevrons))
        )
        return Situation(
            frame.seq,
            Screen(judgment.screen.value),
            phase=None if judgment.phase is None else Phase(judgment.phase.value),
            turn=judgment.turn,
            map=None if reading is None else seen_map(reading),
        )
