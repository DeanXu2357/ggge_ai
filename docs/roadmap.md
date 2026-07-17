# 進度與規劃

更新日期：2026-07-17（工程重構批次見下段；最新里程碑＝07-15
**S9d 應戰路徑整併落地**：確認應戰彈窗＝戰鬥準備
-應戰- 變體，感知單一來源化到 `BattlePrepForecast`、廢 `ReactionPopup`、
執行器 `_choose_reaction_stance` 接進 `_on_battle_prep`；行為保持、
483 tests/3 xfail 全綠、replay 閘門同基準。stance 切換 UI 仍待實機標定。
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

## 暫停快照（2026-07-15 S9d 應戰整併，恢復點）

**裝置現況**：本 session 前半 USB 連上（`R5CRC37JBYJ device`）做了回應探測
——螢幕 Awake、無凍機，遊戲停在主畫面（RANK 21、體力 101/106、STAGE 18）。
**後半要跑實機探測時 adb 掉權限**：`no permissions`——seat0 目前是
`gdm-greeter`（桌面退回登入畫面、idle 1h+），poyu 不在 active seat →
USB uaccess ACL 沒給 poyu（見 [[adb-permissions-seat0]]）。sudo 要密碼
（無免密）、手機無線偵錯已關（5555 拒連），使用者外出無法實體接觸→
**live S9d 探測擋住,等桌面登入或手機開無線偵錯**。凍機硬體檢查
（memtest86+/BIOS）仍最優先。

**恢復點（回到桌面後）**：① `loginctl` 確認 poyu 在 seat0 active（實體登入
桌面即可，必要時重插 USB）→ `adb devices` 應回 `device`。② 探測法已備妥
（子類 `ManualBattleController`、override `_on_battle_prep`：`is_reaction`
時存幀＋raise 停住，把遊戲泊在 -應戰- 畫面不確認；greedy 驅動、entry 用
flow actions 從主畫面 nav_stage 1230,1050 進關）。③ 泊住後手動點候選
stance 切換入口（機頭動作圖示 ~1120,420 或底部 ☰ ~702,921），subagent
判讀每步→標 `REACTION_OPTION_TAPS`＋vision 讀 `available_stances`。

**S9d 進度（本 session）**：
- **關鍵釐清**：應戰決策（#3）在本作不是獨立彈窗，而是敵攻我方時的
  「戰鬥準備 -應戰-」畫面（match `label_battle_prep` 0.948）。所以它走
  `_on_battle_prep`（ACTIONABLE），S8 建在 `_on_not_actionable` 的
  `read_reaction_popup` 路徑永遠到不了＝放錯位置。
- **碼面整併（行為保持，2c2… 見 git）**：感知留 vision 層——`ReactionPopup`
  是 `BattlePrepForecast(is_reaction)` 的重複抽象，已廢除；stance 感知改為
  `BattlePrepForecast.available_stances` stub（同 `support_defense`，未標定
  回 None）。執行器 `_choose_reaction_stance`（純編排：ground→advise_reaction
  →tap stance→拋錯）接進 `_on_battle_prep` 的 is_reaction 分支，`available_stances`
  為 None 時 no-op、落回既有「按開始戰鬥接受預設」＝零行為改變。
- **stance UI 未知數（留給實機）**：2026-07-11 全螢幕捕捉（`assets/screenshots/
  20260711-223704.png`，貝爾汀格攻 GQuuuuuuX、KILL 局）經 subagent 判讀，
  畫面**未見明確的防禦方式切換按鈕**；當前選定 stance 顯示為「閃避」（非
  screen-map 說的預設反擊）、反擊傷害 0。可能切換入口＝我機頭頂動作小圖示
  (~1120,420) 或底部 ☰ 清單鈕 (~702,921)，只能實機點擊驗證。→ S9d-live 要
  標定 `REACTION_OPTION_TAPS`（DefenseKind→tap，controller.py:37 空表待填）
  ＋ vision 讀 `available_stances`/`support_defense`。

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
