# 進度與規劃

更新日期：2026-07-13 晚（**模擬器交戰結算順序對齊實機**：使用者三個
實測案例定案支援防禦承受制與「擊殺主目標消音回擊」；solver 開始為
我方攻擊定價敵方反擊與支援火力）

## 暫停快照（2026-07-13 晚，恢復點）

**裝置現況**：與稍早快照相同——本日未碰實機，手機停在鋼彈X 選關畫面
（HARD 1 已通關），adb server 關、tmux 清。

**本批次成果（commit 4d45691，315 測試/1 xfail、ruff 全綠）**：使用者
提供三個實機觀測案例（M 攻 A，A 有支援防禦 B／支援攻擊 C 的三種結局），
據此把模擬器的交戰結算順序改成與實機一致（全文入檔
docs/combat-formulas.md「交戰結算順序」節）：

1. **支援防禦承受制**：B 代替 A 承受 M 的一擊（傷害以 B 的數值計算、
   B 可被擊破），取代舊的「A 打折受傷」近似；B 陣亡不取消任何後續。
2. **反擊階段只看主目標存活**：A 活著 → A 應戰＋C 支援攻擊都打 M；
   A 被擊殺 → 反擊階段整個取消（含 C 的支援攻擊），M 無傷——「先殺
   A 消音全部回擊」正式成為搜尋樹可利用的戰術（有 solver 測試釘住）。
3. **DefenseResponse 拆軸**（stance × support_defend × support_attack，
   攔截與應戰不再互斥）、支援次數拆防禦/攻擊兩池（bridge 把
   SUPPORT_ATTACK 能力接上新池）、Decision 增 support_hit 機率分支。
4. **solver 我方攻擊不再免費**：EnemyModel 新增 reactions()——policy
   基線＝應戰＋一律攔截（step 對不合格部分自動退化 no-op）、min＝
   攔截與否×五種 stance 全枚舉（案例 2 證明觸發條件未知，不瞎猜規
   則）；我方防禦 max 節點在有合格支援者時加倍枚舉攔截分支。剪枝/TT
   等值性測試的隨機盤面加入雙池支援次數後仍全數等值。
5. 三案例逐字編成 tests/test_battle_sim.py 的 case1-3，另加順序邊界
   案例（反擊先殺 M 則 C 停手、無合格攔截者 fall-through 打回 A、
   擊破攔截者給再動、C 出手不看 A 的應戰選項、C 射程不足不出手）。
   未實測細節以保守假設入檔（sim.py docstring＋formulas 文件）。

**新增待實機標定項**：支援防禦觸發條件（案例 2 顯示合格支援者可能
不攔截；對帳鏈 battle_prep 塌陷紀錄是蒐證來源）、支援防禦承受方倍率
（現用 0.5 預設）。

**下一步**：沿用稍早快照的實機清單（M3b 驗證、對帳鏈實戰、蛇形掃描
計時）；對帳鏈實戰時順帶記錄「預測畫面顯示的承受者是誰」，累積支援
防禦觸發條件的實證樣本。

## 舊快照（2026-07-13 稍早，恢復點）

**裝置現況**：本日未碰實機（純離線開發），沿用 7/12 深夜狀態——手機
停在鋼彈X 選關畫面，HARD 1 已通關，adb server 已關、tmux 已清。

**本批次成果（commits 5acb129..50dddd4，305 測試/1 xfail、ruff 全綠）**，
回應使用者 7/12 的歸因需求（「內建 AI 也能通關且評價更好——我要知道
贏是演算法期望所致，還是隊伍太強隨便打都贏」）：

1. **M1 `vision/digits.py` 模板數字 OCR**：確定性、絕不亂猜（低於門檻
   回 None）。HUD 白字＋modal 深字雙字形庫（全裁自全解析度 PNG）；
   語料 15/15＋modal 24/24。關鍵規則：SQDIFF 再確認需決定性差距才准
   翻案（修 8→6、2→7 回歸）、最長連續字形串（擋表頭亮邊假 '4'）、
   斜線豁免小字形加成（半透明表頭上 '/' 只剩 0.75）。
2. **M2 遊戲預測讀取器（battle/vision.py）**：read_weapon_select_
   forecast／read_battle_prep_forecast（-應戰- 旗標、命中%）／
   read_enemy_summary／read_kill_counter（破壞數標籤錨定，TURN 章
   自動寬度會讓它浮動）＋name_signature 單位圖像簽名（tight-bbox
   dHash，位移 ±4px 距離 0、異單位 25+ bits）。v1 stub（皆有 fixture
   釘住）：武裝選擇命中%（🎯浮動在目標頭上且語料被裁切）、
   support_defense 圖示（無語料）、亮背景破壞數（回 None 重試）。
3. **M3a `battle/panels.py` 詳情面板解析**：左欄 12 數值（跨三分頁
   不變）＋武裝卡列（LV/RANGE/POWER/EN/命中/爆擊＋格鬥/射擊徽章）；
   藍色▲強化數值 12/12 直讀。to_unit_spec＋assumptions；UnitSpec 增
   pilot_shooting/pilot_melee；pilot_attack_for 依徽章選射擊值/格鬥值。
4. **M3b 敵情採集＋stage cache（離線半場）**：scout_intel 點敵→摘要
   卡（sig 去重、幻影點容忍）→開 modal→武裝分頁→解析→cache；
   IntelBudget(6 面板/90s)。stage_cache=data/cache/stages/，只存身分
   與基礎 kit（現 HP 永遠讀畫面），sig 普查不符→cache_stale→現場
   重讀。**GGGE_INTEL=1 才啟用，等實機標定**（SUMMARY_CARD_TAP／
   WEAPONS_TAB_TAP 座標、settle 時間）。
5. **M4a 對帳鏈接線**：每次攻擊先 compute_expectation（formulas 代入
   面板 spec，缺值記 assumption；quality=grounded/assumed/none）→
   讀武裝選擇 forecast 對帳→battle_prep 抓支援防禦塌陷＋命中%→
   破壞數 delta 裁決。分類：[SIM-DIVERGE damage/kill_flip/support_
   defense]、[RNG-BRANCH]（命中<100 的預期擊殺落空＝骰子問題）、
   [MODEL-DIVERGE]（命中=100 沒死＝模型錯）、[SIM-SKIP]（無 grounded
   期望＝永不記功）。attribution 新增 algorithm_credit＝grounded 且
   擊殺確認 / 出手次數，勝場 0 grounded→明示「勝利不可歸因演算法」。
   順修：battle_prep→battle_prep 列為合法轉移（消 12 筆假 retry）。
6. **M4b advisor 提案（GGGE_ADVISOR=1）**：observe.py 把 tacmap＋
   sig 位置投影成 BattleState（敵單位以 sig 為 id），每回合諮詢
   advisor.advise(3s) 記 decision 事件——只提案不執行；實際目標 ≠
   提案目標→[SIM-DIVERGE] proposal_target。
7. **回合計數修復（原任務 #9）**：TURN 數字 OCR 直讀為主（HARD 1
   的 19 張存檔幀重放：前 12 張讀 1、後 7 張讀 2，半解析度 JPEG 也
   乾淨），marker 比對降為後備；+3 以上跳躍視為誤讀拒收。
8. **tacmap v2 角落蛇形全圖掃描（原任務 #7，使用者指示）**：首回合
   相機開到西北角再蛇行到底（邊緣=相位相關量測位移趨零），南緣飽和
   後補走最後一列；模擬世界測試證明任意起點全角落覆蓋＋全單位同步；
   28 腿預算；次回合起用便宜的四向局部刷新。
9. 附帶修復：LLM reader 開機後首讀被限流吞掉（monotonic 從開機起算
   ＋預設 0.0 的組合 bug）；新增 LlmScreenReader.transcribe（名牌
   轉錄，共用限流）——首見 sig 會存名牌裁切＋LLM 轉錄人類可讀名。

**下一步（需實機／使用者在場）**：
1. **M3b 實機驗證**（免費棄局）：`GGGE_INTEL=1` 出擊 HARD 1→turn 1
   採集→棄局→驗 ledger unit_intel/cache_stale 與 data/cache/stages/；
   重跑同關驗零開面板；毀 cache 驗回退。需標定摘要卡/分頁 tap 座標。
2. **對帳鏈實戰**：一場完整 decision→forecast→kill_check jsonl，設法
   誘發支援防禦；`GGGE_ADVISOR=1` 看提案與 proposal_target。
3. 蛇形掃描實機計時（28 腿預算是否過長）；武裝選擇命中%（🎯錨定模板
   需一張未裁切語料）；support_defense 圖示語料；我方單位 modal 開法
   標定（roster 完整數值）。

**遺留缺口（7/12 快照繼承）**：勝利尾巴 unknown 卡死（SECRET CLEAR
演出）、假移動格（殘留紅框）、敵方相位 AUTO chip 撥不動（不影響防護）。

## 舊快照（2026-07-12 深夜，恢復點）

**裝置現況**：手機停在鋼彈X 選關畫面（stage_list 0.95），HARD 1 已通關
（首次獎勵已領：鑽石×50、SECRET 機體、鋼彈X Divider 入手演出走完，
獎勵尾巴以手動 tap 收回選關）。adb server 已關、tmux 已清。

**實測局結果（data/runs/20260712-192608/battle_01.jsonl，245 事件，
1044 秒，破壞數 17/17 敵軍全滅）**：

1. **勝利**：19 次選單位、12 攻擊、25 交戰確認、**11 個 move（10 個
   directional_*、7 個以威脅格導向）**——史上第一次單位真的推進，
   方向全部正確（對比前日 hint 指西）。5 standby（3 超程 2 已移動）。
   隱藏戰鬥照 policy=challenge 接下並打贏。
2. **期望轉移驗證實戰帳**：65 met / 13 retry / 1 miss / 1 expired。
   12 個 retry 全是敵方相位連續應戰彈窗（battle_prep→battle_prep，
   模型當 tap 被吞而重按開始戰鬥——重按恰好是正確處置，功能無害，
   但 log 有噪音）；1 miss＝standby 後被應戰彈窗插隊（合法轉移，
   模型未列）；1 expired＝終局動畫。**改進項：battle_prep→battle_prep
   應列為合法轉移（連續應戰）**。
3. **hub guard 故障注入成功**：戰鬥中手動把 AUTO 撥到全自動（多次
   注入，敵方相位撥不動、hub 相位其一落地），下一次 hub 訪問即
   `AUTO left on btn_auto_full at the hub, forcing manual`＋ledger
   auto_guard 事件＋LLM 診斷讀圖。force 回 absent 是因為終局動畫把
   HUD 收掉，行為正確。
4. **LLM 讀圖 6 次實戰命中**：載入畫面、戰中未知畫面（甚至建議了
   正確的武器鈕）、AUTO 診斷、勝利後 SECRET CLEAR 畫面×3（正確建議
   TAP TO NEXT，但 unknown handler 無控制權——見缺口 2）。
5. 出擊後直接進戰鬥（放棄過的關卡重出擊會跳過 stage_info 與開場
   劇情）——stage_info 閘門這次沒被經過，controller 開頭 15s 探測
   承接，AUTO 本來就是 manual。

**本場暴露的缺口（依痛度排序）**：
1. **回合計數回歸（任務 #9）**：實際 TURN 5、ledger 全程 turn=1，
   marker 比對沒觸發（7/11 同圖是好的）；_turn_scouted 因此不重置、
   偵察只跑一次。有 19 張 select_unit 幀可離線重播。
2. **勝利尾巴 unknown 卡死**：SECRET BATTLE CLEAR／機體入手演出不在
   畫面庫，agent loop 等滿 90×2s 收 FAILED（戰鬥其實已贏、ledger 已
   歸檔）。候選解：unknown handler 在 LLM 建議「tap to advance」類
   場景給受限的 neutral tap 權限，或補模板。
3. **假移動格**：t=104.8 的 cell 移動（1720,604）與目標（786,137）
   反向——weapon_select 返回後殘留的紅色攻擊範圍外框被白框遮罩誤抓
   （同因 20260712-182654 驗出 38 假格）。幀已存 ledger。
4. 敵方相位 AUTO chip 撥不動（注入實測），probe 高分照樣匹配不到
   ——chip 在該相位可能鎖定，不影響防護但注入測試要挑 hub 時機。

**新語料**：`assets/screenshots/20260712-hub-corpus-01.png`（我方
hub、全解析度 PNG，hp_arc 重校準用）、`20260712-enemy-turn-marching-
fullres.png`（敵方回合行軍、全解析度）。

## 舊快照（2026-07-12 晚間，恢復點）

**裝置現況**：手機停在「機動新世紀鋼彈X HARD STAGE 1」選關畫面（出擊
準備鈕），體力 25/104 自然回復中。驗證局用戰鬥選單收場——**放棄戰鬥
不消耗體力／挑戰次數（確認框明文實證），出擊 10 點已退回**，之後可
低成本反覆實測。adb server 已關、tmux 已清。

**本批次成果（commits 99035e1 + 後續，213 測試/1 xfail、ruff 全綠）**：

1. **LLM 讀圖輔助**（`perception/llm.py`）：ollama 讀截圖協助未知畫面
   判別，預設 gemma4:latest（實測 8B 暖機 3.6s 且輸出比 26B 乾淨）；
   接線於 controller 未知場景（neutral tap 前）、AUTO 防呆失敗診斷、
   clear-loop unknown handler。rate limit 60s、任何失敗都退化為原行為。
   **實戰命中**：載入畫面被正確讀出（5.8s）。
2. **AUTO 防呆 act→verify→retry**（`force_manual_auto`）：tap 後要求
   chip 狀態在 6s 內真的轉移，否則視為被吞重試；回傳 manual/absent/
   unconfirmed 三態。stage_info 硬閘門（unconfirmed 拒絕推進出擊）、
   controller 開頭 15s 短預算（修 60s 空燒）、hub 每次訪問複檢。
   **實戰驗證**：使用者遊玩殘留的真實全自動被閘門攔截，full→enemy→
   manual 每步驗證後才出擊，7/11 汙染場景完整重演並被擋下。
3. **期望轉移驗證機制**（使用者定案方向）：`Expectation` 契約（來源
   相位→合法目標集合），met/eaten（on_eaten 回滾 handler 旗標）/miss
   （畫面權威，只記帳）/expired（檢查次數計時）四種裁決，v1 掛在
   選單位/開武裝/攻擊/開始戰鬥/待機。見 docs/battle-phase-states.md。
4. **戰術感知修復（對「往敵人反方向」的診斷回應）**：
   - 診斷實據：兩場戰鬥 0 個 move 事件（單位從沒被下移動指令，全程
     站樁）；`find_move_cells` 白框假設在雪地歸零（白遮罩飽和成一大塊，
     9 張全解析度幀離線重現）；scout hint 指西而敵軍在北（tacmap 22 敵
     vs 實際 14——hub 弧線誤判餵毒＋雪地無特徵相位相關飄移）。
   - 修法（不動任何 HSV 閾值）：威脅格「!」不受敵我誤判污染，升為
     `_seek_move_target` 第 2 優先與 `_hint_from_map` 首選（tacmap 加
     threats 層）；抽不到格子但有方向時改「方向性點擊」fallback
     （PAN_CENTER 朝目標 260px，撞到弧線退 150px，`directional_*`
     basis 記帳）。頂帽/亮度掃描/窄飽和度萃取格子皆試過不可分，
     結論記在此，別重走。
5. 放棄戰鬥流程標定：戰鬥中右上 ☰ → 放棄 (456,850) → 確認 (1346,850)，
   回到選關畫面。已寫入 CLAUDE.md 鐵則。

**尚缺、待使用者下實機測試指令**：
1. 期望轉移驗證＋方向性移動＋威脅格導向的實戰資料（放棄免費，可多輪）。
2. hub guard 故障注入測試（戰鬥中手動撥 AUTO，驗證 hub 複檢抓回）。
3. SIGTERM 中斷時 ledger 未歸檔（20260712-182115 只有 frames 目錄，
   jsonl 沒寫出）——中斷路徑要查，或改 ledger 逐事件 append。
4. 雪地 move-cell 真正的抽取（目前用方向性點擊繞過；圓角/缺口特徵
   模板是下一個候選，需要更多樣本）。
5. hub 弧線 HSV 重校準仍缺全解析度 hub 語料（目前用威脅格繞過）。
6. （承前批次）keyguard 疑似誤報、應戰決策選項優化、roster_calibration
   接線。ensure_manual_auto 60s 空燒已由 2 修掉；stage_info 修正包的
   AdvanceStageInfo 路徑今日已實戰走通。

## 舊快照（2026-07-11 深夜，恢復點）

**裝置現況**：HARD STAGE 1 於 turn 4 **戰敗**（己方單位全滅——隊伍
低於建議戰鬥力＋單位待機不推進，屬預期結果；這場開頭本來就被殘留
AUTO 汙染，定位是活體測試場不是通關嘗試）。`is_defeat_screen` 首次
實機命中、controller 乾淨退出、ledger 歸檔 outcome=defeat（
`data/runs/20260711-225442/battle_01.jsonl`，1195 秒、四回合、13 種
事件：15 對話/13 選單位/9 待機/5 攻擊/27 應戰確認/5 neutral_tap/1
隱藏戰鬥彈窗/1 劇情跳過/4 戰術掃描/3 end_turn）。FAILED 畫面已手動
點「選擇關卡」收回，**裝置現停在鋼彈X 選擇關卡畫面（HARD 1 節點）**，
體力充足。tmux session 已清、adb server 已關（收工紀律）。

**本批次成果（commits 1cd5f38→cef76bb，179 測試/1 xfail、ruff 全綠，
全部附實機驗證證據）**：

1. **is_static 卡死正式修畢，方向為使用者定案的「可操作性優先」**：
   不再判斷「畫面是否靜止」，直接 probe 相位 label 判斷 ACTIONABLE，
   連續兩次一致才 dispatch；回合邊界改用 TURN 數字變化（`_turn_marker`
   比對），刪掉 `_phase_break`/`_none_streak` streak 邏輯；
   `ensure_manual_auto` 改雙讀一致；`_wait_animation` 改「靜止或 label
   回來」雙出口。（bd11a67）
2. **highpass 匹配修好亮背景 label 失效**：TM_CCOEFF_NORMED 對「暗圖
   校準的模板 vs 亮雪地」會掉到 gate 以下（實測 0.764 < 0.80）；模板
   可在 manifest 開 `preprocess: highpass`（減 31×31 高斯局部平均），
   雪地 0.893、暗圖 0.964+、負樣本反而更低。只開給五個相位 label。
   （b750af2，fixture 語料 mode_label/ 七案釘住）
3. **敵軍回合橫幅干擾模板**：「敵軍回合」與「我軍回合」四字共三字，
   cross-match 0.81/0.83 超過 gate——舊迴圈被 is_static 意外遮住、新
   迴圈立刻踩到（敵方回合全程狂點單位卡）。修法不是調閾值：新增
   `label_enemy_turn` 模板一起 probe，`resolve_mode()` argmax，干擾
   模板贏＝NOT_ACTIONABLE。實測 0.991 vs 0.831 分離。（3c2ada4）
4. **對話 cursor 搜尋帶加寬 130→170px**：劇情對話（立繪＋說話者橫幅
   雙行版面）的 ▼ cursor 停在 y~905-925，舊帶搆不到（帶內 0.571 vs
   全幀 0.945），run 2 因此停擺 10 分鐘。（cef76bb）
5. **neutral-tap fallback（使用者建議）**：NOT_ACTIONABLE 連續 3 輪
   什麼都認不出→頂部中央（無按鈕區）輕點一下嘗試推進；對話類畫面
   點哪都會前進，其他畫面安全忽略。每次記 `neutral_tap` ledger 事件
   ＋存幀，未知場景自動留校準素材；副作用防 3 分鐘省電鎖。（cef76bb）
6. **實機煙霧測試（HARD STAGE 1 活戰場，run 1-3）驗證清單**：雪地
   label 偵測（probe 0.86-0.87 穩定）、marker 回合邊界（turn 2-4 正確
   觸發、modal 不誤進位）、完整攻擊鏈（選單位→武裝→鎖定→確認 ×5+）、
   **#3 應戰決策彈窗首次實機捕捉**（標題「戰鬥準備 -應戰-」被
   `label_battle_prep` 以 0.948 承接，`_on_battle_prep` 的開始戰鬥
   tap 能推進不卡死；最佳應戰選項的決策是未來工作）、死亡對話推進、
   劇情對話變體推進、省電鎖 mid-run 自解、unit_detail modal 逃脫、
   隱藏戰鬥 WARNING 彈窗（policy=challenge）、MENU 左移劇情跳過、
   **`is_defeat_screen` 首次實機命中＋乾淨歸檔退出**。run 1 首次產出
   含真實戰鬥事件的完整 jsonl；run 3 打完整場（見上方裝置現況）。
7. **狀態轉換 log（使用者建議）**：主迴圈感知裁決改變時記一行
   「state: 舊 (held N checks) -> 新」含 label/信心證據，四種裁決
   （ACTIONABLE／NOT_ACTIONABLE 干擾模板／NOT_ACTIONABLE 無 label／
   TRANSITION 兩讀不一致）；standby 補記決策脈絡（move cells 數、
   tacmap 敵數、scout hint）；`GGGE_DEBUG=1` 切 DEBUG 級。（a9cd9d7）

**本批次觀察到、尚未處理**：
1. **戰術缺口（既有 v1 弱點實錄）**：武器超程時「no enemy direction
   found, standing by」頻繁出現——scout 有敵人座標但移動目標選擇失敗，
   單位原地待機不推進。對應 battle-skills-improvement 既有記憶，
   屬戰術品質非生命週期問題。
2. **keyguard 疑似誤報**：22:56:15 對話推進中（每 5 秒有輸入）觸發
   「game battery-saver lock engaged」——3 分鐘閒置條件不可能成立，
   疑似劇情畫面調暗＋中央區誤匹配鎖頭圖示；解鎖 swipe 對對話無害
   （等於推進一行）。需要抓到現場幀才能釘 fixture。
3. **ensure_manual_auto 在無 AUTO 鈕畫面燒滿 60 秒 timeout**（對話
   畫面開場時）。可考慮縮短 timeout 或加「畫面有對話 cursor 就跳過」。
4. 期望轉移驗證（act → verify → retry）尚未動工——todo #3，是下一個
   結構性投資。

**尚缺、待裝置**：
1. HARD STAGE 1 乾淨場重打（本場開頭被殘留 AUTO 汙染，見上一快照）。
2. 出擊前 AUTO 防呆自動化（stage_info 畫面上強制 AUTO 手動）——這次
   又是靠人眼攔截。
3. stage_info 修正包（5b6c811）驗證——仍未真正跑到。
4. 應戰決策的選項優化（現在照預設確認）。
5. roster_calibration 接線。

## 舊快照（2026-07-11，恢復點）

**裝置現況**：手機停在「機動新世紀鋼彈X HARD STAGE 1」戰鬥中，我軍回合
TURN 1，破壞數 4/14，畫面在鋼彈F90 的「單位移動／選擇武裝」子畫面，AUTO
已確認為關閉（灰色、非高亮）。這場戰鬥沒有結束、沒有撤退，就是單純停在
原地——`run_manual_battle.py` 已被我手動 SIGTERM 中止（`data/runs/
20260711-214453/battle_01.jsonl` 只有一筆 `finish/interrupted`，全程
437 秒零行動）。下次接手前**先截圖確認畫面沒有被系統動作（省電鎖等）
影響過**，再決定要繼續手動這場、還是撤退重打。

**本批次成果（找到 HARD 關卡並出擊，過程中發現四個獨立問題，沒有新
commit——這批純粹是實機驗證嘗試 + 即時除錯，程式碼未變動）**：

1. **確認並進入「機動新世紀鋼彈X HARD STAGE 1」**：透過關卡選單→
   MAIN STAGE→鋼彈X 系列→選擇，確認 HARD 0/1 未過，建議戰鬥力
   160,000，首次獎勵 LV50 SECRET 機體＋可奪取敵方機體。隱藏條件「2回合
   內擊敗夏基亞·佛羅斯特、歐爾巴·佛羅斯特」達成時敵方會增援。出擊準備
   帶自動編制隊伍（LV81/LV45/LV50/LV45/LV45 主力＋LV22 支援），增幅
   +4,646。

2. **重大發現①：AUTO 殘留全自動狀態，內建 AI 在人為介入前已自動出手**。
   出擊進場後 stage_info 畫面的 AUTO 開關已呈高亮（全自動）狀態，我手動
   點擊試圖切換時意外同時觸發了畫面推進，直接跳進戰鬥；戰鬥開場動畫
   期間內建 AI 已自動打死 4 隻敵人（破壞數 4/14）才被我發現並手動關閉
   AUTO。**這違反了「戰鬥必須由我們的程式操作、絕不能讓內建 AI 接手」
   的紅線**，雖然是裝置殘留狀態造成、非我方主動選擇，且已即時補救，但
   這場戰鬈的開場已被內建 AI 汙染，不能當作 controller 的乾淨驗證證據。
   根因跟先前 stage_info 修正包驗證中斷時發現的 AUTO 競態同源（出擊前
   沒有先確認/強制 AUTO 為手動）。

3. **重大發現②：主機再次硬凍機（第 5 次），這次伴隨主動 adb 操作**。
   `run_manual_battle.py` 於 21:29:51 啟動、21:30:00 左右仍在正常跑
   （log 顯示「AUTO is btn_auto_enemy, cycling toward manual」），
   `journalctl -b -1` 卻在 21:30:24 戛然而止——只有一行例行的
   `freeze-blackbox` 心跳 log，沒有任何 `systemd-shutdown` 序列，跟過去
   四次凍機同簽名。**新線索**：這次凍機發生在腳本啟動後僅 ~36 秒、且
   正值密集 adb shell／uiautomator2 呼叫期間，跟先前「adb server 常駐
   閒置三分鐘後當機」的假說不同方向，暗示主動的 USB／adb I/O 也可能是
   誘因之一，而不只是常駐本身。`system-freeze-investigation` 需要納入
   這個新資料點。

4. **重大發現③：`no permissions` 根因首次查清**。凍機重開機後
   `adb devices` 顯示 `R5CRC37JBYJ no permissions`，`getfacl` 一查發現
   USB 裝置節點的 ACL 只授權給 `gdm-greeter`（`rw-`），poyu 只有 other
   權限（`r--`，無寫入）。`loginctl seat-status seat0` 確認：重開機後
   seat0 預設由 `gdm-greeter`（登入畫面）持有，systemd-logind 把本機
   USB 裝置的 ACL 動態綁在目前持有 seat0 的 session 上；只有使用者**
   實際在實體機器登入桌面**、seat0 轉移給 poyu 的 session 後，adb 權限
   才會恢復——這正是先前快照「no permissions 已解除、原因不明」的真正
   機制。本次使用者中途實體登入後，權限確實立即恢復，驗證了這個推論。
   沒有 sudo 免密碼可以繞過，純系統層限制，不需要也不該動 udev 規則。

5. **重大發現④（本次卡住的直接原因）：`vision/motion.py` 的
   `is_static(threshold=0.015)` 在 HARD STAGE 1 這張雪地地圖上完全無法
   收斂**。即時對現場畫面連續量測 5 次，全部回傳 `False`（背景飄雪
   粒子特效／移動範圍格「!」圖示的脈動動畫／選中單位的紅圈光效，任一或
   合力造成連續幀差異持續超過閾值）。`ManualBattleController.run()`
   主迴圈在 `is_static` 為 `False` 時會直接 `continue`（視為戰鬥仍在
   播動畫），完全不會進到 mode 偵測／`_on_unit_move`／`_on_weapon_
   select` 等行動分支。結果整場戰鬈從 21:44:53 跑到我 21:52:10 手動
   SIGTERM 中止，437 秒內零行動、零有意義 log。**這是全新發現的
   controller 卡死模式，跟先前任何已知問題（AUTO 競態、hp_arc 誤判、
   ENEMY_REACTION_POPUP 缺口）都不同源**，且很可能不是這張地圖獨有——
   任何有持續動畫背景（雨、雪、粒子特效）的戰場都可能觸發同樣的卡死。

**尚缺、待裝置（更新後排序見下方「下一步」）**：
1. **`is_static` 卡死問題需要修法方向**——本次最大的技術阻礙，且動
   `vision.py`／`motion.py` 需要使用者拍板方向（遮罩掉飄雪等已知動畫
   區域再比較？放寬 threshold？連續 N 次 False 後改用備援判斷強制
   評估 mode？）＋照專案紀律走 fixture 回歸測試流程，不能貿然調閾值。
2. **AUTO 開關出擊前防呆**——這次又中招，是人眼即時攔截、不是自動化
   把關。需要在 controller 或 stage_info handler 加上出擊後第一時間
   強制檢查/確保 AUTO 為手動，而不是靠人在旁邊盯。
3. Gundam X HARD STAGE 1 本身還沒清完，卡在 Turn 1 中途（破壞數
   4/14），前段已被內建 AI 汙染，就算修完 is_static 問題後續打完，這場
   也不能當作乾淨的「全程我方 controller 操作」驗證證據——大概率需要
   放棄重打。
4. stage_info 修正包（5b6c811）——仍然是「完全未驗證」，這次也沒機會
   推進。
5. 生命週期 ACTIONABLE/NOT_ACTIONABLE 重構（516987e）的實機行為——同上，
   沒有取得完整一輪戰鬥的即時觀察證據。
6. ENEMY_REACTION_POPUP（#3）畫面錨點標定與 handler——仍未動工。
7. roster_calibration 裝置常數標定——仍未接進 controller.py。

**下一步**：跟使用者討論 `is_static` 卡死的修法方向並取得共識；方案
定案、有 fixture 證據後才動 `vision.py`／`motion.py`；同時把「出擊後
強制確認 AUTO 為手動」做成自動化防呆而非人眼盯場。兩個修好後，放棄
現在這場已被汙染的 HARD STAGE 1，重新出擊乾淨驗證一輪。

## 舊快照（2026-07-10，恢復點）

**裝置現況**：手機已接回，`adb devices` 顯示 `R5CRC37JBYJ device`（上一
快照的 `no permissions` 已解除，原因不明，未深究）。截圖確認畫面在
**選擇關卡**，游標停在關卡 12（劇情預覽「難道非得開火不可嗎！」，建議
戰鬥力 133,000，地形地面，所需 10，略過 3/3，資源 84/103），關卡
9/10/11 均顯示 CLEAR。體力/資源足夠再跑一輪。

**本批次成果（167 測試/1 xfail、ruff 全綠，沿用 commit 3029f79 之後
未變動 — 這批純粹是實機驗證嘗試 + 事後鑑識，沒有新 commit 的程式碼）**：

1. **啟動 `run_clear_loop.py` 打關卡 11**（使用者核可用任一關驗證、10
   體力不是問題）。腳本跑到 `data/runs/20260709-215050/frames/battle_01/`
   共 27 張 probe/move/attack frame，最後一張
   `t0046_turn1_move.jpg`（2026-07-09 21:56:15）。**`battle_01.jsonl`
   從未寫出**——流水帳檔完全不存在，不是「有紀錄但缺 finish 事件」。
2. **重大發現：5b6c811 stage_info 修正包這次也沒被實際跑到**。根因是
   競態：AUTO 開關在使用者先前手動遊玩後被留在「全自動」，遊戲在我們
   的腳本第一次 `perception.observe()` 之前就已經自動跳過
   stage_info（「TAP TO NEXT」）甚至更多畫面。也就是說，先前對這個
   修正包「看起來有效」的印象是誤判——它從未真正被本次流程呼叫到。
   **這修正包目前的驗證狀態退回「完全未驗證」**，且下次驗證必須先解掉
   這個競態（出擊前檢查/強制 AUTO 為手動，或提高腳本啟動後的截圖頻率
   避免被搶跑）。
3. **主機乾淨重開機，非凍機模式**：`journalctl -b -1`／`-b -2`／`-b -3`
   均可見完整 `systemd-shutdown` 序列（SIGTERM 給殘留 process、journal
   正常 stopped），跟過去四次凍結的「無日誌戛然而止」簽名不同，判斷
   跟 `system-freeze-investigation` 的凍機模式無關。07-10 當天另外還有
   13:35、14:10 兩次同簽名的乾淨重開機，同樣非凍機。
4. **未解謎團（需使用者確認）**：最後一張自動化 frame
   （07-09 21:56）到目前截圖（07-10 19:15）之間隔了近 21 小時，中間
   主機重開機三次。這段期間**沒有任何 `battle_01.jsonl` 或其他紀錄**顯示
   關卡 11 是怎麼結束的，但畫面上關卡 11 現在是 CLEAR、關卡 12 變成
   游標所在的「下一關」。最合理的推測是使用者在腳本卡住後（對應
   使用者當時問的「怎麼不會動？」）手動用手機把這場戰鬥打完，但這只是
   推測、尚未跟使用者核實。**如果是手動完成的，這場戰鬥不能算是生命
   週期模型／stage_info 修正包的實機驗證證據**，需要重跑一輪讓自動化
   腳本全程跑完才算數。

**尚缺、待裝置（更新後排序見下方「下一步」）**：
1. stage_info 修正包（5b6c811）——真正的第一次驗證，這次要先排除
   AUTO-full 競態。
2. 生命週期 ACTIONABLE/NOT_ACTIONABLE 重構（516987e）的實機行為——今天
   這次嘗試被中斷，沒有取得完整一輪戰鬥（含 NOT_ACTIONABLE 段落）下的
   即時觀察證據。
3. ENEMY_REACTION_POPUP（#3）畫面錨點標定與 handler——生命週期模型剩下
   唯一的實質缺口，仍未動工。
4. roster_calibration 裝置常數標定——已有純運算邏輯與測試，尚未接進
   controller.py、尚未量測真實列表鈕座標/鏡頭跳轉量。

**下一步**：跟使用者核實關卡 11 戰鬥是否為手動完成；接著重跑
`run_clear_loop.py`（關卡 12 現成可打），這次出擊前先截圖確認 AUTO
開關狀態，避免重蹈 stage_info 競態覆轍，順便補齊生命週期模型與
stage_info 修正包的真正實機證據。

## 舊快照（2026-07-09 更晚）

**裝置現況**：跟上一快照相同，`no permissions` 未處理，本批次全程沒碰
裝置。

**本批次成果（commits a07b05f/ecddb4f/516987e/8bba4d6，167 測試/1
xfail、ruff 全綠）**：

1. `docs/battle-phase-states.md` 從一份畫面狀態分類學（被使用者指出
   「相當空泛」）改寫成使用者定案的生命週期模型：**ACTIONABLE／
   NOT_ACTIONABLE 二元判斷**，不分敵方/第三方回合；可控第三方會自然
   出現在單位列表走 ACTIONABLE 路徑，不可控的自然落 NOT_ACTIONABLE，
   不需要額外探測第三方可控性。敵我互打降低難度這類內容細節刻意不理。
2. **落地進 `controller.py`**（516987e）：`run()` 的 `mode is None`
   fallback 從匿名分支改成有名字的 `_on_not_actionable()`，是應戰彈窗
   （#3）未來的掛載點。**沒有**照文件原稿用 `unit_cards_present` 當
   頂層判斷——落地前發現沒有實機證據能證明卡片列在 unit_move/
   weapon_select 子畫面底下還可見，貿然假設違反紅線；改用
   `mode is not None`（既有 handler 已經在用、已驗證的訊號），
   純重構、行為零改變（回歸測試釘住等價性）。文件已回頭同步這個落差
   （8bba4d6）。
3. `unit_cards_present` 用途不變——還是 `_on_our_turn()` 判斷「選下一個
   還是結束回合」，這是它本來就驗證過的場景。

**尚缺、待裝置**：ENEMY_REACTION_POPUP（應戰彈窗）畫面錨點標定與
handler，是生命週期模型剩下唯一的實質缺口。

## 舊快照（2026-07-09 晚）

**裝置現況**：跟上一快照相同（`adb devices` 顯示實體連接但 `no
permissions`，未處理，本次工作全程沒再碰 adb/裝置）。

**本批次成果（163 測試/1 xfail、ruff 全綠，commits 46a5a70/8c21883）**：

1. **#5 根因新線索（重大）**：用 #18 取樣時發現，`20260706-233847.png`
   （真實「我軍回合、選單位」hub 畫面）上 `find_ally_units` 誤判 0、
   `find_enemy_units` 誤判 9 個假陽性。深查後：現行 HSV 閾值的敵方紅
   校準來源（`20260705-170520.png`）其實是**敵方回合**畫面，跟控制器
   實際掃描發生的**我方回合單位選取 hub**畫面是不同 UI 狀態；hub 狀態
   下未行動我方單位的弧線色相跟敵方紅幾乎同色相（2026-07-09 量測皆
   中位數 hue 3-8）。也就是「閾值對錯了畫面狀態校準」，不是漏了一個
   色域，補帶反而會讓真敵方一起被 `find_ally_units` 誤收。副觀察：
   同一張圖裡已行動/未行動單位弧色不同（一藍一紅相鄰），暗示紅色
   可能是「本回合待行動」高亮而非純陣營色，待更多樣本驗證。**沒有
   修 `vision.py`**——證據不足以安全重新校準，只把此圖存成 #18 的
   xfail 回歸案例釘住現象，詳見 CLAUDE.md 視覺辨識避坑節與
   `tests/fixtures/vision/hp_arc/our_turn_hub_pink_bug.json`。
2. **#18 視覺回歸測試庫首批**（46a5a70）：`scripts/curate_fixture.py`
   （真實截圖裁切→`tests/fixtures/vision/<類別>/<案例>.{jpg,png}+json`）
   ＋ `tests/test_vision_regression.py`（回歸掃描語料庫，xfail 支援）。
   首批 10 案例涵蓋 hp_arc／unit_cards／unit_detail_modal／
   hidden_battle_warning／defeat_screen 五類，全部來自真實截圖（戰敗
   用真模板疊真背景合成，因語料庫目前沒有真正輸掉的截圖）。hp_arc 類
   改存 PNG 無損——JPEG q85/90/95 對這種像素級色彩/形狀判斷會非單調地
   翻轉 blob 分類（實測證據見 commit）。**尚缺**：screen_mode、
   template_locate（MENU 漂移/結束回合對話框）、keyguard 暗幀負例
   三類，留待下次擴充。
3. **roster_calibration 設計骨架**（8c21883）：回應使用者對顏色判斵
   可靠度的質疑，提出「單位列表點擊＋鏡頭跳轉量測」取代弧色判斷我方
   身分/位置的方案——單位列表天然只列可操控單位（含未來換邊劇情也
   成立），點擊造成的鏡頭跳轉用既有 `vision.measure_camera_shift`
   （純地形相位相關，不碰單位顏色）量測、串接成 slot→世界座標表。
   `battle/roster_calibration.py` 只含串接運算，裝置相關常數（列表鈕
   座標、列表列間距、選取單位鏡頭歸位錨點）全部注入，未硬編造值——
   這些待裝置接回才能實測校準，目前用假 capture/tap/shift 測試純運算
   邏輯（`tests/test_roster_calibration.py`）。**尚未接進
   controller.py**，屬 track 1（裝置門檻）工作。

**GitHub 同步**：#5 留言記錄根因新線索；#18 留言記錄首批完成與缺口。

**下一步（沿用 2026-07-09 稍早定案的排序，見下方舊快照）**：軌道 0
剩餘部分（#18 補三類）可以再擠一點，但主要卡點還是裝置——`no
permissions` 沒解決之前，軌道 1（驗證 5b6c811、#5/#6、advisor 影子
模式、roster_calibration 裝置常數標定）都動不了。

## 舊快照（2026-07-09 早）

**裝置現況**：`adb devices` 顯示 R5CRC37JBYJ 已實體連接但 `no permissions`
（與上一快照「手機仍拔離」不符，可能使用者已插回但尚未在裝置上重新授權
USB 偵錯，或 udev/授權狀態跑掉）——本次只用來確認連線就 `adb kill-server`
收工，未深究、未使用裝置。依凍機調查紀律（memory
`system-freeze-investigation`），adb server 只在有人盯著的工作時段開，
用完即殺。下次要用裝置前先處理這個 no permissions。

**本次完成**：把 2026-07-08 快照「Issue 分類」的結論同步成 6 則 GitHub
issue 留言（#19/#17/#13/#3/#12/#14），標明各自「本分支已解決的部分」vs
「仍待實機/正交依賴的部分」，任務清單文件與 GitHub 議題現在一致。

**任務排序定案（使用者 2026-07-09 確認）**：

軌道 0（裝置沒回來也能做，現在就做）：
1. **#18 視覺回歸測試庫**——用既有 `data/runs`/`assets/screenshots` 語料
   建，不需裝置；後續動 `vision.py`（驗證 5b6c811、修 #5/#6）都要靠它當
   回歸網，排最前面。

軌道 1（裝置接回後依序做）：
1. 驗證 `5b6c811` 修正包（含 #1 實機驗證）——程式碼已寫好，只差臨門一腳
   的實機證據。
2. #5 掃描計數修正——#6、#14、advisor 輸入品質的共同根基。
3. #6 鏡頭錨定驗證（緊接 #5）。
4. advisor 影子模式接進 controller（只記流水帳不執行、風險低，是本分支
   最大投資的變現點）。
5. #3 實機半部（應戰彈窗感知標定，跟第 4 點同一輪戰鬥順便收集）。
6. #12 感知端（ScanProvider，先做 SUPPORT/技能鈕簡化可用性判斷，不必等
   完整 OCR）。

軌道 2（維持低優先）：#9 OCR、#8/#11 cache、#13 剩餘 cache 抽查、#10
戰略迴圈——沒有理由提前。

**取捨**：嚴格依賴序會是「#5/#6 全修完才試 advisor」，拖太久看不到
solver 主線的實機反饋；用「影子模式」打破序列依賴——advisor 不影響實際
戰鬥決策，即使輸入不準也只是流水帳多一筆怪建議，不拖累通關，讓 vision
修正與 solver 整合兩條線並行推進。

**下一步**：開始實作 #18（軌道 0，不需裝置）。

## 舊快照（2026-07-08 晚）

**裝置現況**：手機仍拔離。**第四次凍結**：07-08 16:53~16:54（journal 於
16:53:03 例行訊息後戛然而止，與前三次同簽名）——發生在無裝置、無戰鬥、
近乎閒置的機器上：session 開始 4 分鐘、`adb devices` 拉起 adb daemon 約
3 分鐘後。四次凍結的軟體側共同因子收窄為「adb server 常駐」（該 boot
先前 16.5 小時無 adb 無事）；但 Fedora android-tools 的 adb 無 mDNS，
閒置 server 只剩 USB bus 掃描，而先前 USB 重度壓測是陰性——機率性硬體
嫌疑同步上升。詳見 memory `system-freeze-investigation`。**adb server
已殺掉；開機後可能有東西自動拉起（07-08 20:10 曾見一顆掛在
systemd --user 下），做無 adb 對照前先 `pgrep adb`。** memtest86+ 過夜
與 BIOS 更新檢查仍未做。

**本批次成果（離線 solver 主線；151 測試/ruff 全綠）**：
1. **solver 健全性**（1529e14）：置換表加 exact/lower/upper 界值旗標；
   Star1 一般化為 n 元期望節點（含敵方 policy 節點）；修掉 fail-soft
   界值方向寫反的剪枝不健全 bug。回歸手段＝隨機盤面上「剪枝+TT」必須
   等值於「無剪枝參考」（SolverConfig 的 use_tt/use_star1 開關）。
2. **行動生成擴充**（a3adbe6）：SimUnit 技能欄（SimSkill：uses/
   ends_turn）、legal_skills＋reposition_moves（朝各目標推進＋滿移動力
   後撤）進 _ally_decisions——「補 EN 再打」「欺近畫面外目標」「脫離
   致死圈」都由搜尋自己發現（各有行為測試）。另修 PV 決策重複前置 bug。
3. **Sim v1 幾何**（16c52cc）：battle/grid.py BFS 王步可達性——異陣營
   擋路、我方可穿不可停、SimState 選配地圖邊界；legal_attacks 接 reach
   集合做繞路落點。測試含「兩機堵咽喉→敵方對後排攻擊消失」端到端案例。
   支援防禦幾何仍為切比雪夫近似（待辦）。
4. **Bridge＋Advisor**（52be776）：battle/bridge.py 把 BattleState 量化
   成 SimState（能力注入→再動/技能/支援欄位；數值權威序＝現場 > spec
   (OCR/cache) > BridgeDefaults，每個 fallback 記名為假設供歸因）；
   battle/advisor.py 一呼叫完成 bridge→solve→控制器詞彙（世界座標移動
   目標/目標 id/武器）＋假設清單＋搜尋統計。

**Issue 分類（完成本分支可解 vs 不可解，2026-07-08 使用者要求）**：
- 本分支主體：#19（模擬器＋expectiminimax）、#17（內層 GOAP）。
- 被本分支收編：#13（1.5-ply 站位安全→多層搜尋＋葉評估取代）、#3 的
  決策端（防禦應對＝solver 的 defender-reaction max 節點；剩敵方回合
  彈窗感知/handler 是實機部分）。
- 部分解決（決策端解、感知端待裝置）：#12（ActionCatalog/技能生成已
  進搜尋；畫面掃描與 execute 接線待 #9/實機）、#14（advisor 以世界座標
  定移動目標取代全域朝向；輸入品質仍依賴 #5/#6）。
- 本分支解決不了（正交）：#5（掃描計數失準——solver 輸入品質的根基，
  最重要的正交依賴）、#6、#1、#4（實機驗證）、#9（OCR——bridge 的
  UnitSpec 就是它的消費介面）、#8/#11（cache）、#10（戰略迴圈）、
  #18（視覺回歸庫）。

**恢復步驟（手機接回後）**：① `pgrep adb` 確認對照狀態→接回→截圖
（可能鎖屏，swipe 1164 430 1164 60 350 解）→ ② 先實機驗證 5b6c811
修正包（stage_info/keyguard 暗度閘/modal 逃生）→ ③ advisor 影子模式接
進 controller（每次啟動呼叫 advise() 只記流水帳不執行，離線比對 solver
vs 現行啟發式的決策差異，controller 接線的實機驗證證據由此而來）→
④ 敵方回合應對彈窗的感知標定（#3 的實機半）。cell_size 標定：戰術地圖
格距要從實測畫面量測。

**solver 待辦（不擋接線）**：Star2 probing；支援防禦的路徑感知幾何；
敵方 policy 模型精化（現為最近目標）；第三方勢力在 solver 中仍為惰性；
SUPPORT_ATTACK 尚未模擬。

## 舊快照（2026-07-08 凌晨）

**裝置現況**：手機已再次拔離（壓測結束）。遊戲上次確認停在 **HARD 2
戰鬥中 TURN 1 我方回合 hub**。無程式在跑。注意：手機的
`svc power stayon true` 未還原，接回後先跑
`adb shell svc power stayon false`。

**恢復步驟**：接回手機 → `adb devices` → 截圖（可能鎖屏，swipe 1164 430
1164 60 350 解）→ 確認是否仍在戰鬥（可能被登出，屆時從關卡列表重進，
會多耗 10 體力並經過新的 stage_info 動作）→ tmux 跑 `run_manual_battle.py`
實機驗證修正包。

**2026-07-07 深夜凍結調查結論**：7/5–7/7 三次無日誌硬當機（journal 於
07-06 00:09、07-07 00:30、07-07 09:35 戛然而止）。腳本審查無失控模式；
重現測試全數陰性——純 CPU/熱（heavy 全核 burst 一小時、Tctl 峰值 71°C）、
USB adb 流量＋heavy 組合（一小時）、傳輸中拔線（kernel 乾淨零 xhci 錯誤）。
剩餘嫌疑：WiFi adb 路徑（mt7921，凍結 2、3 的實際傳輸方式，未測）與
機率性硬體（建議 memtest86+ 過夜、查 BIOS 更新）。壓測工具在
`data/stress-test/`（stress.py light/heavy、capture_loop.py，gitignored）。
另：09:35 凍結發生在 git commit 寫入途中，留下 4 個 0-byte object 與
斷頭 HEAD——已修復（branch 指回 5b6c8118、重建 index，工作樹無損；
證據存 data/stress-test/git-corruption-evidence.txt）。本 commit 的
roadmap 快照即當時未遂 commit 的內容。

**20260706 深夜實測結論（feat/inner-goap，commits 79fcc0c/5b6c811）**：
clear loop 兩處斷點＋戰鬥三次靜默 stall 全數診斷完畢：
- main_menu 模板是 RANK 2 徽章裁圖，升到 RANK 13 後 0.783 過不了 0.90
  gate → 已重裁成出擊 MAIN STAGE 鈕（79fcc0c，rank/日期不變量）。
- stall 鏈：keyguard 的鎖圖示模板在暗色靜止戰場誤匹配（TM_CCOEFF 深色
  均勻區坑）→ 解鎖拖曳劃在敵方鋼坦克上 → 打開單位設置詳情 modal →
  無 handler 靜默循環＋假相位斷點灌高內部回合數＋unit_cards_present
  誤報 True。
- 修正包（5b6c811）六項：stage_info 畫面動作（AUTO 改手動＋勝利條件
  幀存流水帳＋TAP TO NEXT，使用者多次重申的需求落地）、keyguard 全幀
  暗度第二訊號（語料 30 張真鎖幀 8.7–31.6 全保留，gate 40）、modal
  逃生口（偵測標題帶＋點關閉 (1176,992)；語料 452 幀全中零誤報）、
  unit_cards_present 拒斥 modal、回合數以畫面 TURN 數字變化佐證、
  select 後三幀 post_select_probe 儀器。132 測試全過、ruff 乾淨。

**已知未修/未驗**：
- **mystery A 未解**：第三次 stall 的 modal 在點 FIRST_UNIT_CARD 後約
  4 秒重開、無 keyguard 事件——post_select_probe 儀器已上線，等下次
  發生離線重放。
- main_menu→stage_list 沒有 planner 邊（從 main_menu 起步會 no plan；
  上次手動導航繞過）。
- AdvanceStageInfo 未實機驗證：AUTO chip 離線 probe 0.895@(1820,54)
  沒問題，但 ensure_manual_auto 的靜態幀 gate 可能被 TAP TO NEXT 閃爍
  拖到逾時（有 30s timeout，會 degrade 到戰內重試，不致卡死）。

**接續待辦**：① 恢復戰鬥實機驗證修正包 → ② 重啟 #18 視覺回歸庫
（新素材：RANK 過期模板案例、暗鎖幀、modal 正負樣本、
stage_info、20260706-233158 run 的 hub 幀）→ ③ LLM perception 讀單位
資訊（ollama；格式樣本已採：武裝、技能／能力、OP 兩分頁優先，見
memory llm-perception-unit-info）。

**舊快照（2026-07-06）**：停在選擇關卡（機動戰士鋼彈 HARD 2，★★☆，
SECRET 已奪取），體力 25/80。

**模擬器/expectiminimax 定案（2026-07-06 深夜，feat/inner-goap 分支）**：
使用者確認要**求關卡最佳解**，depth-1 不夠、後端模擬必建。已定案收錄
機制（相位制回合、擊殺再動每回合重置、敵方相位的我方防禦應對
{閃避/防禦/反擊} 是 max 節點、格子移動與路徑封鎖拆支援防禦網、敵人
同樣有再動/支援且受特殊能力放大、支援次數每相位重置）；敵方節點預設
策略模型、介面保留 min；搜尋＝anytime 迭代加深 expectiminimax（殘局
自動精確，離線解全關=加大預算）。傷害/命中公式已從社群 wiki 調查入檔
`docs/combat-formulas.md`（閃避修正等待實機標定）。全文見
agent-architecture.md「戰鬥模擬器與 expectiminimax」節。**v0 骨架已完成
（#19）**：`battle/sim.py`（SimState/step/相位輪換/charge 重置）、
`formulas.py`（公式全參數化）、`enemy_model.py`（policy/min 可插拔）、
`solver.py`（迭代加深＋置換表＋Star1；Star2 與 TT 界值精修留 TODO）；
105 測試全過。裁量記錄：切比雪夫距離；`dodge_hit_penalty=20`、
`support_defend_multiplier=0.5` 為待標定預設；技能尚未接進 solver
行動生成（step 已支援）。新任務 #18＝視覺回歸測試庫（截圖整理成
標註案例釘 vision 閾值）。下一步＝#19 的 v1（格子可達性/路徑封鎖、
敵方回合應對彈窗感知）與 controller 整合。

**架構討論定案（2026-07-06 晚，commits 1dfc800/357bfab/0dccad9，全文見
agent-architecture.md）**：內層戰鬥 GOAP（#17 主 issue，收編 #12/#13）——
BattleState 統一盤面、ActionCatalog＝畫面掃描∪能力注入（擊殺再動等編成
知識灌入）、啟動內鏈式規劃（判死用實際數值 HP 非弧比例）、第三方可控性
開戰探測；**MCTS/模擬器非禁令**（先前誤記為紅線，CLAUDE.md 已更正）；
前置條件即內容（體力管理=資料綁定前置的實例）；編成兩階段（先讀取同步）；
目標介面預留戰役。缺什麼之後再補。

**離線批次（2026-07-06 完成、已 push、已關 issue）**：
- **#15 流水帳決策事件配截圖**（da1bed3）：每個決策事件（select_unit/move/
  attack/standby/tactical_map/story_dialog/hidden_battle_warning/end_turn/
  finish）存一張縮圖 JPEG（長邊 1280、q85）到 `data/runs/<ts>/frames/
  battle_NN/`，存幀失敗軟性略過不中斷。61→65 測試。
- **#16 隱藏戰鬥 WARNING 彈窗辨識**（f3ead6d）：`vision.is_hidden_battle_
  warning`（彈窗 1.0、他處 ≤0.21、gate 0.6）＋控制器依 `hidden_battle_policy`
  決策（預設 challenge 挑戰；OCR 戰力門檻留待實機）。彈窗自帶 AUTO 鈕不碰。

**下一步＝實機驗證**（需使用者提供測試機）：跑一場含索敵與（若觸發）隱藏
戰鬥的戰鬥，驗證 #14 索敵重構（cd89b9f enemy_onscreen）與 #16 彈窗決策，
並讓 #15 的 frames 自然產生，作為 #5/#6/#12/#3 校準的第一手資料。

**任務改用 GitHub Issues 管理**：repo `git@github.com:DeanXu2357/ggge_ai.git`
（public、main）、看板 https://github.com/users/DeanXu2357/projects/2 。
本檔的「工作安排」細節改以 issue #3–#15 追蹤，見 [[github-repo-and-tasks]]。

**今日重大成果**：
- **HARD 2 含隱藏戰鬥由我們的程式全自動通關**（23:43，TOTAL SCORE 8,525
  NEW RECORD、破壞 14/14 含增援、6/10 存活、受損 43%）。流水帳
  `data/runs/20260705-232132/battle_01.jsonl`（outcome battle_result）。
- 四個戰術修正實機驗證：索敵重構（1ddc407，單位改朝世界座標敵群前進）、
  死亡台詞對話自動推進（bd6b132，本場自動處理 5 次無需人工救）、
  殘機單卡辨識（#1）、戰敗畫面辨識（#2，本場贏了未觸發但已上線）。
- 中斷落地流水帳（8350f60）。

**本場暴露、已開 issue 的缺陷**：
- #14（high）索敵 fallback 過粗：鏡頭錨定每次 miss（#6）→退到全域單一朝向
  →前排/側翼單位（如 GQuuuuuuX）走離最近敵人。**最該優先修的戰術缺陷。**
- #12（high）EN 歸零不會用 SKILL/SUPPORT 補能量，直接待機（實戰確認，
  行動列的 SKILL SP／SUPPORT EN 1/1 鈕被無視）。
- ~~#15 流水帳決策事件配截圖~~（已解，da1bed3）。
- ~~#16 隱藏戰鬥 WARNING 彈窗辨識與決策~~（已解，f3ead6d）。
- #5 掃描仍低估我方/第三方（我方 10 掃到 2–6、第三方恆 0）。**#14 的根因。**

**帳號現況**：RANK 11、資金 158,380、體力 25/80。隊伍戰鬥力 111,530
（遠超 HARD 2 建議 70,000——本 session 反覆確認敗因在程式非數值）。

**下一步（依 issue 優先序）**：先修戰術三本柱 #14（索敵 fallback）、#12
（EN/技能行動掃描）、#15（決策截圖）——這三個直接決定戰術品質；再回架構
主線 #7 歸因、#8 cache、#9 OCR、#10 戰略迴圈。

## 現行計畫

架構已與使用者重新定案，全文見 `docs/agent-architecture.md`。核心原則：
程式只內建「機制」不內建「內容」；不建關卡資料庫（跨執行無狀態）；
執行輸入只有目標關卡 + 可用的局外成長 action；關內動作空間完全開放。
不做自建模擬器/MCTS——戰術用遊戲內建預測值做 1-ply 貪婪，再升 1.5-ply
站位安全；戰略靠觀測式戰後歸因決定補強方向。

實作順序（詳見架構文件）：
1. 戰鬥流水帳 + run-scoped 黑板
2. HARD 1 探測（先第 12 關回歸驗證 62bef06，再 HARD 1 收戰敗流程與錨點）
3. OCR 數字讀取（戰力/資金/預期傷害）
4. 戰後歸因 v1（數值差距 vs 程式缺陷）
5. 戰略迴圈（goal + allowed actions、強化與 farming）
6. 行動掃描器 v1（SUPPORT/技能鈕，EN 補給）
7. 1.5-ply 站位安全評估

第 12 關全流程 SUCCESS 記錄（2026-07-04 23:36）：導航→戰鬥→劇情跳過→
結算→回關卡列表全自動，戰鬥中劇情與鎖屏皆自動處理。

## 已完成

### 基礎架構（M1）
- GOAP 核心：`WorldState`（不可變、可雜湊）、`Action`（前置條件/效果/execute）、A* 規劃器（`core/planner.py`）。
- Agent 迴圈（`agent/loop.py`）：sense → plan → act → verify，含信念記憶（latch 無法直接感知的效果，如 `stage_cleared`）、「有進展就重新規劃、無進展才計失敗」的容錯策略。
- 感知/致動介面：`Perception` protocol、`AdbActuator`（landscape 2340x1080 參考座標、依實際解析度縮放）。

### 視覺辨識（M2）
- OpenCV 模板比對：manifest 驅動（`assets/templates/manifest.yaml`），16 個畫面錨點 + 約 20 個元件模板，含搜尋區域限定。
- `RecognizerPipeline`：多辨識器串接、信心度短路（為未來 OCR / Ollama LLM 辨識預留）。
- 標定工具：`scripts/capture.py`、`scripts/crop.py`、`scripts/verify_match.py`。
- 動態偵測（`vision/motion.py`）：`is_static()` 以幀差分辨可操作畫面 vs 劇情/攻擊動畫。

### 通關流程（實機驗證）
- 六個 flow action：進出擊準備 → 出擊（處理首次下載彈窗）→ 跳過劇情（MENU→SKIP，含戰鬥中劇情）→ 戰鬥等待 → 關閉結算 → 排掉獎勵鏈回到關卡列表。
- 新手教學提示框（coach-mark）以 `hint_dialog` 模板偵測並排除。
- AUTO 按鈕三態偵測（青=全自動、紅=敵回合自動、無色=全手動），argmax 模板比對。
- 導航迴圈端到端可跑；第 7~9 關已通關（但 8、9 是內建 AI 打的——這正是要修正的問題）。

## 目前問題（下一步的起點）

戰鬥階段目前依賴遊戲內建全自動 AI，違反專案核心目標：**戰鬥必須由我們的程式操作**。
已確認方向：進戰鬥後將 AUTO 切到無色（全手動），戰術 v1 用簡單啟發式。

已知技術障礙：
- 黑畫面/載入轉場輪詢太粗，錯過可操作的第一幀，內建 AI（青色 AUTO 跨關卡保留）就自己開打。
- 攻擊動畫期間 AUTO 按鈕被遮擋，probe 會回 None——讀寫 AUTO 只能在 `is_static` 的畫面上做並重試。

## 下一步：手動戰鬥控制器

1. **快速接手戰鬥開始**
   - 出擊後以次秒級間隔輪詢，穿過黑畫面/載入畫面，抓到第一個可操作的 battle_map 靜止幀。
   - 立刻把 AUTO 切到無色全手動（is_static 閘控 + 重試）。AUTO 狀態跨關卡保留，之後的關卡只需驗證。
2. **戰鬥 UI 探索與標定**（手動模式下逐步截圖）
   - 我方單位選取、移動格子、選擇武裝、目標選取、攻擊確認、待機、回合結束、單位列表。
   - 單位/敵人位置偵測可能需要顏色/blob 偵測而非模板比對（單位外觀隨編成變動）。
3. **v1 戰術啟發式**
   - 每個可行動單位：移動到最近敵人 → 攻擊 → 下一單位；無可行動單位則結束回合。
   - 全手動模式下也要推進敵方回合（點擊確認敵方行動的畫面）。
4. **整合進 GOAP**
   - 以新的 `ManualBattle` action 取代 `AutoBattle`，效果不變（battle_map → battle_result + stage_cleared），戰術細節封裝在 action 內部（或後續拆成戰鬥層子規劃器）。
5. **驗收**：第 10 關起用全手動控制器實測通關。

## 鎖屏防護（2026-07-04 完成）

Samsung 閒置約 3 分鐘自動鎖屏會吞掉所有點擊，而模板仍能透過變暗的畫面比對成功，
造成長時間戰鬥（敵方回合、劇情暫停）中途卡死——第 12 關兩次全流程測試都因此失敗。
解法（`actuation/keyguard.py`）：
- 偵測：`dumpsys window policy` 的 `KeyguardStateMonitor mIsShowing`（實機驗證可靠）。
- 解鎖：KEYCODE_WAKEUP → `wm dismiss-keyguard` → 從鎖頭圖示往上拖曳（raw 座標，不隨遊戲橫向旋轉）。
- 整合：AgentLoop 每次迭代檢查；ManualBattleController 每 15 秒檢查。
- 戰鬥逾時改為活動制：總預算 60 分鐘 + 10 分鐘無活動守門（動畫算活動）。

## 戰鬥控制器 v2 改進項目

（使用者 2026-07-04 實戰觀察提出）

- **技能與支援能力運用**：v1 只會攻擊/移動/待機。實測發現單位 EN 耗盡時，
  控制器不會使用技能或支援能力補 EN，之後只能待機。單位需要知道自己可用的輔助手段：
  - 角色技能（下中 MP 圓鈕，消耗 SP，如「強勢 DAMAGE+10%」類 buff）
  - 支援能力（下中 SUPPORT 鈕，如 EN 補給 1/1、回復 HP 1/1——EN 桶/愛心圖示）
  - 機體額外技能（武裝選擇環上的「技能」鈕、變形 MANEUVER 等）
  - 決策時機：EN 不足以發動任何武裝時先補 EN；HP 低時回復；進攻前掛 buff
- 感知需求：讀取當前單位 EN/HP 數值（OCR）或至少偵測「所有武裝都因 EN 不足不可用」的狀態
  （武器輪盤圖示灰化/紅字），以及 SUPPORT/技能鈕的可用狀態（次數、SP 量表）
- ~~**主動索敵移動**~~（2026-07-04 完成）：`battle/vision.py` 的
  `find_enemy_units`/`find_ally_units` 以單位腳下的底座圓弧做敵我判斷
  （敵=紅橘弧、我=藍弧；hue + 寬扁長寬比 blob 過濾，我方紅色機體與威脅格「!」不會誤判）。
  移動模式改為：朝最近可見敵人前進（以移動範圍質心當作自身位置代理），
  偵測不到敵環才退回威脅格質心。第 12 關實機畫面驗證 6/6 敵、4/4 友、零誤判。
  尚未處理：敵人全部在鏡頭外時需要捲動地圖索敵。
- 其他既知改進：切換目標選擇最優目標（現在只吃預設）、
  武器選擇考慮傷害/EN 效率而非固定順序

## 大方向：以「完成某一關」為 GOAP 目標的全域策略層

（使用者 2026-07-04 提出；2026-07-05 細化定案於 `docs/agent-architecture.md`，
與本節出入處以架構文件為準——特別是「跨執行無狀態、不存關卡資料」原則）

GOAP 的目標設定為「完成指定關卡」，而達成手段不只遊戲內的戰鬥執行，
還包含遊戲外的資源養成。規劃器要能判斷：目前隊伍打不過這關時，
如何用遊戲外資源（強化、開發、編成調整等）改變/強化隊伍後再挑戰。

概念上是兩層 GOAP：

- **戰略層**（新增）：世界狀態含隊伍戰力、持有資源（資金、經驗值道具、
  機體/角色清單）、目標關卡難度估計。action 例如：強化機體、開發新機體、
  調整編成、重打低難度關卡賺資源、直接挑戰目標關卡。
  「挑戰失敗」是可感知的回饋，會更新戰力估計並觸發重新規劃（先養成再戰）。
- **戰術層**（現有）：關卡內的導航與手動戰鬥控制器。

前置需求：
1. 感知隊伍/資源狀態 —— 需要 OCR（讀資金、等級、戰力數值）或 LLM 辨識，
   這會把原本延期的 OCR/Ollama 辨識器變成必要項目。
2. 標定養成相關畫面：強化、開發、編成（unit_setup 深入）、機體詳情。
3. 戰力 vs 關卡難度的估計模型（可先用「推薦戰力/敵方等級」等遊戲內顯示值）。
4. 失敗偵測：戰敗結算畫面的錨點與處理流程。

**HARD 1 實測計畫**（使用者 2026-07-04 指示）：以現有控制器挑戰 HARD 1
（建議 65,000 vs 我方約 33,000，預期失敗），觀察戰敗流程並盤點缺口。
期望方向再次確認：關卡內戰鬥真的完成不了時，要能從局外成長
（強化/開發/刷資源）想辦法完成關卡——即戰略層是硬需求，不是可選項。

## 之後（延期項目）

- Ollama 多模態 LLM 辨識器、OCR 辨識器、`recognition.yaml` 執行期組態。
- 「略過」掃蕩機制解鎖後的快速重複通關路徑。
- 更聰明的戰術（地形、射程、屬性相剋）。
