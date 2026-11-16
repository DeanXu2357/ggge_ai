"""A probe on 'Plan.next' that logs its input and its output at the DEBUG level.

The judgment of mapgeom is a function of the evidence, so the log is enough to replay
it offline. The evidence only grows, so each input keeps only the newest map reading. The
values are in the JSON form of 'trace_json'.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable

from ggge_ai_2.agent.belief import Belief
from ggge_ai_2.agent.contract import Evidence, Step
from ggge_ai_2.agent.trace_json import encode_belief, encode_gesture, encode_record

log = logging.getLogger(__name__)


def traced[P](
    next_step: Callable[[P, Belief, Evidence], Step],
) -> Callable[[P, Belief, Evidence], Step]:
    @functools.wraps(next_step)
    def traced_next(plan: P, belief: Belief, evidence: Evidence) -> Step:
        if not log.isEnabledFor(logging.DEBUG):
            return next_step(plan, belief, evidence)
        name = type(plan).__name__
        records = evidence.map_readings
        log.debug(
            "plan input",
            extra={
                "plan": name,
                "belief": encode_belief(belief),
                "readings": len(records),
                "newest": encode_record(records[-1]) if records else None,
            },
        )
        step = next_step(plan, belief, evidence)
        log.debug(
            "plan output",
            extra={
                "plan": name,
                "step": step.name,
                "gesture": encode_gesture(step.gesture),
                "expected": [expected.ui.screen.value for expected in step.expected],
            },
        )
        return step

    return traced_next
