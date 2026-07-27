"""討論用的架構骨架：整支機器人只有一個迴圈，一個 tick 只做兩件事。

- tick = sense 一次（覆寫感知符號）→ decide 一步 → act 一步。三行結束，
  沒有子迴圈、沒有輪詢；等待、思考、點擊在這裡是同一種東西。
- 符號空間是扁平的：`in_stage`、`view`、`coverage`、`phase`、`sim_ready`、
  `intent` 全在同一層，不分 outer/in-stage。「我在哪一層」只是其中一個符號。
- 目標只有一個，而且是最外層那個。「階段性目標」不再用 goal 表達，改由
  計畫本身的順序表達：`Bot.plan` 是一條跨 tick 存活的動作陣列。
- 隊頭動作在「eff 成立」時才 pop，不是「執行過」就 pop。所以一個動作會留在
  隊頭反覆執行直到它宣告的效果為真（PanToFrontier 掃到 coverage=complete
  為止），重複不需要計數器也不需要階段目標。代價是 cost 不再是時間估計，
  分岔要用 precondition 而不是成本來選。
- 隊頭跑不動時進 `on_blocked` 三選一：repair（修一段接在前面、保留尾巴）、
  reset（整條丟掉重想）、abandon（頭已無意義就丟頭留尾）。判準只有一個——
  這條計畫的尾巴值多少錢。
- 感知符號每 tick 由 sense 覆寫，讀不到寫 unknown；記憶符號只有 action 能寫。
  畫面永遠是權威，但畫面不能偷偷撤銷我們做過的決定。
- 思考也是 action：SyncSim／SolveTactics 不碰裝置，SolveTactics 甚至把想出來的
  戰術步驟接在自己後面——思考因此會被記帳、會佔一個 tick、可以被打斷。
- 大資料留在 board（地形、單位、預測表），只有 coverage/details/pose 這種
  摘要符號進 state——規劃器不該對著一張 cell map 做搜尋。
- 這一版沒有迴圈偵測：`run(max_ticks)` 的上限是唯一的終止保證，行為好不好
  一律看 `Bot.trace()` 的逐 tick 流水帳。
- 這一版所有動作、感知、裝置都是 mock，真實行為寫在 do() 裡的註解。
"""

from .action import Action, Goal
from .board import MockBoard
from .bot import Bot, BotStuck, TickRecord
from .mocks import MockDevice, MockSensor
from .state import UNKNOWN, BotState

__all__ = [
    "UNKNOWN",
    "Action",
    "Bot",
    "BotStuck",
    "BotState",
    "Goal",
    "MockBoard",
    "MockDevice",
    "MockSensor",
    "TickRecord",
]
