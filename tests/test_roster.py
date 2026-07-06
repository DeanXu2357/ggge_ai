from ggge_ai.domain.roster import (
    CapabilityType,
    RosterEntry,
    TeamRoster,
    UnitCapability,
)


def test_add_unit_and_capabilities():
    roster = TeamRoster()
    roster.add_unit("u1", name="Gundam")
    roster.add_capability("u1", UnitCapability(CapabilityType.KILL_REMOVE, charges=2))
    roster.add_capability("u1", UnitCapability(CapabilityType.SKILL_EN_REFILL))

    entry = roster.entry("u1")
    assert isinstance(entry, RosterEntry)
    assert entry.name == "Gundam"
    assert len(roster.capabilities("u1")) == 2


def test_add_capability_creates_unit_implicitly():
    roster = TeamRoster()
    roster.add_capability("u2", UnitCapability(CapabilityType.SKILL_HEAL))
    assert roster.entry("u2") is not None
    assert roster.capabilities("u2")[0].type is CapabilityType.SKILL_HEAL


def test_unknown_capability_keeps_raw_text():
    cap = UnitCapability.unknown("EXAM system")
    assert cap.type is CapabilityType.UNKNOWN
    assert cap.raw_text == "EXAM system"
    assert cap.is_known is False


def test_missing_unit_returns_empty():
    roster = TeamRoster()
    assert roster.entry("nope") is None
    assert roster.capabilities("nope") == []
