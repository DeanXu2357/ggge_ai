# roadmap

CLAUDE.md 的開工／收工紀律綁這份檔案的暫停快照。`83fce1e` 刪掉 16 份
doc（含本檔前身）後由使用者裁決重建，範圍只有**裝置現況＋恢復點**——
規格不寫在這裡（「程式碼就是規格」）。

## 暫停快照（2026-08-02，v2.1–v2.10 全入庫＋鑑識三翻案；v3 提案待使用者核可）

### 恢復點

- **0802 流水帳回放網頁工具入庫**（`fa04b56`，1621 passed／4
  xfailed；純新增不動既有進度）：`uv run python scripts/
  replay_run.py [run|tar.gz|名稱]` 起本機網頁逐筆回放 run 紀錄
  與留存幀，投影片（前後翻＋只停有幀）／條漫（全列直欄）雙模
  式。回放單位＝entry 逐筆（不做 tick 分組，decisions.md 0802
  一條）；導覽 docs/reviews/replay-run-review.md。裝置現況不變
  （本批未碰實機）。

- **0802 鑑識三翻案＋v2.9 作廢＋v2.10 入庫＋使用者定 v3 方向**
  （`e503d50`，1603 passed；全文 decisions.md 0802 五條）：離線
  鑑識定讞「致動雙態不存在」（53 次平移全部推動畫面 97-107%、
  手勢被吃 0 次）＝拖曳假說與競態假說同證偽、v2.9 四 commit 作
  廢；死因＝量測層投票分桶錯誤＋稀疏區證人不足；85 台=29 個真
  實實體（≈真值 28）沿座標誤差階梯拖影。v2.10（投票聚類修正＋
  地圖邊緣位移當量測依據＋停滯判定須影像佐證＋儀器化）重放對
  照：量測失敗 23→5、救回 18、錯誤寫入 6→0、同時點單位 79→
  39。**使用者裁示：逐步指定移動距離的做法先天不穩→v3 重設計
  「位置一律來自畫面內容」提案已寫（docs/survey-anchor-v3-
  proposal.md），核可前不動工**；C4 指令兜底否決；v2.10 三爭
  點併入 v3。另：說明文字禁英文直翻術語（腿/包絡等）與縮寫。

- **0801 第 6 輪＋v2.7＋v2.8 入庫**（`acbf59d`/`d8d40b2`，1597
  passed／4 xfailed；判讀與裁決全文 decisions.md 0801 午後/傍
  晚/晚三條）：第 6 輪座標重複吸收軸實質解（紅 17/18、merge 全
  包絡、無邊界暴衝；**遊戲更新 2.4.1** 插曲已處置）；佔位假峰
  鑑識＝3 船體＋2 HUD 鈕（誤判幀入 fixture wreck_*）；**密度上
  限判別式被校準數據證偽（反向）**；**掃不完＝致動層**（18/18
  斷鏈腿真位移僅指令 6-29%、橡皮筋；37 腿東西震盪 clamp 0/37
  攔不到）。v2.7＝measure_pan 接象限窗＋fixture＋校準表；
  v2.8＝目視終止邊 clamp＋HUD 兩鈕挖洞（左上洞代價備案、觸發
  器＝第 7 輪西北退休暴增改只留右上）＋船體假峰裁定留 2e
  phantom-drop。**still-witness k=0 回收使用者裁示緩收**。
  reset 成因鏈＝ISLAND_BUDGET 耗盡 relocalise 無解、旗跨 reset
  遺失未治（等實機資料）。

- **0801 使用者診斷解除停工＋v2.6 四件套入庫**（`27f6e12`，
  1587 passed／ruff 綠；裁決全文 decisions.md 0801 使用者診斷/
  追問/v2.6 三條）：使用者親看幀定調「同場景被當不同區域重複
  吸收」＋兩追問釘死缺口（covered() 純幾何星空蓋 EMPTY、四態無
  「是不是格子」、邊界推論制偏離目視教義）。v2.6＝①影像複驗閘
  （逐精靈窗，星座票與合併 delta 須勝原地假設）②邊帶格線
  fallback（象限窗補相位閘死區）③merge delta 包絡閘（Island.
  lost 跨島累加）④格子存在遮罩（EMPTY 毯要格線背書）＋格線終止
  邊界目擊（目視定旗、edge_mismatch 隔離不改旗）。**74 幀實幀
  重放：7/74 裁決改變全數為目標（t11/t12 真滑動、t24 幽靈票）、
  零誤殺、零假邊**。導覽 docs/reviews/scan-v2_6-review.md。

- **0801 第 5 輪判定＋停工（已解除）**（run 20260801-080213；判讀、鑑識
  線索與候選方向 A/B/C 全文 decisions.md 0801 第 5 輪條）：
  W1 PASS（帳面一致、裁剪生效）／**W2 FAIL：80 台 vs 期望 28**
  ＝台數軸連兩次針對性修正未解，**依紀律停工、discord 已通知
  使用者**。根因假說＝同型單位編隊的星座 alias 讓 relocalise
  錯位重錨（merge delta +273×4、(546,−670) 出格、邊界撐到
  48 欄）。**恢復點：使用者裁示方向（A merge delta 包絡閘／
  B relocalise 眾數邊際／C 丟棄不合併）後派 v2.6**；斷鏈軸
  已完結（第 4 輪 broken 18→0）不受影響。

- **0801 第 4 輪決勝過關＋v2.5 入庫**（run 20260801-071055；判讀
  全文 decisions.md）：**水平斷鏈軸完結——東西向 broken 18→0**、
  lattice:constellation 通道實機接通（保留觀察：9/13 水平腿退
  舊路徑、lattice:phase 零出現）、增益 0.44→0.75 爬升。V5 台數
  FAIL 定位第二軸：cells 84 vs census 55 vs 期望 28、29 筆在東
  界外＝邊界定案/重錨後 marks 不裁剪。**v2.5 入庫**（`d056004`：
  fix_boundary 裁剪線外知識＋units/sightings bounded 界內＋
  merge delta 遙測；1571 passed／ruff 綠；設計決定 10 條備案，
  導覽 docs/reviews/scan-v2_5-review.md）。

- **0801 複驗輪第 2 輪**（Phase A run 20260801-042733、Phase B
  20260801-044436-phaseB；判讀與鑑識全文 decisions.md 0801 條）：
  A1/A4 PASS（29 腿 synced、四旗全定）、expire 語意實機驗證、
  **結束回合鈕標定完成**（(300,185)→(997,562) 待機並結束→
  (1365,850) 執行）、應戰彈窗 18 連發正確應答、卡條不彈回。
  三定讞：A6 漏記＝absorb 無條件覆寫（偵測器單幀 23 目擊 vs 最
  終記 10）、增益學習死鎖（0.5×wanted 保護恆真）、東緣橡皮筋
  回彈由 STALL 吸收不修。**水平向斷鏈根因未定**（37 次幾乎全
  east/west、靜止閘 waits 全=1 滑行假說出局）→v2.3 補 BROKEN
  存證待第 3 輪資料定讞。**v2.3 入庫**（`fb2f806`：absorb 同代
  UNIT 滯後＋增益入帳 ACCEPTED≥40px＋BROKEN 幀對存證〔上限 20〕
  ＋--dump-survey-frames＋synced 提前結束；1547 passed／ruff 綠；
  設計決定 20 條＋六爭點裁決備案 decisions.md，導覽
  docs/reviews/scan-v2_3-review.md）。注意：兩輪
  --stage-node 544,667 實際打的都是 UC HARD 1（截圖證實），
  map_scan 基準有效。

- **0801 掃描複驗輪第 1 輪 Phase A FAIL＋診斷定讞**（run
  data/runs/20260801-033746；判讀與 v2.2 裁決全文 decisions.md
  0801 條）：40 tick 不夠、36% 腿數 BROKEN(phase) 斷鏈＝pan 慣性
  滑行殘餘落進相位閘窗口（22.5–40px）；恢復機制（島嶼＋relocalise
  整欄修正）照設計運作。Phase B 未跑（依規格跳過）；結束回合鈕
  目視 (300,185) 待 tap 覆核；棄戰零耗三度實證；裝置收尾乾淨。
  **v2.2 入庫**（`94fa54a`：靜止閘 measure_shift 判準＋逐
  observe 遙測 survey_tick＋SURVEY_TICKS 80；coverage.py 零改動；
  1525 passed／ruff 綠；設計決定 16 條＋五爭點裁決備案
  decisions.md，導覽 docs/reviews/scan-quiescence-v2_2-review.md）。
  **紀律：下一輪複驗同款斷鏈簽名再敗＝連兩輪，停下問使用者。
  驗收標準＝斷鏈率降到個位數（非零）；首要觀察 settle.waits
  分佈。**

- **0801 v2.1 修正批入庫**（`42d8f77`，六 commit fast-forward；
  opus worktree 交付、主 session 親審）：①legs 保險絲改單回合
  上限（expire/reset 歸零、_abandon 不歸零）②`_whole_columns`
  只吸附欄、列保留 relocalise 原值（y 無相位閘）③島嶼釘軸連兩
  次停滯＋pins 過 `_agrees` 支持數複驗④pocket 退休改離質心最近
  成員格、一次一格⑤reset/_abandon 清 clamps ⑥`Island.sightings`
  近鄰去重。迴歸測試 11 條（未修碼 10 條 FAIL 實測）；主 repo
  閘門親跑 **1521 passed／3 xfailed、ruff 綠**。導覽
  docs/reviews/coverage-v2_1-fix-review.md；設計決定 15 條＋三
  爭點裁決備案 decisions.md 0801 條（要點：稀疏島重錨變嚴＝誠實
  但貴，成本歸複驗輪量測；repro2 非判別性，半列情境歸實機收）。
  孤兒 worktree 三個核對後全清（皆已合併）。
- **0731 深夜重審定讞**（使用者指示 re-review）：主 session 親審
  ＋對抗性 reviewer 雙軌、四支復現腳本親跑證實（data/
  review-repros-20260731/；repro3c 因 `_pin` 簽名改變已 TypeError
  ＝凍結證據，勿當回歸跑）。六缺陷全數已修（見上條）。
- **待使用者裁**：v2 的 D1——`StageState.swept` 淘汰（無讀者
  grep 驗證、覆蓋數字改走 evidence["survey"]；已接受入庫，可
  推翻）。修正批/複驗輪先後已自裁＝先修後驗（decisions.md 0801）。
- **第 3 輪＋鑑識完結**（詳 decisions.md 0801）：R4 存證 PASS；
  垂直增益收斂實證；水平第二死鎖＋A6 翻多記（鬼影）；主 session
  離線鑑識定讞＝phaseCorrelate 水平凍值/靜態峰鎖死（7/20
  map_stitch 同款），v2.4 規格＝格線相位權威＋整數欄三重裁決。
- **佇列（首項待使用者核可）**：①掃描 v3 重設計「位置一律來自
  畫面內容」（提案 docs/survey-anchor-v3-proposal.md：角落歸零
  ＋沿邊繞圈＋邊緣定位；核可後動工）②實機第 8 輪（v3 驗收：
  單位數 29-32、手勢數 15-25 把）③2e 首戰 UC HARD 1（符號讀取
  注入、單位↔螢幕對位、陣營證據分層、Move/Attack/Inspect
  plan）。另待裁遺留：v2 的 D1 `StageState.swept` 淘汰確認。
- 裝置現況（0802 第 7 輪收尾後）：R5CRC37JBYJ 在線、遊戲已更新 2.4.1、停 UC 關卡列表（游標 HARD 2
  ——棄戰游標飄移三度實證，重入必明示選關 --stage-node
  544,667）、EN 211/111、資金 1,307,500、鑽 4,200、RANK 26
  （基準漂移＝session 間非本程式活動）。鎖屏靠
  scripts/ensure_unlocked.py。遊戲登入逾時會彈錯誤 300（唯一鈕
  返回標題），恢復流程＝標題→下載→登入獎勵→公告→主頁，座標
  已標定。UC HARD 1 掛 CLEAR 徽章＝0730 舊事故既有狀態非新異常。

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
