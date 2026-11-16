from __future__ import annotations

from dataclasses import dataclass, replace

from ggge_ai_2.interpreter.contract import Interpreter, Screen, Situation, UnitList
from ggge_ai_2.interpreter.elements.unit_list import UnitListButton, unit_list
from ggge_ai_2.stream.contract import Frame

UNIT_LIST_SCREENS = frozenset({Screen.PLAYER_PHASE_OVERVIEW})


@dataclass(frozen=True)
class UnitListCueInterpreter:
    inner: Interpreter

    def interpret(self, frame: Frame, candidates: frozenset[Screen]) -> Situation | None:
        situation = self.inner.interpret(frame, candidates)
        if situation is None:
            return None
        button = (
            unit_list(frame.image)
            if situation.screen in UNIT_LIST_SCREENS
            else UnitListButton.ABSENT
        )
        state = None if button is UnitListButton.ABSENT else UnitList(button.value)
        return replace(situation, unit_list=state)
