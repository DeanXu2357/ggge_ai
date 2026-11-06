from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field

from ggge_ai_2.interpreter.contract import Screen, Situation
from ggge_ai_2.interpreter.screens import QUICK_CHECKS, QuickCheck
from ggge_ai_2.stream.contract import Frame

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class OpenCvInterpreter:
    quick_checks: Mapping[Screen, QuickCheck] = field(default_factory=lambda: QUICK_CHECKS)

    def interpret(self, frame: Frame, candidates: frozenset[Screen]) -> Situation | None:
        passed = sorted(
            screen
            for screen in candidates
            if screen in self.quick_checks and self.quick_checks[screen](frame.image)
        )
        if len(passed) == 1:
            return Situation(frame.seq, passed[0])
        log.info(
            "quick check undecided",
            extra={
                "frame_seq": frame.seq,
                "passed": [screen.value for screen in passed],
                "candidates": sorted(screen.value for screen in candidates),
            },
        )
        return None
