import random

import pytest

from ggge_ai.battle.actions import ActionKind
from ggge_ai.sim.enemy_model import (
    MinimaxEnemy,
    NearestTargetPolicy,
)
from ggge_ai.sim import (
    DEFAULT_PARAMS,
    DefenseKind,
    DefenseResponse,
    Phase,
    SimState,
    SimUnit,
    SimWeapon,
    compute_damage,
    step,
)
from ggge_ai.sim.objective import EvalContext, EvalWeights, default_evaluator
from ggge_ai.sim.solver import (
    SolverConfig,
    solve,
)
from ggge_ai.battle.state import Faction


def _weapon(name="rifle", power=5000, rmax=3, en_cost=0, can_counter=True):
    return SimWeapon(name, power=power, range_min=1, range_max=rmax,
                     en_cost=en_cost, can_counter=can_counter)


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


def test_reactivation_lets_solver_find_double_kill_chain():
    ally = _ally(weapons=[_weapon(power=5000)], react_charges=2, react_charges_max=2)
    e0 = _enemy("e0", pos=(2, 0), hp=5, weapons=[])
    e1 = _enemy("e1", pos=(3, 0), hp=5, weapons=[])
    state = SimState(units=[ally, e0, e1])
    result = solve(state, NearestTargetPolicy(), SolverConfig(time_budget_s=2.0))
    attack_targets = [d.target_id for d in result.pv if d.kind == ActionKind.ATTACK]
    assert set(attack_targets) == {"e0", "e1"}


def test_enemy_phase_picks_better_defense_response():
    # counter kills the attacker (good for us) vs merely defending (enemy lives)
    ally = _ally(uid="a", pos=(0, 0), hp=100000, max_hp=100000,
                 weapons=[_weapon(power=5000)])
    boss = _enemy("boss", pos=(1, 0), hp=40, unit_attack=1000, pilot_attack=1000,
                  weapons=[_weapon(power=200)])
    state = SimState(units=[ally, boss], phase=Phase.ENEMY)
    result = solve(state, NearestTargetPolicy(), SolverConfig(time_budget_s=2.0, max_depth=1))

    ctx = EvalContext(weights=EvalWeights(), base_allies=1, base_enemies=1)

    counter_state = step(
        state,
        _attack(state, "boss", "a", DefenseResponse(DefenseKind.COUNTER)),
    )
    defend_state = step(
        state,
        _attack(state, "boss", "a", DefenseResponse(DefenseKind.DEFEND)),
    )
    v_counter = default_evaluator(counter_state, ctx)
    v_defend = default_evaluator(defend_state, ctx)
    assert v_counter > v_defend
    assert abs(result.value - v_counter) < 1e-6


def test_solver_prices_enemy_counter_on_our_attacks():
    # the strike barely scratches, the counter destroys us: stand by instead
    m = _ally("m", pos=(0, 0), hp=10, max_hp=10, move_range=0,
              unit_attack=1000, pilot_attack=1000,
              weapons=[_weapon("saber", power=200, rmax=1)])
    e = _enemy("e", pos=(1, 0), hp=100_000, max_hp=100_000, move_range=0,
               weapons=[_weapon(power=9000, rmax=1)])
    state = SimState(units=[m, e])
    result = solve(state, NearestTargetPolicy(), SolverConfig(max_depth=1))
    assert result.decision.kind == ActionKind.STANDBY


def test_solver_takes_the_kill_that_silences_return_fire():
    # killing the target first cancels its counter and the support fire
    m = _ally("m", pos=(0, 0), hp=10, max_hp=10, move_range=0,
              weapons=[_weapon(power=9000, rmax=2)])
    e = _enemy("e", pos=(1, 0), hp=5, move_range=0,
               weapons=[_weapon(power=9000, rmax=1)])
    guard = _enemy("g", pos=(2, 0), hp=10**9, max_hp=10**9, move_range=3,
                   weapons=[_weapon(power=9000, rmax=3)],
                   support_attack_charges=1, support_attack_charges_max=1)
    state = SimState(units=[m, e, guard])
    result = solve(state, NearestTargetPolicy(), SolverConfig(max_depth=1))
    assert result.decision.kind == ActionKind.ATTACK
    assert result.decision.target_id == "e"


def test_solver_keeps_the_volley_for_the_kill_that_needs_it():
    # winning line: solo-kill b (saving n's charge), re-act, volley a, n attacks a
    m = _ally("m", pos=(0, 0), hp=10**9, max_hp=10**9, move_range=0,
              weapons=[_weapon(power=5000)], react_charges=1, react_charges_max=1)
    n = _ally("n", pos=(1, 0), hp=10**9, max_hp=10**9, move_range=1,
              weapons=[_weapon(power=5000)],
              support_attack_charges=1, support_attack_charges_max=1)
    b = _enemy("b", pos=(1, 1), hp=1, move_range=0, weapons=[])
    a = _enemy("a", pos=(2, 0), hp=100, move_range=0, weapons=[_weapon(power=5000)])
    dmg = compute_damage(m, a, m.weapons[0], 1.0, DEFAULT_PARAMS)
    a.hp = a.max_hp = int(dmg * 2.5)
    state = SimState(units=[m, n, b, a])
    result = solve(state, NearestTargetPolicy(),
                   SolverConfig(time_budget_s=10.0, max_depth=1))
    end = state
    for d in result.pv:
        end = step(end, d)
    assert not end.enemies()
    assert any(d.kind == ActionKind.ATTACK and d.support is False for d in result.pv)


def test_solver_finds_the_map_shot_that_normal_attacks_cannot_match():
    m = _ally("m", pos=(0, 0), hp=10**9, max_hp=10**9, move_range=0,
              weapons=[SimWeapon("mapgun", power=9000, range_min=1, range_max=4,
                                 map_weapon=True, blast=1)])
    m.weapon_ammo = {"mapgun": 1}
    e0 = _enemy("e0", pos=(2, 0), hp=5, move_range=0, weapons=[])
    e1 = _enemy("e1", pos=(2, 1), hp=5, move_range=0, weapons=[])
    state = SimState(units=[m, e0, e1])
    result = solve(state, NearestTargetPolicy(), SolverConfig(max_depth=1))
    assert result.decision.kind == ActionKind.MAP_ATTACK
    end = step(state, result.decision)
    assert not end.enemies()


def test_min_mode_is_more_pessimistic_than_policy():
    tank = _ally("tank", pos=(1, 0), hp=1_000_000, max_hp=1_000_000, weapons=[])
    weak = _ally("weak", pos=(3, 0), hp=1, weapons=[])
    enemy = _enemy("e", pos=(0, 0), hp=100, weapons=[_weapon(power=5000, rmax=4)],
                   move_range=0)
    state = SimState(units=[tank, weak, enemy], phase=Phase.ENEMY)

    policy_value = solve(state, NearestTargetPolicy(), SolverConfig(max_depth=1)).value
    min_value = solve(state, MinimaxEnemy(), SolverConfig(max_depth=1)).value
    assert min_value < policy_value


def test_smoke_4v4_returns_legal_first_step_within_budget():
    units = []
    for i in range(4):
        units.append(_ally(f"a{i}", pos=(0, i), hp=100,
                           weapons=[_weapon(power=1500, rmax=3)], pilot_attack=3000))
    for i in range(4):
        units.append(_enemy(f"e{i}", pos=(5, i), hp=100,
                            weapons=[_weapon(power=1500, rmax=3)], pilot_attack=3000))
    state = SimState(units=units)
    result = solve(state, NearestTargetPolicy(), SolverConfig(time_budget_s=2.0))
    assert result.decision is not None
    assert result.stats.depth >= 1
    assert result.stats.nodes > 0
    assert result.decision.unit_id in {u.unit_id for u in state.allies()}


def _random_state(rng):
    cells = rng.sample([(x, y) for x in range(5) for y in range(5)], 4)
    units = []
    for i in range(2):
        units.append(SimUnit(
            unit_id=f"a{i}", faction=Faction.ALLY, pos=cells[i],
            hp=rng.randrange(20, 121), max_hp=120,
            en=rng.randrange(0, 31), en_max=30,
            unit_attack=4000, pilot_attack=rng.randrange(800, 1400),
            unit_defense=800, pilot_defense=600,
            reaction=rng.randrange(1500, 3200), mobility=rng.randrange(0, 2000),
            move_range=rng.randrange(1, 4),
            weapons=[SimWeapon("w", power=rng.randrange(1500, 6000), range_min=1,
                               range_max=rng.randrange(1, 4),
                               en_cost=rng.choice([0, 5, 10]))],
            react_charges=rng.randrange(0, 2), react_charges_max=1,
            support_defend_charges=rng.randrange(0, 2), support_defend_charges_max=1,
            support_attack_charges=rng.randrange(0, 2), support_attack_charges_max=1,
        ))
    for i in range(2):
        units.append(SimUnit(
            unit_id=f"e{i}", faction=Faction.ENEMY, pos=cells[2 + i],
            hp=rng.randrange(20, 121), max_hp=120,
            en=rng.randrange(0, 31), en_max=30,
            unit_attack=4000, pilot_attack=rng.randrange(800, 1400),
            unit_defense=800, pilot_defense=600,
            reaction=rng.randrange(1500, 3200), mobility=rng.randrange(0, 2000),
            move_range=rng.randrange(1, 4),
            weapons=[SimWeapon("w", power=rng.randrange(1500, 6000), range_min=1,
                               range_max=rng.randrange(1, 4),
                               en_cost=rng.choice([0, 5, 10]))],
            support_defend_charges=rng.randrange(0, 2), support_defend_charges_max=1,
            support_attack_charges=rng.randrange(0, 2), support_attack_charges_max=1,
        ))
    return SimState(units=units)


def test_pruning_and_tt_match_unpruned_reference():
    for seed in range(8):
        state = _random_state(random.Random(seed))
        for model in (NearestTargetPolicy(), MinimaxEnemy()):
            fast = solve(state, model, SolverConfig(time_budget_s=60.0, max_depth=3))
            slow = solve(state, model, SolverConfig(time_budget_s=60.0, max_depth=3,
                                                    use_tt=False, use_star1=False))
            assert fast.stats.depth == slow.stats.depth == 3
            assert fast.value == pytest.approx(slow.value, abs=1e-6)
            assert fast.stats.nodes <= slow.stats.nodes


def _attack(state, attacker_id, target_id, defense):
    attacker = state.unit(attacker_id)
    weapon = attacker.weapons[0].name if attacker.weapons else None
    return _mk_decision(attacker_id, target_id, weapon, defense)


def _mk_decision(attacker_id, target_id, weapon, defense):
    from ggge_ai.sim import Decision

    return Decision(attacker_id, ActionKind.ATTACK, target_id=target_id,
                    weapon=weapon, hit=True, defense=defense)


def test_solver_refills_en_then_attacks_in_same_activation():
    from ggge_ai.sim import SimSkill

    ally = _ally(weapons=[_weapon(power=5000, en_cost=10)], en=0, en_max=20)
    ally.skills = [SimSkill(ActionKind.SKILL_EN_REFILL, ends_turn=False)]
    enemy = _enemy("e0", pos=(1, 0), hp=5, weapons=[])
    state = SimState(units=[ally, enemy])
    result = solve(state, NearestTargetPolicy(), SolverConfig(time_budget_s=5.0, max_depth=2))
    kinds = [d.kind for d in result.pv[:2]]
    assert kinds == [ActionKind.SKILL_EN_REFILL, ActionKind.ATTACK]


def test_solver_refill_beats_standby_when_it_ends_the_turn():
    from ggge_ai.sim import SimSkill

    ally = _ally(weapons=[_weapon(power=5000, en_cost=10)], en=0, en_max=20)
    ally.skills = [SimSkill(ActionKind.SKILL_EN_REFILL)]
    enemy = _enemy("e0", pos=(1, 0), hp=5, weapons=[], move_range=0)
    state = SimState(units=[ally, enemy])
    result = solve(state, NearestTargetPolicy(), SolverConfig(time_budget_s=5.0, max_depth=4))
    assert result.decision is not None
    assert result.decision.kind == ActionKind.SKILL_EN_REFILL


def test_solver_advances_on_out_of_reach_enemy():
    from ggge_ai.sim import chebyshev

    ally = _ally(pos=(0, 0), weapons=[_weapon(power=5000, rmax=1)], move_range=3)
    enemy = _enemy("e0", pos=(5, 0), hp=5, weapons=[], move_range=0)
    state = SimState(units=[ally, enemy])
    result = solve(state, NearestTargetPolicy(), SolverConfig(time_budget_s=5.0, max_depth=4))
    assert result.decision is not None
    assert result.decision.kind == ActionKind.MOVE
    assert chebyshev(result.decision.move_to, enemy.pos) < 5


def test_solver_retreats_out_of_lethal_reach():
    from ggge_ai.sim import chebyshev

    ally = _ally(pos=(0, 0), hp=10, max_hp=10, weapons=[], move_range=2)
    enemy = _enemy("e0", pos=(2, 0), hp=1000, max_hp=1000, move_range=1,
                   weapons=[_weapon(power=99000, rmax=1)])
    state = SimState(units=[ally, enemy])
    result = solve(state, NearestTargetPolicy(), SolverConfig(time_budget_s=5.0, max_depth=3))
    assert result.decision is not None
    assert result.decision.kind == ActionKind.MOVE
    assert chebyshev(result.decision.move_to, enemy.pos) > 2


def test_solver_defers_the_trigger_kill_past_its_reinforcement_window():
    # HARD-2 pattern: killing the marked enemy inside the window summons
    # an unbeatable reinforcement. The winning line kills the other
    # grunt first and takes the marked one only after the window expired
    # -- the solver must price the spawn inside the tree and defer.
    from ggge_ai.sim import SimEvent

    ally = _ally(weapons=[_weapon(power=5000)])
    marked = _enemy("marked", pos=(2, 0), hp=5, weapons=[])
    grunt = _enemy("grunt", pos=(3, 0), hp=5, weapons=[])
    boss = _enemy("boss", pos=(1, 0), hp=99999, max_hp=99999,
                  unit_attack=90000, pilot_attack=90000,
                  weapons=[_weapon("mega", power=90000, rmax=3)])
    events = {
        "ev1": SimEvent(
            event_id="ev1",
            trigger={"type": "kill", "uid": "marked", "within_turn": 1},
            effect={"type": "spawn", "units": [boss]},
        )
    }
    state = SimState(units=[ally, marked, grunt], pending_events=("ev1",))
    result = solve(
        state,
        NearestTargetPolicy(),
        SolverConfig(time_budget_s=8.0, max_depth=4, events=events),
    )
    attacks = [d.target_id for d in result.pv if d.kind == ActionKind.ATTACK]
    assert attacks and attacks[0] == "grunt"
