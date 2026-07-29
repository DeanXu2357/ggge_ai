"""內層一次攻略：三條終局劇本，加上 tick 紀律與流水帳可重建性。"""

from __future__ import annotations

import json

from ggge_ai.contracts import Ending, HiddenPolicy, Objective, StageOrder
from ggge_ai.runtime.journal import Journal
from ggge_ai.sandbox.advise import Pricing
from ggge_ai.stage.actions import Attack, Brace
from ggge_ai.stage.goals import Annihilation
from ggge_ai.stage.loop import ReactionReflex, StageLoop, TickOutcome
from ggge_ai.stage.planner import Step
from ggge_ai.stage.run import JOURNAL_NAME, run_stage, stage_journal
from ggge_ai.stage.state import Phase, Reaction
from tests.fixtures.stage_offline import (
    FakeExecutor,
    KindPricer,
    MockAdvisor,
    ScriptedPerceiver,
    always_withdraw,
    battle,
    exit_only,
    frame,
    kills_everything,
    never_kills,
    result_screen,
)


def order(stage: str = "S01", max_ticks: int = 20) -> StageOrder:
    return StageOrder(
        stage=stage,
        objectives=frozenset({Objective.CLEAR}),
        hidden_policy=HiddenPolicy.DECLINE,
        max_ticks=max_ticks,
    )


def harness(tmp_path, frames, advisor, *, reflexes=(), stage_order=None):
    perceiver = ScriptedPerceiver(list(frames))
    executor = FakeExecutor()
    journal = stage_journal(tmp_path)
    report = run_stage(
        stage_order or order(),
        perceiver=perceiver,
        executor=executor,
        advisor=advisor,
        victory=Annihilation(),
        journal=journal,
        reflexes=reflexes,
    )
    return report, perceiver, executor, journal


def journal_lines(tmp_path):
    text = (tmp_path / JOURNAL_NAME).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_victory_is_declared_by_the_result_screen_not_by_an_empty_enemy_set(tmp_path):
    frames = [
        frame(battle(allies=["a1"], enemies=["e1"])),
        frame(battle(allies=["a1"], enemies=["e1"])),
        frame(battle(allies=["a1"], enemies=[], actionable=[])),
        result_screen(Ending.VICTORY),
    ]

    report, perceiver, executor, _ = harness(tmp_path, frames, MockAdvisor(kills_everything()))

    assert report.ending is Ending.VICTORY
    assert report.stage == "S01"
    assert report.achieved == {Objective.CLEAR: True}
    assert perceiver.looks == 4
    assert executor.labels == ["attack:a1->e1", "attack:a1->e1"]


def test_the_queue_advances_on_screen_evidence_not_on_having_executed(tmp_path):
    unchanged = battle(allies=["a1"], enemies=["e1"])
    frames = [frame(unchanged), frame(unchanged), frame(unchanged), result_screen(Ending.DEFEAT)]

    _, _, executor, _ = harness(tmp_path, frames, MockAdvisor(kills_everything()))

    # 三張一模一樣的畫面＝三次重送同一個行動，佇列一次也沒彈。
    assert executor.labels == ["attack:a1->e1"] * 3


def test_a_stale_head_throws_the_whole_queue_away(tmp_path):
    start = battle(allies=["a1", "a2"], enemies=["e1", "e2"])
    lost_a2 = battle(allies=["a1"], enemies=["e2"], actionable=[])
    frames = [frame(start), frame(lost_a2), result_screen(Ending.DEFEAT)]
    advisor = MockAdvisor(kills_everything())
    perceiver = ScriptedPerceiver(frames)
    executor = FakeExecutor()
    loop = StageLoop(
        order(),
        perceiver=perceiver,
        executor=executor,
        advisor=advisor,
        victory=Annihilation(),
        journal=stage_journal(tmp_path),
    )

    first = loop.tick()
    second = loop.tick()

    assert first.outcome is TickOutcome.ACTED
    assert len(first.plan) == 2
    assert second.discarded is not None
    assert loop.queue == []


def test_no_plan_available_stops_the_stage_as_stuck(tmp_path):
    frames = [frame(battle(allies=["a1"], enemies=["e1", "e2"]))]

    report, _, executor, _ = harness(tmp_path, frames, MockAdvisor(never_kills()))

    assert report.ending is Ending.STUCK
    assert "search space exhausted" in report.reason
    assert report.achieved == {Objective.CLEAR: False}
    assert executor.performed == []


def test_the_tick_budget_running_out_is_also_an_honest_stuck(tmp_path):
    frames = [frame(battle(allies=["a1"], enemies=["e1"]))]

    report, _, _, _ = harness(
        tmp_path,
        frames,
        MockAdvisor(kills_everything()),
        stage_order=order(max_ticks=3),
    )

    assert report.ending is Ending.STUCK
    assert "tick budget exhausted (3)" in report.reason


def test_the_advisor_verdict_switches_the_goal_and_the_run_reports_withdrew(tmp_path):
    frames = [
        frame(battle(allies=["a1"], enemies=["e1"])),
        result_screen(Ending.DEFEAT, screen="battle_defeat"),
    ]
    advisor = MockAdvisor(exit_only(), verdict=always_withdraw)

    report, _, executor, _ = harness(tmp_path, frames, advisor)

    assert report.ending is Ending.WITHDREW
    assert executor.labels == ["withdraw"]
    assert report.achieved == {Objective.CLEAR: False}


def test_the_reflex_layer_answers_the_popup_before_any_planning_happens(tmp_path):
    reaction = Reaction(defender="a1", attacker="e1", stances=("dodge", "defend"))
    under_fire = battle(
        allies=["a1"], enemies=["e1"], actionable=[], phase=Phase.ENEMY, reaction=reaction
    )
    stances = {"dodge": 5.0, "defend": 1.0}
    advisor = MockAdvisor(
        lambda state, action: Pricing(stances[action.stance])
        if isinstance(action, Brace)
        else None
    )
    frames = [frame(under_fire), result_screen(Ending.DEFEAT)]

    _, _, executor, _ = harness(
        tmp_path, frames, advisor, reflexes=(ReactionReflex(advisor),)
    )

    assert executor.performed == [Brace("a1", "e1", "defend")]
    assert advisor.appraisals == 0


def test_a_tick_makes_at_most_one_device_operation(tmp_path):
    frames = [
        frame(battle(allies=["a1", "a2"], enemies=["e1", "e2"])),
        frame(battle(allies=["a1", "a2"], enemies=["e2"], actionable=["a2"])),
        frame(battle(allies=["a1", "a2"], enemies=[], actionable=[])),
        result_screen(Ending.VICTORY),
    ]

    report, perceiver, executor, _ = harness(tmp_path, frames, MockAdvisor(kills_everything()))

    assert report.ending is Ending.VICTORY
    assert perceiver.looks == 4
    assert len(executor.performed) <= perceiver.looks
    assert len(executor.device.taps) == len(executor.performed)


def test_the_enemy_phase_is_waited_out_and_turns_the_queue_over(tmp_path):
    frames = [
        frame(battle(allies=["a1"], enemies=["e1", "e2"])),
        frame(battle(allies=["a1"], enemies=["e2"], actionable=[], phase=Phase.ENEMY)),
        frame(battle(allies=["a1"], enemies=["e2"])),
        frame(battle(allies=["a1"], enemies=[], actionable=[])),
        result_screen(Ending.VICTORY),
    ]
    advisor = MockAdvisor(kills_everything())
    perceiver = ScriptedPerceiver(frames)
    executor = FakeExecutor()
    loop = StageLoop(
        order(),
        perceiver=perceiver,
        executor=executor,
        advisor=advisor,
        victory=Annihilation(),
        journal=stage_journal(tmp_path),
    )

    outcomes = [loop.tick().outcome for _ in range(4)]

    assert outcomes[0] is TickOutcome.ACTED
    assert outcomes[1] is TickOutcome.WAITING
    assert outcomes[2] is TickOutcome.ACTED
    assert outcomes[3] is TickOutcome.GOAL_MET
    assert executor.labels == ["attack:a1->e1", "attack:a1->e2"]


def test_a_screen_with_no_symbolic_reading_just_waits(tmp_path):
    frames = [frame(None, screen="cutscene"), result_screen(Ending.DEFEAT)]

    report, _, executor, _ = harness(tmp_path, frames, MockAdvisor(kills_everything()))

    assert report.ending is Ending.DEFEAT
    assert executor.performed == []


def test_the_journal_reconstructs_what_each_tick_saw_and_did(tmp_path):
    frames = [
        frame(battle(allies=["a1"], enemies=["e1"]), hp="93%"),
        frame(battle(allies=["a1"], enemies=[], actionable=[])),
        result_screen(Ending.VICTORY),
    ]

    harness(tmp_path, frames, MockAdvisor(kills_everything()))
    lines = journal_lines(tmp_path)

    assert [line["kind"] for line in lines] == ["stage_start", "tick", "tick", "tick", "stage_end"]
    assert lines[0]["stage"] == "S01"
    assert lines[0]["victory"] == "annihilation"

    first, second, third = lines[1], lines[2], lines[3]
    assert first["seen"] == {
        "phase": "player",
        "allies": ["a1"],
        "actionable": ["a1"],
        "enemies": ["e1"],
        "known": ["a1", "e1"],
        "positions": {},
        "reaction": None,
    }
    assert first["evidence"] == {"hp": "93%"}
    assert first["did"] == "attack:a1->e1"
    assert first["outcome"] == "acted"
    assert first["replanned"] is True
    assert first["verdict"] == "pursue"

    assert second["popped"] == ["attack:a1->e1"]
    assert second["did"] is None
    assert second["outcome"] == "goal_met"

    assert third["terminal"] == "victory"
    assert third["seen"] is None
    assert lines[4]["ending"] == "victory"
    assert lines[4]["ticks"] == 3


def test_the_journal_file_is_named_stage_jsonl(tmp_path):
    journal = stage_journal(tmp_path)
    journal.record("probe")

    assert journal.path.name == JOURNAL_NAME
    assert (tmp_path / "stage.jsonl").exists()


def test_run_stage_only_claims_the_objectives_it_can_judge(tmp_path):
    both = StageOrder(
        stage="S02",
        objectives=frozenset({Objective.CLEAR, Objective.SCORE}),
        hidden_policy=HiddenPolicy.DECLINE,
        max_ticks=10,
    )
    frames = [frame(battle(allies=["a1"], enemies=[], actionable=[])), result_screen(Ending.VICTORY)]

    report, _, _, _ = harness(
        tmp_path, frames, MockAdvisor(kills_everything()), stage_order=both
    )

    assert report.ending is Ending.VICTORY
    assert report.achieved == {Objective.CLEAR: True, Objective.SCORE: False}


def test_the_loop_asks_for_exactly_one_frame_per_tick(tmp_path):
    frames = [frame(battle(allies=["a1"], enemies=["e1"]))]
    perceiver = ScriptedPerceiver(frames)
    loop = StageLoop(
        order(),
        perceiver=perceiver,
        executor=FakeExecutor(),
        advisor=MockAdvisor(kills_everything()),
        victory=Annihilation(),
        journal=Journal(tmp_path / JOURNAL_NAME),
    )

    loop.tick()
    loop.tick()

    assert perceiver.looks == 2


def test_an_attack_without_a_kill_guarantee_pops_once_the_unit_is_spent(tmp_path):
    """保守下界的直接後果：沒承諾擊殺就只驗「這機動過了」，敵人還在
    不算計畫破功。"""
    advisor = MockAdvisor(
        KindPricer(attack=Pricing(1.0), standby=Pricing(1.0), withdraw=Pricing(5.0))
    )
    state = battle(allies=["a1"], enemies=["e1"])
    spent = battle(allies=["a1"], enemies=["e1"], actionable=[])
    perceiver = ScriptedPerceiver([frame(state), frame(spent)])
    loop = StageLoop(
        order(),
        perceiver=perceiver,
        executor=FakeExecutor(),
        advisor=advisor,
        victory=Annihilation(),
        journal=Journal(tmp_path / JOURNAL_NAME),
    )
    loop.queue = [Step(Attack("a1", "e1"), Pricing(1.0))]

    loop.tick()
    second = loop.tick()

    assert second.popped == ("attack:a1->e1",)
