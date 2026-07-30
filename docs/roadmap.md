# roadmap

CLAUDE.md 的開工／收工紀律綁這份檔案的暫停快照。`83fce1e` 刪掉 16 份
doc（含本檔前身）後由使用者裁決重建，範圍只有**裝置現況＋恢復點**——
規格不寫在這裡（「程式碼就是規格」）。

## 暫停快照（2026-07-30 10:00 更新，批 2c 派工進行中）

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
  （Observation.state 恆 None，符號讀取歸 2e）；三彈窗簽名缺樣
  ——LOGIN BONUS 本機有 sample-login-bonus-20260729.png、日期
  彈窗疑在 assets/screenshots/20260730-00xx 序列，入 fixtures
  ＋建簽名是下輪小批；實機驗證清單 12 項見 2d 交付報告（①原生
  幀已過，⑤進場乾跑⑧掃描 20-tick 需先寫駕駛 script）。
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
- 下一步順序：①2d 實機驗證輪（先寫進場乾跑＋掃描駕駛 script，
  live-tester 按 2d 交付報告 12 項清單跑）②彈窗簽名補樣小批
  ③2e 首戰 UC HARD 1（符號讀取注入、單位↔螢幕對位、陣營證據
  分層、Move/Attack/Inspect plan）。
- 注意：首次真跑 `python -m ggge_ai`（無 --run-dir）會把 data/runs
  舊 run 目錄一次性全壓縮——刻意行為，勿在意外時機觸發。
