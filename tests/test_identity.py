"""IdentityResolver: layout seeding, position continuity, sig as a
candidate filter, and the passthrough degradation for replay."""

import pytest

from ggge_ai.battle.identity import IdentityResolver
from ggge_ai.battle.stage_def import StageDefinition, StageEvent, StageUnit, assign_uids

SIG_A = "a" * 16
SIG_B = "b" * 16


def _defn(events=None):
    layout = assign_uids(
        [
            StageUnit(uid="", cell=(0, 0), sig=SIG_A),
            StageUnit(uid="", cell=(3, 0), sig=SIG_A),
            StageUnit(uid="", cell=(1, 2), sig=SIG_B),
        ]
    )
    return StageDefinition(stage_id="t/1", layout=layout, events=events or [])


def _seeded(defn=None):
    resolver = IdentityResolver(defn or _defn())
    report = resolver.seed([(1000.0, 500.0), (1285.0, 500.0), (1095.0, 690.0)])
    assert report.ok
    return resolver


def test_seed_binds_layout_cells_to_scan_points():
    resolver = _seeded()
    positions = resolver.positions()
    assert positions["e01"] == (1000.0, 500.0)
    assert positions["e02"] == (1285.0, 500.0)
    assert positions["e03"] == (1095.0, 690.0)


def test_seed_is_input_order_free():
    resolver = IdentityResolver(_defn())
    report = resolver.seed([(1095.0, 690.0), (1000.0, 500.0), (1285.0, 500.0)])
    assert report.ok
    assert resolver.positions()["e01"] == (1000.0, 500.0)


def test_seed_count_mismatch_is_not_ok():
    resolver = IdentityResolver(_defn())
    report = resolver.seed([(1000.0, 500.0), (1285.0, 500.0)])
    assert not report.ok
    assert report.unmatched_uids
    assert resolver.positions() == {}


def test_seed_refuses_passthrough():
    with pytest.raises(ValueError):
        IdentityResolver().seed([(0.0, 0.0)])


def test_shared_sig_resolves_by_position():
    resolver = _seeded()
    assert resolver.resolve((1010.0, 505.0), sig=SIG_A) == "e01"
    assert resolver.resolve((1290.0, 495.0), sig=SIG_A) == "e02"


def test_contradicting_sig_resolves_to_none():
    resolver = _seeded()
    assert resolver.resolve((1000.0, 500.0), sig=SIG_B) is None


def test_ambiguous_position_without_sig_is_none():
    resolver = _seeded()
    resolver.confirm("e01", (1000.0, 500.0))
    resolver.confirm("e02", (1100.0, 500.0))
    assert resolver.resolve((1050.0, 500.0)) is None


def test_refresh_updates_unique_neighbours_quietly():
    resolver = _seeded()
    report = resolver.refresh([(1040.0, 500.0), (1285.0, 560.0), (1095.0, 750.0)])
    assert set(report.updated) == {"e01", "e02", "e03"}
    assert report.ambiguous_points == []
    assert resolver.positions()["e01"] == (1040.0, 500.0)


def test_refresh_leaves_contested_points_ambiguous():
    resolver = _seeded()
    resolver.confirm("e01", (1000.0, 500.0))
    resolver.confirm("e02", (1080.0, 500.0))
    report = resolver.refresh([(1040.0, 500.0)])
    assert report.ambiguous_points == [(1040.0, 500.0)]
    assert "e03" in report.unmatched_uids


def test_dead_uid_stops_matching_and_shrinks_the_denominator():
    resolver = _seeded()
    assert resolver.expected_alive() == 3
    resolver.register_death("e01")
    assert resolver.expected_alive() == 2
    assert resolver.resolve((1000.0, 500.0), sig=SIG_A) == "e02" or (
        resolver.resolve((1000.0, 500.0), sig=SIG_A) is None
    )
    assert "e01" not in resolver.positions()


def test_spawn_registration_extends_tracking_and_denominator():
    spawn = StageEvent(
        event_id="ev1",
        trigger={"type": "turn_start", "turn": 3},
        effect={"type": "spawn", "units": [{"uid": "e09", "cell": [7, 7], "sig": SIG_B}]},
    )
    resolver = _seeded(_defn(events=[spawn]))
    assert resolver.expected_alive() == 3
    resolver.register_spawn("e09", (2000.0, 900.0))
    assert resolver.expected_alive() == 4
    assert resolver.resolve((2005.0, 905.0), sig=SIG_B) == "e09"


def test_candidates_come_from_the_definition():
    resolver = _seeded()
    assert set(resolver.candidates(SIG_A)) == {"e01", "e02"}
    jittered = SIG_B[:-1] + "a"
    assert resolver.candidates(jittered) == ["e03"]


def test_passthrough_degrades_uids_to_sig_strings():
    resolver = IdentityResolver()
    assert resolver.passthrough
    assert resolver.resolve((0.0, 0.0), sig=SIG_A) == f"sig:{SIG_A}"
    assert resolver.resolve((0.0, 0.0)) is None
    assert resolver.expected_alive() is None
    assert resolver.candidates(SIG_A) == [f"sig:{SIG_A}"]


def test_sig_uid_merges_jitter_per_namespace():
    resolver = IdentityResolver()
    jittered = SIG_A[:-1] + "b"
    assert resolver.sig_uid(SIG_A) == f"sig:{SIG_A}"
    assert resolver.sig_uid(jittered) == f"sig:{SIG_A}"
    assert resolver.sig_uid(SIG_A, namespace="ally") == f"sig:{SIG_A}"
    far = "0" * 16
    assert resolver.sig_uid(far) == f"sig:{far}"


def test_uid_for_ally_always_degrades_even_when_seeded():
    resolver = _seeded()
    assert resolver.uid_for(SIG_A, namespace="ally") == f"sig:{SIG_A}"


def test_uid_for_shared_sig_arbitrates_by_position():
    resolver = _seeded()
    assert resolver.uid_for(SIG_A, world=(1010.0, 505.0)) == "e01"
    assert resolver.uid_for(SIG_A, world=(1290.0, 495.0)) == "e02"
    assert resolver.uid_for(SIG_A) is None
    assert resolver.uid_for(SIG_B) == "e03"


def test_expected_sig_round_trips():
    resolver = _seeded()
    assert resolver.expected_sig("e01") == SIG_A
    assert resolver.expected_sig("e03") == SIG_B
    assert resolver.expected_sig(f"sig:{SIG_A}") == SIG_A
    assert resolver.expected_sig("e99") is None


def test_world_to_cell_inverts_the_seed_transform():
    resolver = _seeded()
    assert resolver.world_to_cell((1000.0, 500.0)) == (0, 0)
    assert resolver.world_to_cell((1285.0, 500.0)) == (3, 0)
    assert resolver.world_to_cell((1385.0, 505.0)) == (4, 0)
    assert IdentityResolver().world_to_cell((0.0, 0.0)) is None
