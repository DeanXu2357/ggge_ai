import random

from ggge_ai.battle.actions import ActionKind
from ggge_ai.battle.advisor import AdvisorConfig, advise
from ggge_ai.battle.bridge import UnitSpec
from ggge_ai.battle.sim import SimState, SimUnit, SimWeapon
from ggge_ai.battle.state import BattleState, Faction, UnitState


def _weapon(rmax=3, power=5000, en_cost=0):
    return SimWeapon("rifle", power=power, range_min=1, range_max=rmax, en_cost=en_cost)


def _spec(**kw):
    base = dict(max_hp=100, en_max=50, unit_attack=5000, unit_defense=1000,
                pilot_attack=9000, pilot_defense=1000, reaction=0.0, mobility=0.0,
                move_range=3, weapons=(_weapon(),))
    base.update(kw)
    return UnitSpec(**base)


def _config(**kw):
    base = dict(cell_size=48.0, time_budget_s=5.0, max_depth=2)
    base.update(kw)
    return AdvisorConfig(**base)


def _two_ally_board(**unit_kw):
    b_kw = dict(world_pos=(0.0, 96.0), hp=100, en=50)
    b_kw.update(unit_kw)
    battle = BattleState()
    battle.add_unit(UnitState("a", Faction.ALLY, world_pos=(0.0, 0.0), hp=100, en=50))
    battle.add_unit(UnitState("b", Faction.ALLY, **b_kw))
    battle.add_unit(UnitState("e", Faction.ENEMY, world_pos=(48.0, 0.0), hp=5, en=50))
    return battle


def _two_ally_specs():
    return {"a": _spec(), "b": _spec(), "e": _spec()}


def test_default_advice_activates_first_listed_ally():
    advice = advise(_two_ally_board(), _two_ally_specs(), _config())
    assert advice is not None
    assert advice.unit_id == "a"
    assert advice.kind == ActionKind.ATTACK


def test_unit_id_pins_root_actor():
    advice = advise(_two_ally_board(), _two_ally_specs(), _config(), unit_id="b")
    assert advice is not None
    assert advice.unit_id == "b"


def test_unit_id_on_first_actor_matches_plain_advise():
    plain = advise(_two_ally_board(), _two_ally_specs(), _config())
    pinned = advise(_two_ally_board(), _two_ally_specs(), _config(), unit_id="a")
    assert plain is not None and pinned is not None
    assert (pinned.unit_id, pinned.kind, pinned.target_id, pinned.weapon) == (
        plain.unit_id, plain.kind, plain.target_id, plain.weapon
    )
    assert pinned.move_world == plain.move_world
    assert pinned.value == plain.value


def _random_board(rng):
    battle = BattleState()
    specs = {}
    cells = rng.sample([(x, y) for x in range(5) for y in range(5)], k=5)
    for i, cell in enumerate(cells[:3]):
        uid = f"a{i}"
        battle.add_unit(UnitState(
            uid, Faction.ALLY,
            world_pos=(cell[0] * 48.0, cell[1] * 48.0),
            hp=rng.randint(20, 100), en=50,
        ))
        specs[uid] = _spec()
    for i, cell in enumerate(cells[3:]):
        uid = f"e{i}"
        battle.add_unit(UnitState(
            uid, Faction.ENEMY,
            world_pos=(cell[0] * 48.0, cell[1] * 48.0),
            hp=rng.randint(5, 60), en=50,
        ))
        specs[uid] = _spec()
    return battle, specs


def test_unit_id_noop_promotion_equivalence_over_seeds():
    for seed in range(4):
        rng = random.Random(seed)
        board, specs = _random_board(rng)
        plain = advise(board, specs, _config())
        pinned = advise(board, specs, _config(), unit_id="a0")
        assert plain is not None and pinned is not None, f"seed {seed}"
        assert pinned.value == plain.value, f"seed {seed}"
        assert (pinned.unit_id, pinned.kind, pinned.target_id, pinned.weapon) == (
            plain.unit_id, plain.kind, plain.target_id, plain.weapon
        ), f"seed {seed}"


def test_unit_id_unknown_or_enemy_returns_none():
    board, specs = _two_ally_board(), _two_ally_specs()
    assert advise(board, specs, _config(), unit_id="zzz") is None
    assert advise(board, specs, _config(), unit_id="e") is None


def test_unit_id_acted_or_dead_returns_none():
    acted = _two_ally_board(acted=True)
    assert advise(acted, _two_ally_specs(), _config(), unit_id="b") is None
    dead = _two_ally_board(hp=0)
    assert advise(dead, _two_ally_specs(), _config(), unit_id="b") is None


def test_simstate_key_is_insensitive_to_unit_list_order():
    def units():
        return [
            SimUnit("a", Faction.ALLY, pos=(0, 0), hp=100, max_hp=100),
            SimUnit("b", Faction.ALLY, pos=(1, 0), hp=80, max_hp=100),
            SimUnit("e", Faction.ENEMY, pos=(3, 0), hp=60, max_hp=100),
        ]
    forward = SimState(units=units())
    reordered = SimState(units=list(reversed(units())))
    assert forward.key() == reordered.key()
