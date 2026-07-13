"""BattleAction and ActionCatalog: the open, dual-source action space.

The catalog is synthesised from two sources (docs/agent-architecture.md,
design principle 4):

    battle action space = screen scan (mechanism layer)
                        u  ability injection (content layer, from the roster)

Screen scan is what the game draws on the board right now -- attackable
targets and their expected damage; its provider interface is fixed here
and the real implementation is left to issue #12 (tests use a fake).
Ability injection turns each roster capability into the button it would
press. Preconditions/effects/costs are always data-bound: the code owns
*how* to bind them (the builder functions below), while the actual numbers
come from perception or the blackboard.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from ..domain.roster import CapabilityType, UnitCapability

if TYPE_CHECKING:
    from ..core.action import ExecutionContext
    from .state import BattleState, UnitState


class ActionKind:
    ATTACK = "attack"
    MAP_ATTACK = "map_attack"
    STANDBY = "standby"
    MOVE = "move"
    SELECT_UNIT = "select_unit"
    SKILL_EN_REFILL = "skill_en_refill"
    SKILL_HEAL = "skill_heal"
    SUPPORT_ATTACK = "support_attack"
    SUPPORT_DEFEND = "support_defend"
    RAW = "raw"


Precondition = Callable[["BattleState", "UnitState"], bool]
Effect = Callable[["BattleState", "UnitState"], None]
Executor = Callable[["ExecutionContext"], bool]


def _always(_state: BattleState, _unit: UnitState) -> bool:
    return True


@dataclass
class BattleAction:
    """A battle-layer operator described by precondition/effect/cost, with an
    executable hook bound to an existing handler.

    The offline chain planner reads the structured fields (kind, target_id,
    expected_damage) plus the estimator; precondition filters applicability.
    The execute hook stays None until issue #12 wires the real handler.
    """

    action_id: str
    kind: str
    cost: float = 1.0
    target_id: str | None = None
    weapon: str | None = None
    expected_damage: float | None = None
    capability: UnitCapability | None = None
    precondition: Precondition = _always
    effect: Effect | None = None
    execute: Executor | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def is_applicable(self, state: BattleState, unit: UnitState) -> bool:
        return self.precondition(state, unit)


class ScanProvider(Protocol):
    """Screen-scan source of the catalog (real implementation: issue #12)."""

    def scan(self, state: BattleState, unit: UnitState) -> list[BattleAction]: ...


def make_standby_action(unit_id: str) -> BattleAction:
    return BattleAction(
        action_id=f"{ActionKind.STANDBY}:{unit_id}",
        kind=ActionKind.STANDBY,
        cost=0.0,
    )


def _target_alive(target_id: str) -> Precondition:
    def precondition(state: BattleState, _unit: UnitState) -> bool:
        target = state.unit(target_id)
        return target is not None and target.hp != 0

    return precondition


def build_attack_action(
    unit_id: str,
    target_id: str,
    *,
    expected_damage: float | None = None,
    weapon: str | None = None,
    cost: float = 1.0,
) -> BattleAction:
    return BattleAction(
        action_id=f"{ActionKind.ATTACK}:{unit_id}:{target_id}:{weapon or ''}",
        kind=ActionKind.ATTACK,
        cost=cost,
        target_id=target_id,
        weapon=weapon,
        expected_damage=expected_damage,
        precondition=_target_alive(target_id),
    )


# Capability types that map onto a pressable action. KILL_REMOVE is absent
# on purpose: it is a passive modifier the planner reads as re-activation
# charges, not a button. UNKNOWN is absent so it stays inert to the planner.
_CAPABILITY_ACTION_KIND: dict[CapabilityType, str] = {
    CapabilityType.SKILL_EN_REFILL: ActionKind.SKILL_EN_REFILL,
    CapabilityType.SKILL_HEAL: ActionKind.SKILL_HEAL,
    CapabilityType.SUPPORT_ATTACK: ActionKind.SUPPORT_ATTACK,
    CapabilityType.SUPPORT_DEFEND: ActionKind.SUPPORT_DEFEND,
}


def actions_from_capabilities(
    unit_id: str, capabilities: list[UnitCapability]
) -> list[BattleAction]:
    out: list[BattleAction] = []
    for cap in capabilities:
        kind = _CAPABILITY_ACTION_KIND.get(cap.type)
        if kind is None:
            continue
        out.append(
            BattleAction(
                action_id=f"{kind}:{unit_id}",
                kind=kind,
                capability=cap,
            )
        )
    return out


def _dedup(actions: list[BattleAction]) -> list[BattleAction]:
    seen: set[str] = set()
    out: list[BattleAction] = []
    for action in actions:
        if action.action_id in seen:
            continue
        seen.add(action.action_id)
        out.append(action)
    return out


@dataclass
class ActionCatalog:
    """The unit's action space for one activation, both sources merged."""

    actions: list[BattleAction] = field(default_factory=list)

    @classmethod
    def build(
        cls,
        state: BattleState,
        unit: UnitState,
        scan_provider: ScanProvider | None = None,
        capabilities: list[UnitCapability] | None = None,
    ) -> ActionCatalog:
        scanned = scan_provider.scan(state, unit) if scan_provider is not None else []
        caps = capabilities if capabilities is not None else list(unit.capabilities)
        injected = actions_from_capabilities(unit.unit_id, caps)
        # scan is authority: it comes first so its entry wins on id collision.
        return cls(_dedup([*scanned, *injected]))

    def by_kind(self, kind: str) -> list[BattleAction]:
        return [a for a in self.actions if a.kind == kind]

    def attacks(self) -> list[BattleAction]:
        return self.by_kind(ActionKind.ATTACK)
