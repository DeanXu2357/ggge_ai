"""A scripted sync-map run: one goal, one plan, and three things to watch.

The goal is `sim_ready` and nothing else. Everything that used to be a staged
goal ("get to the hub", "finish the scan", "read the panels") is now just the
order of the plan the planner produced on tick 0.

1. `PanToFrontier` holds the head of the plan for several ticks in a row. Its
   effect is `coverage=complete`, one swipe does not achieve that, and the
   plan does not move on until the board says the map is covered. No counter
   anywhere, no sub-goal, no loop inside the action.
2. A story animation cuts in mid-scan (`view=unknown` for two ticks) and the
   head stops being runnable. `on_blocked` repairs: `WaitOut` is spliced in
   *front* and the tail is untouched -- the `plan` column of the trace shows
   the same four steps still queued behind it.
3. `TapUnit` opens the info panel and loses the camera pose doing it, which
   takes `coverage` back to unknown. `SyncSim` is then blocked, and repair
   splices in the way back (escape the panel, re-anchor, re-scan) while
   `SyncSim` stays at the end of the plan.

Run `python -m ggge_ai.bot.demo` to print the trace.
"""

from __future__ import annotations

from .action import Goal
from .actions import default_catalog
from .board import MockBoard
from .bot import Bot
from .mocks import MockDevice, MockSensor
from .state import UNKNOWN, BotState

BASE_FRAME = {
    "in_stage": True,
    "in_sync_flow": True,
    "view": "hub",
    "obstruction": "none",
    "phase": "our_turn",
    "cards": "present",
    "panel": "closed",
    "unit_list": "expanded",
    "unit_state": "idle",
}

# 劇情動畫剛好插在掃描中間（tick 7、8）：兩 tick 都讀不到畫面，而 obstruction
# 從 story 變 unknown——不是 none，所以 ReachHub 不適用，只剩下等待。
STORY_SCRIPT = [
    {},
    {},
    {},
    {},
    {},
    {},
    {},
    {"view": UNKNOWN, "obstruction": "story"},
    {"view": UNKNOWN, "obstruction": UNKNOWN},
    {},
]


def build_demo_bot() -> Bot:
    state = BotState()
    state.remember(grid="off", zoom="fit", sim_ready=False, intent="none")
    state.goal = Goal("sim_ready", {"sim_ready": True})
    return Bot(
        state=state,
        board=MockBoard(covered_cells=1, total_cells=5, resolved_units=0, candidates=1),
        sensor=MockSensor(BASE_FRAME, STORY_SCRIPT),
        device=MockDevice(),
        catalog=default_catalog(),
    )


def run_demo() -> Bot:
    bot = build_demo_bot()
    bot.run(max_ticks=40)
    return bot


if __name__ == "__main__":
    print(run_demo().trace())
