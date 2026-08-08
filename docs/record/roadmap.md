# roadmap

> Type: record—pause snapshot; replace at session end

CLAUDE.md 的開工／收工紀律綁這份檔案的暫停快照。`83fce1e` 刪掉 16 份
doc（含本檔前身）後由使用者裁決重建，範圍只有**裝置現況＋恢復點**——
規格不寫在這裡（「程式碼就是規格」）。舊快照全文在本檔的 git 歷史
（最後完整版 `66ce53c`），設計裁決在 docs/record/decisions.md。

## 暫停快照（2026-08-09 凌晨，分支 feat/stream-input；串流＋full 實測 59.8 分完整輪創紀錄）

### 恢復點

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
