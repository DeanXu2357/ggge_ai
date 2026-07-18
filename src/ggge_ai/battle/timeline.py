"""Battle phase timeline: the process-scoped memory of control flow.

Owns what the scattered controller flags used to: the last confirmed
phase and the act -> verify contracts auditing every action a handler
fires (TRANSITIONS is the game's UI flow map, mechanism not content).
Pure state -- no captures, no taps: the controller feeds every
classified phase read into observe() and executes the returned ledger
intents; handlers report actions through acted() and query the rest.
The screen stays authoritative: observe() reports divergences, it never
vetoes a dispatch.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# the game's UI flow map, one entry per registered action:
# (targets, checks, retries) = phases the next confirmed read may legally
# land on, label-less reads budgeted before the contract expires (counted
# in reads, not wall time), and eaten-tap retries granted. battle_execute
# gets a generous budget (long battle animations, and a reaction popup's
# enemy turn continues afterwards); battle_prep is among its legal targets
# because consecutive reaction popups re-enter that screen.
TRANSITIONS: dict[str, tuple[tuple[str, ...], int, int]] = {
    "select_unit": (("unit_move", "weapon_select"), 8, 1),
    "open_weapon_select": (("weapon_select",), 8, 1),
    "attack": (("battle_prep",), 8, 1),
    "battle_execute": (("our_turn", "unit_move", "weapon_select", "battle_prep"), 20, 1),
    "standby": (("our_turn",), 12, 1),
}


@dataclass
class Expectation:
    """One act -> verify contract: after `action` (fired while `source` was
    on screen) the next confirmed phase should land in `targets`.

    Verdicts, checked against every phase read fed to observe():
    - observed in targets: transition verified.
    - observed == source: the tap was eaten (power-save lock, mid-animation
      UI) -- on_eaten repairs any handler flag that assumed success, so the
      reactive dispatch retries the action instead of walking a wrong branch.
    - observed is some other real phase: a miss. The screen is authoritative,
      so reality wins and the miss is only recorded as evidence that our
      transition model of the game is wrong somewhere.
    - no label at all: neutral (animations and overlays look like this);
      only `checks_left` label-less reads are budgeted before the contract
      expires as unverifiable."""

    action: str
    source: str | None
    targets: frozenset[str]
    checks_left: int
    on_eaten: Callable[[], None] | None = None
    retries_left: int = 1


@dataclass(frozen=True)
class TimelineEvent:
    """A ledger intent returned by observe(): the controller records it,
    attaching a fresh frame when with_frame asks for one."""

    kind: str
    data: dict
    with_frame: bool = False


@dataclass
class BattleTimeline:
    phase: str | None = None
    _expectation: Expectation | None = field(default=None, repr=False)

    def acted(self, action: str, on_eaten: Callable[[], None] | None = None) -> None:
        """A handler reports the action it just fired; the transition
        contract comes from the TRANSITIONS map, the source is the phase
        the screen last confirmed. One at a time: a newer action supersedes
        whatever contract was still open."""
        targets, checks, retries = TRANSITIONS[action]
        self._expectation = Expectation(
            action=action,
            source=self.phase,
            targets=frozenset(targets),
            checks_left=checks,
            on_eaten=on_eaten,
            retries_left=retries,
        )

    @property
    def expectation_open(self) -> bool:
        return self._expectation is not None

    def observe(self, phase: str | None) -> list[TimelineEvent]:
        """Digest one classified phase read (None = no label confirmed).
        Audits the open contract and returns the ledger intents; the
        confirmed phase is remembered as the source of later actions."""
        events = self._check_expectation(phase)
        if phase is not None:
            self.phase = phase
        return events

    def _check_expectation(self, phase: str | None) -> list[TimelineEvent]:
        exp = self._expectation
        if exp is None:
            return []
        if phase is None:
            exp.checks_left -= 1
            if exp.checks_left <= 0:
                log.warning(
                    "transition after %s unverifiable (no phase label for too long)", exp.action
                )
                self._expectation = None
                return [
                    TimelineEvent(
                        "expectation_expired",
                        {"action": exp.action, "expected": sorted(exp.targets)},
                        with_frame=True,
                    )
                ]
            return []
        if phase in exp.targets:
            log.info("transition verified: %s -> %s", exp.action, phase)
            events = [TimelineEvent("expectation_met", {"action": exp.action, "observed": phase})]
        elif phase == exp.source and exp.retries_left > 0:
            exp.retries_left -= 1
            log.warning("%s left the screen unchanged (tap eaten?), retrying", exp.action)
            if exp.on_eaten is not None:
                exp.on_eaten()
            return [TimelineEvent("expectation_retry", {"action": exp.action, "observed": phase})]
        elif phase == exp.source:
            log.warning("%s still stuck on %s after retrying, giving up on it", exp.action, phase)
            events = [
                TimelineEvent(
                    "expectation_expired",
                    {"action": exp.action, "expected": sorted(exp.targets), "observed": phase},
                    with_frame=True,
                )
            ]
        else:
            log.warning(
                "expected one of %s after %s, observed %s -- accepting the screen",
                sorted(exp.targets),
                exp.action,
                phase,
            )
            events = [
                TimelineEvent(
                    "expectation_miss",
                    {"action": exp.action, "expected": sorted(exp.targets), "observed": phase},
                    with_frame=True,
                )
            ]
        self._expectation = None
        return events
