# roadmap

CLAUDE.md 的開工／收工紀律綁這份檔案的暫停快照。`83fce1e` 刪掉 16 份
doc（含本檔前身）後由使用者裁決重建，範圍只有**裝置現況＋恢復點**——
規格不寫在這裡（「程式碼就是規格」）。

## 暫停快照（2026-07-30 16:00，API 過載中斷點——使用者指示統整
待命，重啟時間由使用者決定）

### 中斷點與重啟指南

- **0731 增補：2c-2d review 使用者裁定完成**（四條，備案
  decisions.md 0731＋reviews/2c-2d-review.md 審後裁定節）。
  程式改動兩筆：①爭點 4 否決：end_turn 反射拆除 `4d3f381`
  （對話框應答歸未來結束回合行動，標定座標停放
  stage/gestures.py）；②爭點 1 追問引出**自動編制位置勘誤**
  `5c0b6c9`——使用者一手記憶推翻 0730 標定（實在出擊鈕左邊
  (1496,1010)，(2001,924) 為空星空），新增 auto_deploy 帶、
  top_right_confirm 改名 bottom_right_confirm，殘留風險三筆見
  decisions.md。pytest 1447 passed／3 xfailed、ruff 綠。
  重啟佇列不變：修正批 → 覆蓋模型 v2。
- **中斷原因**：Anthropic API 大範圍 529 過載（官方事件「Elevated
  errors across many models」），修正批連五次派工早夭（三次
  opus＋兩次非 opus）。主 session 存活、主分支乾淨。
- **重啟第一件事＝派「驗證輪修正批」**（code-editor worktree，
  opus 恢復就用 opus）：五項規格＝①pinch 搬遷＋zoom_out 注入
  ②dry_run_entry 幀源統一（Camera/Perceiver 兩套真相）③格線
  設定頁探針降 advisory、地圖地面真相升唯一判準 ④select 明示化
  （--stage-node 必填＋右欄截圖入 journal）⑤survey-ticks 預設 40
  ＋unlocalised 入 survey_summary。細節：roadmap「2d 實機驗證輪
  完成」條＋decisions.md；實測證據 data/runs/20260730-13*~14*。
  派工時注意告知：覆蓋模型 v2 是下一批，別加深方向腿數耦合。
- **修正批入庫後＝派「覆蓋模型 v2 批」**：完整派工規格已定案
  `docs/survey-coverage-v2.md`（0730 使用者三輪問答核可：四態
  知識圖＋前緣探索＋邊界旗＋五層量測防禦＋衰效降級）。
- 之後：掃描複驗輪（live-tester）→ 2e 首戰。
- 裝置現況：R5CRC37JBYJ 在線、遊戲停 UC 關卡列表（右欄 HARD 2
  ——注意棄戰游標飄移陷阱，重入必明示選關）、EN 161/111、
  資金 1,255,000。鎖屏靠 scripts/ensure_unlocked.py。

## 舊快照（2026-07-30 10:00 更新，批 2c 派工進行中）

### 裝置現況

- 手機：遊戲停在 UC 關卡列表（右欄 HARD STAGE 2）。**EN 161/111
  （超上限）、資金 1,255,000、鑽 2,600、RANK 26**。adb 健康
  （ADB_LIBUSB=1、無 device poll、seat0 正常）。
- **0730 對帳定讞：AUTO 誤啟的 UC HARD 1 自動打完獲勝**——關卡
  列表 HARD 1 掛 CLEAR（達成 2/4）、HARD 2 解鎖（建議戰力
  170,000）。資源差（使用者說明）：**EN +50＝使用者中途手動解
  每日任務的回報**；資金 +270,500 含 HARD 1 首次通關獎酬與使用者
  手動領取，比例未拆分、無懸案。
- 5 秒鎖屏未改系統設定：`scripts/ensure_unlocked.py`（包既成
  Keyguard）每段互動前跑一次即可，實戰驗證通過。
- 重連跳「允許存取手機資料嗎？」USB 彈窗＝按拒絕（備案
  decisions.md）。

### 恢復點

- 分支 `feat/inner-goap` @ 2a3fd27。pytest 1140 passed／3 xfailed、
  ruff 綠（既知 flaky 偶發、單跑綠）。
- 批次進度：**批 0／1a／1b／1c／2a／2b-1／2b-2 全入庫**。
  2b-2 重跑輪 0730 完成：全步驟過關、零資源消耗（**棄戰不耗
  AP／挑戰次數／EN 實證**）；樣本 12 張新增入 stage_panels/
  （AUTO 三態、關卡內敵我四分頁詳情組、格線 ON 地圖）；AUTO
  開關 (1815,52) 三態標定、出擊 (1930,970)／自動編制陷阱、
  TAP TO NEXT 陷阱、放棄流程全入 ui-navigation-map.md 與
  battle-settings-ui.md；次數欄位定讞入 intel-data-spec.md
  （CS 徽章、支援＝資格旗標無數字、彈藥欄關卡內缺樣）。
  站位普查 12–15/18（±1 格）收蒐樣級，權威站位歸批 2d 程式
  掃描（備案 decisions.md）。
- **批 2c 入庫**（b24543e）：面板解析三通道（數值字模／徽章
  模板／封閉 schema LLM，預設 gemma4:31b）＋intel_panels 組裝＋
  parse_panel.py。遺留：能力整區 LLM 通道不可信（要確定性切分）、
  強化頁能力分頁零樣本、關卡內彈藥欄缺樣、CS 多徽章排列未驗、
  accuracy=命中%−100 待 forecast 對帳。
- **批 2d 入庫**（0730 合併，全套 1419 passed）：runtime/
  {screens,keyguard,board,entry,reflexes}＋device/perceive 實機
  通道＋stage/{gestures,survey}＋intel 型別擴充（pilot 三值、
  武裝類別集合、crit_pct、LV/SP；MP/faction 走 dynamics 不進
  cache）。掃描＝符號行動（ShowGrid 供給 grid_on、SurveyBoard
  前置 grid_on、恢復式微步驟、CoverageLedger＋StageState.swept/
  board_synced 雙層簿記、敵回合 expire＋generation 換代）。
  設計決定 16 條整批接受（decisions.md；pinch 延後、卡條收合
  建模傾向比照 grid_on 待使用者裁）。**唯讀探針實機已過**
  （原生幀直通 2340x1080 ✓）。
- **2d 遺留（2e 前置）**：Move/Attack/Inspect/Standby 執行 plan
  未接（需單位↔螢幕點對位）；LivePerceiver.reader 未注入
  （Observation.state 實機恆 None，符號讀取歸 2e）；pinch／
  zoom_out 注入點留白。
- **2d 收尾小批入庫**（0730 合併 1458 passed＋scripts 清理
  7e006ad）：收卡條符號化（CollapseRoster＋SurveyBoard 雙前置；
  roster_collapsed 感知權威、None 永不折成收合；Inspect 效果
  作廢卡條）＋三彈窗簽名解封（全語料 1002 張零誤命中；公告
  近全黑載入空窗仍缺樣回 unknown）＋stage_list 簽名＋
  scripts/dry_run_entry.py（分段停點 select/prep/stage_info/
  map/grid/survey，expect 失敗即停；用法見 docs/reviews/
  2d-closeout-review.md）。scripts 刪 11 支＋孤兒測試、
  CLAUDE.md 常用指令同步（備案 decisions.md）。實機待驗：
  ROSTER_TOGGLE_TAP (1970,780)、STAGE_LIST_PREP_TAP (2035,880)、
  STAGE_INFO_ADVANCE_TAP (1170,780)、卡條換回合是否彈回、
  掃描 20-tick 行為（最大未驗風險）、關卡節點 (544,872) 落
  放棄危險帶（點編號列 y~667 繞開）。
- UC HARD 1 敵情（沙盤先驗素材）：破壞數目標 0/18；薩克群
  6–8＋帶盾精英＋散兵 2；北帶克斯希雅 2–3＋**boss 獨角獸鋼彈
  （巴納吉，可奪取，分數檔 4,000/7,000/10,000）**；西南大型
  殘骸艦地形無單位；詳 map_scan_*.png 與 live-tester 0730 報告。
- 型錄：`_series_index.json`（19 系列、UC=index15）＋初鋼／Z ANT／
  UC 全深度入庫 assets/catalog/；其餘系列與永恆之路待補掃。
- 里程碑（使用者設定）：用蒐集情報評估最高勝率隊伍，二輪起以
  高評價（保守解讀＝三星 COMPLETE，備案待推翻）完成 UC 全系列
  HARD（4 關）。決策自裁授權：保守預設＋逐筆備案 docs/decisions.md；
  需要使用者時 discord-notify。
- **2d 實機驗證輪完成**（0730 晚，run 目錄 data/runs/20260730-
  134751~140043）：A–J 十驗證點全過或部分過、八段 EN 帳全對齊
  零消耗；stage_list 簽名 0.99 穩定、進場閘門四輪一次到位、
  AUTO 讀值與肉眼一致、TAP 點周邊無元件、棄戰座標中、收卡條
  tap 生效且跨戰鬥持續。**發現待修**：①掃描無縮小 20 tick 掃出
  0 cell（東西各燒滿 8 腿未到邊）→ pinch 裁定推翻改搬遷；
  ②dry_run_entry 的 Camera/Perceiver 幀源不一致（邊界存檔是
  陳舊幀，journal 結構化欄位才可信）；③設定頁格線探針兩輪
  unverified（地面真相複驗皆過，疑截圖早於動畫）；④棄戰後
  游標飄移陷阱（已入 ui-navigation-map）；⑤unlocalised 出現
  1 次（fail-soft 正確，觀察中）。
- 下一步順序：①驗證輪修正批（進行中：pinch 搬遷＋幀源統一＋
  格線探針降級地面真相＋select 明示化＋掃描預算調整）②覆蓋
  模型 v2 批（0730 晚使用者定向，module-map 批 2d 條：世界空間
  四態知識圖＋缺口導向平移＋衰效降級 stale 不抹除＋縮小降級為
  最佳化）③掃描複驗輪 ④2e 首戰 UC HARD 1（符號讀取注入、
  單位↔螢幕對位、陣營證據分層、Move/Attack/Inspect plan）。
- 注意：首次真跑 `python -m ggge_ai`（無 --run-dir）會把 data/runs
  舊 run 目錄一次性全壓縮——刻意行為，勿在意外時機觸發。
