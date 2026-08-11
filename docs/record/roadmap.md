# roadmap

> Type: record—pause snapshot; replace at session end

CLAUDE.md 的開工／收工紀律綁這份檔案的暫停快照。`83fce1e` 刪掉 16 份
doc（含本檔前身）後由使用者裁決重建，範圍只有**裝置現況＋恢復點**——
規格不寫在這裡（「程式碼就是規格」）。舊快照全文在本檔的 git 歷史
（最後完整版 `66ce53c`），設計裁決在 docs/record/decisions.md。

## 暫停快照（2026-08-11 下午，分支 feat/stream-input；四界先行實機蓋章——unsure 12→0）

### 恢復點（重開 session 從這裡開始）

- **0811 四界先行批入庫＋實機驗證過關**（`3366fe6` 程式碼、`c040066` 文件；
  裁示 docs/decisions.md 0811 條×2、導覽 docs/reviews/0811-border-first-review.md）：
  ①veil 硬閘——plan_window 收本幀 read_borders 暫定界（provisional_bounds
  只補帳本缺側），越界格不點不記不 chart；journal window 事件新欄位 veil。
  ②plan_pan not bounded 時界定壓過 pending。驗證輪 run 20260811-110638
  （--stream --no-early-close 全盤硬磨）：**unsure 0/500**（基準輪 12 全＝
  圖外格）、boundary E24/N0/S19/W0 與基準零誤差、veil 值（east:24／south:19）
  與最終界一致、肇事窗複現且被 veil 擋下（t=918 窗 [[-9,14],[12,21]] 只點界
  內 24 格）；taps 552（基準 579）；掃描 31.8 分 vs 基準 31.4 分——省下的
  ~72s 被東緣 reroot 循環吃掉（見下）。census 18/18＋10/10、名冊 122/124 張
  （enemy 2 張敗、名冊段本批未動）、abandon ok、scenario.json＋
  intel_report.json 落地（issues 21 筆＝既有離線配對行為）。
- **本輪新立待修**：東緣 expand_lost→reroot 循環——東界可見但票未滿期間
  plan_pan 續指 east，標記 carry 到最東緣格後推鏡重認失敗，三輪歸零返航共耗
  ~120s（t=201-368，證據 seq 見 journal；脆弱性早於本批，舊 plan_pan 同樣
  回 east）。已交 issue-writer 開案。獨立待裁案＝no_feedback 早收調參。
- **裝置現況**：stage_list（UC 系列、游標 uc_hard_1、node 544,667）、棄戰
  乾淨、無在跑程序與監控（tmux sweep0811 已結束、Monitor 已停）。

## 暫停快照（2026-08-11 清晨，分支 feat/stream-input；名冊三修全數實測過關——首份敵我全量 intel 落地）

### 恢復點

- **0811 修理批（使用者核准逐修逐測）＋四輪實測**：①修1 `34413e9`
  select_tab 改陣營鈕高亮判準（實幀量測 B-R 選中 118-150/未選 19-24、門檻
  60）＋2s 壁鐘逾時重點——敵方名冊 0→18/18，四輪連穩。②修2 `7a7b811`＋
  `6c03379` 詳情分頁點擊走 _select_detail_tab（等期望面板＋逾時重點）；v1
  raw-grab await 被 crossfade ~0.4s 中間幀假陽性騙過（run 010819 全 28 台
  假 landed 實錘），v2 改只信 settle 收斂幀後 stats0 0 敗兩輪連穩；
  roster_tab_nav 量得 tab0 首點吞點率 68%（19/28）重點 1 次全救回。③修3
  `4457b30` weapons_more 滑前數卡頭帶、<3 條跳過——ally:8 單卡機四輪
  sentinel 敗根治；卡數對帳（025113 全滑輪 --no-llm 基準 vs 035940 skip
  輪 scenario）逐台相同零漏卡。④**最終輪 run 20260811-035940 全綠**：
  census_closed 18/18+10/10、roster 124/124 failed=0、abandon ok、
  intel_offline exit 0、sweep_end 齊——首份敵我 28 台完整
  scenario.json＋intel_report.json 落地（Ollama 28 台約 99 分）。
- **本輪新立/殘留待辦**：①abandon 收尾偶發把長黑屏轉場判 unknown →
  `abandon:unconfirmed` 誤報 halt（run 002819 一次、裝置實已自行回
  stage_list）——歸 abandon 段待修。②掃描期導航活鎖保險絲又觸發一次
  （run 033941，41 把零裁決，同 171053）——既有已知偶發。③離線對帳
  issues 23 筆＝字模開頭插 1 錯型形成未配對樣板（既有已記錄行為）＋
  enemy:15 LLM 漏名 2 筆。④date_changed 跨午夜彈窗的自動恢復仍未做
  （本批手動導航復原一次：主畫面→登入獎勵×5→關卡→MAIN STAGE→UC→選擇）。
- **裝置現況**：stage_list（UC 系列、游標 uc_hard_1、node 544,667 有效）、
  棄戰乾淨、無在跑程序與監控。
- **0811 上午追加：全盤硬磨量測（使用者指示）**：`--no-early-close` 旗標
  入庫（`ed63576`，close_census 頭一道 guard、量測/首刷用）；量測輪
  run 20260811-092754＝掃描 **31.4 分**（census_closed=false、
  empty_inferred=0、盤內 500 格全實裁 472empty+18+10、taps 579、名冊
  124/124 二連全綠、abandon ok、Ollama 段手動略過）。對照早收版
  26.6-28.3 分＝**早收省 3-5 分（~12-15%）**。unsure 12 全＝南界定案前
  row-20 圖外格 no_feedback（盤外殘帳非盤內未決），對應 no_feedback
  早收調參案仍待裁。

## 暫停快照（2026-08-10 深夜，分支 feat/stream-input；名冊段回歸診斷輪定讞——三 bug 同族根因、修法待裁）

### 恢復點

- **0810 診斷批（診斷 log `34c23a6`）＋儀器化實測 run 20260810-230716
  （26.6 分、census_closed 敵 18/18 我 10/10、abandon:ok、ally 43ok/7failed、
  enemy 0 台）**。逐 bug 定罪（證據都在該 run journal 新欄位＋存證幀）：
  ①stats0 敗 6/10（上輪 9/10、競態）＝視圖切換→tab0 兩點間隔僅 0.051-0.08s
  落在動畫吞輸入窗，`_shot` 重試只重拍不重點；落地視圖 10/10 都
  stage_abilities（視圖全域記憶實錘）。②敵方名冊 0 台＝`select_tab` 判準
  `_await_screen(TROOP_INFO)` 恆真驗不出吞點；幀 00242/00244 證明 tab 點後
  3.7s 我軍仍高亮、座標 (460,600) 本身正確；敵 tab 點在上一台詳情關閉後
  0.086s 送出被關閉動畫吞掉，後續 cell 點也無效。批F 壁鐘只判「畫面有沒有
  變」補不了「動作有沒有生效」（修我方 1→10、壞敵方 1→0 的完整解釋）。
  ③weapons_more sentinel 敗（ally:8）＝該台 weapons 頁僅 1 條 header strip，
  固定 300px 滑距超捲、三攻 strips=0,0,0 不回捲。④184555 sweep_end 缺失＝
  非程式 bug（mtime 證據：in-run Ollama 組裝被中斷、20:01 另用
  build_scenario.py 補產出）；已補 intel_offline_start 事件消歧。⑤掃描期
  無回歸：上輪 aim_overruled 2/homing_lost 5 本輪 0/2＝噪音。
- **統一根因**：名冊段拿「畫面分類到位」當同步點，但分類到位≠動畫結束≠
  可收輸入；吞點後判斷讀舊狀態、重試不重做動作。修法方向（待裁不動工）：
  select_tab 改陣營鈕高亮判準＋逾時重點；tab0 點後 await stage_combo＋逾時
  重點；weapons_more 敗時回捲重滑；詳情關閉→下一動作補壁鐘下限。
- **裝置現況**：run 230716 棄戰乾淨回 stage_list（游標 uc_hard_1、node
  544,667）；離線組裝（Ollama）於 tmux session sweep_diag 內續跑中，跑完
  應見 intel_offline＋sweep_end。

## 暫停快照（2026-08-10 凌晨，分支 feat/projection-switch；單應性切換實測全數過關——25.5 分完整輪，合併待裁）

### 恢復點

- **0810 單應性切換實測 run 20260809-232449（分支 feat/projection-switch，
  `5869820`）：25.5 分完整輪、census_closed、敵 18/18、我方 10 格逐格對上
  真值、零 Halt 零保險絲、aim_failed 0、棄戰 ok**。合併判準逐項對帳（全過）：
  ①aim 拒絕率（同幀成對，507 筆）new **1%** vs old 10%；影子輪基準是
  new 15%/old 38%——切換後實際比預測更好。②殘差：new dx 中位 2.4/p95 18.7、
  dy 0.3/5.3；old dx 14.4/27.4、dy 12.4/16.0。③agent 標的第一風險（②/③
  耦合使實看漂移變大）**未發生**，回退劇本未動用。④次像素格距生效
  （world pitch 92.1/86.7 vs 舊整數 91/86），且格號零平移——boundary
  east24/south19 與歷輪一致、我方十格與真值逐格相同。⑤壁鐘 25.5 分刷新
  紀錄（歷輪 120/96/83/59.8/60.9(halt)/36.5/76.9/55.3），aim_drift 僅 3 次
  （前輪 266-819）、reroot 9 次、nav settle 總耗 6.4 分。⑥殘留：unsure 12
  全為 row-20 圖外格 no_feedback（南界目視前的已知成本，早收調參案待裁）。
- **待辦（依序）**：①**合併 feat/projection-switch → feat/stream-input 待
  使用者裁決**（判準已全數達標）。②未做項＝③座標系縫（需位置鏈整批走
  projection，缺口記 projection.py docstring）、no_feedback 早收調參、
  date_changed／游標飄移的進場恢復（歸 action 架構批）。③本輪起跑前插曲：
  重開機後遊戲落在 SD 外傳活動關難度選單（同判 stage_list、標題讀不到），
  標題複驗閘正確攔停，手動導航（主畫面→出擊 MAIN STAGE）回 UC 列表。
- **裝置現況**：stage_list（UC 系列）、游標 uc_hard_1、node 544,667 有效、
  棄戰乾淨資源零消耗、無在跑程序與監控。

## 暫停快照（2026-08-09 晚間使用者重開機前，分支 feat/projection-switch；切換批①②已入庫、實測輪未跑）

### 恢復點（重開機後從這裡繼續）

- **重開機後開工檢查（照序做）**：①實體桌面登入一次（seat0 ACL，否則 adb
  no permissions——見記憶 adb-permissions-seat0）；②`adb kill-server` 後靠
  settings.json 的 ADB_LIBUSB=1 重起，`ps -T -o spid,comm -C adb` 確認無
  device poll 執行緒；③`uv run python scripts/ensure_unlocked.py`；④probe
  確認裝置在 uc 系列 stage_list（重開機前如此，游標 uc_hard_1、node
  544,667 有效）。
- **0809 第六批（單應性切換批 `5869820`，分支 feat/projection-switch 從
  343d475 分出）**：①aim 判定已切 projection 位置空間殘差＋②錨定次像素
  格距入庫；**③座標系縫刻意未做**（單獨換算會讓格座標更錯，需位置鏈整
  批走 projection，缺口記在 projection.py docstring）。離線重放驗收：
  centred 兩 run 全帶 p95 0.0555/0.0600 格雙過線。923 tests＋ruff 過。
  **下一步＝分支上跑實測輪**（未跑）：判準用分布不用壁鐘——盯 aim_shadow
  的 new 分布（第一風險＝②/③耦合使實看漂移變大，若 |dx| 中位 >0.2 格或
  aim_drift 風暴且 aim_overruled 接不住 → 按劇本回退 fit_lines 改回整數
  格距，不准調 AIM_SLACK_PITCH）、world_anchored 的 pitch（會比舊值小
  0.6-1.1%，確認東界格號沒整體平移）、zero() 退象限窗路徑有無出現、
  aim_failed 事件（出現要留幀）。實測過→提合併回 feat/stream-input 案
  給使用者裁；翻車→分支存證不污染主線。
- **合併判準（使用者 0809 裁示）**：視最終成果有無改善再決定是否合回
  stream-input。改善的口徑＝aim 拒絕率對影子輪基準（old 38%/new 15%）、
  帳品質對真值、保險絲零觸發；壁鐘不當判準（邊際區間三樣本 36.5/76.9/
  55.3 分變異已實錘）。

## 暫停快照（2026-08-09 晚，分支 feat/stream-input；影子數據到手——單應性待切換裁決）

### 恢復點

- **0809 第五批（影子模式 `e8c4ad2`）＋收數據輪 run 20260809-173555（55.3 分
  complete、敵 18/18 我方 10/10 第三輪連續零錯帳、aim_shadow 709 筆零失敗）**：
  ①成對結果（同幀同門檻）：old dx 中位 16.6/p95 42.4 → new 8.3/26.8；dy
  12.7/19.3 → **0.3/8.7（縱軸幾乎歸零）**；同門檻拒絕率 **38%→15%（-60%）**。
  ②離線重放：新模型 centred 口徑 133305 全帶 p95 過 0.10 格；152222 差在
  **錨定格距 1px 量化**（+0.85%×19 欄≈0.16 格），換次像素格距後兩 run 全帶
  0.04-0.06 格＝dx 殘餘可歸零。③新事實三件：WorldGrid 格距參考高度＝y515
  非 650；錨定格距整數量化是 dx 殘差主源；scan_edges(rectify y650) vs
  grid.phase(raw y515) 座標系縫 ~15px 常數偏差。④**切換批（待使用者裁決）
  範圍**＝aim 期望改走 projection＋錨定次像素格距＋座標系縫統一；驗收＝
  重放 harness（已在庫）＋一輪實測分布（不用壁鐘當判準）；保險絲在位。
  ⑤壁鐘三樣本 36.5/76.9/55.3 分＝邊際區間變異實錘，切換後預期 churn 拒絕
  率砍六成起。⑥裝置：stage_list、游標 uc_hard_1、棄戰乾淨。

## 暫停快照（2026-08-09 傍晚，分支 feat/stream-input；兩小件驗證輪定讞——邊際區間才是真兇，單應性升為主線）

### 恢復點

- **0809 第四批（案二週期統一 `486acb2`→實測 16 分活鎖→回退 `443d59e`；案一
  SCREEN_CENTRE `eef94d7` 保留）＋兩輪驗證**：①run 150152（週期統一版）：
  t=238 後 anchor→aim 活鎖 12 分鐘、保險絲 41 把攔停（第二次立功）。死因
  定讞＝遠錨 mod 換週期把兩格距之差按錨距放大成 |dx| 中位 28px 系統性假
  漂移；「兩側同週期」正解＝位置空間逐線比對，歸單應性批次（教訓已入
  sweep_scan.aimed 註解）。②run 152222（回退後＋新 SCREEN_CENTRE）：76.9
  分 complete、census_closed、敵 18/18 我方 10/10 零錯帳——品質連兩輪滿分，
  但時間對 36.5 分基準翻倍。③翻倍歸因（對帳定讞）：**SCREEN_CENTRE 未定罪**
  ——按錨定來源分組的 aim 漂移中位（centre 28.8／mixed 24.0）與舊值基準輪
  （mixed 29.8）同量級，無 220px 級錯位簽名；真兇＝**邊際區間**：全系統
  aim 漂移中位 24-30px 恆貼 0.25 格門檻（~22px），nav settle 收斂率的
  run 間波動（93%→73%，同碼）把大量窗從險過翻成連敗，churn 呈倍數放大
  （aim_drift 288→819、settle 總耗 63 分）。單輪對比在此區間不可靠。
  ④結論：微調已到頭，**案三單應性接線升為主線**——它把漂移中位決定性壓離
  門檻，是唯一能出邊際區間的刀；SCREEN_CENTRE 保留（品質雙輪驗證、速度
  無罪證）。待辦另records：no_feedback 早收調參（南界前 row-20 圖外格）。
  ⑤裝置：stage_list、游標 uc_hard_1（node 544,667）、棄戰乾淨。

## 暫停快照（2026-08-09 午後，分支 feat/stream-input；36.5 分完整輪＝歷史最佳，透視量測入庫待第三步裁量）

### 恢復點

- **0809 第三批（aim 讓位 `a9265ad`＋透視量測報告 `cf7bdec`）＋實測 run
  20260809-133305：全程 36.5 分、complete、census_closed、零錯帳**。
  ①成績：敵 18/18、我方 10 格與真值完全一致（上輪錯帳未再現）、四界全定、
  棄戰 abandon:ok、零 Halt 零保險絲；census 早收豁免 23 格（roster 總驗
  一次過，peaks 111 missing 0）。歷代對照：0805 full 截圖 120 分→0807
  candidates 96 分→0808 串流 candidates 83 分退化→0809 三修 59.8 分→
  **本輪 36.5 分**。②歸因（誠實版）：讓位規則本輪 aim_overruled=0 次
  ＝保險未觸發（無北帶活鎖復發，anchor 多為 SOURCE_CENTRE 不適用），
  提速主力＝settle 修（nav 93% 收斂均 1.06s 總 15.3 分）**連帶治好
  roster 總驗**——011740 敗因確認＝target 其實一路活著，t=3402 counts
  對上後 roster_check 連兩敗（中性幀未收斂→密度峰漏單位）殺 target；
  本輪收斂幀一次過，census 早收復活，尾局豁免取代硬磨。③新量化缺口：
  unsure 16 全 no_feedback，其中 12 格＝南界目視前點到 row 20 圖外格，
  每格 ~7s 燒 ~2 分——「靜止超過實測回饋延遲 p99 即早收 no_feedback」
  的調參案已與使用者討論，待裁；aim_drift 288 次＝透視模型噪音仍在，
  歸第三步。④透視量測定讞（docs/reviews/perspective-measurement.md，
  素材含圖表腳本已入庫）：固定平面單應性、消失點與既有 PERSPECTIVE_VP_X
  =1166/K=1.10e-4 吻合、致命軸=縱線斜格（頂帶 max 0.496 格）、相位比較
  兩側週期不一致 p95 0.156 格（模型無關 bug）、SCREEN_CENTRE 實測
  (1170,553) vs 現行 (950,540) x 偏 220px。**第三步裁量選項已呈使用者**：
  A 整包單應性接線／B 先拆 SCREEN_CENTRE＋週期統一兩小件／C 緩議；
  Claude 建議 B 先行。⑤裝置：stage_list、游標 uc_hard_1（node 544,667）。

## 暫停快照（2026-08-09 清晨，分支 feat/stream-input；settle 提速＋東擴入庫，第二輪實測揭露定位鏈品質問題）

### 恢復點

- **0809 第二批（`fda7a9f`：nav settle poll 0.15＋confirm=2、TAP_REGION 東擴 2050）
  ＋實測 run 20260809-031256（60.9 分，保險絲 Halt，裝置已棄戰復原至 stage_list）**：
  ①戰果混合：東擴驗證成功（col-24 北段 7 格首次入帳）；nav settle 開局 100%
  收斂／0.77s（vs 0805 版 49%／2.89s），但全程均 1.81s／72%、呼叫數暴增至
  1137（活鎖迴圈灌水），總耗時僅 39.2→34.3 分。②帳品質退步：敵 17/18（漏的
  在未掃到的東南帶）、我方 10 正確＋**1 筆錯帳 (20,10)**＝置中反推假說鏡位
  偏一格，把已裁決的 (19,10) 同一台再點一次記成新我方；(20,9) empty 同窗
  可疑；unsure 5；65 格 pending。③兩種活鎖現形：北帶 aim 閘透視活鎖（零推鏡
  ／零 reroot，barren 絲盲區，3 分鐘自癒）；尾局東西乒乓——**PAN_BARREN_LIMIT
  絲首次實戰觸發，41 把即 Halt 存證**，取代舊日 40 分鐘空轉。④歸因：透視帶
  格網模型誤差（row_pitch 均勻假設）＋SCREEN_CENTRE(950,540) 置中期望未經
  實測校準＝定位鏈品質瓶頸；速度已不是主要矛盾。**下一批候選**：(a) 保險絲
  補零推鏡盲區（窗級水位）；(b) SCREEN_CENTRE 實測校準（本輪 recentre 幀
  可量）；(c) aim 閘透視帶處理（界線優先或 row_pitch 隨 y 建模，屬大刀）；
  (d) 置中反推錨定下的裁決應更保守（UNGROUNDED 限制已有，貼容差邊的 aim
  要不要收緊待裁）。⑤裝置現況：stage_list、游標 uc_hard_1（node 544,667）。

- **0809 歸因三修＋實測蓋章（`e694d3c`）**：①串流成效歸帳定案——20260808-184706
  的 83 分＝掃描本體 40 分＋尾局退化 43 分（roster 總驗連兩敗殺早收→追 15 格
  結構性點不到→南北乒乓 132 把耗盡 tap 預算），詳 decisions.md 0809 條。
  ②三修入庫：`--filter-mode` 預設退回 full／PAN_BARREN_LIMIT=40 無產出推鏡
  保險絲（水位＝已裁決格數，補 strandings 只數 reroot 的盲區）／settle 耗時
  入帳（SettleReport observe，journal `settle` 事件 ctx=nav/feedback）。
  ③**實測 run 20260809-011740（串流＋full＋max-taps 900）：全程 59.8 分**、
  敵 18/18、我方 10/10、unsure 1（[7,15] no_feedback）、462 空格全點擊背書、
  四界全定、零 Halt、零保險絲觸發、16 次 reroot 全自癒、棄戰 abandon:ok。
  歷史對照（同關全程壁鐘）：152346 全格截圖 120 分／111734 candidates+roster
  截圖 96 分／184706 candidates 串流 83 分退化未完。**注意：roadmap 舊載
  「run 12＝79 分」與 152346 流水帳（116 分掃描）對不上，79 分數字來源不明，
  基準以流水帳為準**。④settle 量測實錘：nav（poll 0.5s）813 次僅 49% 收斂、
  均 2.89s、**全程共燒 39.2 分＝最大剩餘成本**；feedback（poll 0.15s）554 次
  97% 收斂、均 0.57s。下一刀＝nav settle 降 poll／ROI 化，估可再砍 20-30 分。
  ⑤新發現兩缺口：東緣 col-24 九格本輪結構性點不到（窗邊切格、152346 曾點到
  ——疑 zoom/pitch 差異，待查）；跨午夜 `date_changed` 彈窗分類器認得但進場鏈
  無人處理（本輪手動排除：前往主畫面→登入獎勵×N→公告關閉→出擊面板回關卡列表）。
  ⑥裝置現況：R5CRC37JBYJ 停在 uc 系列 stage_list，游標位置＝uc_hard_1
  （node 544,667 本輪驗證有效；660,650 已飄到 uc_hard_2）。
- **0807 sandbox 前端沙盤第一階段落地（`dd81d29`，分支 `feat/sweep-nodes`）**：
  裁定入帳 decisions.md「（0807）sandbox 前端沙盤介面」條（B1 stdlib server／
  C3 擲骰／D1 手動敵方先行／undo／佔位資料／分期）。已交付：
  `sandbox/scenario.py`（sandbox-scenario/1 載入器＋`build()`＋`check_outcome`）、
  `assets/scenarios/uc_hard_1_placeholder.json`（敵 18 台格位/HP/EN 抄真值、
  樣板五份依 HP/EN 組合、我方 4 台自編佔位）、`scripts/sandbox_ui.py`
  （唯讀盤面，`--scenario … --port 8642`，/api/state 已驗 18+4 與 [9,4] 真值）。
  待辦：瀏覽器目視排版（唯一未驗項）、下一階段＝step 操作＋undo＋擲骰 C3、
  敵我完整數值等使用者另分支的搜集功能。
- **0807 上午收帳＋方向轉換（分支 `feat/sweep-nodes`，工作樹乾淨）**：
  ①**遺失 session 事故**：8/6 起的迭代 session 在 claude code／remote control 介面
  消失但程序仍在跑（持續發 DC 通知），已定位（transcript `13e3eb9f…`）並手動
  kill（PID 2245525）。它的改動全數已 commit，無未入庫殘留。②**run 20 成績**
  （`data/runs/20260807-081538`，49 分鐘完整輪＋乾淨棄戰）：落帳 12/28、零錯帳
  （敵 8 我 3 全對真值）；里程計出帳修正實戰過關；march_inconsistent 15 次全數
  寧可不出帳。未解主因＝`carry_failed` 58 次：底緣透視斜格＋紫色星球徽章污染
  填色驗收簽名。③**rjscan 刪除定案**（`f4d0cc7`：腳本＋jumpscan/roster 模組
  ＋名冊 intent 白名單收回；marchkit 保留給 sweep 接線；還原點 `46ffb06`）。
  ④**方向轉換（使用者 0807 裁示）**：不再用 adb 截圖，研究串流擷取＋已驗證的
  sweep 版本。評估結論：擷取單點在 `runtime/device.py` `Adb.screencap()`＋
  sweep_scan 腳本內 `Camera`；`battle/frame_source.py` 的 FrameSource 是離線
  重放抽象，活體幀源（最新穩定幀）待建。scrcpy 走現有 adb 授權免手機操作；
  候選＝scrcpy+v4l2loopback（主機裝 kernel module）或 py-scrcpy-client。
  批次切法：抽共用 Camera→串流幀源＋幀差收斂 settle→sweep 實機對照。
  ⑤**收斂到 sweep 單流程（使用者裁決後執行）**：舊堆疊 130 檔 28.8k 行刪除
  （`1791aee`，導覽 docs/reviews/sweep-convergence-prune.md）、被取代文件
  16 檔搬 docs/archive/（`9726d49`）、roadmap compact、CLAUDE.md 同步。
  **刪後實機驗證過關**（run `20260807-111734`，~75 分鐘完整輪）：敵 18/18
  全中零錯帳、我方 10/10、四界全定、零 Halt、棄戰 ok 資源零消耗——能力與
  0805 run12 基準同級。過程雜訊：rezeroed 11、inference_retracted 176
  （候選峰不穩翻案重點，機制自行消化）、省電鎖多次觸發 keyguard 皆解。
  另：凍機案結案＝Linux adb 預設 USB backend bug，ADB_LIBUSB=1 根治
  （記憶已更新）。**改善佇列（0807 驗證輪對帳定案）**：①跨窗候選峰不穩
  ——candidates 模式首次實跑 230 筆 inference_retracted（193 格、220 筆
  seen_again＝A 窗非候選 B 窗又是），只耗時不吃正確性（召回離線已證 100%）；
  候選解法＝峰偵測穩定化或帶高亮/乾淨雙幀聯集。②candidates 提速未兌現
  ——點擊 366（full 模式 498）反而 97 分 vs 79 分：翻案重點吃回節省＋省電鎖
  多次打斷；先量化單 tap／單 screencap 往返成本再裁。③盲睡 settle
  （PAN_SETTLE_S=1.5 等常數）＝節奏地板，歸串流批次的幀差收斂解。④省電鎖
  打斷頻率偏高，keyguard 偵測時延也綁截圖往返，同歸串流改善。**恢復點**：
  使用者裁決串流方案（scrcpy+v4l2loopback vs py-scrcpy-client）後開實作
  批次。精簡第二波完成（`a8c772f`）：舊代 uiautomator2 通道退場
  （app/perception/actuation 整包）、capture/ensure_unlocked port 到
  runtime 通道實機驗證過、孤兒 fixtures/模板/ollama extra 清除；
  uiautomator2 依賴剩 sweep_scan pinch 單點（純 adb sendevent 替代可另評）。
  **精簡第三波（0807 午後）**：本地資料清理約 9G（run-shots 全刪、
  screenshots 七月檔留 5 張測試樣本、runs 七月封存 183 檔、
  review-repros／stress-test）；probe_marker＋overlay_lattice 刪
  （`3df6e28`）；**sim/ 整包退場**（`2e1e8c2`，使用者裁決）——sandbox
  為交戰引擎超集，tension／objective 不搬：MP 機制明定 C2 打表後於
  sandbox 重做（mp-tension.md 檔頭）、估值屬 solver 職責（decisions.md
  0807）。**docs 整理批（`62d3deb` 止）**：稽核 21 份→六份搬 archive
  （module-map／2d-closeout-review／scan-v3-review／battle-settings-ui
  ／ui-navigation-map／sweep-node-expansion）；ui-spec.md 成立；
  live-loop-pitfalls 重寫 14 條規則體（每條附現行程式基質）；
  battle-prep-ui／intel-data-spec／architecture 加現況註記。
  **紀錄紀律（使用者 0807 指正，已入記憶）**：記錄裁示禁抽象化、用
  顯式工程敘述原話優先；盤點類指示交報告為止、動工另拿授權。
  待裁：①面板數字讀取鏈（parse_panel＋extract_*＋runtime 三模組＋
  stage/intel*＋roster_panels 39M）與 assets/catalog 去留 ②manifest
  工具鏈已判留（sweep_scan 現用 TemplateManifest）③data/cache 刪除
  ④game-mechanics 三合一合併案 ⑤sweep as-built 規格補寫。
  GitHub Issues 待程式進度再更新（使用者裁示）。
  裝置現況：UC 關卡列表，全程棄戰資源零消耗。

## 歷史里程碑（一行一批；全文見本檔 git 歷史 `66ce53c` 與 docs/record/decisions.md）

- **0806 深夜**：marchkit 共用模組抽取（`0127b53`）、里程計出帳／read_frame_grid
  端點修剪／keyguard 喚醒點修（`3b0f1c1`）；裝置沒電中斷；活動關誤入事故存證。
- **0806 全日**：rjscan（名冊跳轉掃描）八輪＋點擊驗證制六輪迭代——流程穩定但
  定位鏈三題未解，最終 0807 裁定整條刪除；坑冊 docs/how-to/live-loop-pitfalls.md 留存。
- **0806 凌晨**：部隊資訊探針五題定讞（名冊表列／詳情乾淨數字／跳轉行為）；
  真值檔 uc_hard_1.json 使用者校對完畢。
- **0805 全日**：**sweep 12 輪收官＝現行基準**——第 12 輪完掃 79 分鐘、敵 18/18
  全中、四界全定、零 Halt；候選過濾召回 100% GO、candidates 轉預設。待修遺留：
  數字字模三連環、選關右欄驗證、棄戰誤報 unconfirmed。
- **0805 深夜~晨**：sweep v2 信任節點擴張入庫（docs/sweep-node-expansion.md）
  ＋四批修復（棄戰閉環、到邊語意、返航死迴圈、相位包裝翻案）。
- **0804**：sweep 首版入庫（每格點擊清算、`runtime/sweep.py`）；標記格定位批
  ＝首次 coverage=1.0（第 11 輪）；覆蓋模型 v3 as-built（runtime/coverage.py）。
- **0803**：掃描 v3「位置一律來自畫面內容」入庫＋角落錨定接線（第 10 輪五次
  歸零全錨定）；終止邊投影校正；停滯誤判修正；術語全庫清理
  （docs/reference/terminology-map.md）。
- **0802**：流水帳回放工具 scripts/replay_run.py；鑑識三翻案＋v2.9 作廢＋
  v2.10 入庫；使用者定 v3 方向。
- **0801**：覆蓋模型 v2 複驗 1-6 輪＋v2.1~v2.8 逐批修復（水平定位中斷軸完結、
  重複吸收軸實質解）；結束回合鈕標定。
- **0730 以前**：批 0~2d 全入庫（GOAP 骨架、面板解析三通道、runtime 實機通道、
  符號掃描）；2d 實機驗證輪十點全過；棄戰零消耗多度實證；UC HARD 1 敵情與
  型錄入庫。里程碑（使用者設定）：用蒐集情報評估最高勝率隊伍，二輪起以高評價
  完成 UC 全系列 HARD（4 關）。
- 雜項紀律：首次真跑 `python -m ggge_ai`（無 --run-dir）會把 data/runs 舊目錄
  一次性全壓縮（刻意行為）；遊戲登入逾時錯誤 300 恢復流程＝標題→下載→登入
  獎勵→公告→主頁；鎖屏靠 scripts/ensure_unlocked.py。
