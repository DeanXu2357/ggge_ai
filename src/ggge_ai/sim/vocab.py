"""Vocabulary the simulated stage world is written in.

Faction and the decision kinds are owned by the simulator: this is the
language SimState/step/solve speak, defined with no imports so the sim
package stays free of the perception stack. The battle layer builds on
top of it -- battle.state re-exports Faction and battle.actions.ActionKind
extends DecisionKind with execution-only kinds (select_unit, support
buttons, raw taps) that exist on screen but not inside the world model.
The string values are shared across both layers and serialized into run
ledgers, so they must never diverge.
"""

from __future__ import annotations

from enum import Enum


class Faction(Enum):
    ALLY = "ally"
    ENEMY = "enemy"
    THIRD_PARTY = "third_party"


class DecisionKind:
    """The action kinds that exist inside the world model -- what step()
    executes and the search branches over."""

    ATTACK = "attack"
    MAP_ATTACK = "map_attack"
    MOVE = "move"
    STANDBY = "standby"
    SKILL_EN_REFILL = "skill_en_refill"
    SKILL_HEAL = "skill_heal"
