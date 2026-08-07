# roadmap

CLAUDE.md 的開工／收工紀律綁這份檔案的暫停快照。`83fce1e` 刪掉 16 份
doc（含本檔前身）後由使用者裁決重建，範圍只有**裝置現況＋恢復點**——
規格不寫在這裡（「程式碼就是規格」）。舊快照全文在本檔的 git 歷史
（最後完整版 `66ce53c`），設計裁決在 docs/decisions.md。

## 暫停快照（2026-08-07 上午，舊迭代 session 已停止；rjscan 已刪除 `f4d0cc7`，串流輸入評估中）

### 恢復點

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
  批次切法：抽共用 Camera→串流幀源＋幀差收斂 settle→sweep 實機對照 0805
  run12 基準。**恢復點**：使用者裁決串流方案後開實作批次；另有「收斂到
  sweep 單流程、刪舊堆疊」與「docs archive」兩案待使用者裁。裝置現況：
  UC 關卡列表，全程棄戰資源零消耗。

## 歷史里程碑（一行一批；全文見本檔 git 歷史 `66ce53c` 與 docs/decisions.md）

- **0806 深夜**：marchkit 共用模組抽取（`0127b53`）、里程計出帳／read_frame_grid
  端點修剪／keyguard 喚醒點修（`3b0f1c1`）；裝置沒電中斷；活動關誤入事故存證。
- **0806 全日**：rjscan（名冊跳轉掃描）八輪＋點擊驗證制六輪迭代——流程穩定但
  定位鏈三題未解，最終 0807 裁定整條刪除；坑冊 docs/live-loop-pitfalls.md 留存。
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
  （docs/terminology-map.md）。
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
