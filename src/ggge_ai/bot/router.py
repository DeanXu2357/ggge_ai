"""The router: two parallel consumers of one FrameReading.

    FrameReading ──┬──> ReflexTable:  tags -> handler  (reflex arc)
                   └──> SymbolTable:  tags -> facts    (for the planner)

Reflex routing never goes through symbols; the symbol table never fires
handlers. The symbol table is pure translation -- stateless, current frame
only, no access to goal/plan/memory. A rule that wants history or plan
context is not translation and does not belong here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ggge_ai.goap.state import Value

from .frame import FrameReading, Tag
from .state import UNKNOWN

if TYPE_CHECKING:
    from .action import Action
    from .bot import Bot

Rule = Callable[[FrameReading], Value]


def from_identity(mapping: Mapping[str, Value]) -> Rule:
    """Screen identity as an ordinary symbol, derived from the identity tags.

    Exactly one registered identity tag on the frame yields its value; zero
    (nothing recognised) and two (contradictory readings) are equally UNKNOWN.
    The tick log already carries the tag list, so which of the two happened is
    read off the record rather than signalled here.
    """

    def rule(reading: FrameReading) -> Value:
        hits = [value for name, value in mapping.items() if reading.has(name)]
        if len(hits) != 1:
            return UNKNOWN
        return hits[0]

    return rule


def tag_value(mapping: Mapping[str, Value], default: Value = UNKNOWN) -> Rule:
    def rule(reading: FrameReading) -> Value:
        for name, value in mapping.items():
            if reading.has(name):
                return value
        return default

    return rule


def tag_present(name: str, present: Value, absent: Value) -> Rule:
    return tag_value({name: present}, default=absent)


def identity_scope(identities: Iterable[str], inner: Rule, otherwise: Value = UNKNOWN) -> Rule:
    """Scope a rule to the screen that owns it: no identity tag, no default value.

    This is what keeps a tag rule total without lying -- "no expanded-list tag"
    means `collapsed` while the hub's identity tag is on the frame, and means
    "no idea" on a frame that cannot attest to the hub at all. A frame we
    cannot read must never manufacture facts out of absent tags.
    """

    allowed = frozenset(identities)

    def rule(reading: FrameReading) -> Value:
        if not any(reading.has(name) for name in allowed):
            return otherwise
        return inner(reading)

    return rule


class SymbolTable:
    """Per-symbol total mapping from one frame to every perception symbol.

    Registered per *symbol*, not per tag: each rule owns its default, so every
    perception symbol is fully recomputed from the current frame on every
    translate() call. Nothing can go stale -- a popup that disappears takes its
    symbol value with it on the very next frame.

    `identities` is the closed registration list of identity tags (tag name ->
    screen value). It lives here because screen identity is just another
    symbol, and it is exposed so the completeness check can keep those same
    tags out of the reflex table.
    """

    def __init__(
        self,
        rules: Mapping[str, Rule],
        identities: Mapping[str, Value] | None = None,
    ) -> None:
        self.rules = dict(rules)
        self.identities = dict(identities or {})

    @property
    def symbols(self) -> frozenset[str]:
        return frozenset(self.rules)

    @property
    def identity_tags(self) -> frozenset[str]:
        return frozenset(self.identities)

    def translate(self, reading: FrameReading) -> dict[str, Value]:
        return {symbol: rule(reading) for symbol, rule in self.rules.items()}


@dataclass(frozen=True)
class ReflexRule:
    """One tag-to-handler registration: dispatch only, no behaviour.

    `handler` owns everything behavioural -- its settle sleep, and any
    hold/timeout logic for being dispatched again (a back-style handler
    that must not re-press on an unchanged frame implements that check
    itself). Handlers never write symbols; their effect is attested by the
    next tick's frame. Identity tags are never registered here -- choice
    dialogs are screens the plan drives, and `misrouted_identity_tags` makes
    that a static rule rather than a runtime one.
    """

    tag: str
    handler: Callable[[Bot, Tag], None]
    blocking: bool = True


class ReflexTable:
    def __init__(self, rules: Iterable[ReflexRule] = ()) -> None:
        self.rules = list(rules)

    def match(self, reading: FrameReading) -> tuple[ReflexRule, Tag] | None:
        for rule in self.rules:
            if not rule.blocking:
                continue
            tag = reading.tag(rule.tag)
            if tag is not None:
                return rule, tag
        return None


class ReflexRouter:
    """Stateless dispatcher over a ReflexTable.

    The contract with the loop is strictly binary: a matched blocking tag
    runs its handler and the tick ends (non-None return = the tick's
    outcome); no match returns None and the tick proceeds to the queue.
    The router makes no behavioural decisions -- no hold, no timeout, no
    claim-then-release; what to do when dispatched again on an unchanged
    frame is defined inside the handler, next tick.
    """

    def __init__(self, table: ReflexTable) -> None:
        self.table = table

    def route(self, bot: Bot, reading: FrameReading) -> str | None:
        hit = self.table.match(reading)
        if hit is None:
            return None
        rule, tag = hit
        rule.handler(bot, tag)
        return f"reflex:{rule.tag}"


def misrouted_identity_tags(table: SymbolTable, reflexes: ReflexTable) -> set[str]:
    """Identity tags are barred from the reflex table -- one tag space, checked statically.

    A screen identity that can fire a handler is a screen whose verdict is
    settled by a reflex tap instead of by the plan; the end-turn dialog is
    exactly that case, and the auto-battle button is on it. Returns the
    offending names (empty = clean).
    """

    return {rule.tag for rule in reflexes.rules} & set(table.identities)


def unproduced_symbols(
    catalog: Iterable[Action],
    table: SymbolTable,
    memory_symbols: Iterable[str],
    board_symbols: Iterable[str] = (),
) -> set[str]:
    """Every symbol an action's pre/eff mentions must have exactly one producer.

    A symbol nobody produces is a guaranteed runtime PlanNotFound; this makes
    it a test failure instead. Returns the offending names (empty = complete).
    """

    produced = set(table.symbols) | set(memory_symbols) | set(board_symbols)
    used: set[str] = set()
    for action in catalog:
        used.update(action.pre)
        used.update(action.eff)
    return used - produced
