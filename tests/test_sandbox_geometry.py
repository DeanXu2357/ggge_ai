"""格盤幾何：Chebyshev 距離、武器射程帶、移動範圍與路徑阻擋。"""

from ggge_ai.sandbox.model import (
    Faction,
    MoveKind,
    Unit,
    Weapon,
    chebyshev,
    in_band,
    legal_attacks,
    nearest_free_cell,
    reachable_cells,
    reposition_moves,
    BattleState,
)


def _unit(uid, faction, pos, move=3, hp=100, weapons=None):
    return Unit(
        unit_id=uid,
        faction=faction,
        pos=pos,
        hp=hp,
        max_hp=100,
        move_range=move,
        weapons=weapons if weapons is not None else [],
    )


def _saber():
    return Weapon("saber", power=1000, range_min=1, range_max=1)


def test_distance_is_chebyshev_so_a_diagonal_step_costs_one():
    assert chebyshev((0, 0), (3, 3)) == 3
    assert chebyshev((0, 0), (3, 0)) == 3
    assert chebyshev((2, -2), (0, 0)) == 2


def test_weapon_reach_is_an_inclusive_band():
    ranged = Weapon("cannon", power=100, range_min=2, range_max=4)
    assert not in_band(1, ranged)
    assert in_band(2, ranged)
    assert in_band(4, ranged)
    assert not in_band(5, ranged)


def test_move_range_bounds_reachability():
    ally = _unit("a", Faction.ALLY, (0, 0), move=1)
    state = BattleState(units=[ally])
    assert reachable_cells(state, ally) == {
        (x, y) for x in (-1, 0, 1) for y in (-1, 0, 1)
    }


def test_enemy_wall_blocks_the_straight_path_but_a_detour_is_found():
    ally = _unit("a", Faction.ALLY, (0, 0), move=3)
    wall = [_unit(f"w{i}", Faction.ENEMY, (1, y)) for i, y in enumerate((-1, 0, 1))]
    state = BattleState(units=[ally, *wall])
    reach = reachable_cells(state, ally)
    assert (2, 0) not in reach
    assert (2, 2) in reach


def test_friendly_unit_is_passable_but_not_a_landing_cell():
    ally = _unit("a", Faction.ALLY, (0, 0), move=2)
    friend = _unit("f", Faction.ALLY, (1, 0))
    pincer = [_unit(f"p{i}", Faction.ENEMY, c) for i, c in enumerate(((1, 1), (1, -1)))]
    state = BattleState(units=[ally, friend, *pincer])
    reach = reachable_cells(state, ally)
    assert (2, 0) in reach
    assert (1, 0) not in reach


def test_bounds_confine_reachability():
    ally = _unit("a", Faction.ALLY, (0, 0), move=2)
    state = BattleState(units=[ally], bounds=((0, 0), (1, 0)))
    assert reachable_cells(state, ally) == {(0, 0), (1, 0)}


def test_blocking_the_choke_removes_the_attack_on_the_backline():
    bounds = ((0, 0), (4, 1))
    weak = _unit("weak", Faction.ALLY, (0, 0), hp=1)
    tank_a = _unit("ta", Faction.ALLY, (1, 0))
    tank_b = _unit("tb", Faction.ALLY, (1, 1))
    enemy = _unit("e", Faction.ENEMY, (4, 0), move=3, weapons=[_saber()])

    blocked = BattleState(units=[weak, tank_a, tank_b, enemy], bounds=bounds)
    assert all(d.target_id != "weak" for d in legal_attacks(blocked, enemy))

    opened = BattleState(units=[weak, tank_a, enemy], bounds=bounds)
    on_weak = [d for d in legal_attacks(opened, enemy) if d.target_id == "weak"]
    assert on_weak and on_weak[0].move_to == (1, 1)


def test_legal_attacks_enumerate_only_targets_the_band_can_cover():
    rifle = Weapon("rifle", power=1500, range_min=1, range_max=2)
    ally = _unit("a", Faction.ALLY, (0, 0), move=1, weapons=[rifle])
    near = _unit("near", Faction.ENEMY, (2, 0))
    far = _unit("far", Faction.ENEMY, (9, 0))
    state = BattleState(units=[ally, near, far])
    ids = {d.target_id for d in legal_attacks(state, ally)}
    assert ids == {"near"}


def test_reposition_moves_offer_advance_and_retreat():
    ally = _unit("a", Faction.ALLY, (0, 0), move=2)
    enemy = _unit("e", Faction.ENEMY, (5, 0))
    state = BattleState(units=[ally, enemy])
    moves = reposition_moves(state, ally)
    dests = {d.move_to for d in moves}
    assert (2, 0) in dests
    assert any(chebyshev(c, enemy.pos) > 5 for c in dests)
    assert all(d.kind is MoveKind.REPOSITION for d in moves)


def test_nearest_free_cell_resolves_a_shared_landing_cell():
    assert nearest_free_cell((0, 0), set()) == (0, 0)
    assert chebyshev(nearest_free_cell((0, 0), {(0, 0)}), (0, 0)) == 1
