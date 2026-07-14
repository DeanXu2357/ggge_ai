"""Stage definition v2: uid identity, conditions, events, screen-authority
load semantics."""

import json

from ggge_ai.battle import stage_def
from ggge_ai.battle.stage_def import (
    Condition,
    StageConditions,
    StageDefinition,
    StageEvent,
    StageUnit,
)

SIG_A = "a" * 16
SIG_B = "b" * 16


def _stats():
    return dict(
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
    )


def _weapon():
    return dict(
        kind="melee",
        level=1,
        range_min=1,
        range_max=2,
        power=3500,
        en_cost=27,
        hit_pct=100,
        crit_pct=5,
    )


def _defn(stage_id="g/hard_2"):
    layout = stage_def.assign_uids(
        [
            StageUnit(uid="", cell=(3, 0), sig=SIG_A, stats=_stats(), weapons=[_weapon()]),
            StageUnit(uid="", cell=(1, 2), sig=SIG_A, name_text="鋼彈"),
            StageUnit(uid="", cell=(5, 1), sig=SIG_B, faction="third_party"),
        ]
    )
    events = [
        StageEvent(
            event_id="ev1",
            trigger={"type": "kill", "uid": "e01", "within_turn": 2},
            effect={
                "type": "spawn",
                "units": [{"uid": "e09", "cell": [7, 7], "sig": SIG_B}],
            },
            observations=[{"turn": 3, "kills_so_far": [{"uid": "e01", "turn": 2}]}],
        )
    ]
    return StageDefinition(
        stage_id=stage_id,
        layout=layout,
        conditions=StageConditions(
            victory=[Condition(type="decapitate", params={"targets": ["e01"]}, source="manual")],
            defeat=[Condition(type="all_allies_lost")],
        ),
        events=events,
    )


def test_round_trip(tmp_path):
    saved = _defn()
    stage_def.save_stage_def(saved, root=tmp_path)
    loaded = stage_def.load_stage_def("g/hard_2", root=tmp_path)
    assert loaded is not None
    assert loaded == saved


def test_uid_issue_is_row_major_and_input_order_free():
    units = [
        StageUnit(uid="", cell=(3, 0), sig=SIG_A),
        StageUnit(uid="", cell=(1, 2), sig=SIG_A),
        StageUnit(uid="", cell=(0, 0), sig=SIG_B),
    ]
    first = {u.cell: u.uid for u in stage_def.assign_uids([*units])}
    shuffled = {
        u.cell: u.uid
        for u in stage_def.assign_uids(
            [
                StageUnit(uid="", cell=(1, 2), sig=SIG_A),
                StageUnit(uid="", cell=(0, 0), sig=SIG_B),
                StageUnit(uid="", cell=(3, 0), sig=SIG_A),
            ]
        )
    }
    assert first == shuffled
    assert first[(0, 0)] == "e01"
    assert first[(3, 0)] == "e02"
    assert first[(1, 2)] == "e03"


def test_uid_prefix_splits_factions():
    issued = stage_def.assign_uids(
        [
            StageUnit(uid="", cell=(0, 0)),
            StageUnit(uid="", cell=(1, 0), faction="third_party"),
        ]
    )
    assert {u.uid for u in issued} == {"e01", "t01"}


def test_find_by_sig_returns_all_candidates_within_tolerance():
    defn = _defn()
    jittered = SIG_A[:-1] + "b"
    candidates = stage_def.find_by_sig(defn, jittered)
    assert {u.uid for u in candidates} == {"e01", "e02"}


def test_find_by_sig_includes_reinforcement_spawns():
    defn = _defn()
    candidates = stage_def.find_by_sig(defn, SIG_B)
    assert {u.uid for u in candidates} == {"t01", "e09"}


def test_layout_unit_to_spec_delegates_to_panels():
    defn = _defn()
    armed = next(u for u in defn.layout if u.stats)
    spec, assumptions = armed.to_spec()
    assert spec.max_hp == 51349
    assert spec.weapons[0].power == 3500


def test_missing_file_returns_none(tmp_path):
    assert stage_def.load_stage_def("nowhere", root=tmp_path) is None


def test_old_schema_is_ignored(tmp_path):
    path = stage_def.stage_path("g/hard_1", root=tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema": 1, "units": {}}), encoding="utf-8")
    assert stage_def.load_stage_def("g/hard_1", root=tmp_path) is None


def test_broken_file_returns_none(tmp_path):
    path = stage_def.stage_path("g/hard_1", root=tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    assert stage_def.load_stage_def("g/hard_1", root=tmp_path) is None


def test_default_conditions_are_annihilate_mirror():
    conditions = stage_def.default_conditions()
    assert conditions.victory[0].type == "annihilate"
    assert conditions.defeat[0].type == "all_allies_lost"
    assert conditions.victory[0].source == "default"


def test_stale_status_round_trips(tmp_path):
    defn = _defn()
    defn.status = "stale"
    stage_def.save_stage_def(defn, root=tmp_path)
    loaded = stage_def.load_stage_def("g/hard_2", root=tmp_path)
    assert loaded is not None
    assert loaded.status == "stale"
