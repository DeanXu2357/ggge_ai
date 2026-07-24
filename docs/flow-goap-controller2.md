# 戰鬥內流程層 GOAP：BattleController2 與 sync_initial_map（Round 2 正式規格）

2026-07-24 與使用者逐題定案。本檔取代
[scan-flow-robustness-plan.md](scan-flow-robustness-plan.md)「Round 2（草案）」
段（該段保留為歷史、已加指標）。架構定位見
[agent-architecture.md](agent-architecture.md) 尾節「戰鬥內流程層 GOAP」：
三規劃器各管各的狀態空間（戰略層 GOAP／流程層 GOAP／戰術層 solver），
互不巢狀，只透過真實畫面耦合。

## 使用者定案（2026-07-24 討論，逐條）

1. **三值化＋詞彙升級**：`unknown` 是 WorldState 一等值。
   `classify_frame`／各探針的可辨識案例要擴充——「我方回合可行動、
   單位列表收合」這種態必須存在於詞彙中，且有動作能過渡到
   「列表展開」（輪四的洞的根治）。
2. **tick 間意外＝先求有**：下個 tick 發現非上一動作預期的畫面，先 log
   成結構化事件；分流規則從最簡單的開始——diff 只碰「剩餘計畫不依賴的
   keys」→續走，否則 replan。反應邏輯之後按實機證據演化，第一版的
   任務是讓我們**知道流程進行中有這樣一個洞**。
3. **全域不變式**：「畫面乾淨」（無 modal、無選取殘留、無變暗）做成
   主線動作共用前置條件＋修復動作；任何一步弄髒畫面，replan 自動繞去
   修復。這是 Round 2 重做的核心理由，不是把六步腳本包成六個 Action。
4. **可觀測性是一等交付物**：意外發生時系統必須明確記錄
   「這個情況我們沒準備」（事件＋原生存證），這是 GOAP 化的底線收益。
5. **遷移＝新入口**：實作 `BattleController2`，舊 `battle/controller.py`
   行為零改動；共用 helper 直接重用。Round 1.x 八輪實機戰果不上賭桌。
6. **範圍＝`sync_initial_map` goal**，驗證形態＝`controller2.run(goal)`
   獨立推進。外層 AgentLoop 維持「接 BattleController」的現有邊界；
   `sync_sim` 旗標併入 clear_stage goal 是後續整合、不在本輪。
7. **不設獨立中斷 router**：controller2 內所有意外畫面一律走 GOAP
   詞彙；keyguard 留在 tick 前置雜務（同 `AgentLoop` 現行做法）。
   劇情彈窗 v1 不進詞彙——遇到＝unknown 誠實中止＋存證，有實機證據
   再加 SkipStory 動作。每種障礙只有一個擁有者。
8. **實機順序：controller2 冷跑 probe 優先於輪十三**。裝置現況
   （EX-2 IF TURN 1 hub、cache 空）讓給 probe；輪十三（R1.9~1.12
   首戰）延後到 probe 之後。
9. **survey 粒度＝逐單位 GOAP 化**：每台單位的 identify／面板讀取是
   獨立 Action，planner 可逐台重排與跳過。**控險約束**：R1.5（疊層
   閘門、escape 紀律）與 R1.9（tap 前臨場複驗、snap、幽靈 drop）的
   單台機制**原樣**作為動作 execute 內身；被替換的只有 `survey_stage`
   的外層迭代／排序編排。既有單台機制測試不動。

## 結構鐵則

- **ensure 語意、冪等**：所有動作都是「設成目標值」（如
  `set_battle_grid(..., True)`），絕無盲 toggle。因此在 `unknown` 述詞
  上規劃天然安全——最壞情況是多排一步廉價的 ensure。
- **動作安全分級**：目錄結構上只收「純讀取／可逆導航」級動作。tap
  單位進選取態屬可逆導航（escape 走 R1.5 紀律：先驗回 hub、絕不 tap
  地圖格）；**會提交遊戲行動的 tap 型別上進不了這一層**。
  sync_initial_map 本來就不需要提交任何行動。
- **黑板即記憶**：進度述詞（census_built 等）來自 controller2 的
  run-scoped 黑板；感知述詞每 tick 從畫面重讀。不需要 AgentLoop 的
  memory-latch 機制。
- **fail loud**：`PlanNotFound`／replan 上限／巨集動作內部的
  `SurveyIncomplete` → 誠實中止＋當下 state dump＋原生 diag 存幀。
  GOAP 不吞錯、不變成瞎試迴圈；「連續兩輪停問使用者」紀律不變。
- `goap/` 泛用機制零改動（`Value` 已含 `str`、WorldState 支援動態
  key，`"unknown"` 與 `unit:<cid>` 都不需要新機制；goal 的動態條件用
  `Goal` 子類覆寫 `is_satisfied`/`heuristic`）。

## 狀態詞彙

| 述詞 | 值域 | 來源 |
|---|---|---|
| `view` | hub / unit_move / weapon_select / settings / … / unknown | `map_view.classify_frame`（本輪擴充案例＋fixture） |
| `unit_list` | expanded / collapsed / unknown | `vision.unit_list_state`（批8 已落地，直接消費） |
| `grid` | on / off / unknown | lattice 探針；被蓋住／讀不到時誠實 unknown |
| `zoom` | max / not_max / unknown | 格線 pitch 推導；格線 off 時 unknown |
| `obstruction` | none / modal / selection_residue / dimmed / unknown | 既有偵測器（`is_unit_detail_modal`、R1.7 `enemy_selection_active`；dimmed 需 fixture 佐證，無證據先標缺樣） |
| `stage_def_loaded` / `stage_def_valid` | bool | 黑板（LoadStageDef／Validate 寫入） |
| `census_built` | bool | 黑板 |
| `unit:<cid>` | unresolved / resolved / dropped | 黑板；census 完成後動態展開，每台候選一鍵 |
| `sim_synced` / `def_saved` | bool | 黑板 |

感知一律吃 `frame` 參數、可離線 fixture 驗證（2026-07-21 操作/辨識
分離定案）。無 fixture 證據的新探針不猜閾值——標 unknown-capable＋
記入缺樣清單（「沒有新截圖證據不動閾值」紅線）。

## tick 語意（**2026-07-24 使用者定案：扁平 persistent-queue，規劃／
執行／判斷三者解耦，禁止巢狀 plan-execute 迴圈**）

**設計紅線（結構層，非行為層）**：`run()` 是**單層** while 迴圈；規劃
是「queue 空了才補貨」的事件、不是迴圈層級的每圈動作；action queue
**跨 tick 存活**；每個 tick 恰好一次截圖、一個判斷入口、執行 queue
的一步。這是本層的價值主張——宣告式動作＋規劃器解耦，不是把寫死
順序包成 A* 儀式再塞回巢狀執行迴圈（Round 2.0 首版做成 AgentLoop
式雙層巢狀＝退化成 controller 1 的 router，已定調重塑）。

單層迴圈骨架（語意權威，實作照此結構）：

```
queue = []          # 剩餘計畫，跨 tick 存活
pending = None      # 上一 tick 執行、待本 tick 感知確認的動作＋當時 deps／state／ok

while replans <= max_replans:
    keyguard 前置
    frame, state = 感知()          # 每 tick 恰好一次截圖
    log flow_tick(state)

    # ── 單一判斷入口 ──
    if goal 滿足(state): return True
    if pending: 判斷(pending, state)   # 見下：effect 成立／無害 diff → 保留 queue；
                                       #       打中依賴／卡住 → 清空 queue（→ 下方自然 replan）；
                                       #       達失敗上限 → fail loud return False
    if view=unknown 且非可清障礙:
        清空 queue；有界等待＋節流 diag；超時 fail loud；continue

    # ── 規劃＝補貨事件（queue 空才觸發）──
    if not queue:
        queue = plan(state, goal, actions)   # PlanNotFound → fail loud＋state dump
        replans += 1; log flow_plan(queue)

    # ── 執行 queue 一步 ──
    action = queue.pop(0)
    deps = 剩餘 queue（＋goal）依賴的 keys
    execute(action); sleep(settle)
    pending = (action, deps, state, ok)      # 下一 tick 感知後才判斷
```

判斷（pending 對本 tick 新 state）——與 Round 2.0 分流規則逐條等價，
只是移到單一入口、對 queue 動作而非對巢狀 for 的 break/continue：

- `ok` 且 effect 成立 → 確認，失敗計數歸零，**保留 queue**。
- 非預期變化（diff 非空）→ ledger 記 `unplanned_transition`（from／
  to／上一動作／diff keys），失敗計數歸零；diff 只碰剩餘 queue 不
  依賴的 keys → **保留 queue**（續走），否則 **清空 queue**（replan）。
- 零變化 → 失敗計數＋1，達 `max_consecutive_failures` → fail loud；
  否則 **清空 queue**（replan）。
- `view=unknown` → 有界等待＋原生 diag 存幀（節流），超時誠實中止。
- `PlanNotFound` → 中止＋state dump（「沒準備的情況」的明確訊號）。

與 Round 2.0 巢狀版的**刻意差異**（重塑輪逐項記錄，皆為改善或中性）：

1. 每 tick 單次截圖——巢狀版 replan（inner break）時外圈會再截一次，
   扁平版天然無雙截。
2. keyguard／unknown 檢查／`flow_tick` 現在**每步**發生（單一判斷
   入口），巢狀版只在每個 plan 開頭發生；扁平版能在步與步之間接住
   中途冒出的 unknown／變暗，更貼近 Round 1.11 的失敗回應精神。
   `flow_tick` 因此每 tick 一筆（觀測性更細）——計數這類事件的既有
   測試需隨語意更新並記錄。
3. 動作**呼叫順序**、`flow_plan`／`unplanned_transition`／`flow_abort`
   的**內容與觸發條件**逐條保持不變（既有 flow 測試對這些的斷言
   不得改動）。

ledger 事件：`flow_plan`（計畫全文）、`flow_tick`（state 快照）、
`unplanned_transition`、`flow_unknown`（含幀路徑）、`flow_abort`。

## 動作目錄

修復／導航（execute 重用既有 helper；只存在於 controller 方法內的
邏輯允許「抽出＋原地委派」的位元級等價搬遷，既有測試釘住）：

- `ReachHub`（`map_view.return_to_top`）
- `ClearObstruction`（`map_view.clear_obstruction`，Round 1 收斂的
  單一事實來源）
- `ClearSelectionResidue`（R1.7 空地 tap 解除鏈）
- `ExpandUnitList`／`CollapseUnitList`（`map_view.collapse_unit_list`
  一系）
- `EnableGrid`／`DisableGrid`（`battle_settings.set_battle_grid`）
- `ZoomToMax`（既有 pinch-verify helper）

巨集／內容動作：

- `LoadStageDef`：無裝置操作；effect `stage_def_loaded`。
- `RunCoverageScan`：`CoverageScanSource.collect()` **原樣整顆包**
  （八輪戰果、內部回復協定零改動）。pre：view=hub、obstruction=none、
  unit_list=collapsed、grid=on、zoom=max；effect：census_built＋
  展開 `unit:<cid>` 述詞。
- `ValidateAgainstDef`（**2026-07-24 稍晚讀碼修正：非純計算**）：包
  `scout_intel.validate_stage` 原樣——幾何 census（免費）＋抽樣
  spot-tap 讀摘要卡（**會操作裝置**），只比敵方佈局（deploy_slots＝
  出擊格永不 cache 的既有 schema-3 決定）。pre 含乾淨畫面述詞；新
  呼叫點把 R1.5 classify/escape 閘門接進其 `_read_summary_at`
  （參數本來就收、現行呼叫端沒接；scout_intel 零改動、舊線行為
  不變）。不符 → `stage_def_valid=False` → replan 自然落到 cold
  路徑（「不符整關過期退回現場全讀」紅線）。逐台部分重用 cache 是
  逐單位化的未來收益，v1 不做。
- `SurveyUnit(c)`（逐台，per-candidate 實例由 census 生成）：
  execute＝bring_to_view → identify（R1.5 閘門＋R1.9 複驗原樣）→
  面板讀取 → escape 回 hub。pre：view=hub、obstruction=none、
  census_built；effect：`unit:<c>`=resolved（幽靈依 R1.9 證據
  drop）。
- `SyncSim`：彙整黑板 → sim 落地（走 content/grounding 既有管線）；
  pre：全部 `unit:<c>` 非 unresolved，或 warm 路徑 validated。
- `SaveStageDef`：定義檔匯出＋醒目 log（讓人知道有這份資料）。

goal `SyncInitialMap`：`Goal` 子類；is_satisfied＝`sim_synced` 且
（warm：`stage_def_valid`；cold：全候選 resolved＋`def_saved`）；
heuristic＝未竟進度計數。warm/cold 由 A* 成本自然分岔，不寫 if。

## 分輪（委派迴圈慣例；基準 883 passed／3 xfailed 只增不減＋ruff 綠）

### Round 2.0：flow kernel（opus worktree，純離線）

範圍：`src/ggge_ai/battle/flow/`（`vocabulary.py` translator、
`actions.py` 修復／導航動作、`controller2.py` tick 迴圈與 ledger
事件）；`classify_frame`／探針案例與 fixture 擴充（像素級探針用
PNG）；巨集與逐單位動作**不在本輪**。

測試（fake perception/actuator，沿用既有慣例）：happy path（乾淨
hub 冷態 → 計畫順序與現行 `_scout` 前置一致，斷言 helper 呼叫序）、
modal 注入 → replan 經 ClearObstruction、殘留注入、unknown 有界等待
→ 中止＋存證、PlanNotFound 誠實中止、unplanned_transition 續走／
replan 分流規則單元測試、三值 unknown 永不當已知答案。

紅線：`controller.py` 行為零改動（抽出＋委派須位元級等價）、
`goap/` 零改動、scan／survey 內部零改動、無新截圖證據不動任何閾值。

**Round 2.0 已合併（`ca99e89`）但 `run()` 做成 AgentLoop 式雙層巢狀
（外圈規劃／內圈執行）——退化成 controller 1 的 router、違反本層
「規劃／執行解耦」的價值主張，使用者複核駁回，插入 Round 2.05 重塑。**

### Round 2.05：`run()` 扁平化重塑（opus worktree，純離線）

**唯一範圍**：把 `controller2.py` 的 `run()` 從雙層巢狀改成上節
「tick 語意」的**單層 persistent-queue** 骨架——規劃＝queue 補貨
事件、queue 跨 tick 存活、單一判斷入口、每 tick 一步一截圖。分流
規則（effect 成立／無害 diff 續走／打中依賴或卡住 replan／unknown
等待／PlanNotFound dump）與所有 `flow_*` 事件的**內容與觸發條件
逐條等價**；只有結構從巢狀變扁平。

- **只動 `run()`（與必要的私有 helper 如 `_plan_deps`／`_judge`
  抽取）**；`vocabulary.py`／`actions.py`／`map_view.py`／`goap/`
  零改動。
- 既有 flow 測試中對**動作呼叫順序、`flow_plan`／
  `unplanned_transition`／`flow_abort` 內容與觸發**的斷言全綠不改；
  對 `flow_tick`／keyguard **計數**的斷言若因單一判斷入口而位移，
  逐條更新並在 commit 訊息記錄理由（上節「刻意差異」1-3）。
- 結構驗收（**杜絕再漂**）：`run()` 內不得有第二層 `for`／`while`
  在同一次規劃結果上逐步執行；`plan()` 呼叫點只能在 `if not queue`
  分支內；queue 與 pending 是跨 tick 存活的迴圈外變數。
- 基準 925 passed／4 skipped／3 xfailed 只增不減＋ruff 綠。

### Round 2.1：巨集＋逐單位動作＋goal（opus worktree，純離線）

**前置**：Round 2.05 已合併（`run()` 已是扁平 queue 形狀），本輪
在其上擴充動作目錄與 goal，不再碰 `run()` 骨架。

範圍：`LoadStageDef`／`RunCoverageScan`／`ValidateAgainstDef`／
`SurveyUnit(c)`／`SyncSim`／`SaveStageDef`＋`SyncInitialMap` goal＋
`scripts/run_sync_map.py`（獨立驗證腳本，2026-07-21 定案慣例）。
`survey_stage` 外層編排被逐單位動作取代時，單台機制函式簽名不變、
既有測試不動；warm／cold／validate 失效三分支 fake-world 測試。

**2026-07-24 稍晚前置讀碼發現（2.1 dev-plan 必須處理）**：

- `survey_stage` 迴圈有跨單位共享狀態：`claimed` 格（重複格 ghost
  drop）與 `ally_world`（隨辨識到的我方增長，`ghost_of_ally` 判決
  因此**順序相依**）。逐單位化必須把它們收進黑板上的共享
  SurveyContext；v1 動作 cost 以 census 序當 tie-break，維持與現行
  走訪順序等價——planner 重排是之後的自由度，不是第一版目標。
- 單台判決鏈（identify 失敗→diag→ghost_of_ally 優先→無峰 drop→
  snap 一次→仍無 banner fail loud；`survey_stage` ~425-475）目前
  內嵌在迴圈裡：抽成模組級 per-candidate 函式＋`survey_stage` 原地
  委派（位元級等價、既有測試釘住），`SurveyUnit(c)` 與舊線共用
  同一份，不複製貼上。
- 全程 wall-clock（`SURVEY_WALL_CLOCK_S`）在逐單位化後改由
  controller2 的 run 預算承接；語意不變（超時誠實中止、部分定義檔
  永不落地——`SaveStageDef` 的 pre 就是全候選 resolved）。
- `SyncSim` 走既有 content 管線（`ground_unit` 假設回報鏈、
  `stage_sim` 定義檔直建），不新增公式。

### Round 2.2：實機 probe（sonnet，主工作目錄）

1. 冷跑：現況 EX-2 IF TURN 1 hub、`data/cache/stages/` 空——
   `run_sync_map.py` 應走 cold 路徑到定義檔匯出＋sim synced＋雙 log。
2. 還原 `stages.bak-20260723/` 再跑暖路徑，驗 ValidateAgainstDef。
3. 觀察重點：意外畫面時的 `unplanned_transition`／`flow_unknown`
   事件是否如實記錄（可觀測性驗收）。
4. 戰鬥前 discord-notify；結果回寫 roadmap 與
   live-verification-queue。**probe 優先於輪十三**（使用者定案 8）。

## 風險與邊界

- 逐單位 GOAP 化重排 survey 外層編排：以「單台機制原樣、僅編排搬家」
  控險；等價風險集中在 Round 2.1 的編排層測試。
- 無 router 的代價：初期詞彙外畫面會較常誠實中止而非硬繞——這是
  刻意的（每次中止帶存證，餵下一輪詞彙擴充；定案 4 的精神）。
- controller2 與舊 controller 並存期間，共用 helper 的任何修改都同時
  影響兩線——本規格各輪都禁止改 helper 行為，只准重用與等價搬遷。
- 輪十三延後：R1.9~1.12 首戰證據晚到；若 probe 期間掃描主體再敗，
  敗因可能與舊線待驗修復重疊，屆時證據要分清是哪一層的。
