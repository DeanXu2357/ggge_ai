from __future__ import annotations

import logging
from dataclasses import dataclass

from ggge_ai_2.interpreter.contract import Interpreter, Screen, Situation
from ggge_ai_2.stream.contract import Frame

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoggedInterpreter:
    inner: Interpreter

    def interpret(self, frame: Frame, candidates: frozenset[Screen]) -> Situation | None:
        situation = self.inner.interpret(frame, candidates)
        log.info(
            "interpreted",
            extra={
                "frame_seq": frame.seq,
                "screen": None if situation is None else situation.screen.value,
            },
        )
        return situation
