"""Grounding a unit's content into a simulator unit.

One function owns the number fallback chain shared by every SimState
builder: caller-known live values first (the board is authority), then
the per-unit spec (panel OCR or content cache), then SpecDefaults --
with every fallback reported as a human-readable assumption, because an
assumption is never silently equal to a fact. Roster capabilities are
injected as the simulator's dynamic fields here too (KILL_REMOVE ->
re-activation charges, skill capabilities -> the skill inventory,
SUPPORT_DEFEND / SUPPORT_ATTACK -> the matching support-charge pools).
"""

from __future__ import annotations

from collections.abc import Iterable

from ..domain.roster import CapabilityType, UnitCapability
from ..sim import Cell, SimSkill, SimUnit
from ..sim.vocab import DecisionKind, Faction
from .kit import SpecDefaults, UnitSpec

_CAPABILITY_SKILL_KIND: dict[CapabilityType, str] = {
    CapabilityType.SKILL_EN_REFILL: DecisionKind.SKILL_EN_REFILL,
    CapabilityType.SKILL_HEAL: DecisionKind.SKILL_HEAL,
}


def ground_unit(
    unit_id: str,
    faction: Faction,
    cell: Cell,
    spec: UnitSpec | None,
    defaults: SpecDefaults,
    *,
    hp: int | None = None,
    max_hp: int | None = None,
    en: int | None = None,
    acted: bool = False,
    capabilities: Iterable[UnitCapability] = (),
) -> tuple[SimUnit, list[str]]:
    spec = spec or UnitSpec()
    assumptions: list[str] = []

    def note(name: str, value: object) -> None:
        assumptions.append(f"{unit_id}: {name} unknown, assumed {value}")

    known_max_hp = max_hp if max_hp is not None else spec.max_hp
    known_hp = hp
    if known_hp is None:
        known_hp = known_max_hp if known_max_hp is not None else defaults.hp
        note("HP", known_hp)
    if known_max_hp is None:
        known_max_hp = max(known_hp, defaults.hp)
        note("max HP", known_max_hp)
    en_max = spec.en_max
    known_en = en
    if known_en is None:
        known_en = en_max if en_max is not None else defaults.en
        note("EN", known_en)
    if en_max is None:
        en_max = max(known_en, defaults.en)
        note("max EN", en_max)
    if spec.move_range is None:
        note("move range", defaults.move_range)
    if not spec.weapons:
        assumptions.append(f"{unit_id}: no weapons known, inert in the simulation")

    reacts = 0
    support_defends = 0
    support_attacks = 0
    skills: list[SimSkill] = []
    for cap in capabilities:
        if cap.type is CapabilityType.KILL_REMOVE:
            reacts += cap.charges if cap.charges is not None else 1
        elif cap.type is CapabilityType.SUPPORT_DEFEND:
            support_defends += cap.charges if cap.charges is not None else 1
        elif cap.type is CapabilityType.SUPPORT_ATTACK:
            support_attacks += cap.charges if cap.charges is not None else 1
        elif cap.type in _CAPABILITY_SKILL_KIND:
            skills.append(
                SimSkill(
                    kind=_CAPABILITY_SKILL_KIND[cap.type],
                    uses=cap.charges if cap.charges is not None else 1,
                )
            )

    unit = SimUnit(
        unit_id=unit_id,
        faction=faction,
        pos=cell,
        hp=known_hp,
        max_hp=known_max_hp,
        en=known_en,
        en_max=en_max,
        unit_attack=spec.unit_attack if spec.unit_attack is not None else defaults.unit_attack,
        unit_defense=spec.unit_defense if spec.unit_defense is not None else defaults.unit_defense,
        pilot_attack=spec.pilot_attack if spec.pilot_attack is not None else defaults.pilot_attack,
        pilot_defense=spec.pilot_defense if spec.pilot_defense is not None else defaults.pilot_defense,
        reaction=spec.reaction if spec.reaction is not None else defaults.reaction,
        mobility=spec.mobility if spec.mobility is not None else defaults.mobility,
        move_range=spec.move_range if spec.move_range is not None else defaults.move_range,
        weapons=list(spec.weapons),
        skills=skills,
        acted=acted,
        react_charges=reacts,
        react_charges_max=reacts,
        support_defend_charges=support_defends,
        support_defend_charges_max=support_defends,
        support_attack_charges=support_attacks,
        support_attack_charges_max=support_attacks,
    )
    return unit, assumptions
