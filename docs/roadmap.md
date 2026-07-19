# 進度與規劃

更新日期：2026-07-19（最新里程碑＝**07-19 晚 S9d 應戰 UI 辨識落地**（見暫停
快照）；tick 收攏見 07-19 段；router middleware 見 07-18 段；工程重構批次見
07-17 段；前一里程碑＝07-15 **S9d 應戰路徑整併落地**：確認應戰彈窗＝戰鬥準備
-應戰- 變體，感知單一來源化到 `BattlePrepForecast`、廢 `ReactionPopup`、
執行器 `_choose_reaction_stance` 接進 `_on_battle_prep`。
前情：S 批次離線段 S0-S8 全落地）

**2026-07-17 離線工程重構（行為不變、非里程碑）**：`ManualBattleController.run()`
兩項結構整理——① 每圈單次截圖：中斷偵測器（終局/敗北/隱藏關/modal/劇情）
共用一張 frame，相位/對話框兩讀複用為第一讀、第二讀才重截（防抖不變），
約 8→2 adb 截圖/idle tick，正對凍機嫌疑的截圖 I/O；`perception.observe/probe`
加選參 `frame=`，預設 None 照舊自截（flow.py/AgentLoop 不受影響）。② 中斷
cascade（一串 `if vision.is_*()`）收成優先序偵測表 router（`_route_interrupts`
＋`LoopStep`），相位 ACTIONABLE/NOT_ACTIONABLE 分支維持明確 fall-through。
483 tests/3 xfail、ruff 全綠；commit 13e336f。③ **sim 子套件抽取**
（a51a2b1）：純機制引擎 `sim.py→sim/core.py`＋`solver/formulas/enemy_model/
grid` 移入 `battle/sim/`（相依驗證：只 import `..state`/`..actions`+stdlib，
不碰 perception/vision/controller），`__init__` re-export 保舊路徑；
`bridge/objectives/stage_sim/advisor` 留 battle/ 當 adapter/client 層。
④ **SimAdvisor 介面型態**（b462c03）：controller 對 sim 的操作面收斂成
`SimAdvisor` Protocol（`advise`/`advise_reaction`），`DefaultAdvisor` 為預設
實作、以 `advisor: SimAdvisor` 欄位依賴反轉注入（可換 fake/替代 solver），
移除 `advisor_mod.*` 直呼。⑤ **邊界重構定案（使用者拍板三決策：升頂層／
刪 battle/planner.py／action 執行域留 battle）**，七小步 commit
（ca58ba9…8599f5a）落地四層單向依賴 `battle → content → planner → sim`
（全圖見 agent-architecture.md「套件分層」）：sim 升頂層＋擁有詞彙
（`sim/vocab.py` Faction/DecisionKind，battle 反向 re-export/別名）；
評估詞彙下沉 `sim/objective.py`（Objective/EvalWeights/EvalContext，
solver 不再被 objectives 編譯器穿透）；搜尋層抽 `planner/`（solver＋
enemy_model）；`content/` 資料綁定層（kit＝UnitSpec/UnitStats/WeaponRow/
SpecDefaults、grounding＝數值落地＋假設回報、stage_def（含 sig 距離）、
objectives、stage_sim 直建定義檔座標不經 BattleState）；`core/`→`goap/`
改名；死碼 battle/planner.py（plan_activation，production 零引用）連測試
刪除。行為不變、477 tests（483−6 刪除的 planner 測試）/3 xfail、ruff 全綠。
**裝置現況與 S9 恢復點不變，見下。**

**2026-07-18 router middleware（行為近似不變、非里程碑）**：controller 兩層
路由的 log 收成 middleware（使用者提案「既然走 router 就加 middleware 記部份
handler 的 log」）。① 中斷路由：`_handle_*` 改回傳宣告式意圖
（`LoopStep.log=(kind, extras)`／`finish=outcome`），`_dispatch_interrupt`
統一補共用幀＋執行，handler 不再直接碰 ledger；格式一致、沒 handler 能默默
漏記——`end_turn` 以前整段沒進 ledger，現自動補上。② 相位路由：抽
`_dispatch_phase`，正常結束記一筆信封 `phase`（名字＋`outcome=ok`＋
`elapsed_ms`），domain log 仍留 `_on_*` 內；兩個終止例外（PilotAbort／
SurveyIncomplete）沿用原記錄並轉 `LoopStep(done=True)` 走同一離場接縫。
純機制、流水帳只供工程分析不當先驗故改格式安全。484 tests（+7 middleware）
/3 xfail、ruff 全綠；文件見 battle-phase-states.md「路由與 middleware」。
**裝置現況與 S9 恢復點不變，見下。**

**2026-07-19 tick 收攏（行為不變、非里程碑）**：`run()` 的兩段路由（中斷
pipeline＋裸露的相位分支）收成單一「分類→分派」接縫，tick 主體＝截圖→
`_classify`→`_dispatch` 三行。討論定調：覆蓋層是 **interrupt**（每 tick 邊界
採樣的非同步外部事件）不是 exception——phase 層無法靠「失敗」發現它們
（模板穿透變暗覆蓋層會自信誤讀、無 label 又與動畫無法區分），z-order 掃描
是 label 可信的前置條件；「報錯重判」通道維持在既有 expectation 機制當
備援。實作：① `_overlay_pipeline` 一張 `(state, detect, handle)` 表，掃描
順序與配對不漂移；② `_classify` 回傳扁平 state（覆蓋層／去前綴相位／
`not_actionable`），label 簿記（`_log_state`／`_check_expectation`／
`_judge_pending`）隨 mode 讀取走，覆蓋層 tick 不燒 expectation 預算；
③ `_dispatch` 依 state 選 middleware，`LoopStep` 增 `activity` 欄餵 idle
看門狗（neutral tap 不算進展的語意上移）；④ `_dispatch_phase` 改收去前綴
phase 名。行為等價（偵測順序、短路成本、per-tick 截圖副作用、terminal
出口全保留）；491 tests（+7 classify/dispatch）/3 xfail、ruff 全綠；文件
battle-phase-states.md「分類與分派」。**裝置現況與 S9 恢復點不變，見下。**

**2026-07-19（續）BattleTimeline 三批次（行為不變、非里程碑）**：controller
的「時間記憶」拆進新物件 `battle/timeline.py`（純狀態、不截圖不點擊；與管
空間的 BoardTracker 分工），使用者定調「handler 只看當下畫面、跨 tick 記憶
歸注入物件」。① act→verify 契約搬入：UI 流程圖集中成 `TRANSITIONS` 表，
handler 改報 `acted("attack")`，`_classify` 每 tick 餵 `observe(phase)` 並執行
回傳 ledger intent，`_dispatched_mode` 廢除（來源＝畫面最後確認的 phase）；
ledger 期望事件改記去前綴相位名（流水帳僅工程分析，格式安全）。② turn
偵測搬入 `on_turn_read`（OCR 跳號防呆＋marker fallback，turn 權威 1-based
對齊 ledger/tracker），六個散裝旗標（scouted/advised/sig_refreshed/resynced/
intel_done/full_scan_done）收成 `due()`/`mark_*` 工作閘門（turn scope 翻頁
自動重上膛）。③ `_ActionState`→`timeline.activation`，被吞回滾從 on_eaten
lambda 內化成表上 `repair` 欄，`ends_activation` 取代散落的 reset。timeline
只記帳回報 divergence 永不否決分派（畫面權威紅線）；④⑤（使用者批准的
行為變更，落地順序抑制先行避免過渡態亂 nudge）：not_actionable 在契約
開啟時安靜等（不累 miss、不 nudge、不燒 LLM；垂死對話游標照答，敵方
回合無契約保留 keep-alive tap），然後刪除 `_wait_animation` 45 秒阻塞
——確認開戰後短 settle 即 return，動畫由主迴圈 NOT_ACTIONABLE tick
消化、終局由每 tick 的覆蓋層掃描接住（舊兩出口都是迴圈原生功能），
`settle_timeout_s`／`frame_diff` 依賴一併移除，全系統只剩一個迴圈
（測試套件 130s→100s，reconcile_wiring 不再空轉即為切除證據）。
503 tests/3 xfail、ruff 全綠；文件 battle-phase-states.md「期望轉移驗證」。
**裝置現況與 S9 恢復點不變，見下。**

## 暫停快照（2026-07-19 晚 S9d 應戰 UI 辨識落地，恢復點）

**S9d 辨識落地（2026-07-19 晚，純離線、未碰實機）**：照 `docs/battle-prep-ui.md`
§9 vision 清單全數接進程式，20 張 20260719 PNG fixture 離線驗證：
- `vision.read_reaction_stance_menu`：dodge 圖示定錨（**像素證據推翻「錨點隨武器
  數右移」——動作列是固定槽位格**，dodge (1540,940)、defend (1352,940)、武器往左
  pitch 187）、defend/shield 靠鈕圖示互斥判別（裁片相關 −0.12）、EN 黃字定武器槽
  佔用、鈕心 V≥120 判可用（**開放假設：SHORT 無確認可用樣本，V 閘門可能誤殺深色
  可用圖示，S10 實戰驗證**）。回傳 stance→tap（`ReactionStanceMenu`）。
- `read_battle_prep_forecast`：`hit_pct` 改頭像列掃描 `read_avatar_hits`（列置中
  x≈963、pitch 200、pct 白字左緣＝頭像圓心 x、專用 `hit` 字型**缺 '3'**；應戰取
  紅環、攻擊取最右藍環）；`support_defense` 標籤模板（-應戰- bool／-攻擊- None）。
- OCR 三修：hud `6_c` 修 14168→14188；中央攻/反 48px 大字是另一字體、hud 字模把
  8/9/5 誤讀成 6（163188→163168 等四例，subagent 逐位轉錄裁決）→ 專用 `attack`
  字型；hit% 字體 hud 讀不動（'0'→'1'）→ 專用 `hit` 字型。
- 標定連帶抓到 `tracker.on_battle_prep` 陣營映射 bug：舊碼假設 -攻擊- 時左面板
  是我方，實測**左面板永遠是敵方**（右我左敵、兩變體皆然）→ 改為固定映射
  （-攻擊- prep 的信念更新原本左右反貼）。
- 15 個新 fixture JSON（7 forecast 全欄位＋4 stance 選單＋4 拒讀負樣本）；
  521 tests/3 xfail、ruff 全綠。**controller/sim 未動**。

**裝置現況**：前段 session USB 全程在線健康（`R5CRC37JBYJ device`、Awake、**無凍機**，
遊戲 RANK 23、體力 95/108）。使用者選「直接跑實機」（接受凍機風險，未先做
memtest86+/platform-tools）並授權主對話直接讀圖（破 screenshot-cost-discipline、
該 session 限定，**辨識落地 session 未沿用**——目視標定/轉錄一律走 subagent）。
手機省電觸控鎖曾因對話中閒置逾時觸發一次、使用者手動解，
Keyguard 本可處理（見 [[stage-clear-loop-status]]「battery-saver touch lock」）。

**S9d 標定成果（2026-07-19 白天 session）**：應戰 stance UI 已實機標定完成。
- 產出：`docs/battle-prep-ui.md`（正式地圖）＋`tests/fixtures/vision/forecast/`
  10 張 PNG fixture＋`reaction_live_20260719.md`（逐步記錄）＋2 memory
  （[[battle-prep-ui-map]]、[[forecast-lowerbound-enemy-defense-ai]]）。
- 標定：陣營右我左敵（攻擊/應戰皆然）、is_reaction＝標題、stance 相對定位錨點策略
  （閃避最右錨/防禦次右/counter 武器往左 pitch≈170、亮度 V 分辨可用）、defend 減傷20%
  ／dodge 敵命中-20%（效果卡＋forecast delta 驗證）、命中率＝頭像上方、攻擊順序＝
  頭像①②③（動態）、支援攻擊/支援反擊順序。
- 機制知識（sim/solver 建模需求）：forecast 傷害＝保守下界（KILL 才確定擊殺、
  無 KILL≠打不死）、敵方 AI 反擊會死就防禦保命、賭暴擊/降防欺敵；「①殺主單位→
  反擊階段全取消（含支援反擊）」sim 已建模（core.py:873），此塊無需改。

**恢復點**：① vision 辨識已落地（見上），下一步＝`docs/battle-prep-ui.md` §9
剩餘兩塊：**controller 接線**（`_choose_reaction_stance` 改消費
`read_reaction_stance_menu`：點我方頭像→讀選單→點 stance→行動選擇→開始戰鬥，
廢固定 `REACTION_OPTION_TAPS` 表；需實機驗證）與 **sim/solver**（forecast 保守
下界、敵方防禦保命 enemy_model、欺敵博弈、support_defend 互斥枚舉修正、先攻
queue）。② 實戰驗證開放假設：SHORT 可用性 V 閘門、hit 字型缺 '3'。
③ adb 上次 session 在線健康；純程式任務照舊免連線。

**還差的截圖情境（待使用者實機截圖）**：
1. ~~`support_defense` 畫面~~ **已於 2026-07-19 取得**（reaction_support_defense_20260719.png，
   盾圖示「支援防禦」標籤＝標定依據）。
2. ~~應戰多武裝機體選單~~ **已取得**（reaction_shield_menu：F91 5 武器、pitch~170、
   錨點隨武器數移動→須模板定位錨點）。
3. ~~`shield` 選項~~ **已取得**（reaction_shield_menu：有盾機體防禦鈕＝shield 減40%＝
   SHIELD_MULTIPLIER 0.6、非獨立選項；修正先前 defend/shield 判斷）。
4.（可選）敵方 AI 保命實例（選目標顯 KILL→進戰鬥準備敵改防禦、KILL 消失）、
   暴擊武裝 forecast 下界顯示、技能發動後流程。

**規劃定稿**：stage-definition＋uid 身分制＋M8 雙行為 observer 合併為
**S0-S10 批次**（計畫全文 `~/.claude/plans/nifty-forging-sonnet.md`；
需求 docs/stage-definition-requirements.md）。使用者三個修正定調：
①hub 誤判歸根究底是 observer 元件缺陷→**S0 元件除錯先行**，
「敵人存不存在由定義檔決定」的補償性設計拿掉（定義檔只當 turn-1
開局先驗與身分描述）；②**弧色只當第一層啟發式**，我方可控單位權威=
hub 下方可操作單位卡條；③指定截圖當 observer 端到端實測案例
（observer_board fixture 機制）。舊 Stage B/C 收編 S9/S10（B0 作廢）；
執行節奏=S1 完成後停下給使用者過目 schema。

**S0 成果（413 測試/3 xfail、ruff 綠、replay 閘門與基準一致）**：

1. **d32430f observe 證據分層**：poisoned 掃描上無敵方 sig 對位的
   紅帶弧，先對位 tracker ally 信念（卡條驅動的 activation 錨定鏈）
   →回收為未行動我方；對不上才丟棄。敵方 sig 優先權、乾淨掃描路徑
   不變。
2. **3676323 vision.count_unit_cards**：卡底藍 HP 條計數（pitch
   175px；藍條寬=剩餘 HP 比例，實測 92/66/18px 受傷條，12px 下限；
   亮度剖面會被亮地形淹沒不可用；卡條實延伸至 x≈1949，舊 900px box
   只見 5 張）。select_unit ledger 事件帶 cards 欄位；`_build_board`
   缺額 note（cards>盤面我方＝未來 M8-① resync 觸發訊號）；replay
   增 cards 對比；4 張 PNG fixture（7/6/10/0，subagent 目視 ground
   truth）＋合成測試釘閘門。
3. **ec72087 observer_board check**：真實截圖＋標注先驗（tracker
   信念/intel 位置）→斷言解析後盤面陣營數；mixed_factions（3 粉紅
   回收＋敵恰 1）與 pink_bug（9 假敵→4 回收 0 敵）兩案例釘住修復。

**S0 判定紀錄**：弧結構差異（敵弧維持紅左＋橙右雙色調 vs 未行動我方
全寬粉紅＋黃上線，`yellow_only` 欄 32 vs 0）只有 n=1 敵樣本→僅當
啟發式不當權威；相位邊界快照離線證據足（phase_start_clean 乾淨、
位置攜帶由遊戲規則保證），捕捉時機歸 S9；卡條語義實測=未行動可操作
列表（回合起點=存活數、隨啟動遞減、擊殺再動會補卡回升→單調性僅
advisory）。

**S0 未竟（歸 S9 實機）**：自機卡/敵機卡判別（已知風險①的關閉條件）、
相位邊界快照的捕捉時機標定。

**S1-S4 已落地（461 passed/3 xfail、ruff 綠）**：S1 schema v2
（e9d4064，使用者已過目放行）；S2 條件驅動 Objective（34ddcf4——
terminal 回終局值、bounds 隨附否則 Star1 不健全、預設路徑與現行為
等值有多 seed 守衛、depth-1 斬首盤打指揮官/素設定打雜兵對照）；
S3 sim events（8d88c70——**pending_events＋fired_events 兩個 tuple
都進 key()**：within_turn 視窗會「過期不觸發」，只放 pending 會讓
已觸發/已過期在 weaken 靜態值不進 key 下碰撞；拆增援口案例=solver
先殺別隻、等視窗過期再殺標記敵）；S4 IdentityResolver（ce2855f——
seed 貪婪雙射＋refresh 互斥唯一鄰居兩套配對、sig 只當候選過濾、
passthrough 模式供 replay）。

**S5 身分翻轉已落地（fdd847f，465 passed/3 xfail、ruff 綠）**：盤面
unit_id/tracker 信念鍵/SimExpectation id/executor 目標驗證全講 uid，
sig 降純證據；controller 與 tracker 共用單一 resolver（canonical 登錄
序一致）；我方永遠走 "sig:<hex>" 降級 uid（我方身分不進定義檔）；
`target_ok` 複合驗證（預期 sig 容差＋共享 sig 時 HP 信念交叉）。
replay 閘門：reader 命中率不動、tracker 一致性同基準（33 信念/1 死）；
dead-sig advisory 變多＝舊 kill_check 精確查 key 漏登記擊殺的修正。
**殘餘風險（S10 要量測）**：同機種雙機開局同滿血→HP 交叉檢查無法
分辨雙胞胎，錯鎖對象可通過驗證直到血量分歧；緩解案（錨定目標世界
位置）留 S10 實測後定。

**S6 已落地（f021ef1，466 passed/3 xfail）**：`survey_stage` 全量
fail-loud（每台開面板無 sig 去重、pilot_hint 快照、SurveyIncomplete
不寫部分檔）＋`validate_stage`（幾何普查免費＋共享 sig 組優先抽查）；
controller `_ensure_stage_definition` 取代 `_acquire_intel_once`（溫啟
採用=seeded resolver 換入 tracker＋uid specs＋開局信念；否則冷掃；
survey_abort 與 pilot_abort 同軌）；`tacmap.locate()`＋`_bring_to_view`
pan 導航（S9b 實機驗證）；GGGE_INTEL 必附 stage_id、GGGE_PILOT 必開
INTEL；IntelBudget 與 stage_cache.py 退役。

**S7 已落地（f11cec4）**：M8-①`_board_with_resync`（expected_alive
當分母、缺敵一回合一次局部重掃；pilot 空盤先 resync 再問、仍空=
`board_empty_after_resync` abort；擊殺在破壞數判決處 `register_death`
讓分母跟著降）；M8-③ 盈餘無主紅弧（已解析敵=expected 才算，缺額歸
resync、我方缺額歸卡條，避免 tap 粉紅我方）→`stage_event_observed`
＋軟性增量 survey＋發 uid 寫回定義檔 events（保守 turn_start 觸發、
原始觀測隨檔）；M8-④ `stage_sim.to_sim_state`（layout＋增援同格網
量化、增援模板留在 EventTable 不上開局盤、conditions 編譯 objective）
＋斬首關離線解到終局 smoke。

**S8 已落地（e0eccb7）**：M8-② 離線半——`vision.ReactionPopup`＋
`read_reaction_popup`（S9d 模板落地前回 None）；`solve_reaction`
**根節點枚舉限制在彈窗實際提供的選項**（樹內防禦節點不受限；空集=
無決策）；`advise_reaction(allowed_stances, allow_support_defend)`；
controller `_maybe_handle_reaction` 在 NOT_ACTIONABLE 最優先（雙名牌
ground 到 uid 否則 `reaction_ungrounded` abort；stance 座標未標定=
`reaction_taps_uncalibrated` abort，座標表 `REACTION_OPTION_TAPS`
留給 S9d；貪婪模式只記 ledger 不動手）。**（S9d 已修正接線）**：上述
`ReactionPopup`/`read_reaction_popup`/`_maybe_handle_reaction`（NOT_ACTIONABLE
路徑）已廢——應戰＝battle_prep -應戰- 變體，感知併入 `BattlePrepForecast`、
執行器改 `_choose_reaction_stance` 接進 `_on_battle_prep`。`solve_reaction`
根節點限制與 `advise_reaction` 介面不變。

**下一步（實機段進行中）**：S9 實機標定批次（memtest86+/BIOS 凍機檢查
先行）——a) stage-info 條件樣本＋片語 parser（諮詢點）b) 冷掃全量實跑
一關（`_bring_to_view` 驗證）c) pilot 對齊探測（收編舊 B1/B2/B3，uid
語義）**d) 應戰彈窗：碼面接線已整併完成（本 session），剩 stance 切換
UI 實機標定＝`REACTION_OPTION_TAPS`＋vision 讀 `available_stances`/
`support_defense`（參考幀 20260711-223704）** e) 登場演出樣本 → S10
整合戰（驗收指標見計畫；翻預設要使用者簽核）。

## 本日稍早批次（2026-07-14 pilot 離線 M1-M7）

**裝置現況**（本批次純離線未碰實機）：遊戲停在主畫面（棄局後遇日期
變更彈窗已收）、體力 ~96、adb server 關。WiFi adb 已配對（poyu@fedora；
重連只需 `adb connect 192.168.50.28:<無線偵錯主頁port>`，port 每次重開
會變）。凍機硬體檢查（memtest86+/BIOS）仍最優先，見
system-freeze-investigation。

**本批次成果（396 測試/3 xfail、ruff 全綠；計畫全文
~/.claude/plans/cheerful-wibbling-umbrella.md）**：

1. **M1 advisor unit_id**（1e28dc0）：`advise(unit_id=...)` 重排 units
   釘根節點行動者（solver 零改動；`SimState.key()` 排序＝TT 順序不敏感
   有測試釘住）。
2. **M2 BoardTracker**（49ba7e6）：forecast/prep/破壞數/回合邊界四掛鉤
   的讀值不再用完即丟——sig-keyed 信念（HP/EN/生死/位置），process
   內活、絕不落地；`apply()` 回填盤面並把每筆攜帶值列為 assumption。
   observe 增 `hub_poisoned`（無 sig 對位的敵弧丟棄）。
3. **M3 寫回接線**（b264cbd）＋ **M5 sig 位置逐回合刷新**（158a7b8）：
   唯一鄰居零 tap 靜默更新、歧義才 tap（預算 6 tap/25s），修掉
   turn-1 凍結位置的身分衰減。
4. **M6 pilot**（7b984f0）：`GGGE_PILOT=1` 時 solver 驅動每次啟動
   （executor.py 純原語：anchor 辨識選中機→單機建議→移動格吸附→
   武器槽→切目標驗證）。失敗分類照使用者定案：無意見類退貪婪記
   `pilot_fallback`；對齊失敗類 `pilot_abort` 直接結束整場留現場。
   我方單位可掛 sig（隨行動增量學習）。run_manual_battle.py 旗標
   與 flow.py 對齊（GGGE_INTEL/ADVISOR/PILOT/STAGE_ID）。
5. **M7 advise_reaction**（e4a3a83）：應戰彈窗由 solver 決定（使用者
   定案，不用靜態預設）——重用 `_our_defense_node` 當根的迭代加深；
   攻擊者無 spec→None→abort。執行端偵測仍缺（#3 實機標定）。
6. **sig 抖動正規化**（099626f）：實戰語料證明同一單位 sig 跨面板
   漂移 3-5 bits——tracker/target_ok/refresh 全部改走
   `signature_distance` 容差 6；位置型目標（無 sig 可驗）降無意見。
7. **M4 HSV 判決＝不可分**（b395319）：417 張截圖三角測量＋subagent
   目視 ground truth——決定性幀 `our_turn_hub_mixed_factions`（同幀
   混編：粉紅我方 H7-8/S135/V202 vs 真敵紅 H8/S136/V204，統計完全
   重疊；人眼差異在血條黑缺損段與黃內線）。兩張新 strict-xfail PNG
   fixture 入庫；**逐像素色彩路線正式關閉，不再迭代閾值**。
   `scripts/replay_frames.py`：run 幀重播 harness（observer 改動的
   回歸閘門；基準：JPEG 幀 sig 欄位劣化最重；tracker 重播顯示實機
   sig 抖動會鏈式超出容差——6 機編成出 17 個我方信念，驗證局要盯）。
8. **M4 諮詢定案落地**（b587fe2）：`_build_board` 常態 `hub_poisoned=
   True`（盤面只收 sig 確認敵）；intel 預算動態跟隨敵機種類數（上限
   12、每面板 ~15s），顯式預算維持固定供測試。

（本批次尾聲的 M8 雙行為 observer 定案與 7/14 晚關卡定義檔定案，
已全部併入上方 S 批次計畫與 docs/stage-definition-requirements.md。）

**已知風險（實機驗證要盯，S9 對應）**：① intel 掃描會 tap 到粉紅
我方弧——tap 自己單位可能開自機摘要卡（讀進敵方 intel＝污染）或
選中單位，7/13 實戰沒炸但未系統驗證（S9 自機卡判別關閉此風險）；
② 實機 sig 抖動鏈式漂移（見上）；③ anchor 單解錯位風險（fail-fast
會抓後果）。

## 歷史

舊暫停快照（2026-07-08 ～ 07-14 凌晨）、初期計畫、已完成清單、
戰鬥控制器 v2 改進項目等歷史內容已全部移至 [archive.md](archive.md)
——除了了解歷史脈絡,開發時不需要讀。
