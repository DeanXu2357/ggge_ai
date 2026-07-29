"""What a tick reports, and what the supervisor does with it.

The record has to stand on its own: planning cost (`plan_ms`), which side of
the fork the tick took (`replanned`), and the verdict when the tick runs out
of road (`stuck:*`). Running out of road is a returned value here, not an
exception, so these tests also stand guard over the price of that: a verdict
tick files exactly one record and touches no device. Turning a verdict into
BotStuck is `run`'s job, and the second half pins that seam.
"""

from __future__ import annotations

import pytest

from ggge_ai.bot.action import Goal
from ggge_ai.bot.bot import Bot, BotStuck, TickRecord
from ggge_ai.bot.demo import STORY, build_demo_bot, run_demo
from ggge_ai.goap.planner import PlanResult
from tests.test_bot_skeleton import _DeadScreen, _mini_bot


def _plan_ticks(bot: Bot, kind: str) -> list[TickRecord]:
    return [record for record in bot.log if record.replanned == kind]


# --- plan_ms 只在 think() 真的被呼叫的拍上有值 ---


def test_refill_tick_carries_the_planning_cost():
    bot = run_demo()

    refills = _plan_ticks(bot, "refill")
    assert refills
    assert bot.log[0].replanned == "refill"
    assert all(record.plan_ms is not None for record in refills)


def test_replan_tick_carries_the_planning_cost():
    bot = run_demo()

    replans = _plan_ticks(bot, "replan")
    assert replans
    assert all(record.plan_ms is not None for record in replans)


def test_ticks_that_never_reached_the_planner_have_no_planning_cost():
    bot = run_demo()

    reflex = next(record for record in bot.log if record.outcome.startswith("reflex:"))
    assert reflex.plan_ms is None

    executed = [
        record for record in bot.log if record.outcome == "executed" and record.replanned is None
    ]
    assert executed
    assert all(record.plan_ms is None for record in executed)


def test_sense_failure_never_reaches_the_planner():
    bot = build_demo_bot()
    bot.screen = _DeadScreen()

    with pytest.raises(OSError):
        bot.tick()

    record = bot.log[-1]
    assert record.outcome == "panic:sense"
    assert record.plan_ms is None
    assert record.replanned is None


# --- done 是迴圈自己的裁決：不經 think()，所以既無 replanned 也無 plan_ms ---


def test_done_lands_on_the_tick_that_pops_the_last_step():
    bot = run_demo()

    record = bot.log[-1]
    assert record.outcome == "done"
    assert record.popped == ["SyncSim"]
    assert record.plan == []
    assert record.replanned is None
    assert record.plan_ms is None


def test_a_goal_less_tick_finishes_without_asking_the_planner():
    # goal 是 None＝無所求：頂部檢查當場收工，planner 連呼叫都沒有。
    bot = build_demo_bot()
    bot.state.goal = None

    bot.tick()

    record = bot.log[-1]
    assert record.outcome == "done"
    assert record.replanned is None
    assert record.plan_ms is None
    assert bot.finished
    assert bot.device.interactions == 0


# --- 走不下去是回傳值：tick 不丟例外，只留一筆判定並停手 ---


def test_no_route_on_the_refill_path_is_a_returned_verdict():
    bot = build_demo_bot()
    bot.state.goal = Goal("impossible", {"no_such_symbol": True})

    record = bot.tick()

    assert record.outcome == "stuck:no_plan"
    assert record.replanned == "refill"
    assert record.plan_ms is not None
    assert bot.log == [record]
    assert bot.device.interactions == 0
    assert not bot.finished


def test_no_route_found_on_the_replan_path_records_the_replan():
    bot = _mini_bot(Goal("setup", {"grid": "on", "zoom": "max"}), script=[None, STORY, None])
    bot.tick()
    assert bot.log[0].replanned == "refill"
    quiet = bot.device.interactions

    bot.catalog = [action for action in bot.catalog if action.name != "Observe"]
    record = bot.tick()

    assert record.outcome == "stuck:no_plan"
    assert record.replanned == "replan"
    assert record.plan_ms is not None
    assert bot.log == [bot.log[0], record]
    assert bot.device.interactions == quiet


def test_an_empty_plan_is_a_split_view_not_a_finish(monkeypatch):
    # 迴圈判定 goal 未滿足才會問 planner；planner 卻說無事可做＝兩邊對同一組
    # 符號看法分裂。摺成 stuck:no_plan 當場停機，不准無聲 refill 空轉。
    bot = build_demo_bot()
    monkeypatch.setattr("ggge_ai.bot.bot.plan", lambda *args, **kwargs: PlanResult([], 0.0, 0))

    assert bot.think() is None

    record = bot.tick()

    assert record.outcome == "stuck:no_plan"
    assert record.replanned == "refill"
    assert not bot.finished
    assert bot.device.interactions == 0


# --- 判定變例外是 run() 的職責 ---


def test_run_escalates_a_no_route_verdict_naming_the_goal():
    bot = build_demo_bot()
    bot.state.goal = Goal("impossible", {"no_such_symbol": True})

    with pytest.raises(BotStuck) as excinfo:
        bot.run(max_ticks=5)

    assert excinfo.value.kind == "no_plan"
    assert "no plan for goal 'impossible'" in str(excinfo.value)
    assert len(bot.log) == 1
    assert bot.log[-1].outcome == "stuck:no_plan"
