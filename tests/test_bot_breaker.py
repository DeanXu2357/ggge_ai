"""The replan-storm breaker: a pure predicate over the tail of the tick log.

Two halves. The predicate is checked on hand-built records, because that is
all it is allowed to need -- if it can be fooled by a log it never saw a bot
produce, it cannot be replayed offline either. The loop half then earns the
threshold on a world that flips under the plan every tick, and pins the one
ordering that matters: reaching the goal on the tick that completes the
streak is a finished run, not a trip.
"""

from __future__ import annotations

import pytest

from ggge_ai.bot.action import Action, Goal
from ggge_ai.bot.board import MockBoard
from ggge_ai.bot.bot import REPLAN_STORM_TICKS, Bot, BotStuck, TickRecord, replan_storm
from ggge_ai.bot.frame import FrameReading, Tag
from ggge_ai.bot.mocks import IdentityClassifier, MockClock, MockDevice, MockScreen
from ggge_ai.bot.router import ReflexTable, SymbolTable, from_identity, tag_present
from ggge_ai.bot.state import BotState


def _tick(replanned: str | None, outcome: str = "executed") -> TickRecord:
    return TickRecord(
        tick=0,
        tags=[],
        outcome=outcome,
        head=None,
        popped=[],
        replanned=replanned,
        plan_len=0,
    )


def _replans(count: int) -> list[TickRecord]:
    return [_tick("replan") for _ in range(count)]


# --- 謂詞：只看流水帳尾巴，不需要 bot ---


def test_exactly_n_consecutive_replans_trip():
    assert replan_storm(_replans(REPLAN_STORM_TICKS)) is True


def test_one_replan_short_of_n_does_not_trip():
    assert replan_storm(_replans(REPLAN_STORM_TICKS - 1)) is False


def test_a_streak_longer_than_n_stays_tripped():
    assert replan_storm(_replans(REPLAN_STORM_TICKS + 5)) is True


@pytest.mark.parametrize(
    "interruption",
    [_tick(None, outcome="reflex:info_popup"), _tick("refill"), _tick(None)],
    ids=["reflex", "refill", "no_replan"],
)
def test_any_non_replan_record_inside_the_window_breaks_the_streak(interruption: TickRecord):
    log = _replans(REPLAN_STORM_TICKS * 2)
    log[-3] = interruption

    assert replan_storm(log) is False


def test_a_full_streak_after_an_interruption_trips_again():
    log = [*_replans(3), _tick("refill"), *_replans(REPLAN_STORM_TICKS)]

    assert replan_storm(log) is True


def test_a_log_shorter_than_the_window_never_trips():
    assert replan_storm([]) is False
    assert replan_storm(_replans(1)) is False


def test_the_window_is_a_parameter():
    assert replan_storm(_replans(3), n=3) is True
    assert replan_storm(_replans(2), n=3) is False


# --- 迴圈：視圖每拍翻面，隊頭每拍誠實過期 ---


_SCREEN_A = FrameReading((Tag("screen_a"),))
_SCREEN_B = FrameReading((Tag("screen_b"),))
_CLEARED = FrameReading((Tag("cleared_banner"),))


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
        reflex_table=ReflexTable(),
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

    # 第 0 拍是 refill，其後每拍隊頭過期一次——第 n 次 replan 落帳後就跳閘。
    assert len(bot.log) == REPLAN_STORM_TICKS + 1
    assert bot.log[0].replanned == "refill"
    assert [record.replanned for record in bot.log[1:]] == ["replan"] * REPLAN_STORM_TICKS

    last = bot.log[-1]
    assert last.outcome == "executed"
    assert last.replanned == "replan"
    assert last.head in {"AimA", "AimB"}
    # 跳閘不留自己的記錄：最後一筆是那一拍完整走完的執行記錄。
    assert all(not record.outcome.startswith("panic") for record in bot.log)


def test_a_goal_reached_on_the_tripping_tick_finishes_instead_of_tripping():
    bot = _flip_bot([*_alternating(REPLAN_STORM_TICKS), _CLEARED])

    bot.run(max_ticks=60)

    assert bot.finished
    assert len(bot.log) == REPLAN_STORM_TICKS + 1

    last = bot.log[-1]
    assert last.outcome == "done"
    assert last.replanned == "replan"
    # 收工那拍自己補滿了連續 replan：謂詞成立，但 finished 先判，所以沒跳閘。
    assert replan_storm(bot.log) is True
