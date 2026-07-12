"""Stage-intel cache: perception memoization with the screen as authority."""

from ggge_ai.battle import stage_cache
from ggge_ai.battle.stage_cache import CachedUnit


def _unit(sig="a" * 16):
    return CachedUnit(
        sig=sig,
        name_text="鋼彈原型機",
        stats=dict(
            hp=51349,
            en=377,
            move_range=4,
            unit_attack=3586,
            unit_defense=3939,
            unit_mobility=3219,
            pilot_shooting=168,
            pilot_melee=168,
            pilot_awakening=179,
            pilot_defense=204,
            pilot_reaction=223,
            sp=15,
        ),
        weapons=[
            dict(
                kind="melee",
                level=1,
                range_min=1,
                range_max=2,
                power=3500,
                en_cost=27,
                hit_pct=100,
                crit_pct=5,
            )
        ],
    )


def test_round_trip(tmp_path):
    stage_cache.save_stage("g/hard_1", {"a" * 16: _unit()}, root=tmp_path)
    loaded = stage_cache.load_stage("g/hard_1", root=tmp_path)
    assert set(loaded) == {"a" * 16}
    unit = loaded["a" * 16]
    assert unit.name_text == "鋼彈原型機"
    spec, assumptions = unit.to_spec()
    assert spec.max_hp == 51349
    assert spec.weapons[0].power == 3500.0
    assert assumptions == []


def test_missing_stage_is_empty(tmp_path):
    assert stage_cache.load_stage("nope", root=tmp_path) == {}


def test_schema_mismatch_is_ignored(tmp_path):
    path = stage_cache.save_stage("s", {"a" * 16: _unit()}, root=tmp_path)
    data = path.read_text(encoding="utf-8").replace('"schema": 1', '"schema": 0')
    path.write_text(data, encoding="utf-8")
    assert stage_cache.load_stage("s", root=tmp_path) == {}


def test_corrupt_file_is_ignored(tmp_path):
    path = stage_cache.stage_path("s", root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken", encoding="utf-8")
    assert stage_cache.load_stage("s", root=tmp_path) == {}


def test_find_exact_and_near_and_far():
    sig = "00000000000000ff"
    units = {sig: _unit(sig)}
    assert stage_cache.find(units, sig) is units[sig]
    near = "00000000000000fe"
    assert stage_cache.find(units, near) is units[sig]
    far = "ffffffffffffff00"
    assert stage_cache.find(units, far) is None
    assert stage_cache.find(units, None) is None
    assert stage_cache.find({}, sig) is None
