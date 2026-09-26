from __future__ import annotations

from typing import Protocol

from ggge_ai_2.stream.contract import Frame
from ggge_ai_2.uisim.contract import UiFact, UiState
from ggge_ai_2.verdict import Verdict


class Interpreter(Protocol):
    def interpret(self, frame: Frame) -> UiState | None: ...

    def verify(self, frame: Frame, fact: UiFact) -> Verdict:
        """Check one fact on this frame only.

        Do not ask for a fact that the frame cannot show. A fact that needs more than
        one screen is the work of the agent, over more than one cycle.
        """
        ...
