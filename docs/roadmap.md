# roadmap

CLAUDE.md 的開工／收工紀律綁這份檔案的暫停快照。`83fce1e` 刪掉 16 份
doc（含本檔前身）後由使用者裁決重建，範圍只有**裝置現況＋恢復點**——
規格不寫在這裡（「程式碼就是規格」）。

## 暫停快照（2026-07-30 07:30，使用者重開電腦收工）

### 裝置現況

- 手機（不受電腦重開影響）：遊戲停在主畫面、畫面變暗（省電觸控鎖
  疑掛上）、無彈窗（assets/screenshots/20260730-072407.png）。
  EN 111/111 滿、資金 984,500（偵察輪前 982,500，差 +2,000）——
  **UC HARD 1 的 AUTO 誤啟戰鬥結局未確認**（可能自動打完領獎、也
  可能棄戰退還），重連後第一件事＝對帳：關卡列表 HARD 1 星數／
  評價有無變化＋資源差異記錄。
- 系統鎖屏 5 秒重鎖（lock_screen_lock_after_timeout=5000）實測會
  吞 tap；舊 `actuation/keyguard.py` 有既成解法，下輪偵察前先接上
  （或請使用者調長 timeout）。
- 電腦重開後：adb 依紀律 `ADB_LIBUSB=1` 起 server＋`ps -T` 驗無
  device poll 執行緒；**開機後 no permissions 需實體桌面登入一次**
  （seat0 ACL）。

### 恢復點

- 分支 `feat/inner-goap`。`uv run pytest -q` 1140 passed／3 xfailed、
  ruff 綠（`test_not_actionable` 歷史 flaky 偶發、單跑綠）。
- 批次進度：**批 0／1a／1b／1c／2a 全入庫**；2b-1 機隊蒐樣入庫
  （tests/fixtures/vision/roster_panels/ 18 張＋intel-data-spec
  修訂：反応＝駕駛員專屬、射擊／格鬥拆分、支援防禦上限關外可推）。
  **2b-2 偵察輪未完成**：先被 AUTO 誤啟（指示寫「不碰」而開關沿用
  前態——已定則改「主動確認 OFF」）、再被 5 秒鎖屏連環阻斷，
  agent 已停；**部分樣本已搶收入庫**（tests/fixtures/vision/
  stage_panels/ 10 張：Geara Doga 與 Kshatriya 各三頁詳情組、
  出擊準備、關卡資訊條件頁、戰場地圖）——但 AUTO 事故輪拍的樣本
  僅當格式參考，站位全覽與次數欄位確認仍待重跑。
- 重跑 2b-2 的規格要點全在文件：進戰鬥檢查清單（AUTO=OFF＋格線
  ON＋入圖複核，ui-navigation-map.md）、盤面全覽站位掃描（全單位
  格座標＋地圖邊界）、逐敵三頁詳情＋次數欄位確認、AUTO 與格線
  開關標定、棄戰流程實測。live agent 派工鐵則：只准寫
  assets/screenshots/ 與 tests/fixtures/，禁止寫程式。
- 型錄：`_series_index.json`（19 系列、UC=index15）＋初鋼／Z ANT／
  UC 全深度入庫 assets/catalog/；其餘系列與永恆之路待補掃。
- 里程碑（使用者設定）：用蒐集情報評估最高勝率隊伍，二輪起以
  高評價（保守解讀＝三星 COMPLETE，備案待推翻）完成 UC 全系列
  HARD（4 關）。決策自裁授權：保守預設＋逐筆備案 docs/decisions.md；
  需要使用者時 discord-notify。
- 下一步順序：①重連對帳 ②重跑偵察輪（帶全部修正）③2c 解析方法
  裁定（roster_panels 已有、stage_panels 待收）④2d 實機通道
  （module-map 批 2d：LivePerceiver／LiveExecutor、反射組、程式版
  進場閘門、盤面全覽掃描）⑤2e 首戰 UC HARD 1。
- 注意：首次真跑 `python -m ggge_ai`（無 --run-dir）會把 data/runs
  舊 run 目錄一次性全壓縮——刻意行為，勿在意外時機觸發。
