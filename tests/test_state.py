from ggge_ai.goap.state import WorldState


def test_with_updates_is_immutable():
    s1 = WorldState(screen="main_menu")
    s2 = s1.with_updates({"screen": "stage_select"})
    assert s1["screen"] == "main_menu"
    assert s2["screen"] == "stage_select"


def test_equality_and_hash():
    a = WorldState(screen="x", my_turn=True)
    b = WorldState({"my_turn": True, "screen": "x"})
    assert a == b
    assert hash(a) == hash(b)
    assert len({a, b}) == 1


def test_satisfies():
    s = WorldState(screen="battle_map", my_turn=True)
    assert s.satisfies({"screen": "battle_map"})
    assert not s.satisfies({"screen": "battle_map", "all_enemies_defeated": True})
    assert s.count_unmet({"screen": "x", "my_turn": True}) == 1
