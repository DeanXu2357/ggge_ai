"""The tick log is the only truth, so it must be complete on its own.

Aggregates are computed over `bot.log` when someone asks; nothing else keeps
score. This file pins the columns no other column can reconstruct -- planning
cost (`plan_ms`), which side of the fork the tick took (`replanned`) and why
it died (`panic:<kind>`) -- including on the paths where `think()` dies.
"""

from __future__ import annotations

import pytest

from ggge_ai.bot.action import Action, Goal
from ggge_ai.bot.bot import Bot, BotStuck, TickRecord
from ggge_ai.bot.demo import STORY, build_demo_bot, run_demo
from ggge_ai.goap.state import WorldState
from tests.test_bot_skeleton import _DeadScreen, _mini_bot


class _Ungrounded(Action):
    """A planner operator that lies: routable in search, inapplicable in the loop."""

    name = "Ungrounded"
    pre = {"no_such_symbol": True}
    eff = {"grid": "on"}

    def check(self, state: WorldState) -> bool:
        return True

    def do(self, bot: Bot) -> None:
        raise AssertionError("an inapplicable head must never run")


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


def test_a_goal_less_tick_still_measures_the_call():
    # goal 是 None 時 think() 仍被呼叫、當場回空——量到的是呼叫本身
    # （MockClock 不因計算前進，所以是 0），不是「沒量」。
    bot = build_demo_bot()
    bot.state.goal = None

    bot.tick()

    record = bot.log[-1]
    assert record.outcome == "done"
    assert record.replanned == "refill"
    assert record.plan_ms == 0


# --- think() 死在裡面時，記錄仍要說出死前做了什麼 ---


def test_missing_vocabulary_records_the_refill_it_died_in():
    bot = build_demo_bot()
    bot.state.goal = Goal("impossible", {"no_such_symbol": True})

    with pytest.raises(BotStuck) as excinfo:
        bot.tick()

    assert excinfo.value.kind == "no_plan"
    record = bot.log[-1]
    assert record.outcome == "panic:no_plan"
    assert record.replanned == "refill"
    assert record.plan_ms is not None


def test_a_vocabulary_hole_found_on_the_replan_path_records_the_replan():
    bot = _mini_bot(Goal("setup", {"grid": "on", "zoom": "max"}), script=[None, STORY, None])
    bot.tick()
    assert bot.log[0].replanned == "refill"

    bot.catalog = [action for action in bot.catalog if action.name != "Observe"]

    with pytest.raises(BotStuck):
        bot.tick()

    record = bot.log[-1]
    assert record.outcome == "panic:no_plan"
    assert record.replanned == "replan"
    assert record.plan_ms is not None


def test_an_inapplicable_fresh_head_is_a_different_panic_kind():
    bot = _mini_bot(Goal("grid", {"grid": "on"}))
    bot.catalog = [_Ungrounded()]

    with pytest.raises(BotStuck) as excinfo:
        bot.tick()

    assert excinfo.value.kind == "stale_plan"
    record = bot.log[-1]
    assert record.outcome == "panic:stale_plan"
    assert record.replanned == "refill"
    assert record.plan_ms is not None
