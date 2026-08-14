"""沙盤門面：彙整後的候選要與逐項列舉器一致，讀取與推進走同一個物件。"""

from __future__ import annotations

import ast
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
    legal_attacks,
    legal_map_attacks,
    legal_reactions,
    legal_skills,
    pending_units,
    reachable_cells,
    reposition_moves,
    standby,
    strike_damage,
    strike_hit_probability,
)

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = ROOT / "assets/scenarios/uc_hard_1_placeholder.json"
FACADE = ROOT / "src/ggge_ai/sandbox/facade.py"

FULL = 100000
BOSS_HP = 200000


def _rifle(name="rifle", power=1500, rmin=1, rmax=3, en_cost=0, can_counter=True):
    return Weapon(name, power=power, range_min=rmin, range_max=rmax, en_cost=en_cost,
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
        for uid, pos in (("e1", (2, 0)), ("e2", (3, 1)))
    ]
    return BattleState(units=[lead, wing, *foes], bounds=((0, 0), (5, 5)))


def _engagement() -> BattleState:
    attacker = Unit(
        unit_id="boss", faction=Faction.ENEMY, pos=(9, 0), hp=BOSS_HP, max_hp=BOSS_HP,
        move_range=8, unit_attack=5000, pilot_attack=1000, mobility=400,
        unit_defense=3000, pilot_defense=3000,
        weapons=[_rifle(rmax=1)],
    )
    defender = Unit(
        unit_id="d", faction=Faction.ALLY, pos=(0, 0), hp=9000, max_hp=9000, en=50, en_max=50,
        unit_attack=4000, pilot_attack=4000, unit_defense=2000, pilot_defense=2000,
        reaction=2000, mobility=300, has_shield=True,
        weapons=[_rifle(), _rifle(name="pistol", can_counter=False)],
    )
    supporter = Unit(
        unit_id="s", faction=Faction.ALLY, pos=(0, 1), hp=9000, max_hp=9000, move_range=3,
        unit_attack=4000, pilot_attack=4000, unit_defense=1000, pilot_defense=1000,
        weapons=[_rifle()],
        support_defend_charges=1, support_defend_charges_max=1,
        support_attack_charges=1, support_attack_charges_max=1,
    )
    return BattleState(units=[defender, supporter, attacker], phase=Faction.ENEMY)


def _entry(payload, uid):
    return next(entry for entry in payload["units"] if entry["uid"] == uid)


def _kind(entry, kind):
    return next(c for c in entry["candidates"] if c["kind"] == kind)


def _boss_strike(sandbox):
    return _kind(_entry(sandbox.pending_decision(), "boss"), "attack")


def _option(payload, stance, *, support_defend=False, support_attack=True):
    return next(
        o for o in payload["options"]
        if o["stance"] == stance
        and o["support_defend"] == support_defend
        and o["support_attack"] == support_attack
    )


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


def test_the_facade_imports_no_private_model_helper():
    tree = ast.parse(FACADE.read_text(encoding="utf-8"))

    private = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.name.startswith("_")
    ]

    assert private == []


def test_pending_decision_matches_the_piecewise_enumerators():
    state = _skirmish()
    payload = Sandbox(state, DEFAULT_RULES).pending_decision()

    assert payload["kind"] == "activation"
    assert [entry["uid"] for entry in payload["units"]] == [
        unit.unit_id for unit in pending_units(state, state.phase)
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


def test_map_attack_candidates_price_every_unit_in_the_blast():
    state = _skirmish()
    entry = _entry(Sandbox(state, DEFAULT_RULES).pending_decision(), "a")

    shell = _kind(entry, "map_attack")
    actor = state.unit("a")
    gun = actor.weapon("mapgun")
    assert shell["aim"] == [2, 0]
    assert [victim["uid"] for victim in shell["victims"]] == ["e1", "e2"]
    assert shell["target_id"] == "e1"
    assert shell["hit_probability"] == 1.0
    assert shell["expected_damage"] == sum(
        strike_damage(actor, state.unit(uid), gun, rules=DEFAULT_RULES) for uid in ("e1", "e2")
    )
    assert shell["expected_damage"] > shell["victims"][0]["expected_damage"]


def test_standby_candidates_carry_no_forecast():
    entry = _entry(Sandbox(_skirmish(), DEFAULT_RULES).pending_decision(), "a2")

    wait = _kind(entry, "standby")
    assert (wait["hit_probability"], wait["expected_damage"], wait["victims"]) == (None, None, [])


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


def test_act_passes_the_dice_through_to_the_model():
    landed = Sandbox(_skirmish(), DEFAULT_RULES)
    missed = Sandbox(_skirmish(), DEFAULT_RULES)
    shot = _kind(_entry(landed.pending_decision(), "a"), "attack")

    struck = landed.act(shot)
    spared = missed.act({**shot, "hit": False})

    target = shot["target_id"]
    assert next(u for u in struck["units"] if u["uid"] == target)["hp"] < FULL
    assert next(u for u in spared["units"] if u["uid"] == target)["hp"] == FULL


def test_act_passes_the_counter_die_through_to_the_model():
    countered = Sandbox(_engagement(), DEFAULT_RULES)
    whiffed = Sandbox(_engagement(), DEFAULT_RULES)
    strike = _boss_strike(countered)
    reaction = {"stance": "counter", "weapon": "rifle", "support_attack": False}

    hurt = countered.act(strike, reaction)
    unhurt = whiffed.act({**strike, "counter_hit": False}, reaction)

    assert next(u for u in hurt["units"] if u["uid"] == "boss")["hp"] < BOSS_HP
    assert next(u for u in unhurt["units"] if u["uid"] == "boss")["hp"] == BOSS_HP


def test_act_round_trips_the_support_attack_choice():
    joined = Sandbox(_engagement(), DEFAULT_RULES)
    held = Sandbox(_engagement(), DEFAULT_RULES)
    strike = _boss_strike(joined)

    with_volley = joined.act(strike, {"stance": "none", "support_attack": True})
    without_volley = held.act(strike, {"stance": "none", "support_attack": False})

    assert next(u for u in with_volley["units"] if u["uid"] == "boss")["hp"] < BOSS_HP
    assert next(u for u in without_volley["units"] if u["uid"] == "boss")["hp"] == BOSS_HP


def test_act_rejects_a_candidate_that_is_no_longer_legal():
    sandbox = Sandbox(_skirmish(), DEFAULT_RULES)
    wait = _kind(_entry(sandbox.pending_decision(), "a"), "standby")
    sandbox.act(wait)

    with pytest.raises(ValueError, match="合法清單"):
        sandbox.act(wait)


def test_act_rejects_an_invented_candidate():
    sandbox = Sandbox(_skirmish(), DEFAULT_RULES)

    with pytest.raises(ValueError, match="合法清單"):
        sandbox.act({"kind": "attack", "unit_id": "a", "target_id": "e1", "weapon": "beam"})


def test_act_rejects_a_malformed_cell():
    sandbox = Sandbox(_skirmish(), DEFAULT_RULES)

    with pytest.raises(ValueError, match="格位"):
        sandbox.act({"kind": "reposition", "unit_id": "a", "move_to": [1, 2, 3]})


def test_act_rejects_a_reaction_that_the_rules_forbid():
    sandbox = Sandbox(_engagement(), DEFAULT_RULES)
    strike = _boss_strike(sandbox)

    with pytest.raises(ValueError, match="應戰"):
        sandbox.act(strike, {"stance": "defend", "support_defend": True})


def test_reaction_options_equal_the_model_enumerator():
    state = _engagement()
    sandbox = Sandbox(state, DEFAULT_RULES)
    strike = _boss_strike(sandbox)

    payload = sandbox.reaction_options(strike)

    expected = legal_reactions(
        state, state.unit("d"), state.unit("boss"),
        state.unit("boss").weapon("rifle"), attacker_pos=(1, 0),
    )
    assert payload["attacker_cell"] == [1, 0]
    assert [
        (o["stance"], o["weapon"], o["support_defend"], o["support_attack"])
        for o in payload["options"]
    ] == [
        (str(r.stance), r.weapon, r.support_defend, r.support_attack) for r in expected
    ]


def test_reaction_options_read_the_counter_from_the_post_move_cell():
    sandbox = Sandbox(_engagement(), DEFAULT_RULES)
    strike = _boss_strike(sandbox)

    payload = sandbox.reaction_options(strike)

    assert strike["move_to"] == [1, 0]
    assert any(option["stance"] == "counter" for option in payload["options"])
    assert not any(option["weapon"] == "pistol" for option in payload["options"])


def test_support_defense_never_pairs_with_defend_or_shield():
    sandbox = Sandbox(_engagement(), DEFAULT_RULES)

    payload = sandbox.reaction_options(_boss_strike(sandbox))

    assert payload["support_defender"] == "s"
    paired = {o["stance"] for o in payload["options"] if o["support_defend"]}
    assert paired == {"none", "dodge", "counter"}


def test_reaction_options_offer_both_support_attack_variants():
    sandbox = Sandbox(_engagement(), DEFAULT_RULES)

    payload = sandbox.reaction_options(_boss_strike(sandbox))

    assert _option(payload, "none", support_attack=True)["support_attackers"] == ["s"]
    assert _option(payload, "none", support_attack=False)["support_attackers"] == []


def test_no_two_reaction_options_resolve_the_same_way():
    sandbox = Sandbox(_engagement(), DEFAULT_RULES)

    payload = sandbox.reaction_options(_boss_strike(sandbox))

    resolutions = [
        (
            option["struck"],
            option["hit_probability"],
            option["expected_damage"],
            option["weapon"],
            tuple(option["support_attackers"]),
        )
        for option in payload["options"]
    ]
    assert len(set(resolutions)) == len(resolutions)


def test_reaction_options_price_each_defense():
    sandbox = Sandbox(_engagement(), DEFAULT_RULES)

    payload = sandbox.reaction_options(_boss_strike(sandbox))

    plain = _option(payload, "none")
    assert _option(payload, "defend")["expected_damage"] < plain["expected_damage"]
    assert _option(payload, "shield")["expected_damage"] < _option(payload, "defend")[
        "expected_damage"
    ]
    assert _option(payload, "dodge")["hit_probability"] < plain["hit_probability"]
    assert plain["struck"] == "d"
    assert _option(payload, "none", support_defend=True)["struck"] == "s"


def test_reaction_options_reject_a_candidate_that_is_not_an_attack():
    sandbox = Sandbox(_skirmish(), DEFAULT_RULES)
    wait = _kind(_entry(sandbox.pending_decision(), "a"), "standby")

    with pytest.raises(ValueError, match="只有攻擊"):
        sandbox.reaction_options(wait)


def test_reaction_options_reject_an_unknown_weapon():
    sandbox = Sandbox(_engagement(), DEFAULT_RULES)
    strike = _boss_strike(sandbox)

    with pytest.raises(ValueError, match="沒有這個武裝"):
        sandbox.reaction_options({**strike, "weapon": "beam"})


def test_reaction_options_reject_a_map_weapon():
    sandbox = Sandbox(_skirmish(), DEFAULT_RULES)
    shot = _kind(_entry(sandbox.pending_decision(), "a"), "attack")

    with pytest.raises(ValueError, match="地圖兵器"):
        sandbox.reaction_options({**shot, "weapon": "mapgun"})


def test_advice_stays_empty_without_an_advisor():
    sandbox = Sandbox(_engagement(), DEFAULT_RULES)

    assert Sandbox(_skirmish(), DEFAULT_RULES).pending_decision()["advice"] is None
    assert sandbox.reaction_options(_boss_strike(sandbox))["advice"] is None


def test_an_advisor_fills_the_advice_field_for_both_payloads():
    payload = Sandbox(_skirmish(), DEFAULT_RULES, advisor=_StubAdvisor()).pending_decision()

    advice = payload["advice"]
    assert advice["verdict"] == "pursue"
    assert len(advice["pricing"]) == sum(
        len(entry["candidates"]) for entry in payload["units"]
    )
    assert advice["pricing"][0] == {"cost": 0.0, "guarantee": "kill", "note": ""}

    sandbox = Sandbox(_engagement(), DEFAULT_RULES, advisor=_StubAdvisor())
    reaction = sandbox.reaction_options(_boss_strike(sandbox))
    assert len(reaction["advice"]["pricing"]) == len(reaction["options"])
