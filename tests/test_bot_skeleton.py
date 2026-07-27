"""Offline tests for the reshaped bot loop (spec: docs/bot-architecture.md).

The demo trace is the fixture for the loop's semantics: same-tick
continuation, standing instructions, observation as a planned step, reflex
dismissal, whole-queue replan, and evidence pops of steps that never fired.
The crafted mini-bots cover unreadable frames, the reflex dispatch contract,
the panic paths, and the two router tables' contracts.
"""

from __future__ import annotations

import pytest

from ggge_ai.bot.action import Action, Goal
from ggge_ai.bot.actions import (
    IDENTITY_VIEWS,
    MEMORY_SYMBOLS,
    default_catalog,
    default_reflex_table,
    default_symbol_table,
)
from ggge_ai.bot.board import BOARD_SYMBOLS, MockBoard
from ggge_ai.bot.bot import Bot, BotStuck
from ggge_ai.bot.demo import BASE_FRAME, STORY, build_demo_bot, run_demo
from ggge_ai.bot.frame import FrameReading, Tag
from ggge_ai.bot.mocks import IdentityClassifier, MockClock, MockDevice, MockScreen
from ggge_ai.bot.router import (
    ReflexRouter,
    ReflexRule,
    ReflexTable,
    misrouted_identity_tags,
    unproduced_symbols,
)
from ggge_ai.bot.state import UNKNOWN, BotState
from ggge_ai.goap.planner import plan


def _mini_bot(
    goal: Goal,
    base: FrameReading = BASE_FRAME,
    script: list[FrameReading | None] | None = None,
    reflexes: ReflexTable | None = None,
    board: MockBoard | None = None,
) -> Bot:
    state = BotState()
    state.remember(sim_ready=False, intent="none")
    state.goal = goal
    return Bot(
        state=state,
        board=board or MockBoard(covered_cells=1, total_cells=5, candidates=1),
        screen=MockScreen(base, script or []),
        classifier=IdentityClassifier(),
        device=MockDevice(),
        clock=MockClock(),
        catalog=default_catalog(),
        symbol_table=default_symbol_table(),
        reflex_table=reflexes or default_reflex_table(),
    )


def _panel_replan_index(bot: Bot) -> int:
    # 故事幀也會讓隊頭 pre 破裂重規劃，所以要點名的是面板那一次。
    return next(
        i for i, r in enumerate(bot.log) if r.replanned == "replan" and r.symbols["view"] == "panel"
    )


# --- demo：迴圈語意的整體 fixture ---


def test_demo_reaches_the_outer_goal():
    bot = run_demo()

    assert bot.finished
    assert bot.log[-1].outcome == "done"
    assert bot.state.get("sim_ready") is True


def test_no_bookkeeping_only_ticks():
    bot = run_demo()

    for record in bot.log:
        assert record.outcome.split(":")[0] in {"executed", "reflex", "done"}
    assert any(record.popped and record.outcome == "executed" for record in bot.log)


def test_one_device_interaction_per_tick():
    bot = build_demo_bot()
    before = bot.device.interactions
    for _ in range(40):
        bot.tick()
        assert bot.device.interactions - before <= 1
        before = bot.device.interactions
        if bot.finished:
            break
    assert bot.finished


def test_pan_holds_the_head_then_pops_into_the_next_step():
    bot = run_demo()

    executed = [r for r in bot.log if r.head == "PanToFrontier" and r.outcome == "executed"]
    assert len(executed) >= 3

    handoff = next(r for r in bot.log if "PanToFrontier" in r.popped)
    assert handoff.outcome == "executed"
    assert handoff.head != "PanToFrontier"
    assert handoff.symbols["coverage"] == "complete"


def test_unskippable_story_costs_the_device_nothing_and_the_goal_still_lands():
    bot = build_demo_bot()

    observed = 0
    for _ in range(40):
        before = bot.device.interactions
        bot.tick()
        record = bot.log[-1]
        if record.head == "Observe":
            observed += 1
            assert record.symbols["view"] == UNKNOWN
            assert bot.device.interactions == before
        if bot.finished:
            break

    assert observed == 2
    assert bot.finished
    assert bot.state.get("sim_ready") is True


def test_reflex_dismisses_popup_at_the_classifier_supplied_point():
    bot = run_demo()

    index = next(i for i, r in enumerate(bot.log) if r.outcome == "reflex:info_popup")
    assert (1170, 760) in bot.device.taps
    assert bot.log[index].plan == bot.log[index - 1].plan


def test_replan_throws_the_whole_queue_away_and_executes_same_tick():
    bot = run_demo()

    record = bot.log[_panel_replan_index(bot)]
    assert record.outcome == "executed"
    assert record.head == "EscapePanel"
    assert record.symbols["coverage"] == UNKNOWN
    assert record.plan[-1] == "SyncSim"


def test_evidence_pops_steps_that_never_fired():
    bot = run_demo()

    tail = bot.log[_panel_replan_index(bot) + 1 :]

    ensure_pop = next(r for r in tail if len(r.popped) >= 3)
    assert {"CollapseUnitList", "EnableGrid", "ZoomToMax"} <= set(ensure_pop.popped)
    assert ensure_pop.outcome == "executed"

    free_pop = next(r for r in tail if "PanToFrontier" in r.popped)
    assert all(r.head != "PanToFrontier" for r in tail)
    assert free_pop.head == "SyncSim"


def test_perception_symbols_are_recomputed_every_tick():
    bot = run_demo()

    weapon_tick = next(r for r in bot.log if r.symbols.get("panel_tab") == "weapon")
    back_on_hub = next(r for r in bot.log[weapon_tick.tick :] if r.symbols["view"] == "hub")
    assert back_on_hub.symbols["panel_tab"] == UNKNOWN


# --- 不可讀的幀：由計畫裡的觀察動作承接，迴圈裡沒有 unknown 分支 ---


def test_the_planner_routes_out_of_an_unreadable_screen():
    state = BotState()
    state.remember(sim_ready=False, intent="none")
    state.sense_update(default_symbol_table().translate(STORY))
    state.sense_update(MockBoard(covered_cells=1, total_cells=5, candidates=1).summary_symbols())
    assert state.get("view") == UNKNOWN

    result = plan(state.to_world_state(), Goal("grid", {"grid": "on"}), default_catalog())

    assert [step.name for step in result.actions] == ["Observe", "EnableGrid"]


def test_a_run_that_starts_unreadable_observes_first_and_carries_on():
    bot = _mini_bot(Goal("grid", {"grid": "on"}), script=[STORY, None])

    bot.run(max_ticks=5)

    assert bot.log[0].replanned == "refill"
    assert bot.log[0].head == "Observe"
    assert bot.log[0].symbols["view"] == UNKNOWN
    assert bot.log[1].head == "EnableGrid"
    assert bot.device.taps == [(2180, 140)]
    assert bot.finished


def test_a_frame_going_unreadable_replans_into_an_observe_led_plan():
    bot = _mini_bot(Goal("setup", {"grid": "on", "zoom": "max"}), script=[None, STORY, None])

    bot.tick()
    assert bot.log[0].outcome == "executed"

    quiet = bot.device.interactions
    bot.tick()

    assert bot.log[1].replanned == "replan"
    assert bot.log[1].head == "Observe"
    assert bot.log[1].plan[0] == "Observe"
    assert bot.log[1].symbols["view"] == UNKNOWN
    assert bot.device.interactions == quiet

    bot.run(max_ticks=5)

    assert bot.finished
    assert bot.state.get("grid") == "on"
    assert bot.state.get("zoom") == "max"


def test_two_identity_tags_on_one_frame_take_the_same_observation_route():
    # 兩個畫面身分同時命中是互相矛盾的讀數，不是「兩個都成立」——一樣是
    # view unknown，走同一條觀察路徑。
    contradictory = FrameReading((Tag("hub"), Tag("unit_panel"), Tag("turn_ours")))
    bot = _mini_bot(Goal("grid", {"grid": "on"}), base=contradictory)

    bot.run(max_ticks=3)

    assert [r.outcome for r in bot.log] == ["executed"] * 3
    assert [r.head for r in bot.log] == ["Observe"] * 3
    assert all(r.symbols["view"] == UNKNOWN for r in bot.log)
    assert bot.device.interactions == 0


def test_reflex_dispatches_every_tick_the_tag_is_present():
    # router 只派發不決策：tag 還在就每拍進一次 handler（多頁劇情連點的
    # 基礎）；等待／重觸發／timeout 屬於 handler 內容，不屬於 route 編排。
    popup = FrameReading((Tag("info_popup", point=(500, 500)),))
    taps: list[tuple[int, int]] = []

    def dismiss(bot: Bot, tag: Tag) -> None:
        assert tag.point is not None
        bot.device.tap(*tag.point)
        taps.append(tag.point)

    table = ReflexTable([ReflexRule(tag="info_popup", handler=dismiss)])
    bot = _mini_bot(Goal("grid", {"grid": "on"}), script=[popup, popup], reflexes=table)

    bot.run(max_ticks=6)

    assert taps == [(500, 500), (500, 500)]
    assert [r.outcome for r in bot.log[:2]] == ["reflex:info_popup", "reflex:info_popup"]
    assert bot.finished


# --- panic 路徑 ---


def test_unknown_views_do_not_panic_only_max_ticks_stops_them():
    # 持續讀不出畫面不是詞彙洞，PlanNotFound 也就永遠不會發生；「一直重規劃
    # 卻沒有進度」的超限裁決是熔斷器的事（延後、從流水帳導出），v1 的粗保險
    # 只有 max_ticks。
    bot = _mini_bot(Goal("grid", {"grid": "on"}), script=[STORY] * 8)

    bot.run(max_ticks=6)

    assert not bot.finished
    assert [r.head for r in bot.log] == ["Observe"] * 6
    assert all(r.outcome == "executed" for r in bot.log)
    assert bot.device.interactions == 0


def test_missing_vocabulary_panics_with_a_dump():
    bot = _mini_bot(
        Goal("sim_ready", {"sim_ready": True}),
        board=MockBoard(covered_cells=5, total_cells=5, candidates=1, pose="lost"),
    )
    bot.catalog = [action for action in bot.catalog if action.name != "ReAnchor"]

    with pytest.raises(BotStuck) as excinfo:
        bot.tick()

    assert "no plan for goal 'sim_ready'" in str(excinfo.value)
    assert "pose='lost'" in str(excinfo.value)
    assert bot.log[-1].outcome == "panic"


# --- router 兩張表的契約 ---


def test_reflex_router_first_registered_blocking_rule_wins():
    fired: list[str] = []

    def first(bot: Bot, tag: Tag) -> None:
        fired.append(f"first:{tag.name}")

    def second(bot: Bot, tag: Tag) -> None:
        fired.append(f"second:{tag.name}")

    router = ReflexRouter(
        ReflexTable(
            [
                ReflexRule(tag="a", handler=first),
                ReflexRule(tag="b", handler=second),
            ]
        )
    )
    both = FrameReading((Tag("b"), Tag("a")))

    assert router.route(None, both) == "reflex:a"
    assert fired == ["first:a"]


def test_symbol_table_is_total_on_any_frame():
    table = default_symbol_table()

    blank = table.translate(FrameReading())
    assert set(blank) == set(table.symbols)
    assert all(value == UNKNOWN for value in blank.values())

    hub = table.translate(BASE_FRAME)
    assert hub["view"] == "hub"
    assert hub["grid"] == "off"
    assert hub["zoom"] == "not_max"
    assert hub["cards"] == "present"
    assert hub["unit_list"] == "expanded"
    assert hub["unit_state"] == "idle"


def test_scoped_symbols_are_unknown_without_their_identity_tag():
    # tag 缺席只有在所屬畫面在場時才讀得出「關閉」；不可作證的幀上，
    # 預設值就是偽造事實。全域符號（turn）不受畫面身分限制。
    table = default_symbol_table()

    orphan = table.translate(FrameReading((Tag("unit_cards"), Tag("turn_ours"))))

    assert orphan["view"] == UNKNOWN
    assert orphan["cards"] == UNKNOWN
    assert orphan["grid"] == UNKNOWN
    assert orphan["unit_list"] == UNKNOWN
    assert orphan["unit_state"] == UNKNOWN
    assert orphan["turn"] == "our_turn"


def test_identity_tags_are_barred_from_the_reflex_table():
    table = default_symbol_table()
    assert table.identity_tags == frozenset(IDENTITY_VIEWS)
    assert misrouted_identity_tags(table, default_reflex_table()) == set()

    def dismiss(bot: Bot, tag: Tag) -> None:
        raise AssertionError("an identity tag must never reach a reflex handler")

    smuggled = ReflexTable([*default_reflex_table().rules, ReflexRule("unit_panel", dismiss)])
    assert misrouted_identity_tags(table, smuggled) == {"unit_panel"}


def test_every_catalog_symbol_has_exactly_one_producer():
    missing = unproduced_symbols(
        default_catalog(), default_symbol_table(), MEMORY_SYMBOLS, BOARD_SYMBOLS
    )
    assert missing == set()


def test_unproduced_symbols_flags_vocabulary_holes():
    class Bogus(Action):
        name = "Bogus"
        pre = {"no_such_symbol": True}

    missing = unproduced_symbols(
        [*default_catalog(), Bogus()], default_symbol_table(), MEMORY_SYMBOLS, BOARD_SYMBOLS
    )
    assert missing == {"no_such_symbol"}
