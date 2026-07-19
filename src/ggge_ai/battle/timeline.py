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
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Transition:
    """One row of the game's UI flow map: where an action may legally land
    (`targets`), how many label-less reads the contract survives (`checks`,
    counted in reads, not wall time), how many eaten-tap retries it gets,
    which activation flag to roll back when the tap was eaten (`repair`),
    and whether the action closes the current unit activation."""

    targets: tuple[str, ...]
    checks: int = 8
    retries: int = 1
    repair: str | None = None
    ends_activation: bool = False


# battle_execute gets a generous budget (long battle animations, and a
# reaction popup's enemy turn continues afterwards); battle_prep is among
# its legal targets because consecutive reaction popups re-enter that screen
TRANSITIONS: dict[str, Transition] = {
    "select_unit": Transition(("unit_move", "weapon_select")),
    "open_weapon_select": Transition(("weapon_select",), repair="tried_in_place"),
    "attack": Transition(("battle_prep",)),
    "battle_execute": Transition(
        ("our_turn", "unit_move", "weapon_select", "battle_prep"),
        checks=20,
        ends_activation=True,
    ),
    "standby": Transition(("our_turn",), checks=12, ends_activation=True),
}


@dataclass
class Activation:
    """Per-unit activation state threading the unit_move <-> weapon_select
    visits; reset when the activation ends (standby, battle executed, or a
    fresh hub visit)."""

    tried_in_place: bool = False
    moved: bool = False
    plan: object | None = None

    def reset(self) -> None:
        self.tried_in_place = False
        self.moved = False
        self.plan = None


@dataclass
class Expectation:
    """One act -> verify contract: after `action` (fired while `source` was
    on screen) the next confirmed phase should land in `targets`.

    Verdicts, checked against every phase read fed to observe():
    - observed in targets: transition verified.
    - observed == source: the tap was eaten (power-save lock, mid-animation
      UI) -- the transition's `repair` flag rolls back on the activation, so
      the reactive dispatch retries the action instead of walking a wrong
      branch.
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
    repair: str | None = None
    retries_left: int = 1


@dataclass(frozen=True)
class TimelineEvent:
    """A ledger intent returned by observe(): the controller records it,
    attaching a fresh frame when with_frame asks for one."""

    kind: str
    data: dict
    with_frame: bool = False


# a TURN read jumping further than this from the current turn is a misread:
# a single bad OCR must not poison the counter forever (every later true
# value would compare lower); real skips are 1-2 turns
TURN_JUMP_MAX = 3


@dataclass
class BattleTimeline:
    phase: str | None = None
    # aligned with BattleLedger.turn / BoardTracker.turn, both 1-based
    turn: int = 1
    activation: Activation = field(default_factory=Activation)
    _expectation: Expectation | None = field(default=None, repr=False)
    _marker: object | None = field(default=None, repr=False)
    _done_jobs: set[str] = field(default_factory=set, repr=False)

    def on_turn_read(self, number: int | None, marker) -> bool:
        """Turn-boundary decision from the hub's TURN chip: digit OCR is the
        primary read (the HARD 1 ledger sat on turn=1 all battle because the
        marker-diff compare never fired), the marker crop compare stays as
        the fallback for frames where the chip does not read. Returns True
        when a new turn begins; turn-scoped jobs re-arm on it."""
        from ggge_ai.battle import vision

        if number is not None:
            advanced = False
            if number - self.turn > TURN_JUMP_MAX:
                log.warning(
                    "TURN read %d jumps too far from %d, ignoring as a misread",
                    number,
                    self.turn,
                )
            elif number > self.turn:
                self._new_turn(number)
                log.info("new turn detected (TURN %d on screen)", number)
                advanced = True
            self._marker = marker
            return advanced
        if self._marker is None:
            self._marker = marker
            return False
        if vision.turn_marker_changed(self._marker, marker):
            self._marker = marker
            self._new_turn(self.turn + 1)
            log.info("new turn detected (marker change, turn %d)", self.turn)
            return True
        return False

    def _new_turn(self, turn: int) -> None:
        self.turn = turn
        self._done_jobs = {k for k in self._done_jobs if not k.startswith("turn:")}

    def due(self, job: str, scope: str = "turn") -> bool:
        """Once-per-scope work gate: the first ask per turn (or per battle)
        returns True and claims the job; later asks say no. Consuming on the
        ask keeps the call sites to one line -- pair every True with actually
        doing the work."""
        key = f"{scope}:{job}"
        if key in self._done_jobs:
            return False
        self._done_jobs.add(key)
        return True

    def pending(self, job: str, scope: str = "turn") -> bool:
        """Read-only peek at a work gate: True while the job is unclaimed.
        due() claims on the ask, so any caller that only needs to know --
        not to do the work -- must peek here or it steals the job (the
        20260719 grid-window regression: _scout's due() ate the intel gate
        and the survey never ran)."""
        return f"{scope}:{job}" not in self._done_jobs

    def mark_done(self, job: str, scope: str = "turn") -> None:
        self._done_jobs.add(f"{scope}:{job}")

    def mark_pending(self, job: str, scope: str = "turn") -> None:
        self._done_jobs.discard(f"{scope}:{job}")

    def acted(self, action: str) -> None:
        """A handler reports the action it just fired; the transition
        contract comes from the TRANSITIONS map, the source is the phase
        the screen last confirmed. One at a time: a newer action supersedes
        whatever contract was still open. An activation-ending action
        resets the per-unit state on the spot."""
        t = TRANSITIONS[action]
        self._expectation = Expectation(
            action=action,
            source=self.phase,
            targets=frozenset(t.targets),
            checks_left=t.checks,
            repair=t.repair,
            retries_left=t.retries,
        )
        if t.ends_activation:
            self.activation.reset()

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
            if exp.repair is not None:
                setattr(self.activation, exp.repair, False)
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
