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

## tick 語意

每 tick：keyguard 前置 → 單次截圖 → translator（frame＋probe＋黑板→
WorldState）→ goal 檢查 → A* 規劃 → **只執行計畫第一步** → 重感知。
搜尋空間極小，每 tick 重規劃成本可忽略，v1 採最保守形態。

- 預期 effect 成立 → 續。
- 非預期變化 → ledger 記 `unplanned_transition`（from／to／上一動作／
  diff keys）；diff 只碰剩餘計畫不依賴的 keys → 續走，否則 replan。
- 零變化 → 失敗計數，有界（沿用 LoopConfig 形態）後 fail loud。
- `view=unknown` → 有界等待＋原生 diag 存幀（節流），超時誠實中止。
- `PlanNotFound` → 中止＋state dump（「沒準備的情況」的明確訊號）。

ledger 新事件：`flow_plan`（計畫全文）、`flow_tick`（state 快照）、
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
- `ValidateAgainstDef`：純計算；只比敵方佈局（deploy_slots＝出擊格
  永不 cache 的既有 schema-3 決定）。不符 → `stage_def_valid=False`
  → replan 自然落到 cold 路徑（「不符整關過期退回現場全讀」紅線）。
  逐台部分重用 cache 是逐單位化的未來收益，v1 不做。
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

### Round 2.1：巨集＋逐單位動作＋goal（opus worktree，純離線）

範圍：`LoadStageDef`／`RunCoverageScan`／`ValidateAgainstDef`／
`SurveyUnit(c)`／`SyncSim`／`SaveStageDef`＋`SyncInitialMap` goal＋
`scripts/run_sync_map.py`（獨立驗證腳本，2026-07-21 定案慣例）。
`survey_stage` 外層編排被逐單位動作取代時，單台機制函式簽名不變、
既有測試不動；warm／cold／validate 失效三分支 fake-world 測試。

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
