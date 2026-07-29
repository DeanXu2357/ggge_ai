"""expectiminimax：節點型別、剪枝等價、敵方模型注入與目標注入。"""

import random
from dataclasses import replace

import pytest

from ggge_ai.sandbox.model import (
    BattleState,
    Decision,
    Faction,
    MoveKind,
    Reaction,
    Skill,
    StageEvent,
    Stance,
    Unit,
    Weapon,
    chebyshev,
    step,
    strike_damage,
)
from ggge_ai.sandbox.search import (
    EvalContext,
    EvalWeights,
    MinimaxEnemy,
    NearestTargetPolicy,
    Objective,
    SearchConfig,
    annihilation_objective,
    default_evaluator,
    eval_bounds,
    solve,
    solve_reaction,
)


def _weapon(name="rifle", power=5000, rmax=3, en_cost=0):
    return Weapon(name, power=power, range_min=1, range_max=rmax, en_cost=en_cost)


def _ally(uid="a", pos=(0, 0), hp=100, weapons=None, **kw):
    base = dict(unit_id=uid, faction=Faction.ALLY, pos=pos, hp=hp, max_hp=100,
                en=50, en_max=50, unit_attack=5000, pilot_attack=9000, move_range=3,
                weapons=weapons if weapons is not None else [])
    base.update(kw)
    return Unit(**base)


def _enemy(uid="e", pos=(2, 0), hp=100, weapons=None, **kw):
    base = dict(unit_id=uid, faction=Faction.ENEMY, pos=pos, hp=hp, max_hp=100,
                en=50, en_max=50, unit_attack=5000, pilot_attack=9000, move_range=3,
                unit_defense=1000, pilot_defense=1000,
                weapons=weapons if weapons is not None else [])
    base.update(kw)
    return Unit(**base)


def _decapitate_objective(target_id, base_allies, base_enemies, weights=None):
    vmin, vmax = eval_bounds(base_allies, base_enemies, weights or EvalWeights())

    def terminal(state, ctx):
        if state.unit(target_id) is None:
            return vmax
        if not state.allies():
            return vmin
        return None

    return Objective(terminal=terminal, evaluator=default_evaluator, bounds=(vmin, vmax))


def test_a_chance_step_lets_the_search_chain_two_kills():
    ally = _ally(weapons=[_weapon()], chance_steps=2, chance_steps_max=2)
    state = BattleState(units=[ally,
                               _enemy("e0", pos=(2, 0), hp=5),
                               _enemy("e1", pos=(3, 0), hp=5)])
    result = solve(state, NearestTargetPolicy(), SearchConfig(time_budget_s=2.0))
    targets = [d.target_id for d in result.pv if d.kind is MoveKind.ATTACK]
    assert set(targets) == {"e0", "e1"}


def test_our_reaction_node_picks_the_better_stance():
    ally = _ally(hp=100000, max_hp=100000, weapons=[_weapon()])
    boss = _enemy("boss", pos=(1, 0), hp=40, unit_attack=1000, pilot_attack=1000,
                  weapons=[_weapon(power=200)])
    state = BattleState(units=[ally, boss], phase=Faction.ENEMY)
    result = solve(state, NearestTargetPolicy(), SearchConfig(time_budget_s=2.0, max_depth=1))

    ctx = EvalContext(weights=EvalWeights(), base_allies=1, base_enemies=1)
    incoming = Decision("boss", MoveKind.ATTACK, target_id="a", weapon="rifle", hit=True)
    countered = step(state, replace(incoming, reaction=Reaction(stance=Stance.COUNTER)))
    defended = step(state, replace(incoming, reaction=Reaction(stance=Stance.DEFEND)))
    v_counter = default_evaluator(countered, ctx)
    v_defend = default_evaluator(defended, ctx)
    assert v_counter > v_defend
    assert result.value == pytest.approx(v_counter, abs=1e-6)


def test_the_search_prices_the_enemy_counter_on_our_attacks():
    m = _ally("m", hp=10, max_hp=10, move_range=0, unit_attack=1000, pilot_attack=1000,
              weapons=[_weapon("saber", power=200, rmax=1)])
    e = _enemy("e", pos=(1, 0), hp=100_000, max_hp=100_000, move_range=0,
               weapons=[_weapon(power=9000, rmax=1)])
    result = solve(BattleState(units=[m, e]), NearestTargetPolicy(), SearchConfig(max_depth=1))
    assert result.decision.kind is MoveKind.STANDBY


def test_the_search_takes_the_kill_that_silences_return_fire():
    m = _ally("m", hp=10, max_hp=10, move_range=0, weapons=[_weapon(power=9000, rmax=2)])
    e = _enemy("e", pos=(1, 0), hp=5, move_range=0, weapons=[_weapon(power=9000, rmax=1)])
    guard = _enemy("g", pos=(2, 0), hp=10**9, max_hp=10**9, move_range=3,
                   weapons=[_weapon(power=9000, rmax=3)],
                   support_attack_charges=1, support_attack_charges_max=1)
    result = solve(BattleState(units=[m, e, guard]), NearestTargetPolicy(),
                   SearchConfig(max_depth=1))
    assert result.decision.kind is MoveKind.ATTACK
    assert result.decision.target_id == "e"


def test_the_search_keeps_the_volley_for_the_kill_that_needs_it():
    m = _ally("m", hp=10**9, max_hp=10**9, move_range=0, weapons=[_weapon()],
              chance_steps=1, chance_steps_max=1)
    n = _ally("n", pos=(1, 0), hp=10**9, max_hp=10**9, move_range=1, weapons=[_weapon()],
              support_attack_charges=1, support_attack_charges_max=1)
    b = _enemy("b", pos=(1, 1), hp=1, move_range=0)
    a = _enemy("a", pos=(2, 0), hp=100, move_range=0, weapons=[_weapon()])
    a.hp = a.max_hp = int(strike_damage(m, a, m.weapons[0]) * 2.5)
    state = BattleState(units=[m, n, b, a])
    result = solve(state, NearestTargetPolicy(),
                   SearchConfig(time_budget_s=10.0, max_depth=1))
    end = state
    for decision in result.pv:
        end = step(end, decision)
    assert not end.enemies()
    assert any(d.kind is MoveKind.ATTACK and d.support is False for d in result.pv)


def test_the_search_finds_the_map_shot_normal_attacks_cannot_match():
    m = _ally("m", hp=10**9, max_hp=10**9, move_range=0,
              weapons=[Weapon("mapgun", power=9000, range_min=1, range_max=4,
                              map_weapon=True, blast=1)])
    m.ammo = {"mapgun": 1}
    state = BattleState(units=[m,
                               _enemy("e0", pos=(2, 0), hp=5, move_range=0),
                               _enemy("e1", pos=(2, 1), hp=5, move_range=0)])
    result = solve(state, NearestTargetPolicy(), SearchConfig(max_depth=1))
    assert result.decision.kind is MoveKind.MAP_ATTACK
    assert not step(state, result.decision).enemies()


def test_min_mode_is_more_pessimistic_than_policy():
    tank = _ally("tank", pos=(1, 0), hp=1_000_000, max_hp=1_000_000)
    weak = _ally("weak", pos=(3, 0), hp=1)
    enemy = _enemy("e", pos=(0, 0), weapons=[_weapon(rmax=4)], move_range=0)
    state = BattleState(units=[tank, weak, enemy], phase=Faction.ENEMY)
    policy = solve(state, NearestTargetPolicy(), SearchConfig(max_depth=1)).value
    worst = solve(state, MinimaxEnemy(), SearchConfig(max_depth=1)).value
    assert worst < policy


def test_smoke_4v4_returns_a_legal_first_step_within_budget():
    units = [_ally(f"a{i}", pos=(0, i), weapons=[_weapon(power=1500)], pilot_attack=3000)
             for i in range(4)]
    units += [_enemy(f"e{i}", pos=(5, i), weapons=[_weapon(power=1500)], pilot_attack=3000)
              for i in range(4)]
    state = BattleState(units=units)
    result = solve(state, NearestTargetPolicy(), SearchConfig(time_budget_s=2.0))
    assert result.decision is not None
    assert result.stats.depth >= 1
    assert result.stats.nodes > 0
    assert result.decision.unit_id in {u.unit_id for u in state.allies()}


def _random_state(rng):
    cells = rng.sample([(x, y) for x in range(5) for y in range(5)], 4)
    units = []
    for side, faction, offset in (("a", Faction.ALLY, 0), ("e", Faction.ENEMY, 2)):
        for i in range(2):
            units.append(Unit(
                unit_id=f"{side}{i}", faction=faction, pos=cells[offset + i],
                hp=rng.randrange(20, 121), max_hp=120,
                en=rng.randrange(0, 31), en_max=30,
                unit_attack=4000, pilot_attack=rng.randrange(800, 1400),
                unit_defense=800, pilot_defense=600,
                reaction=rng.randrange(1500, 3200), mobility=rng.randrange(0, 2000),
                move_range=rng.randrange(1, 4),
                weapons=[Weapon("w", power=rng.randrange(1500, 6000), range_min=1,
                                range_max=rng.randrange(1, 4),
                                en_cost=rng.choice([0, 5, 10]))],
                chance_steps=rng.randrange(0, 2) if faction is Faction.ALLY else 0,
                chance_steps_max=1 if faction is Faction.ALLY else 0,
                support_defend_charges=rng.randrange(0, 2), support_defend_charges_max=1,
                support_attack_charges=rng.randrange(0, 2), support_attack_charges_max=1,
            ))
    return BattleState(units=units)


def test_star1_and_tt_match_the_unpruned_reference():
    for seed in range(8):
        state = _random_state(random.Random(seed))
        for model in (NearestTargetPolicy(), MinimaxEnemy()):
            fast = solve(state, model, SearchConfig(time_budget_s=60.0, max_depth=3))
            slow = solve(state, model, SearchConfig(time_budget_s=60.0, max_depth=3,
                                                   use_tt=False, use_star1=False))
            assert fast.stats.depth == slow.stats.depth == 3
            assert fast.value == pytest.approx(slow.value, abs=1e-6)
            assert fast.stats.nodes <= slow.stats.nodes


def test_the_search_refills_en_then_attacks_in_one_activation():
    ally = _ally(weapons=[_weapon(en_cost=10)], en=0, en_max=20)
    ally.skills = [Skill(MoveKind.SKILL_EN_REFILL, ends_activation=False)]
    state = BattleState(units=[ally, _enemy("e0", pos=(1, 0), hp=5)])
    result = solve(state, NearestTargetPolicy(), SearchConfig(time_budget_s=5.0, max_depth=2))
    assert [d.kind for d in result.pv[:2]] == [MoveKind.SKILL_EN_REFILL, MoveKind.ATTACK]


def test_refill_beats_standby_when_it_ends_the_activation():
    ally = _ally(weapons=[_weapon(en_cost=10)], en=0, en_max=20)
    ally.skills = [Skill(MoveKind.SKILL_EN_REFILL)]
    state = BattleState(units=[ally, _enemy("e0", pos=(1, 0), hp=5, move_range=0)])
    result = solve(state, NearestTargetPolicy(), SearchConfig(time_budget_s=5.0, max_depth=4))
    assert result.decision.kind is MoveKind.SKILL_EN_REFILL


def test_the_search_advances_on_an_out_of_reach_enemy():
    ally = _ally(weapons=[_weapon(rmax=1)], move_range=3)
    enemy = _enemy("e0", pos=(5, 0), hp=5, move_range=0)
    result = solve(BattleState(units=[ally, enemy]), NearestTargetPolicy(),
                   SearchConfig(time_budget_s=5.0, max_depth=4))
    assert result.decision.kind is MoveKind.REPOSITION
    assert chebyshev(result.decision.move_to, enemy.pos) < 5


def test_the_search_retreats_out_of_lethal_reach():
    ally = _ally(hp=10, max_hp=10, move_range=2)
    enemy = _enemy("e0", pos=(2, 0), hp=1000, max_hp=1000, move_range=1,
                   weapons=[_weapon(power=99000, rmax=1)])
    result = solve(BattleState(units=[ally, enemy]), NearestTargetPolicy(),
                   SearchConfig(time_budget_s=5.0, max_depth=3))
    assert result.decision.kind is MoveKind.REPOSITION
    assert chebyshev(result.decision.move_to, enemy.pos) > 2


def test_the_search_defers_a_trigger_kill_past_its_reinforcement_window():
    boss = _enemy("boss", pos=(1, 0), hp=99999, max_hp=99999,
                  unit_attack=90000, pilot_attack=90000,
                  weapons=[_weapon("mega", power=90000)])
    events = {
        "ev1": StageEvent(event_id="ev1",
                          trigger={"type": "kill", "uid": "marked", "within_turn": 1},
                          effect={"type": "spawn", "units": [boss]})
    }
    state = BattleState(units=[_ally(weapons=[_weapon()]),
                               _enemy("marked", pos=(2, 0), hp=5),
                               _enemy("grunt", pos=(3, 0), hp=5)],
                        pending_events=("ev1",))
    result = solve(state, NearestTargetPolicy(),
                   SearchConfig(time_budget_s=8.0, max_depth=4, events=events))
    attacks = [d.target_id for d in result.pv if d.kind is MoveKind.ATTACK]
    assert attacks and attacks[0] == "grunt"


def test_eval_bounds_contain_the_evaluator_and_terminal_values():
    weights = EvalWeights()
    vmin, vmax = eval_bounds(2, 2, weights)
    ctx = EvalContext(weights=weights, base_allies=2, base_enemies=2)
    won = BattleState(units=[_ally("a0"), _ally("a1", pos=(0, 1))])
    lost = BattleState(units=[_enemy("e0"), _enemy("e1", pos=(2, 1))])
    assert vmin <= default_evaluator(won, ctx) <= vmax
    assert vmin <= default_evaluator(lost, ctx) <= vmax


def test_the_default_config_matches_a_wrapped_annihilation_objective():
    rng = random.Random(7)
    for _ in range(5):
        units = [
            _ally("a1", pos=(rng.randint(0, 2), rng.randint(0, 2)), hp=rng.randint(20, 100),
                  weapons=[_weapon(power=rng.choice([2000, 5000]))]),
            _ally("a2", pos=(0, 3), hp=rng.randint(20, 100), weapons=[_weapon()]),
            _enemy("e1", pos=(rng.randint(3, 5), rng.randint(0, 2)), hp=rng.randint(20, 100),
                   weapons=[_weapon(power=rng.choice([2000, 4000]))]),
            _enemy("e2", pos=(5, 3), hp=rng.randint(20, 100), weapons=[_weapon()]),
        ]
        state = BattleState(units=[u.clone() for u in units])
        plain = solve(state, NearestTargetPolicy(),
                      SearchConfig(time_budget_s=3.0, max_depth=2))
        wrapped = solve(state, NearestTargetPolicy(),
                        SearchConfig(time_budget_s=3.0, max_depth=2,
                                     objective=annihilation_objective()))
        assert plain.value == wrapped.value
        assert plain.decision == wrapped.decision


def test_an_injected_objective_redirects_the_search_to_the_commander():
    state = BattleState(units=[_ally(weapons=[_weapon()]),
                               _enemy("minion", pos=(2, 0), hp=5),
                               _enemy("boss", pos=(3, 0), hp=5)])
    objective = _decapitate_objective("boss", 1, 2)
    result = solve(state, NearestTargetPolicy(),
                   SearchConfig(time_budget_s=2.0, max_depth=1, objective=objective))
    attacks = [d.target_id for d in result.pv if d.kind is MoveKind.ATTACK]
    assert attacks and attacks[0] == "boss"
    assert result.value == objective.bounds[1]

    plain = solve(state, NearestTargetPolicy(), SearchConfig(time_budget_s=2.0, max_depth=1))
    plain_attacks = [d.target_id for d in plain.pv if d.kind is MoveKind.ATTACK]
    assert plain_attacks and plain_attacks[0] == "minion"


def test_star1_and_tt_agree_under_an_injected_objective():
    state = BattleState(units=[_ally(weapons=[_weapon(power=3000)],
                                     chance_steps=1, chance_steps_max=1),
                               _enemy("minion", pos=(2, 0), hp=40,
                                      weapons=[_weapon(power=800)]),
                               _enemy("boss", pos=(3, 0), hp=40,
                                      weapons=[_weapon(power=800)])])
    objective = _decapitate_objective("boss", 1, 2)

    def run(use_star1, use_tt):
        return solve(state, NearestTargetPolicy(),
                     SearchConfig(time_budget_s=5.0, max_depth=3, use_star1=use_star1,
                                  use_tt=use_tt, objective=objective)).value

    reference = run(False, False)
    assert run(True, True) == reference
    assert run(True, False) == reference
    assert run(False, True) == reference


def test_an_injected_leaf_evaluator_replaces_the_default():
    # 預設評估器對「誰都沒死、血量沒變」的三個候選一視同仁，會取第一個（前進）；
    # 注入的評估器獎勵拉開距離，選擇必須翻成後退。
    def prefer_distance(state, ctx):
        ally = state.unit("a")
        return float(chebyshev(ally.pos, (5, 0))) if ally is not None else 0.0

    objective = Objective(terminal=lambda s, c: None, evaluator=prefer_distance,
                          bounds=(0.0, 20.0))
    state = BattleState(units=[_ally(move_range=2), _enemy("e0", pos=(5, 0), move_range=0)])
    result = solve(state, NearestTargetPolicy(),
                   SearchConfig(time_budget_s=2.0, max_depth=1, objective=objective))
    assert result.decision.kind is MoveKind.REPOSITION
    assert chebyshev(result.decision.move_to, (5, 0)) == 7
    assert result.value == 7.0

    plain = solve(state, NearestTargetPolicy(), SearchConfig(time_budget_s=2.0, max_depth=1))
    assert chebyshev(plain.decision.move_to, (5, 0)) == 3


def test_solve_reaction_only_offers_the_stances_the_popup_shows():
    ally = _ally(hp=100000, max_hp=100000, weapons=[_weapon()])
    boss = _enemy("boss", pos=(1, 0), hp=40, unit_attack=1000, pilot_attack=1000,
                  weapons=[_weapon(power=200)])
    state = BattleState(units=[ally, boss], phase=Faction.ENEMY)
    attack = Decision("boss", MoveKind.ATTACK, target_id="a", weapon="rifle")

    free = solve_reaction(state, attack, NearestTargetPolicy(),
                          SearchConfig(time_budget_s=2.0, max_depth=1))
    assert free.decision.reaction.stance is Stance.COUNTER

    limited = solve_reaction(state, attack, NearestTargetPolicy(),
                             SearchConfig(time_budget_s=2.0, max_depth=1),
                             allowed_stances=(Stance.DEFEND, Stance.DODGE))
    assert limited.decision.reaction.stance in (Stance.DEFEND, Stance.DODGE)

    none_left = solve_reaction(state, attack, NearestTargetPolicy(),
                               SearchConfig(time_budget_s=2.0, max_depth=1),
                               allowed_stances=())
    assert none_left.decision is None


def test_solve_reaction_can_forbid_the_interception():
    defender = _ally("d", pos=(0, 0), hp=100000, max_hp=100000)
    guard = _ally("g", pos=(1, 1), hp=100000, max_hp=100000, move_range=3,
                  support_defend_charges=1, support_defend_charges_max=1)
    boss = _enemy("boss", pos=(1, 0), weapons=[_weapon(power=200)])
    state = BattleState(units=[defender, guard, boss], phase=Faction.ENEMY)
    attack = Decision("boss", MoveKind.ATTACK, target_id="d", weapon="rifle")
    result = solve_reaction(state, attack, NearestTargetPolicy(),
                            SearchConfig(time_budget_s=2.0, max_depth=1),
                            allow_support_defend=False)
    assert result.decision.reaction.support_defend is False
