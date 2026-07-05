from ggge_ai.agent.attribution import (
    DiagClass,
    DiagCode,
    Severity,
    attribute_events,
    attribute_ledger,
)
from ggge_ai.battle.ledger import BattleLedger


def _ev(kind, t, **data):
    return {"t": t, "turn": 1, "kind": kind, **data}


def _finish(events, outcome, t):
    return events + [_ev("finish", t, outcome=outcome)]


def test_idle_timeout_is_code_stall_defect():
    events = _finish(
        [
            _ev("select_unit", 1.0),
            _ev("attack", 2.0, slot=0),
            _ev("engagement_confirm", 3.0),
        ],
        "idle_timeout",
        900.0,
    )
    report = attribute_events(events)
    assert report.resolved is False
    assert report.verdict is DiagClass.CODE
    stall = next(f for f in report.findings if f.code is DiagCode.STALL_DEFECT)
    assert stall.diag_class is DiagClass.CODE
    assert stall.severity is Severity.CRITICAL
    assert report.metrics["idle_gap_s"] >= 120.0


def test_heavy_out_of_range_standby_flags_seek_defect():
    events = []
    t = 0.0
    for _ in range(8):
        t += 1
        events.append(_ev("select_unit", t))
        t += 1
        events.append(_ev("move", t, basis="scout_hint", target=[0, 0], cell=[0, 0]))
        t += 1
        events.append(_ev("standby", t, reason="out_of_range"))
    events = _finish(events, "battle_result", t + 5)
    report = attribute_events(events)
    seek = next(f for f in report.findings if f.code is DiagCode.SEEK_DEFECT)
    assert seek.diag_class is DiagClass.CODE
    assert seek.severity is Severity.WARN
    assert report.metrics["passive_share"] == 1.0
    assert report.metrics["passive_reason_range"] == 8


def test_en_standby_flags_skill_defect():
    events = _finish(
        [
            _ev("select_unit", 1.0),
            _ev("standby", 2.0, reason="en_depleted"),
        ],
        "battle_result",
        10.0,
    )
    report = attribute_events(events)
    skill = next(f for f in report.findings if f.code is DiagCode.SKILL_DEFECT)
    assert skill.diag_class is DiagClass.CODE
    assert report.metrics["passive_reason_en"] == 1


def test_damage_fields_activate_growth_diagnosis():
    events = _finish(
        [
            _ev("select_unit", 1.0),
            _ev("attack", 2.0, slot=0, actual_damage=1200),
            _ev("attack", 3.0, slot=0, actual_damage=800),
        ],
        "battle_result",
        10.0,
    )
    report = attribute_events(events)
    fp = next(f for f in report.findings if f.code is DiagCode.FIREPOWER_GAP)
    assert fp.diag_class is DiagClass.GROWTH
    assert report.metrics["median_damage"] == 1000
    assert "火力不足" not in " ".join(report.coverage_notes)


def test_clean_win_has_no_actionable_finding():
    events = []
    t = 0.0
    for _ in range(6):
        t += 1
        events.append(_ev("select_unit", t))
        t += 1
        events.append(_ev("attack", t, slot=0))
        t += 1
        events.append(_ev("engagement_confirm", t))
    events = _finish(events, "battle_result", t + 3)
    report = attribute_events(events)
    assert report.resolved is True
    assert report.verdict is DiagClass.INCONCLUSIVE
    assert all(f.severity is Severity.INFO for f in report.findings)


def test_missing_data_emits_coverage_notes():
    events = _finish([_ev("select_unit", 1.0), _ev("attack", 2.0, slot=0)], "battle_result", 5.0)
    report = attribute_events(events)
    joined = " ".join(report.coverage_notes)
    assert "火力不足" in joined
    assert "編成短板" in joined


def test_interrupted_outcome_is_inconclusive():
    events = _finish([_ev("select_unit", 1.0)], "interrupted", 900.0)
    report = attribute_events(events)
    assert report.verdict is DiagClass.INCONCLUSIVE
    stall = next(f for f in report.findings if f.code is DiagCode.STALL_DEFECT)
    assert stall.diag_class is DiagClass.INCONCLUSIVE
    assert stall.severity is Severity.INFO


def test_attribute_ledger_reads_live_events_without_mutating():
    ledger = BattleLedger()
    ledger.record("select_unit")
    ledger.record("standby", reason="out_of_range")
    ledger.finish("idle_timeout")
    before = len(ledger.events)
    report = attribute_ledger(ledger, source="live")
    assert report.source == "live"
    assert report.outcome == "idle_timeout"
    assert len(ledger.events) == before
