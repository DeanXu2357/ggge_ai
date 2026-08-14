"""沙盤門面：彙整後的候選要與逐項列舉器一致，讀取與推進走同一個物件。"""

from __future__ import annotations

from pathlib import Path

import pytest

from ggge_ai.sandbox.advise import Appraisal, Guarantee, Pricing, Verdict
from ggge_ai.sandbox.facade import Sandbox
from ggge_ai.sandbox.model import (
    DEFAULT_RULES,
    BattleState,
    Faction,
    MoveKind,
    Skill,
    StageEvent,
    Unit,
    Weapon,
    _pending,
    legal_attacks,
    legal_map_attacks,
    legal_skills,
    reachable_cells,
    reposition_moves,
    standby,
    strike_damage,
    strike_hit_probability,
)

PLACEHOLDER = Path(__file__).resolve().parents[1] / "assets/scenarios/uc_hard_1_placeholder.json"

FULL = 100000


def _rifle(name="rifle", power=1500, rmax=3, en_cost=0, can_counter=True):
    return Weapon(name, power=power, range_min=1, range_max=rmax, en_cost=en_cost,
                  can_counter=can_counter)


def _map_gun():
    return Weapon("mapgun", power=5000, range_min=1, range_max=4, map_weapon=True, blast=1)


def _skirmish() -> BattleState:
    lead = Unit(
        unit_id="a", faction=Faction.ALLY, pos=(0, 0), hp=100, max_hp=100, en=30, en_max=50,
        unit_attack=5000, pilot_attack=5000, move_range=2,
        weapons=[_rifle(), _map_gun()], ammo={"mapgun": 1},
        skills=[Skill(MoveKind.SKILL_EN_REFILL, amount=10)],
    )
    wing = Unit(
        unit_id="a2", faction=Faction.ALLY, pos=(0, 3), hp=100, max_hp=100, en=10, en_max=10,
        unit_attack=4000, pilot_attack=4000, move_range=1, weapons=[_rifle()],
    )
    foes = [
        Unit(unit_id=uid, faction=Faction.ENEMY, pos=pos, hp=FULL, max_hp=FULL,
             unit_defense=1000, pilot_defense=1000, weapons=[_rifle()])
        for uid, pos in (("e1", (2, 0)), ("e2", (3, 2)))
    ]
    return BattleState(units=[lead, wing, *foes], bounds=((0, 0), (5, 5)))


def _engagement() -> BattleState:
    attacker = Unit(
        unit_id="boss", faction=Faction.ENEMY, pos=(1, 0), hp=9000, max_hp=9000,
        unit_attack=5000, pilot_attack=1000, mobility=400, weapons=[_rifle()],
    )
    defender = Unit(
        unit_id="d", faction=Faction.ALLY, pos=(0, 0), hp=9000, max_hp=9000, en=50, en_max=50,
        unit_attack=4000, pilot_attack=4000, unit_defense=2000, pilot_defense=2000,
        reaction=3000, mobility=300, has_shield=True,
        weapons=[_rifle(), _rifle(name="pistol", can_counter=False)],
    )
    supporter = Unit(
        unit_id="s", faction=Faction.ALLY, pos=(0, 1), hp=9000, max_hp=9000, move_range=3,
        unit_defense=1000, pilot_defense=1000,
        support_defend_charges=1, support_defend_charges_max=1,
    )
    return BattleState(units=[defender, supporter, attacker], phase=Faction.ENEMY)


def _entry(payload, uid):
    return next(entry for entry in payload["units"] if entry["uid"] == uid)


def _kind(entry, kind):
    return next(c for c in entry["candidates"] if c["kind"] == kind)


class _StubAdvisor:
    def appraise(self, state):
        return Appraisal(verdict=Verdict.PURSUE, reason="stub")

    def price(self, state, candidates):
        return [Pricing(cost=float(i), guarantee=Guarantee.KILL) for i in range(len(candidates))]


@pytest.fixture(scope="module")
def placeholder():
    return Sandbox.from_scenario(PLACEHOLDER)


def test_snapshot_carries_board_and_units(placeholder):
    payload = placeholder.snapshot()

    assert payload["board"] == {"cols": 25, "rows": 20}
    assert (payload["turn"], payload["phase"], payload["outcome"]) == (1, "ally", None)
    assert len(payload["units"]) == 28
    enemy = next(u for u in payload["units"] if u["cell"] == [9, 4])
    assert (enemy["uid"], enemy["hp"], enemy["en_max"]) == ("e1", 83811, 513)
    assert {"name", "power", "range_min", "range_max", "en_cost", "accuracy", "ammo"} <= set(
        enemy["weapons"][0]
    )


def test_snapshot_reports_skills_and_charges(placeholder):
    support = next(u for u in placeholder.units() if u["has_shield"])

    assert support["skills"] == [{"kind": "skill_en_refill", "amount": 120.0, "uses": 1}]
    assert support["support_defend_charges"] == 1


def test_read_methods_report_the_scenario_products(placeholder):
    assert placeholder.turn() == 1
    assert placeholder.phase() == "ally"
    assert placeholder.board() == {"cols": 25, "rows": 20}
    assert placeholder.rules()["defend_multiplier"] == DEFAULT_RULES.defend_multiplier
    assert placeholder.units() == placeholder.snapshot()["units"]


def test_events_serialize_their_spawned_units():
    state = _skirmish()
    reinforcement = Unit(unit_id="e9", faction=Faction.ENEMY, pos=(5, 5), hp=10, max_hp=10)
    events = {
        "ev1": StageEvent(
            event_id="ev1",
            trigger={"type": "kill", "uid": "e1"},
            effect={"type": "spawn", "units": [reinforcement]},
        )
    }

    table = Sandbox(state, DEFAULT_RULES, events).events()

    assert table["ev1"]["trigger"] == {"type": "kill", "uid": "e1"}
    assert table["ev1"]["effect"]["units"] == [
        Sandbox(BattleState(units=[reinforcement]), DEFAULT_RULES).units()[0]
    ]


def test_pending_decision_matches_the_piecewise_enumerators():
    state = _skirmish()
    payload = Sandbox(state, DEFAULT_RULES).pending_decision()

    assert payload["kind"] == "activation"
    assert [entry["uid"] for entry in payload["units"]] == [
        unit.unit_id for unit in _pending(state, state.phase)
    ]
    for entry in payload["units"]:
        unit = state.unit(entry["uid"])
        reach = reachable_cells(state, unit)
        expected = [
            *legal_attacks(state, unit, reach=reach),
            *legal_map_attacks(state, unit),
            *legal_skills(unit),
            *reposition_moves(state, unit, reach=reach),
            standby(unit.unit_id),
        ]
        assert entry["moves"] == sorted([cell[0], cell[1]] for cell in reach)
        assert [
            (c["kind"], c["unit_id"], c["weapon"], c["move_to"], c["aim"], c["amount"])
            for c in entry["candidates"]
        ] == [
            (
                str(d.kind),
                d.unit_id,
                d.weapon,
                None if d.move_to is None else list(d.move_to),
                None if d.aim is None else list(d.aim),
                d.amount,
            )
            for d in expected
        ]


def test_pending_decision_lists_every_kind_of_candidate():
    entry = _entry(Sandbox(_skirmish(), DEFAULT_RULES).pending_decision(), "a")

    kinds = {candidate["kind"] for candidate in entry["candidates"]}
    assert {"attack", "map_attack", "skill_en_refill", "reposition", "standby"} <= kinds


def test_attack_candidates_carry_the_formula_numbers():
    state = _skirmish()
    entry = _entry(Sandbox(state, DEFAULT_RULES).pending_decision(), "a")

    shot = _kind(entry, "attack")
    actor = state.unit("a")
    target = state.unit(shot["target_id"])
    weapon = actor.weapon(shot["weapon"])
    assert shot["hit_probability"] == strike_hit_probability(
        actor, target, weapon, rules=DEFAULT_RULES
    )
    assert shot["expected_damage"] == strike_damage(actor, target, weapon, rules=DEFAULT_RULES)


def test_map_attack_candidates_name_the_unit_under_the_aim():
    state = _skirmish()
    entry = _entry(Sandbox(state, DEFAULT_RULES).pending_decision(), "a")

    shell = _kind(entry, "map_attack")
    victim = state.unit(shell["target_id"])
    assert list(victim.pos) == shell["aim"]
    assert shell["hit_probability"] == 1.0
    assert shell["expected_damage"] == strike_damage(
        state.unit("a"), victim, state.unit("a").weapon("mapgun"), rules=DEFAULT_RULES
    )


def test_standby_candidates_carry_no_forecast():
    entry = _entry(Sandbox(_skirmish(), DEFAULT_RULES).pending_decision(), "a2")

    wait = _kind(entry, "standby")
    assert (wait["hit_probability"], wait["expected_damage"]) == (None, None)


def test_act_advances_the_state_and_leaves_the_input_alone():
    state = _skirmish()
    before = state.key()
    sandbox = Sandbox(state, DEFAULT_RULES)

    sandbox.act(_kind(_entry(sandbox.pending_decision(), "a"), "standby"))

    assert state.key() == before
    assert [entry["uid"] for entry in sandbox.pending_decision()["units"]] == ["a2"]


def test_act_applies_the_chosen_attack_and_the_defender_stance():
    plain = Sandbox(_skirmish(), DEFAULT_RULES)
    guarded = Sandbox(_skirmish(), DEFAULT_RULES)
    shot = _kind(_entry(plain.pending_decision(), "a"), "attack")

    snapshot = plain.act(shot)
    defended = guarded.act(shot, {"stance": "defend"})

    hit = next(u for u in snapshot["units"] if u["uid"] == shot["target_id"])
    softened = next(u for u in defended["units"] if u["uid"] == shot["target_id"])
    assert hit["hp"] < softened["hp"] < FULL


def test_act_rotates_the_phase_when_the_side_is_finished():
    sandbox = Sandbox(_skirmish(), DEFAULT_RULES)

    for uid in ("a", "a2"):
        sandbox.act(_kind(_entry(sandbox.pending_decision(), uid), "standby"))

    assert sandbox.phase() == "enemy"
    assert sandbox.turn() == 1


def test_reaction_options_cover_the_stances_and_the_support_defense():
    payload = Sandbox(_engagement(), DEFAULT_RULES).reaction_options("boss", "d")

    assert payload["kind"] == "reaction"
    assert payload["support_defender"] == "s"
    offered = {(option["stance"], option["weapon"], option["support_defend"])
               for option in payload["options"]}
    assert ("none", None, False) in offered
    assert ("shield", None, False) in offered
    assert ("counter", "rifle", False) in offered
    assert ("counter", "rifle", True) in offered
    assert ("counter", "pistol", False) not in offered


def test_reaction_options_price_each_defense():
    payload = Sandbox(_engagement(), DEFAULT_RULES).reaction_options("boss", "d")
    picked = {(o["stance"], o["support_defend"]): o for o in payload["options"]}

    plain = picked[("none", False)]
    assert picked[("defend", False)]["expected_damage"] < plain["expected_damage"]
    assert picked[("shield", False)]["expected_damage"] < picked[("defend", False)][
        "expected_damage"
    ]
    assert picked[("dodge", False)]["hit_probability"] < plain["hit_probability"]
    assert plain["struck"] == "d"
    assert picked[("none", True)]["struck"] == "s"


def test_reaction_options_are_empty_for_an_unknown_pair():
    payload = Sandbox(_engagement(), DEFAULT_RULES).reaction_options("boss", "ghost")

    assert payload["options"] == []
    assert payload["advice"] is None


def test_advice_stays_empty_without_an_advisor():
    sandbox = Sandbox(_skirmish(), DEFAULT_RULES)

    assert sandbox.pending_decision()["advice"] is None
    assert Sandbox(_engagement(), DEFAULT_RULES).reaction_options("boss", "d")["advice"] is None


def test_an_advisor_fills_the_advice_field_for_both_payloads():
    payload = Sandbox(_skirmish(), DEFAULT_RULES, advisor=_StubAdvisor()).pending_decision()

    advice = payload["advice"]
    assert advice["verdict"] == "pursue"
    assert len(advice["pricing"]) == sum(
        len(entry["candidates"]) for entry in payload["units"]
    )
    assert advice["pricing"][0] == {"cost": 0.0, "guarantee": "kill", "note": ""}

    reaction = Sandbox(_engagement(), DEFAULT_RULES, advisor=_StubAdvisor()).reaction_options(
        "boss", "d"
    )
    assert len(reaction["advice"]["pricing"]) == len(reaction["options"])
