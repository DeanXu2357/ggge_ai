from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from ggge_ai_2.interpreter.contract import ALL_SCREENS
from ggge_ai_2.stream.contract import Frame
from ggge_ai_2.uisim.contract import Screen, ScreenIs, UiFact, UiState
from ggge_ai_2.verdict import Verdict


@dataclass
class LabeledInterpreter:
    """Reads the image code that 'fakes.stream.frames' writes into each frame."""

    labels: Mapping[int, UiState]
    interpreted: list[int] = field(default_factory=list)

    def _label(self, frame: Frame) -> UiState | None:
        return self.labels.get(int(frame.image.flat[0]))

    def interpret(
        self, frame: Frame, candidates: frozenset[Screen] = ALL_SCREENS
    ) -> UiState | None:
        self.interpreted.append(frame.seq)
        shown = self._label(frame)
        return shown if shown is not None and shown.screen in candidates else None

    def verify(self, frame: Frame, fact: UiFact) -> Verdict:
        shown = self._label(frame)
        if shown is None:
            return Verdict.UNREADABLE
        if isinstance(fact, ScreenIs):
            holds = shown.screen is fact.screen and shown.overlays == fact.overlays
        else:
            holds = shown.map_mode is fact.mode
        return Verdict.HOLDS if holds else Verdict.DOES_NOT_HOLD
