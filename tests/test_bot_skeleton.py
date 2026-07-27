import pytest

from ggge_ai.bot.actions import PanToFrontier, SyncSim
from ggge_ai.bot.bot import BotStuck
from ggge_ai.bot.demo import build_demo_bot, run_demo


def _cornered_bot():
    """Demo bot with the camera pose lost and nothing in the catalog that can restore it."""
    bot = build_demo_bot()
    bot.catalog = [PanToFrontier(), SyncSim()]
    bot.state.remember(grid="on", zoom="max")
    bot.sensor.override(unit_list="collapsed")
    bot.board.pose = "lost"
    bot.plan = [PanToFrontier(), SyncSim()]
    return bot


def test_demo_reaches_the_outer_goal():
    bot = run_demo()

    assert bot.finished
    assert bot.log[-1].outcome == "done"
    assert bot.state.get("sim_ready") is True


def test_pan_holds_the_head_until_coverage_completes():
    bot = run_demo()

    runs, current = [], 0
    for record in bot.log:
        if record.head == "PanToFrontier" and record.outcome == "executed":
            current += 1
            continue
        runs.append(current)
        current = 0
    runs.append(current)
    assert max(runs) >= 3

    end = next(
        index
        for index in range(1, len(bot.log))
        if bot.log[index - 1].head == "PanToFrontier"
        and bot.log[index - 1].outcome == "executed"
        and bot.log[index].head != "PanToFrontier"
    )
    assert bot.log[end].outcome == "popped"
    assert bot.log[end].symbols["coverage"] == "complete"


def test_repair_prepends_and_keeps_the_tail():
    bot = run_demo()

    repairs = [index for index, record in enumerate(bot.log) if record.outcome == "blocked:repair"]
    assert len(repairs) == 2
    for index in repairs:
        before = bot.log[index - 1].plan
        after = bot.log[index].plan
        assert len(after) > len(before)
        assert after[len(after) - len(before) :] == before

    assert bot.log[repairs[0]].plan[0] == "WaitOut"
    assert "ReAnchor" in bot.log[repairs[1]].plan


def test_repair_without_a_route_falls_back_to_reset():
    bot = _cornered_bot()

    bot.tick()

    assert bot.log[-1].head == "PanToFrontier"
    assert bot.log[-1].outcome == "blocked:reset"
    assert bot.plan == []


def test_reset_without_a_plan_aborts():
    bot = _cornered_bot()
    bot.tick()

    with pytest.raises(BotStuck) as excinfo:
        bot.tick()

    assert "no plan for goal 'sim_ready'" in str(excinfo.value)
