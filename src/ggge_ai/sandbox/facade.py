"""沙盤門面：外界唯一的查詢與推進入口。

只做彙整與序列化：候選一律轉呼叫 model 層的列舉器與公式，本模組不含遊戲規則。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict
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
    blast_victims,
    find_support_attackers,
    find_support_defender,
    legal_attacks,
    legal_map_attacks,
    legal_reactions,
    legal_skills,
    pending_units,
    reachable_cells,
    reaction_defense,
    reposition_moves,
    standby,
    step,
    strike_damage,
    strike_hit_probability,
)

ACTIVATION = "activation"
REACTION = "reaction"

DECISION_FIELDS = ("kind", "unit_id", "move_to", "target_id", "weapon", "amount", "aim")


def _cell(cell: Cell | None) -> list[int] | None:
    return None if cell is None else [cell[0], cell[1]]


def _as_cell(raw: Any) -> Cell | None:
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError(f"格位要寫成 [x, y]，讀到 {raw!r}")
    return (int(raw[0]), int(raw[1]))


def _as_die(raw: Any) -> bool | None:
    return None if raw is None else bool(raw)


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


def _candidate_key(candidate: Mapping[str, Any]) -> tuple:
    missing = sorted({"kind", "unit_id"} - set(candidate))
    if missing:
        raise ValueError(f"候選缺欄位：{'、'.join(missing)}")
    return (
        str(candidate["kind"]),
        str(candidate["unit_id"]),
        _as_cell(candidate.get("move_to")),
        candidate.get("target_id"),
        candidate.get("weapon"),
        candidate.get("amount"),
        _as_cell(candidate.get("aim")),
    )


def _decision_of(candidate: Mapping[str, Any], reaction: Mapping[str, Any] | None) -> Decision:
    kind, unit_id, move_to, target_id, weapon, amount, aim = _candidate_key(candidate)
    try:
        move_kind = MoveKind(kind)
    except ValueError as exc:
        raise ValueError(f"行動類型不合法：{kind!r}") from exc
    return Decision(
        unit_id=unit_id,
        kind=move_kind,
        move_to=move_to,
        target_id=target_id,
        weapon=weapon,
        amount=amount,
        aim=aim,
        reaction=_reaction_of(reaction),
        hit=_as_die(candidate.get("hit")),
        counter_hit=_as_die(candidate.get("counter_hit")),
        support_hit=_as_die(candidate.get("support_hit")),
    )


def _reaction_of(raw: Mapping[str, Any] | None) -> Reaction | None:
    if raw is None:
        return None
    stance = raw.get("stance", Stance.NONE)
    try:
        return Reaction(
            stance=Stance(stance),
            weapon=raw.get("weapon"),
            support_defend=bool(raw.get("support_defend", False)),
            support_attack=bool(raw.get("support_attack", True)),
        )
    except ValueError as exc:
        raise ValueError(f"應戰姿態不合法：{stance!r}") from exc


class Sandbox:
    def __init__(
        self,
        state: BattleState,
        rules: Rules,
        events: EventTable | None = None,
        advisor: Advisor[BattleState, Decision | Reaction] | None = None,
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
        advisor: Advisor[BattleState, Decision | Reaction] | None = None,
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
        for actor in pending_units(self._state, self._state.phase):
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

    def reaction_options(self, candidate: Mapping[str, Any]) -> dict[str, Any]:
        attacker, defender, weapon, origin = self._engagement(candidate)
        options = legal_reactions(self._state, defender, attacker, weapon, attacker_pos=origin)
        volley = find_support_attackers(self._state, defender, attacker, foe_pos=origin)
        supporters = [
            unit.unit_id for unit, _ in volley[: max(0, self._rules.max_support_attackers)]
        ]
        interceptor = find_support_defender(self._state, defender)
        return {
            "kind": REACTION,
            "attacker": attacker.unit_id,
            "defender": defender.unit_id,
            "weapon": weapon.name,
            "attacker_cell": list(origin),
            "support_defender": None if interceptor is None else interceptor.unit_id,
            "options": [
                self._reaction_payload(attacker, defender, weapon, option, supporters)
                for option in options
            ],
            "advice": self._advice(options),
        }

    def act(
        self,
        candidate: Mapping[str, Any],
        reaction: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        decision = _decision_of(candidate, reaction)
        self._require_legal(candidate)
        if decision.reaction is not None:
            self._require_legal_reaction(candidate, decision.reaction)
        self._state = step(self._state, decision, rules=self._rules, events=self._events)
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
            "victims": [],
        }
        shot = actor.weapon(decision.weapon)
        if decision.kind is MoveKind.ATTACK:
            target = self._state.unit(decision.target_id)
            if target is not None:
                payload["hit_probability"] = strike_hit_probability(
                    actor, target, shot, rules=self._rules
                )
                payload["expected_damage"] = self._damage(actor, target, shot)
        elif decision.kind is MoveKind.MAP_ATTACK and shot is not None and decision.aim is not None:
            victims = blast_victims(self._state, actor, shot, decision.aim)
            payload["victims"] = [
                {"uid": victim.unit_id, "expected_damage": self._damage(actor, victim, shot)}
                for victim in victims
            ]
            aimed = next((victim for victim in victims if victim.pos == decision.aim), None)
            payload["target_id"] = None if aimed is None else aimed.unit_id
            # 地圖兵器不擲命中：_apply_map_attack 沒有命中節點，一定落地。
            payload["hit_probability"] = 1.0
            payload["expected_damage"] = sum(hit["expected_damage"] for hit in payload["victims"])
        return payload

    def _reaction_payload(
        self,
        attacker: Unit,
        defender: Unit,
        weapon: Weapon,
        option: Reaction,
        supporters: Sequence[str],
    ) -> dict[str, Any]:
        struck, multiplier, _ = reaction_defense(self._state, defender, option, self._rules)
        return {
            "stance": str(option.stance),
            "weapon": option.weapon,
            "support_defend": option.support_defend,
            "support_attack": option.support_attack,
            "support_attackers": list(supporters) if option.support_attack else [],
            "struck": struck.unit_id,
            "hit_probability": strike_hit_probability(
                attacker,
                defender,
                weapon,
                dodging=option.stance is Stance.DODGE,
                rules=self._rules,
            ),
            "expected_damage": self._damage(
                attacker, struck, weapon, defense_multiplier=multiplier
            ),
        }

    def _engagement(self, candidate: Mapping[str, Any]) -> tuple[Unit, Unit, Weapon, Cell]:
        kind, unit_id, move_to, target_id, name, _amount, _aim = _candidate_key(candidate)
        if kind != MoveKind.ATTACK:
            raise ValueError(f"只有攻擊有應戰節點，讀到 {kind!r}")
        attacker = self._state.unit(unit_id)
        defender = self._state.unit(target_id)
        if attacker is None or defender is None:
            raise ValueError(f"交戰雙方要在盤面上：{unit_id!r} 對 {target_id!r}")
        if name is None:
            raise ValueError("應戰列舉要指名武裝")
        weapon = attacker.weapon(name)
        if weapon is None:
            raise ValueError(f"{unit_id} 沒有這個武裝：{name!r}")
        if weapon.map_weapon:
            raise ValueError(f"地圖兵器沒有應戰節點：{name!r}")
        self._require_legal(candidate)
        return attacker, defender, weapon, attacker.pos if move_to is None else move_to

    def _require_legal(self, candidate: Mapping[str, Any]) -> None:
        key = _candidate_key(candidate)
        if key not in self._legal_keys(key[1]):
            raise ValueError(f"這個候選不在目前的合法清單裡：{dict(zip(DECISION_FIELDS, key))}")

    def _require_legal_reaction(self, candidate: Mapping[str, Any], reaction: Reaction) -> None:
        attacker, defender, weapon, origin = self._engagement(candidate)
        if reaction not in legal_reactions(
            self._state, defender, attacker, weapon, attacker_pos=origin
        ):
            raise ValueError(f"這個應戰不在合法選項裡：{reaction}")

    def _legal_keys(self, unit_id: str) -> set[tuple]:
        for actor in pending_units(self._state, self._state.phase):
            if actor.unit_id == unit_id:
                payload, _ = self._activation(actor)
                return {_candidate_key(entry) for entry in payload["candidates"]}
        return set()

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

    def _advice(self, candidates: Sequence[Decision | Reaction]) -> dict[str, Any] | None:
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
