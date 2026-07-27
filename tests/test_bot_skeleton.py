"""Offline tests for the reshaped bot loop (spec: docs/bot-architecture.md).

The demo trace is the fixture for the loop's semantics: same-tick
continuation, standing instructions, the wait slot, reflex dismissal,
whole-queue replan, and evidence pops of steps that never fired. The
crafted mini-bots cover the refire gates, the panic paths, and the two
router tables' contracts.
"""

from __future__ import annotations

import pytest

from ggge_ai.bot.action import Action, Goal
from ggge_ai.bot.actions import (
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
from ggge_ai.bot.router import ReflexRouter, ReflexRule, ReflexTable, unproduced_symbols
from ggge_ai.bot.state import UNKNOWN, BotState


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


# --- demo：迴圈語意的整體 fixture ---


def test_demo_reaches_the_outer_goal():
    bot = run_demo()

    assert bot.finished
    assert bot.log[-1].outcome == "done"
    assert bot.state.get("sim_ready") is True


def test_no_bookkeeping_only_ticks():
    bot = run_demo()

    for record in bot.log:
        assert record.outcome.split(":")[0] in {"executed", "reflex", "wait", "done"}
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


def test_wait_slot_absorbs_unskippable_story_without_touching_the_queue():
    bot = run_demo()

    waits = [i for i, r in enumerate(bot.log) if r.outcome == "wait:unknown"]
    assert len(waits) == 2
    for index in waits:
        assert bot.log[index].plan == bot.log[index - 1].plan
        assert bot.log[index].phase == UNKNOWN


def test_reflex_dismisses_popup_at_the_classifier_supplied_point():
    bot = run_demo()

    index = next(i for i, r in enumerate(bot.log) if r.outcome == "reflex:info_popup")
    assert (1170, 760) in bot.device.taps
    assert bot.log[index].plan == bot.log[index - 1].plan


def test_replan_throws_the_whole_queue_away_and_executes_same_tick():
    bot = run_demo()

    record = next(r for r in bot.log if r.replanned == "replan")
    assert record.outcome == "executed"
    assert record.head == "EscapePanel"
    assert record.symbols["coverage"] == UNKNOWN
    assert record.plan[-1] == "SyncSim"


def test_evidence_pops_steps_that_never_fired():
    bot = run_demo()

    replan_at = next(i for i, r in enumerate(bot.log) if r.replanned == "replan")
    tail = bot.log[replan_at + 1 :]

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


# --- refire 閘門 ---


def test_action_refire_gate_holds_while_the_frame_is_frozen():
    bot = _mini_bot(Goal("grid", {"grid": "on"}), script=[None, BASE_FRAME])

    bot.run(max_ticks=5)

    assert [r.outcome for r in bot.log] == ["executed", "wait:refire", "done"]
    assert bot.device.taps.count((2180, 140)) == 1


def test_reflex_refire_gate_fires_once_on_identical_frames():
    popup = FrameReading(UNKNOWN, (Tag("info_popup", point=(500, 500)),))
    taps: list[tuple[int, int]] = []

    def dismiss(bot: Bot, tag: Tag) -> None:
        assert tag.point is not None
        bot.device.tap(*tag.point)
        taps.append(tag.point)

    table = ReflexTable([ReflexRule(tag="info_popup", handler=dismiss, refire="require_change")])
    bot = _mini_bot(Goal("grid", {"grid": "on"}), script=[popup, popup], reflexes=table)

    bot.run(max_ticks=6)

    assert taps == [(500, 500)]
    assert [r.outcome for r in bot.log[:2]] == ["reflex:info_popup", "wait:refire"]
    assert bot.finished


# --- panic 路徑 ---


def test_unknown_waits_do_not_panic_only_max_ticks_stops_them():
    # 連續 unknown 的超限裁決是熔斷器的事（延後、從流水帳導出）；
    # v1 的等待格只記帳，粗保險只有 max_ticks。
    bot = _mini_bot(Goal("grid", {"grid": "on"}), script=[STORY] * 8)

    bot.run(max_ticks=6)

    assert not bot.finished
    assert [r.outcome for r in bot.log] == ["wait:unknown"] * 6
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
    both = FrameReading(UNKNOWN, (Tag("b"), Tag("a")))

    assert router.route(None, both) == "reflex:a"
    assert fired == ["first:a"]


def test_symbol_table_is_total_on_any_frame():
    table = default_symbol_table()

    blank = table.translate(FrameReading(UNKNOWN))
    assert set(blank) == set(table.symbols)
    assert all(value == UNKNOWN for value in blank.values())

    hub = table.translate(BASE_FRAME)
    assert hub["grid"] == "off"
    assert hub["zoom"] == "not_max"
    assert hub["cards"] == "present"
    assert hub["unit_list"] == "expanded"
    assert hub["unit_state"] == "idle"


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
