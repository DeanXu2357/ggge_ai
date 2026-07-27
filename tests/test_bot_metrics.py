"""Metrics: the online fold must equal the same fold replayed over the log.

The tick log is the single source of truth, so every A-layer counter is
pinned key by key against the same reduction computed from `bot.log` -- a
counter that drifts from the records behind it is the failure this file
exists to catch. The B layer (planner) is the whitelisted exception: search
cost and PlanNotFound cannot be derived from any TickRecord column.
"""

from __future__ import annotations

import pytest

from ggge_ai.bot.action import Goal
from ggge_ai.bot.bot import BotStuck
from ggge_ai.bot.demo import build_demo_bot, run_demo
from ggge_ai.bot.metrics import Metrics


def _suffixes(snapshot: dict[str, int], prefix: str) -> set[str]:
    return {key[len(prefix) :] for key in snapshot if key.startswith(prefix)}


# --- A 層：_record 摺出來的計數＝對流水帳做同樣的 fold ---


def test_tick_total_and_outcome_counters_match_the_log():
    bot = run_demo()
    snapshot = bot.metrics.snapshot()

    assert snapshot["tick.total"] == len(bot.log)

    outcomes = {record.outcome for record in bot.log}
    assert _suffixes(snapshot, "tick.outcome.") == outcomes
    for outcome in outcomes:
        assert snapshot[f"tick.outcome.{outcome}"] == len(
            [r for r in bot.log if r.outcome == outcome]
        )

    # 鍵的尾段是流水帳欄位的字面值，冒號照留。
    assert snapshot["tick.outcome.reflex:info_popup"] == 1
    assert snapshot["tick.outcome.done"] == 1


def test_replan_counters_match_the_log():
    bot = run_demo()
    snapshot = bot.metrics.snapshot()

    kinds = {r.replanned for r in bot.log if r.replanned is not None}
    assert kinds == {"refill", "replan"}
    assert _suffixes(snapshot, "replan.") == kinds
    for kind in kinds:
        assert snapshot[f"replan.{kind}"] == len([r for r in bot.log if r.replanned == kind])


def test_step_popped_counters_match_the_log():
    bot = run_demo()
    snapshot = bot.metrics.snapshot()

    assert snapshot["step_popped.total"] == sum(len(r.popped) for r in bot.log)

    names = {name for r in bot.log for name in r.popped}
    assert _suffixes(snapshot, "step_popped.") == names | {"total"}
    for name in names:
        assert snapshot[f"step_popped.{name}"] == sum(r.popped.count(name) for r in bot.log)


def test_action_executed_counters_match_the_log():
    bot = run_demo()
    snapshot = bot.metrics.snapshot()

    executed = [r for r in bot.log if r.outcome == "executed" and r.head is not None]
    assert snapshot["action_executed.total"] == len(executed)

    heads = {r.head for r in executed}
    assert _suffixes(snapshot, "action_executed.") == heads | {"total"}
    for head in heads:
        assert snapshot[f"action_executed.{head}"] == len([r for r in executed if r.head == head])

    # 反射拍沒有 head，不能算進互動數。
    assert snapshot["action_executed.total"] < snapshot["tick.total"]


@pytest.mark.parametrize("field", ["duration_ms", "slept_ms"])
def test_tick_observations_match_the_log(field: str):
    bot = run_demo()
    snapshot = bot.metrics.snapshot()
    values = [getattr(r, field) for r in bot.log]

    assert snapshot[f"tick.{field}.n"] == len(bot.log)
    assert snapshot[f"tick.{field}.sum"] == sum(values)
    assert snapshot[f"tick.{field}.min"] == min(values)
    assert snapshot[f"tick.{field}.max"] == max(values)


# --- B 層：只有 planner（該事實無法從 TickRecord 導出）---


def test_planner_counts_one_call_per_replan_tick():
    bot = run_demo()
    snapshot = bot.metrics.snapshot()

    calls = len([r for r in bot.log if r.replanned is not None])
    assert snapshot["plan.calls"] == calls
    # MockClock 只因 sleep 前進，所以 mock 下延遲必為 0——這裡只釘次數。
    assert snapshot["plan.latency_ms.n"] == calls
    assert "plan.not_found" not in snapshot


def test_plan_not_found_is_counted_on_the_panic_path():
    bot = build_demo_bot()
    bot.state.goal = Goal("impossible", {"no_such_symbol": True})

    with pytest.raises(BotStuck):
        bot.tick()

    snapshot = bot.metrics.snapshot()
    assert snapshot["plan.not_found"] == 1
    assert snapshot["plan.calls"] == 1
    assert snapshot["plan.latency_ms.n"] == 1
    assert snapshot["tick.outcome.panic"] == 1


# --- Metrics 自身 ---


def test_count_accumulates_and_defaults_to_one():
    metrics = Metrics()
    metrics.count("a")
    metrics.count("a")
    metrics.count("a", 3)
    metrics.count("b")

    assert metrics.snapshot() == {"a": 5, "b": 1}


def test_observe_keeps_n_sum_min_max():
    metrics = Metrics()
    for value in (7, 2, 5):
        metrics.observe("lat", value)

    assert metrics.snapshot() == {"lat.n": 3, "lat.sum": 14, "lat.min": 2, "lat.max": 7}


def test_snapshot_omits_keys_never_observed():
    metrics = Metrics()
    metrics.count("a")
    metrics.observe("b", 4)

    assert metrics.snapshot() == {"a": 1, "b.n": 1, "b.sum": 4, "b.min": 4, "b.max": 4}
