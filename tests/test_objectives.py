"""Condition-driven objectives: terminal taxonomy, bounds, and the
solver walking toward the stage goal instead of farming kills."""

import random

from ggge_ai.content import objectives
from ggge_ai.battle.actions import ActionKind
from ggge_ai.planner.enemy_model import NearestTargetPolicy
from ggge_ai.sim import SimState, SimUnit, SimWeapon
from ggge_ai.sim.objective import annihilation_objective
from ggge_ai.planner.solver import SolverConfig, solve
from ggge_ai.content.stage_def import Condition, StageConditions, default_conditions
from ggge_ai.battle.state import Faction


def _weapon(name="rifle", power=5000, rmax=3, en_cost=0):
    return SimWeapon(name, power=power, range_min=1, range_max=rmax, en_cost=en_cost)


def _ally(uid="a", pos=(0, 0), hp=100, weapons=None, **kw):
    base = dict(unit_id=uid, faction=Faction.ALLY, pos=pos, hp=hp, max_hp=100,
                en=50, en_max=50, unit_attack=5000, pilot_attack=9000, move_range=3,
                weapons=weapons if weapons is not None else [])
    base.update(kw)
    return SimUnit(**base)


def _enemy(uid="e", pos=(2, 0), hp=100, weapons=None, **kw):
    base = dict(unit_id=uid, faction=Faction.ENEMY, pos=pos, hp=hp, max_hp=100,
                en=50, en_max=50, unit_attack=5000, pilot_attack=9000, move_range=3,
                unit_defense=1000, pilot_defense=1000,
                weapons=weapons if weapons is not None else [])
    base.update(kw)
    return SimUnit(**base)


def _objective(victory=None, defeat=None, allies=2, enemies=2):
    conditions = StageConditions(
        victory=victory if victory is not None else [Condition(type="annihilate")],
        defeat=defeat if defeat is not None else [],
    )
    return objectives.make_objective(conditions, allies, enemies)


def test_annihilate_victory_is_positive_terminal():
    obj, _ = _objective()
    state = SimState(units=[_ally()])
    assert obj.terminal(state, None) > 0


def test_all_allies_lost_is_implied_and_negative():
    obj, _ = _objective()
    state = SimState(units=[_enemy()])
    assert obj.terminal(state, None) < 0


def test_defeat_wins_ties():
    obj, _ = _objective()
    state = SimState(units=[])
    assert obj.terminal(state, None) < 0


def test_decapitate_ends_with_targets_dead_only():
    obj, _ = _objective(
        victory=[Condition(type="decapitate", params={"targets": ["boss"]})]
    )
    fighting = SimState(units=[_ally(), _enemy("boss"), _enemy("minion")])
    assert obj.terminal(fighting, None) is None
    beheaded = SimState(units=[_ally(), _enemy("minion")])
    assert obj.terminal(beheaded, None) > 0


def test_ward_lost_is_negative_terminal():
    obj, _ = _objective(defeat=[Condition(type="ward_lost", params={"wards": ["vip"]})])
    ward_alive = SimState(
        units=[_ally(), _ally("vip", pos=(1, 1)), _enemy()]
    )
    assert obj.terminal(ward_alive, None) is None
    ward_dead = SimState(units=[_ally(), _enemy()])
    assert obj.terminal(ward_dead, None) < 0


def test_turn_limit_expiry_sides():
    survive, _ = _objective(victory=[Condition(type="turn_limit", params={"turns": 3})])
    rush, _ = _objective(defeat=[Condition(type="turn_limit", params={"turns": 3})])
    live = SimState(units=[_ally(), _enemy()], turn=3)
    over = SimState(units=[_ally(), _enemy()], turn=4)
    assert survive.terminal(live, None) is None
    assert survive.terminal(over, None) > 0
    assert rush.terminal(over, None) < 0


def test_reach_triggers_on_ally_at_cell():
    obj, _ = _objective(
        victory=[Condition(type="reach", params={"cell": [5, 5], "radius": 0})]
    )
    away = SimState(units=[_ally(pos=(0, 0)), _enemy()])
    there = SimState(units=[_ally(pos=(5, 5)), _enemy()])
    assert obj.terminal(away, None) is None
    assert obj.terminal(there, None) > 0


def test_verbatim_victory_degrades_to_annihilate_with_note():
    obj, notes = _objective(
        victory=[Condition(type="escort_convoy", text="護送車隊到北端")]
    )
    assert any("outside the taxonomy" in n for n in notes)
    assert any("degrading to annihilate" in n for n in notes)
    state = SimState(units=[_ally()])
    assert obj.terminal(state, None) > 0


def test_bounds_contain_terminal_values():
    obj, _ = _objective(
        victory=[Condition(type="decapitate", params={"targets": ["boss"]})],
        defeat=[Condition(type="ward_lost", params={"wards": ["vip"]})],
    )
    vmin, vmax = obj.bounds
    won = SimState(units=[_ally()])
    assert vmin <= obj.terminal(won, None) <= vmax
    lost = SimState(units=[_enemy()])
    assert vmin <= obj.terminal(lost, None) <= vmax


def test_decapitation_stage_goes_for_the_commander():
    # depth 1 = a single activation: only the commander kill reaches the
    # win terminal inside the horizon, so the objective must outweigh the
    # equal kill-count value of the nearer minion. (With a wider horizon
    # both orders win and the fixed terminal value is indifferent between
    # them -- a documented v1 simplification.)
    ally = _ally(weapons=[_weapon(power=5000)])
    minion = _enemy("minion", pos=(2, 0), hp=5, weapons=[])
    boss = _enemy("boss", pos=(3, 0), hp=5, weapons=[])
    conditions = StageConditions(
        victory=[Condition(type="decapitate", params={"targets": ["boss"]})],
        defeat=[],
    )
    obj, _ = objectives.make_objective(conditions, 1, 2)
    state = SimState(units=[ally, minion, boss])
    result = solve(
        state,
        NearestTargetPolicy(),
        SolverConfig(time_budget_s=2.0, max_depth=1, objective=obj),
    )
    attacks = [d.target_id for d in result.pv if d.kind == ActionKind.ATTACK]
    assert attacks and attacks[0] == "boss"
    vmin, vmax = obj.bounds
    assert result.value == vmax

    plain = solve(
        state,
        NearestTargetPolicy(),
        SolverConfig(time_budget_s=2.0, max_depth=1),
    )
    plain_attacks = [d.target_id for d in plain.pv if d.kind == ActionKind.ATTACK]
    assert plain_attacks and plain_attacks[0] == "minion"


def test_star1_and_tt_agree_under_a_condition_objective():
    ally = _ally(weapons=[_weapon(power=3000)], react_charges=1, react_charges_max=1)
    minion = _enemy("minion", pos=(2, 0), hp=40, weapons=[_weapon(power=800)])
    boss = _enemy("boss", pos=(3, 0), hp=40, weapons=[_weapon(power=800)])
    conditions = StageConditions(
        victory=[Condition(type="decapitate", params={"targets": ["boss"]})],
        defeat=[],
    )
    obj, _ = objectives.make_objective(conditions, 1, 2)
    state = SimState(units=[ally, minion, boss])

    def run(use_star1, use_tt):
        return solve(
            state,
            NearestTargetPolicy(),
            SolverConfig(
                time_budget_s=5.0,
                max_depth=3,
                use_star1=use_star1,
                use_tt=use_tt,
                objective=obj,
            ),
        ).value

    reference = run(False, False)
    assert run(True, True) == reference
    assert run(True, False) == reference
    assert run(False, True) == reference


def test_default_config_matches_wrapped_annihilation_objective():
    rng = random.Random(7)
    for _ in range(5):
        units = [
            _ally(
                "a1",
                pos=(rng.randint(0, 2), rng.randint(0, 2)),
                hp=rng.randint(20, 100),
                weapons=[_weapon(power=rng.choice([2000, 5000]))],
            ),
            _ally("a2", pos=(0, 3), hp=rng.randint(20, 100), weapons=[_weapon()]),
            _enemy(
                "e1",
                pos=(rng.randint(3, 5), rng.randint(0, 2)),
                hp=rng.randint(20, 100),
                weapons=[_weapon(power=rng.choice([2000, 4000]))],
            ),
            _enemy("e2", pos=(5, 3), hp=rng.randint(20, 100), weapons=[_weapon()]),
        ]
        state = SimState(units=[u.clone() for u in units])
        plain = solve(state, NearestTargetPolicy(), SolverConfig(time_budget_s=3.0, max_depth=2))
        wrapped = solve(
            state,
            NearestTargetPolicy(),
            SolverConfig(
                time_budget_s=3.0,
                max_depth=2,
                objective=annihilation_objective(),
            ),
        )
        assert plain.value == wrapped.value
        assert plain.decision == wrapped.decision


def test_default_conditions_round_trip_into_an_objective():
    obj, notes = objectives.make_objective(default_conditions(), 2, 2)
    assert notes == []
    state = SimState(units=[_ally(), _enemy()])
    assert obj.terminal(state, None) is None
