"""The replan-storm breaker: `run` counts what the ticks report to it.

The streak is a local of the supervisor, not a shape read back out of the
log, so it is earned tick by tick on a world that flips under the plan. What
the scenarios pin is when the count moves: a replan raises it, a tick that
ran the bookkeeping through without throwing the queue away clears it, and a
tick a reflex ended does neither -- a popup burst must not launder a storm.
Tests read `bot.log` afterwards, which is analysis, not machinery.
"""

from __future__ import annotations

import pytest

from ggge_ai.bot.action import Action, Goal
from ggge_ai.bot.board import MockBoard
from ggge_ai.bot.bot import REPLAN_STORM_TICKS, Bot, BotStuck
from ggge_ai.bot.frame import FrameReading, Tag
from ggge_ai.bot.mocks import IdentityClassifier, MockClock, MockDevice, MockScreen
from ggge_ai.bot.router import ReflexRule, ReflexTable, SymbolTable, from_identity, tag_present
from ggge_ai.bot.state import BotState

_SCREEN_A = FrameReading((Tag("screen_a"),))
_SCREEN_B = FrameReading((Tag("screen_b"),))
_WON = FrameReading((Tag("locked_banner"), Tag("cleared_banner")))
_POPUP = FrameReading((Tag("info_popup", point=(500, 500)),))


class _AimA(Action):
    name = "AimA"
    pre = {"view": "a"}
    eff = {"locked": True}

    def do(self, bot: Bot) -> None:
        bot.device.tap(10, 10)


class _AimB(Action):
    name = "AimB"
    pre = {"view": "b"}
    eff = {"locked": True}

    def do(self, bot: Bot) -> None:
        bot.device.tap(20, 20)


class _Fire(Action):
    name = "Fire"
    pre = {"locked": True}
    eff = {"cleared": True}

    def do(self, bot: Bot) -> None:
        bot.device.tap(30, 30)


def _dismiss(bot: Bot, tag: Tag) -> None:
    assert tag.point is not None
    bot.device.tap(*tag.point)


def _flip_bot(script: list[FrameReading | None]) -> Bot:
    state = BotState()
    state.goal = Goal("cleared", {"cleared": True})
    table = SymbolTable(
        {
            "view": from_identity({"screen_a": "a", "screen_b": "b"}),
            "locked": tag_present("locked_banner", True, False),
            "cleared": tag_present("cleared_banner", True, False),
        },
        identities={"screen_a": "a", "screen_b": "b"},
    )
    return Bot(
        state=state,
        board=MockBoard(),
        screen=MockScreen(_SCREEN_A, script),
        classifier=IdentityClassifier(),
        device=MockDevice(),
        clock=MockClock(),
        catalog=[_AimA(), _AimB(), _Fire()],
        symbol_table=table,
        reflex_table=ReflexTable([ReflexRule(tag="info_popup", handler=_dismiss)]),
    )


def _alternating(ticks: int) -> list[FrameReading | None]:
    return [_SCREEN_A if index % 2 == 0 else _SCREEN_B for index in range(ticks)]


def test_a_view_flipping_under_the_plan_trips_the_breaker():
    bot = _flip_bot(_alternating(REPLAN_STORM_TICKS * 3))

    with pytest.raises(BotStuck) as excinfo:
        bot.run(max_ticks=60)

    assert excinfo.value.kind == "replan_storm"
    assert "replan storm" in str(excinfo.value)
    assert not bot.finished


def test_the_tripping_run_ends_on_a_complete_record_of_the_nth_replan():
    bot = _flip_bot(_alternating(REPLAN_STORM_TICKS * 3))

    with pytest.raises(BotStuck):
        bot.run(max_ticks=60)

    # 第 0 拍是 refill，其後每拍隊頭過期一次——第 n 次 replan 落帳後才跳閘。
    assert len(bot.log) == REPLAN_STORM_TICKS + 1
    assert bot.log[0].replanned == "refill"
    assert all(record.replanned == "replan" for record in bot.log[-REPLAN_STORM_TICKS:])

    last = bot.log[-1]
    assert last.outcome == "executed"
    assert last.head in {"AimA", "AimB"}
    # 跳閘不留自己的記錄：最後一筆是那一拍完整走完的執行記錄。
    assert all(not record.outcome.startswith(("panic", "stuck")) for record in bot.log)


def test_a_reflex_tick_neither_counts_nor_clears_the_streak():
    half = REPLAN_STORM_TICKS // 2
    script = [*_alternating(half + 1), _POPUP, *_alternating(half + 1)]

    bot = _flip_bot(script)
    with pytest.raises(BotStuck) as excinfo:
        bot.run(max_ticks=60)

    assert excinfo.value.kind == "replan_storm"

    popup = next(record for record in bot.log if record.outcome == "reflex:info_popup")
    assert (500, 500) in bot.device.taps
    assert popup.replanned is None
    # 反射拍就落在最後 n 筆裡：讀流水帳尾巴的規則會漏掉這場風暴，計數器不會。
    assert not all(record.replanned == "replan" for record in bot.log[-REPLAN_STORM_TICKS:])
    assert len([r for r in bot.log if r.replanned == "replan"]) == REPLAN_STORM_TICKS


def test_a_tick_that_kept_its_plan_clears_the_streak():
    nearly = REPLAN_STORM_TICKS - 1
    # 同一視圖連兩幀＝隊頭沒過期，bookkeeping 走完卻沒翻桌——計數歸零的唯一證據。
    script = [*_alternating(nearly + 1), _SCREEN_B, *_alternating(nearly)]
    assert script[nearly] is _SCREEN_B

    bot = _flip_bot(script)
    bot.run(max_ticks=len(script))

    assert not bot.finished
    assert len(bot.log) == len(script)

    survivor = bot.log[nearly + 1]
    assert survivor.outcome == "executed"
    assert survivor.replanned is None
    assert len([r for r in bot.log if r.replanned == "replan"]) == nearly * 2


def test_a_goal_reached_one_replan_short_of_the_threshold_finishes():
    # 連續 n-1 次翻桌後目標達成：收工那拍隊列被證據清空，頂部檢查直接裁決
    # done——不經 planner，也就不可能再補上第 n 次 replan。
    bot = _flip_bot([*_alternating(REPLAN_STORM_TICKS), _WON])

    bot.run(max_ticks=60)

    assert bot.finished
    assert len(bot.log) == REPLAN_STORM_TICKS + 1
    assert len([r for r in bot.log if r.replanned == "replan"]) == REPLAN_STORM_TICKS - 1

    last = bot.log[-1]
    assert last.outcome == "done"
    assert last.replanned is None
    assert last.popped == ["AimB", "Fire"]
