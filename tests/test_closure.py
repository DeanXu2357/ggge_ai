"""Offline books-closure check (silent-events batch C, issue #27).

Synthetic ledgers only -- the closure math is exercised against hand-built
event streams so the arithmetic (movement, residual split, score) is exact.
"""

from __future__ import annotations

import json
from pathlib import Path

from ggge_ai.agent.closure import (
    ClosureReport,
    close_events,
    close_file,
    close_target,
    run_summary,
)


def _board(turn: int, *units: dict) -> dict:
    return {"kind": "board_belief", "turn": turn, "units": list(units)}


def _unit(uid: str, faction: str, hp: int | None, *, alive: bool = True) -> dict:
    return {
        "uid": uid,
        "faction": faction,
        "world_pos": None,
        "hp": hp,
        "en": None,
        "alive": alive,
        "source": "intel",
        "hp_turn": 1,
    }


def _uatt(uid: str, delta: int, observed_hp: int, *, turn: int = 2, read_source: str = "intel") -> dict:
    return {
        "kind": "unattributed_damage",
        "turn": turn,
        "uid": uid,
        "expected_hp": observed_hp - delta,
        "observed_hp": observed_hp,
        "delta": delta,
        "read_source": read_source,
        "prior_source": "forecast",
        "prior_hp_turn": 1,
        "world_pos": None,
    }


def _finish(outcome: str = "battle_result") -> dict:
    return {"kind": "finish", "turn": 3, "outcome": outcome}


def test_perfect_closure_scores_full() -> None:
    events = [
        _board(1, _unit("sig:e1", "enemy", 100), _unit("ally:a1", "ally", 500)),
        {"kind": "attack", "turn": 1, "attacker_sig": "a", "target_sig": "e"},
        _board(2, _unit("sig:e1", "enemy", 60), _unit("ally:a1", "ally", 500)),
        _finish(),
    ]
    r = close_events(events, "perfect")
    assert not r.degraded
    assert r.total_movement == 40
    assert r.unknown_total == 0
    assert r.completeness == 1.0
    assert r.unresolved_rate == 0.0


def test_unknown_residual_lowers_score() -> None:
    events = [
        _board(1, _unit("sig:e1", "enemy", 100)),
        _board(2, _unit("sig:e1", "enemy", 50)),
        _uatt("sig:e1", delta=-30, observed_hp=50, read_source="intel"),
        _finish(),
    ]
    r = close_events(events, "unknown")
    assert not r.degraded
    assert r.total_movement == 50
    assert r.unknown_total == 30
    assert r.explained_total == 20
    assert r.completeness == 0.4
    assert r.unresolved_rate == 0.6
    unit = r.units[0]
    assert unit.unknown_count == 1
    assert unit.kill_count == 0


def test_kill_residual_is_attributed_not_unknown() -> None:
    events = [
        _board(1, _unit("sig:e2", "enemy", 100)),
        _board(2, _unit("sig:e2", "enemy", 0, alive=False)),
        _uatt("sig:e2", delta=-30, observed_hp=0, read_source="outcome"),
        _finish(),
    ]
    r = close_events(events, "kill")
    assert not r.degraded
    assert r.total_movement == 100
    assert r.unknown_total == 0
    assert r.kill_total == 30
    assert r.completeness == 1.0
    unit = r.units[0]
    assert unit.kill_count == 1
    assert unit.unknown_count == 0


def test_dead_transition_without_hp_read_charges_last_hp() -> None:
    events = [
        _board(1, _unit("sig:e3", "enemy", 80)),
        _board(2, _unit("sig:e3", "enemy", None, alive=False)),
        _finish(),
    ]
    r = close_events(events, "dead")
    assert r.total_movement == 80
    assert r.completeness == 1.0


def test_old_format_degrades_gracefully() -> None:
    events = [
        {"kind": "select_unit", "turn": 1},
        {"kind": "attack", "turn": 1, "attacker_sig": "a", "target_sig": "e"},
        {"kind": "factions", "turn": 1, "allies": [], "enemies": [], "third_party": []},
        _finish(),
    ]
    r = close_events(events, "old")
    assert r.degraded
    assert r.completeness is None
    assert "事件不足" in (r.degrade_reason or "")
    assert "帳目閉合檢查：old" in r.render()
    assert "降級" in r.render()


def test_unattributed_without_snapshots_degrades() -> None:
    events = [
        _uatt("sig:e1", delta=-30, observed_hp=50),
        _finish(),
    ]
    r = close_events(events, "no-anchor")
    assert r.degraded
    assert r.completeness is None
    assert "缺回合錨點" in (r.degrade_reason or "")


def test_third_party_direction_consistent() -> None:
    events = [
        _board(1, _unit("sig:e1", "enemy", 100), _unit("sig:t1", "third_party", 80)),
        _board(2, _unit("sig:e1", "enemy", 70), _unit("sig:t1", "third_party", 50)),
        _finish(),
    ]
    r = close_events(events, "tp-ok")
    third = [u for u in r.units if not u.closeable]
    assert len(third) == 1
    assert third[0].direction_violations == []
    # third-party excluded from the score denominator (enemy movement only)
    assert r.total_movement == 30


def test_third_party_direction_violation_flagged() -> None:
    events = [
        _board(1, _unit("sig:e1", "enemy", 100), _unit("sig:t1", "third_party", 50)),
        _board(2, _unit("sig:e1", "enemy", 70), _unit("sig:t1", "third_party", 80)),
        _finish(),
    ]
    r = close_events(events, "tp-bad")
    third = [u for u in r.units if not u.closeable]
    assert len(third[0].direction_violations) == 1
    assert "上升" in third[0].direction_violations[0]
    # the violation does not touch the closeable score
    assert r.total_movement == 30
    assert r.completeness == 1.0


def test_movement_floored_to_residual_when_snapshots_sparse() -> None:
    # only one snapshot -> no snapshot delta, but a residual was recorded:
    # the residual is a floor so it can never exceed the movement it charges.
    events = [
        _board(1, _unit("sig:e1", "enemy", 100)),
        _uatt("sig:e1", delta=-40, observed_hp=60, turn=1, read_source="intel"),
        _finish(),
    ]
    r = close_events(events, "sparse")
    assert r.total_movement == 40
    assert r.unknown_total == 40
    assert r.completeness == 0.0


def test_close_file_and_target_roundtrip(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260721-000000"
    run_dir.mkdir()
    events = [
        _board(1, _unit("sig:e1", "enemy", 100)),
        _board(2, _unit("sig:e1", "enemy", 60)),
        _finish(),
    ]
    path = run_dir / "battle_01.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")

    single = close_file(path)
    assert isinstance(single, ClosureReport)
    assert single.completeness == 1.0

    from_dir = close_target(run_dir)
    assert len(from_dir) == 1
    assert from_dir[0].completeness == 1.0


def test_run_summary_weights_by_denominator() -> None:
    r1 = close_events(
        [
            _board(1, _unit("sig:e1", "enemy", 100)),
            _board(2, _unit("sig:e1", "enemy", 50)),
            _uatt("sig:e1", delta=-30, observed_hp=50),
        ],
        "b1",
    )
    r2 = close_events(
        [
            {"kind": "select_unit", "turn": 1},
            _finish(),
        ],
        "b2",
    )
    summary = run_summary([r1, r2])
    assert "可評分 1" in summary
    assert "降級 1" in summary
    assert "40.0%" in summary


def test_empty_ledger_degrades() -> None:
    r = close_events([], "empty")
    assert r.degraded
    assert r.completeness is None
