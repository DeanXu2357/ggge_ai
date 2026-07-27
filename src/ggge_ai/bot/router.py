"""The router: two parallel consumers of one FrameReading.

    FrameReading ──┬──> ReflexTable:  tags -> handler        (reflex arc)
                   └──> SymbolTable:  {phase, tags} -> facts (for the planner)

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


def from_phase(mapping: Mapping[str, Value], default: Value = UNKNOWN) -> Rule:
    def rule(reading: FrameReading) -> Value:
        return mapping.get(reading.phase, default)

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


def on_phases(phases: Iterable[str], inner: Rule, otherwise: Value = UNKNOWN) -> Rule:
    """Gate a rule by phase: outside `phases` the symbol is honestly `otherwise`.

    This is what keeps a tag rule total without lying -- "no expanded-list tag"
    means `collapsed` on the hub, but means "no idea" on any other screen.
    """

    allowed = frozenset(phases)

    def rule(reading: FrameReading) -> Value:
        if reading.phase not in allowed:
            return otherwise
        return inner(reading)

    return rule


class SymbolTable:
    """Per-symbol total mapping from one frame to every perception symbol.

    Registered per *symbol*, not per tag: each rule owns its default, so every
    perception symbol is fully recomputed from the current frame on every
    translate() call. Nothing can go stale -- a popup that disappears takes its
    symbol value with it on the very next frame.
    """

    def __init__(self, rules: Mapping[str, Rule]) -> None:
        self.rules = dict(rules)

    @property
    def symbols(self) -> frozenset[str]:
        return frozenset(self.rules)

    def translate(self, reading: FrameReading) -> dict[str, Value]:
        return {symbol: rule(reading) for symbol, rule in self.rules.items()}


@dataclass(frozen=True)
class ReflexRule:
    """One tag-to-handler registration.

    `handler` acts on the device and owns its own settle sleep; it never
    writes symbols -- its effect is attested by the next tick's frame.
    `refire="require_change"` refuses to fire again while the frame key is
    unchanged since the last firing (back-style hazards); `"safe"` may fire
    every tick (tap-through pages). Choice dialogs and unidentified modals
    are never registered here -- that is a structural rule, not a runtime one.
    """

    tag: str
    handler: Callable[[Bot, Tag], None]
    refire: str = "safe"
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
    """Runtime dispatcher over a ReflexTable: one per bot run.

    Owns the refire fingerprint, so every piece of reflex semantics -- match
    order (first registered blocking rule wins), the refire gate, handler
    firing -- lives in this module. The loop only asks "did you handle this
    frame?": a non-None return is the tick's outcome and ends the tick.
    The table stays pure registration data and can be shared; the router is
    the per-run stateful wrapper around it.
    """

    def __init__(self, table: ReflexTable) -> None:
        self.table = table
        self._last: tuple[str, tuple] | None = None

    def route(self, bot: Bot, reading: FrameReading) -> str | None:
        hit = self.table.match(reading)
        if hit is None:
            return None
        rule, tag = hit
        key = (rule.tag, reading.key())
        if rule.refire == "require_change" and self._last == key:
            return "wait:refire"
        rule.handler(bot, tag)
        self._last = key
        return f"reflex:{rule.tag}"


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
