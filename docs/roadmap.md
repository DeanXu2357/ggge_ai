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
  170,000）；資金 +270,500＝首次通關獎酬（入帳時點在 07:24 快照
  後，疑重獲焦點才結算同步）。
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
- **2c 解析方法已裁定**（decisions.md）：混合式——數值欄數字
  字模模板匹配＋固定徽章小模板＋自由文字本地視覺 LLM（ollama
  gemma3:27b）＋型錄白名單對齊。**2c 解析器實作已派 code-editor
  （opus worktree）進行中**，交付：runtime/ 解析模組＋字模模板
  ＋fixture 釘死測試＋scripts/parse_panel.py。
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
- 下一步順序：①2c 解析器收工驗證入庫（worktree 交付審查）
  ②2d 實機通道（module-map 批 2d：LivePerceiver／LiveExecutor、
  反射組、程式版進場閘門、盤面全覽掃描）③2e 首戰 UC HARD 1。
- 注意：首次真跑 `python -m ggge_ai`（無 --run-dir）會把 data/runs
  舊 run 目錄一次性全壓縮——刻意行為，勿在意外時機觸發。
