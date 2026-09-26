from __future__ import annotations

from typing import Protocol

from ggge_ai_2.stream.contract import Frame
from ggge_ai_2.uisim.contract import Screen, UiFact, UiState
from ggge_ai_2.verdict import Verdict

ALL_SCREENS: frozenset[Screen] = frozenset(Screen)


class Interpreter(Protocol):
    def interpret(
        self, frame: Frame, candidates: frozenset[Screen] = ALL_SCREENS
    ) -> UiState | None:
        """Return the state whose screen is the closest candidate to this frame.

        Return None when no candidate is close enough. Without this threshold, an
        unmodeled popup reads as a known screen and the agent never halts on it.
        """
        ...

    def verify(self, frame: Frame, fact: UiFact) -> Verdict:
        """Check one fact on this frame only.

        Do not ask for a fact that the frame cannot show. A fact that needs more than
        one screen is the work of the agent, over more than one cycle.
        """
        ...
