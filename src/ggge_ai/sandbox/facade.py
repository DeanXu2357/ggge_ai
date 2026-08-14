"""沙盤門面：外界唯一的查詢與推進入口。

只做彙整與序列化：候選一律轉呼叫 model 層的列舉器與公式，本模組不含遊戲規則。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from . import scenario as scenario_mod
from .advise import Advisor
from .model import (
    NO_DEFENSE_MULTIPLIER,
    BattleState,
    Cell,
    Decision,
    EventTable,
    MoveKind,
    Reaction,
    Rules,
    Stance,
    Unit,
    Weapon,
    _counter_weapon,
    _interception_multiplier,
    _pending,
    _stance_multiplier,
    find_support_defender,
    legal_attacks,
    legal_map_attacks,
    legal_skills,
    reachable_cells,
    reposition_moves,
    standby,
    step,
    strike_damage,
    strike_hit_probability,
    targets_of,
)

ACTIVATION = "activation"
REACTION = "reaction"


def _cell(cell: Cell | None) -> list[int] | None:
    return None if cell is None else [cell[0], cell[1]]


def _as_cell(raw: Any) -> Cell | None:
    if raw is None:
        return None
    return (int(raw[0]), int(raw[1]))


def _unit_payload(unit: Unit) -> dict[str, Any]:
    return {
        "uid": unit.unit_id,
        "faction": str(unit.faction),
        "cell": list(unit.pos),
        "hp": unit.hp,
        "max_hp": unit.max_hp,
        "en": unit.en,
        "en_max": unit.en_max,
        "acted": unit.acted,
        "move_range": unit.move_range,
        "mobility": unit.mobility,
        "unit_attack": unit.unit_attack,
        "unit_defense": unit.unit_defense,
        "pilot_attack": unit.pilot_attack,
        "pilot_defense": unit.pilot_defense,
        "reaction": unit.reaction,
        "has_shield": unit.has_shield,
        "attack_shield": unit.attack_shield,
        "chance_steps": unit.chance_steps,
        "support_attack_charges": unit.support_attack_charges,
        "support_defend_charges": unit.support_defend_charges,
        "weapons": [
            {
                "name": weapon.name,
                "power": weapon.power,
                "range_min": weapon.range_min,
                "range_max": weapon.range_max,
                "en_cost": weapon.en_cost,
                "accuracy": weapon.accuracy,
                "can_counter": weapon.can_counter,
                "map_weapon": weapon.map_weapon,
                "ammo": unit.ammo.get(weapon.name),
            }
            for weapon in unit.weapons
        ],
        "skills": [
            {"kind": str(skill.kind), "amount": skill.amount, "uses": skill.uses}
            for skill in unit.skills
        ],
    }


def _decision_of(candidate: Mapping[str, Any], reaction: Mapping[str, Any] | None) -> Decision:
    return Decision(
        unit_id=str(candidate["unit_id"]),
        kind=MoveKind(candidate["kind"]),
        move_to=_as_cell(candidate.get("move_to")),
        target_id=candidate.get("target_id"),
        weapon=candidate.get("weapon"),
        amount=candidate.get("amount"),
        aim=_as_cell(candidate.get("aim")),
        reaction=_reaction_of(reaction),
    )


def _reaction_of(raw: Mapping[str, Any] | None) -> Reaction | None:
    if raw is None:
        return None
    return Reaction(
        stance=Stance(raw.get("stance", Stance.NONE)),
        weapon=raw.get("weapon"),
        support_defend=bool(raw.get("support_defend", False)),
        support_attack=bool(raw.get("support_attack", True)),
    )


def _legal_reactions(defender: Unit, attacker: Unit, *, support_defend: bool) -> list[Reaction]:
    stances = [Stance.NONE, Stance.DODGE, Stance.DEFEND]
    if defender.has_shield:
        stances.append(Stance.SHIELD)
    out = [Reaction(stance=stance) for stance in stances]
    out.extend(
        Reaction(stance=Stance.COUNTER, weapon=weapon.name)
        for weapon in defender.weapons
        if _counter_weapon(defender, weapon.name, attacker) is not None
    )
    if support_defend:
        out.extend(replace(option, support_defend=True) for option in list(out))
    return out


class Sandbox:
    def __init__(
        self,
        state: BattleState,
        rules: Rules,
        events: EventTable | None = None,
        advisor: Advisor[BattleState, Any] | None = None,
        *,
        scenario: scenario_mod.Scenario | None = None,
    ) -> None:
        self._state = state
        self._rules = rules
        self._events: EventTable = dict(events or {})
        self._advisor = advisor
        self._scenario = scenario

    @classmethod
    def from_scenario(
        cls,
        path: str | Path,
        advisor: Advisor[BattleState, Any] | None = None,
    ) -> Sandbox:
        scenario = scenario_mod.load(path)
        state, rules, events = scenario.build()
        return cls(state, rules, events, advisor, scenario=scenario)

    def turn(self) -> int:
        return self._state.turn

    def phase(self) -> str:
        return str(self._state.phase)

    def outcome(self) -> str | None:
        if self._scenario is None:
            return None
        return scenario_mod.check_outcome(self._scenario, self._state)

    def units(self) -> list[dict[str, Any]]:
        return [_unit_payload(unit) for unit in self._state.units]

    def rules(self) -> dict[str, Any]:
        return asdict(self._rules)

    def events(self) -> dict[str, Any]:
        return {
            event_id: {"trigger": dict(event.trigger), "effect": self._effect(event.effect)}
            for event_id, event in self._events.items()
        }

    def board(self) -> dict[str, int]:
        if self._scenario is not None:
            return {"cols": self._scenario.board.cols, "rows": self._scenario.board.rows}
        if self._state.bounds is None:
            return {"cols": 0, "rows": 0}
        (min_x, min_y), (max_x, max_y) = self._state.bounds
        return {"cols": max_x - min_x + 1, "rows": max_y - min_y + 1}

    def snapshot(self) -> dict[str, Any]:
        return {
            "stage": "" if self._scenario is None else self._scenario.stage,
            "note": "" if self._scenario is None else self._scenario.note,
            "board": self.board(),
            "turn": self.turn(),
            "phase": self.phase(),
            "outcome": self.outcome(),
            "units": self.units(),
        }

    def pending_decision(self) -> dict[str, Any]:
        units: list[dict[str, Any]] = []
        decisions: list[Decision] = []
        for actor in _pending(self._state, self._state.phase):
            payload, candidates = self._activation(actor)
            units.append(payload)
            decisions.extend(candidates)
        return {
            "kind": ACTIVATION,
            "turn": self.turn(),
            "phase": self.phase(),
            "units": units,
            "advice": self._advice(decisions),
        }

    def reaction_options(
        self, attacker_id: str, defender_id: str, weapon: str | None = None
    ) -> dict[str, Any]:
        attacker = self._state.unit(attacker_id)
        defender = self._state.unit(defender_id)
        if attacker is None or defender is None:
            return {
                "kind": REACTION,
                "attacker": attacker_id,
                "defender": defender_id,
                "weapon": weapon,
                "support_defender": None,
                "options": [],
                "advice": None,
            }
        shot = attacker.weapon(weapon)
        interceptor = find_support_defender(self._state, defender)
        options = _legal_reactions(defender, attacker, support_defend=interceptor is not None)
        return {
            "kind": REACTION,
            "attacker": attacker_id,
            "defender": defender_id,
            "weapon": None if shot is None else shot.name,
            "support_defender": None if interceptor is None else interceptor.unit_id,
            "options": [
                self._reaction_payload(attacker, defender, shot, interceptor, option)
                for option in options
            ],
            "advice": self._advice(options),
        }

    def act(
        self,
        candidate: Mapping[str, Any],
        reaction: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._state = step(
            self._state,
            _decision_of(candidate, reaction),
            rules=self._rules,
            events=self._events,
        )
        return self.snapshot()

    def _effect(self, effect: dict[str, Any]) -> dict[str, Any]:
        out = dict(effect)
        if out.get("type") == "spawn":
            out["units"] = [_unit_payload(unit) for unit in out.get("units", ())]
        return out

    def _activation(self, actor: Unit) -> tuple[dict[str, Any], list[Decision]]:
        reach = reachable_cells(self._state, actor)
        candidates = [
            *legal_attacks(self._state, actor, reach=reach),
            *legal_map_attacks(self._state, actor),
            *legal_skills(actor),
            *reposition_moves(self._state, actor, reach=reach),
            standby(actor.unit_id),
        ]
        payload = {
            "uid": actor.unit_id,
            "faction": str(actor.faction),
            "cell": list(actor.pos),
            "moves": sorted(_cell(cell) for cell in reach),
            "candidates": [self._candidate(actor, decision) for decision in candidates],
        }
        return payload, candidates

    def _candidate(self, actor: Unit, decision: Decision) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": str(decision.kind),
            "unit_id": decision.unit_id,
            "move_to": _cell(decision.move_to),
            "target_id": decision.target_id,
            "weapon": decision.weapon,
            "amount": decision.amount,
            "aim": _cell(decision.aim),
            "hit_probability": None,
            "expected_damage": None,
        }
        if decision.kind is MoveKind.ATTACK:
            target = self._state.unit(decision.target_id)
            shot = actor.weapon(decision.weapon)
            if target is not None:
                payload["hit_probability"] = strike_hit_probability(
                    actor, target, shot, rules=self._rules
                )
                payload["expected_damage"] = self._damage(actor, target, shot)
        elif decision.kind is MoveKind.MAP_ATTACK:
            victim = next(
                (u for u in targets_of(self._state, actor) if u.pos == decision.aim), None
            )
            if victim is not None:
                shot = actor.weapon(decision.weapon)
                payload["target_id"] = victim.unit_id
                # 地圖兵器不擲命中：_apply_map_attack 沒有命中節點，一定落地。
                payload["hit_probability"] = 1.0
                payload["expected_damage"] = self._damage(actor, victim, shot)
        return payload

    def _reaction_payload(
        self,
        attacker: Unit,
        defender: Unit,
        shot: Weapon | None,
        interceptor: Unit | None,
        option: Reaction,
    ) -> dict[str, Any]:
        struck = defender
        multiplier = _stance_multiplier(option, self._rules)
        if option.support_defend and interceptor is not None:
            struck = interceptor
            multiplier = _interception_multiplier(interceptor, self._rules)
        return {
            "stance": str(option.stance),
            "weapon": option.weapon,
            "support_defend": option.support_defend,
            "struck": struck.unit_id,
            "hit_probability": strike_hit_probability(
                attacker,
                defender,
                shot,
                dodging=option.stance is Stance.DODGE,
                rules=self._rules,
            ),
            "expected_damage": self._damage(
                attacker, struck, shot, defense_multiplier=multiplier
            ),
        }

    def _damage(
        self,
        attacker: Unit,
        struck: Unit,
        shot: Weapon | None,
        *,
        defense_multiplier: float = NO_DEFENSE_MULTIPLIER,
    ) -> int | None:
        if shot is None:
            return None
        return strike_damage(
            attacker, struck, shot, defense_multiplier=defense_multiplier, rules=self._rules
        )

    def _advice(self, candidates: Sequence[Any]) -> dict[str, Any] | None:
        if self._advisor is None:
            return None
        appraisal = self._advisor.appraise(self._state)
        # pricing 與酬載裡的候選逐位對齊：單位依序、單位內候選依序攤平成一條清單。
        pricing = self._advisor.price(self._state, candidates)
        return {
            "verdict": appraisal.verdict.value,
            "reason": appraisal.reason,
            "pricing": [
                None
                if price is None
                else {
                    "cost": price.cost,
                    "guarantee": price.guarantee.value,
                    "note": price.note,
                }
                for price in pricing
            ],
        }
