"""A scripted sync-map run: one goal, one queue, and five things to watch.

The goal is `sim_ready` and nothing else; the staging lives in the order of
the plan the planner produced on tick 0.

1. Same-tick continuation everywhere: a step whose effect shows up in this
   tick's frame is popped and the next step fires on the same reading --
   there is not a single bookkeeping-only tick in the whole trace.
2. `PanToFrontier` holds the head for several ticks (standing instruction);
   an unskippable story animation (no identity tag, ticks 6-7) breaks its
   `view` precondition, and the replan answers with `Observe` at the head --
   a standing instruction with nothing to send, so the story costs the device
   nothing and the hub frame at tick 8 pops it plus three ensure steps at once.
3. A one-button popup rides in on tick 10 as an `info_popup` tag: the reflex
   table dismisses it at the classifier-supplied point. The reflex check runs
   before the queue, so a tagged frame is handled without disturbing the plan
   even though its screen identity is unreadable.
4. `TapUnit` loses the camera pose; when `SyncSim` reaches the head its pre
   no longer holds -> the whole queue is thrown away and replanned from the
   panel state, and the new head executes the same tick. No repair surgery.
5. The replanned route re-lists the ensure steps (hub facts are UNKNOWN from
   inside the panel), and the next hub frame pops four of them at once for
   free -- evidence advancing the queue past steps that never fired.

Run `python -m ggge_ai.bot.demo` to print the trace.
"""

from __future__ import annotations

from .action import Goal
from .actions import default_catalog, default_reflex_table, default_symbol_table
from .board import MockBoard
from .bot import Bot
from .frame import FrameReading, Tag
from .mocks import IdentityClassifier, MockClock, MockDevice, MockScreen
from .state import BotState

BASE_FRAME = FrameReading(
    (Tag("hub"), Tag("unit_cards"), Tag("turn_ours"), Tag("unit_list_expanded")),
)

STORY = FrameReading()
POPUP = FrameReading((Tag("info_popup", point=(1170, 760)),))

# 劇情動畫插在掃描中間（tick 6、7，無 skip 鈕＝只能等）；資訊彈窗蓋在
# 開面板之後（tick 10，有 tag＝反射點掉）。其餘拍不干擾。
SCRIPT: list[FrameReading | None] = [None] * 6 + [STORY, STORY, None, None, POPUP]


def build_demo_bot() -> Bot:
    state = BotState()
    state.remember(sim_ready=False, intent="none")
    state.goal = Goal("sim_ready", {"sim_ready": True})
    return Bot(
        state=state,
        board=MockBoard(covered_cells=1, total_cells=5, resolved_units=0, candidates=1),
        screen=MockScreen(BASE_FRAME, SCRIPT),
        classifier=IdentityClassifier(),
        device=MockDevice(),
        clock=MockClock(),
        catalog=default_catalog(),
        symbol_table=default_symbol_table(),
        reflex_table=default_reflex_table(),
    )


def run_demo() -> Bot:
    bot = build_demo_bot()
    bot.run(max_ticks=40)
    return bot


if __name__ == "__main__":
    print(run_demo().trace())
