"""BattleController2: the flow-layer tick loop. A new entry point beside the
legacy battle/controller.py (定案 5: the Round 1.x live winners do not go back on
the table) that drives the map-setup dance as sense -> plan -> act -> verify ->
re-sense over the ``goap`` A*.

The loop is a single level: one keyguard chore, one capture, one judgment entry
and one queue step per tick. The action queue survives across ticks; planning
is a restock event that fires only when the queue empties, never a per-iteration
ritual (the 2026-07-24 flat persistent-queue settlement -- the Round 2.0 nested
plan/execute pair had degenerated into a controller-1 router). Each tick
confirms the previous tick's action against the freshly sensed frame: the
declared effect holding keeps the queue, an unplanned diff off the remaining
plan's dependencies is recorded and the queue keeps going (定案 2's simplest
split), a diff onto a dependency (or a stall) drops the queue for a replan.
Observability is a first-class deliverable (定案 4): an unexpected screen is
always recorded as "we were not prepared for this" with native evidence, never
silently swallowed into a retry spin.

No interrupt router (定案 7): every off-vocabulary screen goes through the GOAP
vocabulary; the keyguard stays a tick pre-chore. A screen the vocabulary cannot
name resolves to unknown and, absent a clearable obstruction, is waited out then
honestly aborted with a native diag frame -- evidence for the next vocabulary
round, not a hard workaround.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ...goap.action import Goal
from ...goap.planner import PlanNotFound, plan
from ...goap.state import Value, WorldState
from . import vocabulary
from .actions import REPAIR_NAV_ACTIONS, FlowContext

log = logging.getLogger(__name__)


@dataclass
class FlowConfig:
    max_replans: int = 40
    max_consecutive_failures: int = 3
    settle_delay_s: float = 0.5
    max_unknown_waits: int = 90
    unknown_wait_s: float = 2.0
    diag_every: int = 3


def _diff_keys(before: Mapping[str, Value], after: Mapping[str, Value]) -> set[str]:
    keys = set(before.keys()) | set(after.keys())
    return {k for k in keys if before.get(k) != after.get(k)}


class BattleController2:
    """Drives one flow goal to satisfaction (or an honest abort). ``ledger_log``
    mirrors CoverageScanSource.ledger_log (``log(kind, **data)``) and may be
    None; ``diag_save(frame, tag) -> path`` stashes a native unknown-frame and
    may be None; ``progress`` supplies the blackboard's progress predicates each
    tick (Round 2.1 wires the run blackboard here)."""

    def __init__(
        self,
        perception,
        actuator,
        *,
        actions=REPAIR_NAV_ACTIONS,
        translator: Callable[..., WorldState] | None = None,
        progress: Callable[[], Mapping[str, Value]] | None = None,
        pincher=None,
        keyguard=None,
        ledger_log: Callable[..., None] | None = None,
        diag_save: Callable[[object, str], str | None] | None = None,
        config: FlowConfig | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.perception = perception
        self.actuator = actuator
        self.actions = list(actions)
        self.translator = translator or (
            lambda frame, probe, prog: vocabulary.translate(frame, probe, prog)
        )
        self.progress = progress
        self.pincher = pincher
        self.keyguard = keyguard
        self.ledger_log = ledger_log
        self.diag_save = diag_save
        self.config = config or FlowConfig()
        self._sleep = sleep or time.sleep

    def _log(self, kind: str, **data) -> None:
        if self.ledger_log is not None:
            self.ledger_log(kind, **data)

    def _sense(self) -> tuple[object, WorldState]:
        frame = self.perception.capture()
        prog = self.progress() if self.progress is not None else None
        state = self.translator(frame, self.perception.probe, prog)
        return frame, state

    def _context(self, frame) -> FlowContext:
        return FlowContext(
            perception=self.perception,
            actuator=self.actuator,
            frame=frame,
            pincher=self.pincher,
            keyguard=self.keyguard,
            log=self.ledger_log,
            sleep=self._sleep,
        )

    @staticmethod
    def _plan_deps(remaining, goal: Goal) -> set[str]:
        """Keys the rest of the plan (and the goal) depend on. An unplanned
        change that misses all of these cannot invalidate the remaining plan, so
        the loop keeps the same plan; a change that hits one triggers a replan."""
        deps: set[str] = set()
        for action in remaining:
            deps.update(action.preconditions.keys())
        deps.update(getattr(goal, "conditions", {}).keys())
        return deps

    def _judge(self, pending, state) -> str:
        """Confirm the previous tick's action against the freshly sensed state.

        Returns the queue verdict: ``confirmed`` (the declared effect holds),
        ``diverted_keep`` (an unplanned but harmless diff -- the same plan may
        keep going), ``diverted_replan`` (an unplanned diff hit a key the rest
        of the plan or the goal depends on), or ``stalled`` (the world did not
        move). The unplanned_transition ledger event is emitted here (定案 4);
        the failure counter and abort live in ``run`` where the config is."""
        action, deps, before, ok = pending
        if ok and state.satisfies(action.effects):
            return "confirmed"
        diff = _diff_keys(before, state)
        if diff:
            self._log(
                "unplanned_transition",
                action=action.name,
                from_state=dict(before),
                to_state=dict(state),
                diff=sorted(diff),
            )
            return "diverted_replan" if diff & deps else "diverted_keep"
        return "stalled"

    def run(self, goal: Goal) -> bool:
        cfg = self.config
        replans = 0
        failures = 0
        unknown_waits = 0

        queue = []  # remaining plan steps, alive across ticks
        pending = None  # last-executed action + its deps/from-state/ok, judged next tick

        while replans <= cfg.max_replans:
            if self.keyguard is not None:
                self.keyguard.ensure_unlocked()
            frame, state = self._sense()
            self._log("flow_tick", state=dict(state))

            if goal.is_satisfied(state):
                log.info("flow goal %s satisfied", goal.name)
                return True

            if pending is not None:
                verdict = self._judge(pending, state)
                judged = pending[0]
                pending = None
                if verdict == "stalled":
                    failures += 1
                    log.warning("flow: %s made no progress (failures=%d)", judged.name, failures)
                    if failures >= cfg.max_consecutive_failures:
                        self._log(
                            "flow_abort", reason="stuck", action=judged.name, state=dict(state)
                        )
                        return False
                    queue = []  # replan
                else:
                    failures = 0
                    if verdict == "diverted_replan":
                        queue = []  # the change may invalidate the rest of the plan

            clearable = state.get(vocabulary.OBSTRUCTION) in vocabulary.CLEARABLE_OBSTRUCTIONS
            if state.get(vocabulary.VIEW) == vocabulary.UNKNOWN and not clearable:
                # a genuinely opaque frame (story/animation/transition): wait it
                # out rather than plan from a misread state. A clearable
                # obstruction on an unknown frame does NOT wait -- it replans.
                queue = []
                unknown_waits += 1
                if unknown_waits > cfg.max_unknown_waits:
                    log.error("flow: view stayed unknown too long, aborting")
                    self._log("flow_abort", reason="view_unknown_timeout", state=dict(state))
                    return False
                if self.diag_save is not None and unknown_waits % cfg.diag_every == 0:
                    path = self.diag_save(frame, f"flow_unknown_{unknown_waits}")
                    self._log("flow_unknown", frame_path=path, wait=unknown_waits)
                self._sleep(cfg.unknown_wait_s)
                continue
            unknown_waits = 0

            if not queue:
                try:
                    result = plan(state, goal, self.actions)
                except PlanNotFound as exc:
                    log.error("flow: no plan from %r to %s", state, goal.name)
                    self._log(
                        "flow_abort",
                        reason="plan_not_found",
                        state=dict(state),
                        expanded=exc.expanded,
                        exhausted=exc.exhausted,
                    )
                    return False
                queue = list(result.actions)
                replans += 1
                self._log("flow_plan", plan=[a.name for a in queue], cost=result.total_cost)

            action = queue.pop(0)
            deps = self._plan_deps(queue, goal)
            ctx = self._context(frame)
            log.info("flow executing %s", action.name)
            ok = action.execute(ctx)
            self._sleep(cfg.settle_delay_s)
            pending = (action, deps, state, ok)

        log.error("flow: replan limit reached")
        self._log("flow_abort", reason="replan_limit")
        return False
