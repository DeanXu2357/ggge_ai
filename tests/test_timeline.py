"""BattleTimeline: the process-scoped control-flow memory. acted() opens an
act -> verify contract from the TRANSITIONS map; observe() audits every phase
read against it and returns ledger intents. Reality always wins -- a miss is
recorded evidence, never a fight with the screen; only the eaten-tap case
feeds back into behavior, via the on_eaten repair hook."""

from ggge_ai.battle.timeline import TRANSITIONS, BattleTimeline


def test_verified_transition_returns_met_and_clears():
    t = BattleTimeline(phase="our_turn")
    t.acted("select_unit")

    events = t.observe("unit_move")

    assert t.expectation_open is False
    assert [e.kind for e in events] == ["expectation_met"]
    assert events[0].data == {"action": "select_unit", "observed": "unit_move"}
    assert events[0].with_frame is False


def test_unexpected_screen_is_a_recorded_miss_not_a_fight():
    t = BattleTimeline(phase="weapon_select")
    t.acted("attack")

    events = t.observe("skill")

    assert t.expectation_open is False
    miss = events[0]
    assert miss.kind == "expectation_miss"
    assert miss.data["expected"] == ["battle_prep"]
    assert miss.data["observed"] == "skill"
    assert miss.with_frame is True


def test_eaten_tap_repairs_the_activation_flag_once_then_expires():
    t = BattleTimeline(phase="unit_move")
    t.activation.tried_in_place = True
    t.acted("open_weapon_select")

    events = t.observe("unit_move")
    assert t.activation.tried_in_place is False  # repaired for the retry
    assert [e.kind for e in events] == ["expectation_retry"]
    assert t.expectation_open is True  # re-armed, waiting for the retry

    events = t.observe("unit_move")
    assert [e.kind for e in events] == ["expectation_expired"]
    assert t.expectation_open is False


def test_activation_ending_action_resets_the_per_unit_state():
    t = BattleTimeline(phase="battle_prep")
    t.activation.tried_in_place = True
    t.activation.moved = True

    t.acted("battle_execute")

    assert t.activation.tried_in_place is False
    assert t.activation.moved is False
    assert t.activation.plan is None


def test_label_less_reads_burn_the_budget_not_the_clock():
    t = BattleTimeline(phase="weapon_select")
    t.acted("attack")

    for _ in range(TRANSITIONS["attack"].checks - 1):
        assert t.observe(None) == []
    assert t.expectation_open is True

    events = t.observe(None)
    assert [e.kind for e in events] == ["expectation_expired"]
    assert t.expectation_open is False


def test_target_after_label_less_stretch_still_verifies():
    t = BattleTimeline(phase="battle_prep")
    t.acted("battle_execute")

    for _ in range(5):
        assert t.observe(None) == []
    events = t.observe("our_turn")

    assert [e.kind for e in events] == ["expectation_met"]


def test_no_expectation_is_a_noop_and_phase_is_tracked():
    t = BattleTimeline()
    assert t.observe("our_turn") == []
    assert t.phase == "our_turn"
    assert t.observe(None) == []
    assert t.phase == "our_turn"


def test_acted_records_the_current_phase_as_source():
    t = BattleTimeline(phase="unit_move")
    t.acted("standby")
    assert t._expectation.source == "unit_move"
    assert "our_turn" in t._expectation.targets


def test_newer_action_supersedes_the_open_contract():
    t = BattleTimeline(phase="our_turn")
    t.acted("select_unit")
    t.phase = "unit_move"
    t.acted("open_weapon_select")

    events = t.observe("weapon_select")

    assert [e.kind for e in events] == ["expectation_met"]
    assert events[0].data["action"] == "open_weapon_select"


def test_turn_ocr_advances_and_rearms_turn_jobs():
    t = BattleTimeline()
    assert t.due("scout") is True
    assert t.due("scout") is False
    assert t.due("full_scan", scope="battle") is True

    assert t.on_turn_read(2, marker=None) is True
    assert t.turn == 2
    assert t.due("scout") is True  # turn scope re-armed
    assert t.due("full_scan", scope="battle") is False  # battle scope survives


def test_pending_peeks_without_claiming():
    """due() claims on the ask; pending() must not -- a peeking caller that
    used due() stole the intel gate and skipped the survey (20260719)."""
    t = BattleTimeline()
    assert t.pending("intel", scope="battle") is True
    assert t.pending("intel", scope="battle") is True
    assert t.due("intel", scope="battle") is True
    assert t.pending("intel", scope="battle") is False
    assert t.due("intel", scope="battle") is False


def test_turn_ocr_same_or_lower_number_does_not_advance():
    t = BattleTimeline(turn=3)
    assert t.on_turn_read(3, marker=None) is False
    assert t.on_turn_read(2, marker=None) is False
    assert t.turn == 3


def test_absurd_turn_jump_is_rejected_as_misread():
    t = BattleTimeline()
    assert t.on_turn_read(77, marker=None) is False
    assert t.turn == 1


def test_unreadable_chip_falls_back_to_marker_compare():
    import numpy as np

    one = np.zeros((36, 40), np.uint8)
    one[:, :20] = 255
    two = np.zeros((36, 40), np.uint8)
    two[:, 20:] = 255

    t = BattleTimeline()
    assert t.on_turn_read(None, marker=one) is False  # baseline stored
    assert t.on_turn_read(None, marker=two) is True
    assert t.turn == 2


def test_mark_pending_rearms_a_consumed_job():
    t = BattleTimeline()
    assert t.due("scout") is True
    t.mark_pending("scout")
    assert t.due("scout") is True
