"""Team roster and unit capabilities: the ability-injection source.

The strategic layer reads each deployed unit's abilities on the setup
screen and writes them here; the battle-layer ActionCatalog draws its
"ability injection" half from this roster (docs/agent-architecture.md,
design principle 4). Only the capability *taxonomy* below is a mechanism
baked into code -- which unit actually owns which capability is content
and always comes from runtime perception, never hardcoded. A roster is
process-scoped memory: it lives on the blackboard and is rebuilt every
run, never persisted as a prior.

An ability whose transcription does not map onto a known taxonomy type is
kept as CapabilityType.UNKNOWN with its raw text preserved. Such
capabilities are inert to the planner (they neither plan nor raise) until
a future taxonomy entry gives them meaning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CapabilityType(Enum):
    """Planning semantics of a unit ability (the mechanism-layer taxonomy)."""

    KILL_REMOVE = "kill_remove"
    SKILL_EN_REFILL = "skill_en_refill"
    SKILL_HEAL = "skill_heal"
    SUPPORT_ATTACK = "support_attack"
    SUPPORT_DEFEND = "support_defend"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class UnitCapability:
    """One ability bound to a unit.

    `charges` carries the type-specific magnitude the game shows, e.g. the
    number of extra activations a KILL_REMOVE grants. `raw_text` keeps the
    original transcription; for UNKNOWN capabilities it is the only
    authoritative field.
    """

    type: CapabilityType
    raw_text: str = ""
    charges: int | None = None

    @classmethod
    def unknown(cls, raw_text: str) -> UnitCapability:
        return cls(CapabilityType.UNKNOWN, raw_text=raw_text)

    @property
    def is_known(self) -> bool:
        return self.type is not CapabilityType.UNKNOWN


@dataclass
class RosterEntry:
    """A deployed unit's identity plus its perceived capabilities."""

    unit_id: str
    name: str = ""
    capabilities: list[UnitCapability] = field(default_factory=list)


@dataclass
class TeamRoster:
    """Per-unit capability memory read from the setup screen at deploy time."""

    entries: dict[str, RosterEntry] = field(default_factory=dict)

    def add_unit(self, unit_id: str, name: str = "") -> RosterEntry:
        entry = self.entries.get(unit_id)
        if entry is None:
            entry = RosterEntry(unit_id=unit_id, name=name)
            self.entries[unit_id] = entry
        elif name:
            entry.name = name
        return entry

    def add_capability(self, unit_id: str, capability: UnitCapability) -> None:
        self.add_unit(unit_id).capabilities.append(capability)

    def entry(self, unit_id: str) -> RosterEntry | None:
        return self.entries.get(unit_id)

    def capabilities(self, unit_id: str) -> list[UnitCapability]:
        entry = self.entries.get(unit_id)
        return list(entry.capabilities) if entry is not None else []
