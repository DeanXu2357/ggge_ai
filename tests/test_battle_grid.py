from ggge_ai.battle.grid import grid_move_validator, reachable_cells
from ggge_ai.battle.sim import SimState, SimUnit, SimWeapon, legal_attacks
from ggge_ai.battle.state import Faction


def _unit(uid, faction, pos, move=3, hp=100, weapons=None):
    return SimUnit(unit_id=uid, faction=faction, pos=pos, hp=hp, max_hp=100,
                   move_range=move, weapons=weapons if weapons is not None else [])


def _saber():
    return SimWeapon("saber", power=1000, range_min=1, range_max=1)


def test_enemy_wall_blocks_straight_path_but_detour_is_found():
    ally = _unit("a", Faction.ALLY, (0, 0), move=3)
    wall = [_unit(f"w{i}", Faction.ENEMY, (1, y)) for i, y in enumerate((-1, 0, 1))]
    s = SimState(units=[ally, *wall])
    reach = reachable_cells(s, ally)
    assert (2, 0) not in reach
    assert (2, 2) in reach
    assert not grid_move_validator(s, ally, (2, 0))


def test_friendly_unit_is_passable_but_not_a_landing_cell():
    ally = _unit("a", Faction.ALLY, (0, 0), move=2)
    friend = _unit("f", Faction.ALLY, (1, 0))
    pincer = [_unit(f"p{i}", Faction.ENEMY, c) for i, c in enumerate(((1, 1), (1, -1)))]
    s = SimState(units=[ally, friend, *pincer])
    reach = reachable_cells(s, ally)
    assert (2, 0) in reach
    assert (1, 0) not in reach


def test_bounds_confine_reachability():
    ally = _unit("a", Faction.ALLY, (0, 0), move=2)
    s = SimState(units=[ally], bounds=((0, 0), (1, 0)))
    assert reachable_cells(s, ally) == {(0, 0), (1, 0)}


def test_blocking_the_choke_removes_the_attack_on_the_backline():
    bounds = ((0, 0), (4, 1))
    weak = _unit("weak", Faction.ALLY, (0, 0), hp=1)
    tank_a = _unit("ta", Faction.ALLY, (1, 0))
    tank_b = _unit("tb", Faction.ALLY, (1, 1))
    enemy = _unit("e", Faction.ENEMY, (4, 0), move=3, weapons=[_saber()])

    blocked = SimState(units=[weak, tank_a, tank_b, enemy], bounds=bounds)
    attacks = legal_attacks(blocked, enemy, reach=reachable_cells(blocked, enemy))
    assert all(d.target_id != "weak" for d in attacks)

    opened = SimState(units=[weak, tank_a, enemy], bounds=bounds)
    attacks = legal_attacks(opened, enemy, reach=reachable_cells(opened, enemy))
    on_weak = [d for d in attacks if d.target_id == "weak"]
    assert on_weak and on_weak[0].move_to == (1, 1)
