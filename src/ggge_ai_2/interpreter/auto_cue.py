from __future__ import annotations

from dataclasses import dataclass, replace

from ggge_ai_2.interpreter.contract import Interpreter, Screen, Situation
from ggge_ai_2.interpreter.elements.auto_key import auto_mode
from ggge_ai_2.stream.contract import Frame

# The enemy turn is left out because the button can look lit there.
AUTO_SCREENS = frozenset(
    {
        Screen.PLAYER_PHASE_OVERVIEW,
        Screen.SELECT_ACTION_IN_BATTLE,
        Screen.SELECT_WEAPON_IN_BATTLE,
        Screen.SELECT_WEAPON_IN_ATTACK_PREPARE,
        Screen.BATTLE_PREP_ATTACK,
        Screen.BATTLE_PREP_RESPONSE_ATTACK,
        Screen.BATTLE_INFO_PREVIEW,
        Screen.CHALLENGE_BATTLE_CHECK,
    }
)


@dataclass(frozen=True)
class AutoCueInterpreter:
    inner: Interpreter

    def interpret(self, frame: Frame, candidates: frozenset[Screen]) -> Situation | None:
        situation = self.inner.interpret(frame, candidates)
        if situation is None:
            return None
        auto = auto_mode(frame.image) if situation.screen in AUTO_SCREENS else None
        return replace(situation, auto=auto)
