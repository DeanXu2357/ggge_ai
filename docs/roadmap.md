# roadmap

CLAUDE.md 的開工／收工紀律綁這份檔案的暫停快照。`83fce1e` 刪掉 16 份
doc（含本檔前身）後由使用者裁決重建，範圍只有**裝置現況＋恢復點**——
規格不寫在這裡（「程式碼就是規格」）。

## 暫停快照（2026-08-03，掃描 v3 骨架＋量測誠實修正輪入庫；待實機第 8 輪）

### 恢復點

- **0803 掃描 v3 入庫＋術語全庫清理**（v3＝骨架批三 commit＋修正
  輪五 commit 併入；術語＝四 commit）：**位置一律解自畫面內容**
  ——角落歸零、沿邊繞圈讀地圖終止邊當地標、補中央靠單位排列比對
  ＋佔位一致性複驗；逐幀位移累加的里程計、定位中斷側緩衝（島嶼）
  與重錨、增益學習、推不動推論界線全數退場。**骨架批交付版驗證
  抓到已重現的量錯寫入**（複驗與候選同源＝恆等式；相關器凍住長
  兩格鬼影），修正輪依使用者裁示把複驗主判準換成佔位資訊比對，
  重現腳本主 session 親跑複核：注入錯誤全轉拒收、鬼影 2→0、正常
  路徑零誤差。決策備案 decisions.md 0803 五條、導覽
  docs/reviews/scan-v3-review.md（第九節＝修正輪）。術語清理＝
  「腿」等十詞全庫換白話（對照表 docs/terminology-map.md），
  島嶼／大陸／幽靈／星空四個譬喻詞保留但每份文件首次出現要有
  情境定義句。裝置現況不變（v3 全程未碰實機）。
- **0803 實機第 8 輪跑完＝v3 首次上機，主症狀定讞為「沿邊繞圈提早
  收手」**（run `data/runs/20260803-075745/`，158 次觀測、79 把平移
  撞頂 80 拍上限、耗時 12 分 57 秒、棄戰零消耗第四度實證）。
  **紅線沒破**：記到 20 台低於真值（約 28-29）、零鬼影、退休格 0。
  **根因（主 session 用實幀比對定讞，非代理推論）**：`_unchanged`
  把相位相關器凍住的輸出當可信的「沒動」——`SHIFT_MIN_RESPONSE`
  0.05 太低，雜訊等級回應也算 `known`。實幀對照：真的推動 178px
  的那一對 conf=0.063／逐像素平均差 19.36，真的沒動的那一對
  conf=0.965／平均差 0.34，**兩者裁決一模一樣**。連兩次誤判就把
  那一側從繞圈路線拿掉（東 t15/t16→t17 換側、南 t29/t30→t31），
  鏡頭根本沒推到地圖東／南緣，於是東、南**整輪一次都沒讀到終止
  邊**，地標只拿到西(1175)、北(307)。修正批進行中。
  **注意：live-tester 報告的「東緣差 11px 出取樣帶」是提早收手的
  結果、不是獨立成因**——收手當下鏡頭不在東界，真正的東界在哪
  這一輪沒量到，取樣帶要不要改得等修好之後重測。
  其他數據：定位來源 edge 7／單位排列比對 37／still 43／重疊區
  量測 **0 次**；定位中斷 13 筆（佔位一致性 12、相位 1）；重新
  歸零 3 次（其中兩次 `_forget()` 清空整張圖與地標，讓最終台數
  失去對帳意義）。**另兩個待評估的量測數據**（與提早收手無關，
  重測後再判要不要動）：①格線讀取器普遍只讀到格網的一小塊子窗
  ——lattice 框寬中位數僅 `MAP_REGION` 的 0.57，158 幀裡只有 12 幀
  超過 80%，這是終止邊量不到的上游成因候選，且實測「單純放寬
  取樣帶」無效（左側 HUD 假脊＋頭尾裁剪會砍掉最外幾欄，要連
  `read_lattice` 選欄邏輯一起看）②西北角判 `unreadable corner`
  那次是險過未過：西側外側紋理 10.53 對門檻 `EDGE_QUIET_HIGH`
  10.0，只差 0.53。`dry_run_entry.py` 必須從關卡列表起跑，停在
  主畫面會在 select 閘門硬停（可用主畫面右下 MAIN STAGE 1890,790
  進去）。
- **0803 停滯誤判已修入庫**（`STILL_MIN_RESPONSE` 0.25，只作用於
  `_unchanged`；門檻取自第 8 輪 157 對相鄰觀測的離線重算——凍住組
  回應值 0.055–0.162、正常組 0.413–0.993，中間空白）。逐對對帳
  修好 11、零退步、零件真正靜止被翻成移動；實機幀入 fixture
  `tests/fixtures/vision/map_scan/stall_20260803/`。**修正批誠實
  指出：第 8 輪的錨定點其實不是真正的西北角**（t5/t6 各真的往北
  推了約 235px 卻被判卡住，而北緣從未進畫面），修好之後歸零會往
  北推得更遠——那一段沒有實幀，要靠重跑確認。
- **下一步＝重跑實機（第 9 輪）**。第一件事是量**四個角落各推
  到底時，四側地圖終止邊各讀不讀得到**——v3 的座標全靠它，0719
  的九張實幀裡只有兩張讀得到（皆北側）。讀不到要修的是終止邊
  偵測／取樣帶，不是 v3 骨架。其餘對帳項：水平相關器凍值頻率、
  單位數 29-32、四邊與人工普查一致、手勢數 15-25 把、
  `_outbids` 的 3px 餘裕在實幀上的行為。

- **0802 流水帳回放網頁工具入庫＋補修**（`fa04b56`＋`de07f0a`＋
  `f006388`，1625 passed／4 xfailed；純新增不動既有進度）：
  `uv run python scripts/replay_run.py [run|tar.gz|名稱]` 起本機
  網頁逐筆回放 run 紀錄與留存幀，投影片（前後翻＋只停有圖，
  ←/j、→/l 快捷鍵）／直頁顯示（全列直欄、文字左圖右）雙模式。回放單位＝entry 逐筆（不做 tick 分
  組）；補修收齊 prev/curr 欄位＋survey 側傾印命名慣例附掛
  （17→144/282 筆有圖；decisions.md 0802 兩條）；導覽
  docs/reviews/replay-run-review.md。**附帶發現 test_not_
  actionable 先天 flaky（time.time 同值 71% 走錯支）待使用者裁
  示**（導覽第五節有鑑識）。裝置現況不變（本批未碰實機）。

- **0802 鑑識三翻案＋v2.9 作廢＋v2.10 入庫＋使用者定 v3 方
  向**（`e503d50`，1603 passed；全文 decisions.md 0802 五
  條）：離線鑑識定讞「致動雙態不存在」（53 次平移全部推動畫
  面 97-107%、手勢被吃 0 次）＝拖曳假說與競態假說同證偽、v2.9
  四 commit 作廢；死因＝量測層投票分桶錯誤＋稀疏區佐證來源不
  足；85 台=29 個真實實體（≈真值 28）沿座標誤差階梯拖出重複
  殘影。v2.10（投票聚類修正＋地圖邊緣位移當量測依據＋停滯判
  定須影像佐證＋儀器化）重放對照：量測失敗 23→5、救回 18、錯
  誤寫入 6→0、同時點單位 79→39。**使用者裁示：逐步指定移動距
  離的做法先天不穩→v3 重設計「位置一律來自畫面內容」提案已寫
  （docs/survey-anchor-v3-proposal.md），核可前不動工**；C4 指
  令兜底否決；v2.10 三爭點併入 v3。另：說明文字禁英文直翻術語
  （leg／envelope 之類的直譯）與縮寫。

- **0801 第 6 輪＋v2.7＋v2.8 入庫**（`acbf59d`/`d8d40b2`，
  1597 passed／4 xfailed；判讀與裁決全文 decisions.md 0801 午
  後/傍晚/晚三條）：第 6 輪座標重複吸收軸實質解（紅 17/18、
  merge 全在合理範圍、無邊界暴衝；**遊戲更新 2.4.1** 插
  曲已處置）；佔位假峰鑑識＝3 船體＋2 HUD 鈕（誤判幀入
  fixture wreck_*）；**密度上限判別式被校準數據證偽（反
  向）**；**掃不完＝致動層**（18/18 把定位中斷的平移真位移
  僅指令 6-29%、屬邊緣回彈；37 把平移東西震盪 clamp 0/37 攔
  不到）。v2.7＝measure_pan 接象限窗＋fixture＋校準表；
  v2.8＝目視終止邊 clamp＋HUD 兩鈕挖洞（左上洞代價備案、觸
  發器＝第 7 輪西北退休暴增改只留右上）＋船體假峰裁定留 2e
  phantom-drop。**still-witness k=0 回收使用者裁示緩收**。
  reset 成因鏈＝ISLAND_BUDGET 耗盡 relocalise 無解、旗跨 reset
  遺失未治（等實機資料）。

- **0801 使用者診斷解除停工＋v2.6 四件套入庫**（`27f6e12`，
  1587 passed／ruff 綠；裁決全文 decisions.md 0801 使用者
  診斷/追問/v2.6 三條）：使用者親看幀定調「同場景被當不同區
  域重複吸收」＋兩追問釘死缺口（covered() 純幾何把地圖外的
  星空背景也蓋 EMPTY、四態無「是不是格子」、邊界推論制偏離
  目視教義）。v2.6＝①影像複驗閘（逐精靈窗，排列比對的票與合
  併 delta 須勝原地假設）②邊帶格線 fallback（象限窗補相位閘死
  區）③merge delta 合理範圍閘（Island.lost 跨島累加）④格子存
  在遮罩（EMPTY 毯要格線背書）＋格線終止邊界目擊（目視定旗、
  edge_mismatch 隔離不改旗）。**74 幀實幀重放：7/74 裁決改變
  全數為目標（t11/t12 真滑動、t24 幽靈票——幽靈＝週期圖案錯位配
  對出的假位移候選，畫面上無真實對應）、零誤殺、零假邊**。導覽
  docs/reviews/scan-v2_6-review.md。

- **0801 第 5 輪判定＋停工（已解除）**（run 20260801-080213；
  判讀、鑑識線索與候選方向 A/B/C 全文 decisions.md 0801 第
  5 輪條）：W1 PASS（帳面一致、裁剪生效）／**W2 FAIL：80 台
  vs 期望 28**＝台數軸連兩次針對性修正未解，**依紀律停工、
  discord 已通知使用者**。根因假說＝同型單位編隊使單位排列比對
  產生 alias，讓 relocalise 錯位重錨（merge delta +273×4、
  (546,−670) 出格、邊界撐到 48 欄）。**恢復點：使用者裁示方向
  （A merge delta 合理範圍閘／B relocalise 眾數邊際／C 丟棄不
  合併）後派 v2.6**；定位中斷軸已完結（第 4 輪 broken 18→0）
  不受影響。

- **0801 第 4 輪決勝過關＋v2.5 入庫**（run 20260801-071055；
  判讀全文 decisions.md）：**水平向定位中斷軸完結——東西
  向 broken 18→0**、lattice:constellation 通道實機接通（保
  留觀察：9/13 把水平向的平移退舊路徑、lattice:phase 零出
  現）、增益 0.44→0.75 爬升。V5 台數 FAIL 定位第二軸：cells
  84 vs census 55 vs 期望 28、29 筆在東界外＝邊界定案/重錨
  後 marks 不裁剪。**v2.5 入庫**（`d056004`：fix_boundary
  裁剪線外知識＋units/sightings bounded 界內＋merge delta
  遙測；1571 passed／ruff 綠；設計決定 10 條備案，導覽
  docs/reviews/scan-v2_5-review.md）。

- **0801 複驗輪第 2 輪**（Phase A run 20260801-042733、Phase
  B 20260801-044436-phaseB；判讀與鑑識全文 decisions.md 0801
  條）：A1/A4 PASS（29 把平移就 synced、四旗全定）、expire 語
  意實機驗證、**結束回合鈕標定完成**（(300,185)→(997,562) 待
  機並結束→(1365,850) 執行）、應戰彈窗 18 連發正確應答、卡條
  不彈回。三定讞：A6 漏記＝absorb 無條件覆寫（偵測器單幀 23 目
  擊 vs 最終記 10）、增益學習死鎖（0.5×wanted 保護恆真）、東
  緣邊緣回彈由 STALL 吸收不修。**水平向定位中斷根因未定**（37
  次幾乎全 east/west、靜止閘 waits 全=1 滑行假說出局）→v2.3
  補 BROKEN 存證待第 3 輪資料定讞。**v2.3 入庫**（`fb2f806`：
  absorb 同代 UNIT 滯後＋增益入帳 ACCEPTED≥40px＋BROKEN 幀
  對存證〔上限 20〕＋--dump-survey-frames＋synced 提前結
  束；1547 passed／ruff 綠；設計決定 20 條＋六爭點裁決備案
  decisions.md，導覽 docs/reviews/scan-v2_3-review.md）。注
  意：兩輪 --stage-node 544,667 實際打的都是 UC HARD 1（截圖證
  實），map_scan 基準有效。

- **0801 掃描複驗輪第 1 輪 Phase A FAIL＋診斷定讞**（run
  data/runs/20260801-033746；判讀與 v2.2 裁決全文 decisions.md
  0801 條）：40 tick 不夠、36% 的平移次數 BROKEN(phase)
  定位中斷＝pan 慣性滑行殘餘落進相位閘窗口（22.5–40px）；
  恢復機制（島嶼〔定位中斷後位置不明的觀測暫存區，等重新定
  位才併回〕＋relocalise 整欄修正）照設計運作。Phase B 未跑
  （依規格跳過）；結束回合鈕目視 (300,185) 待 tap 覆核；棄
  戰零耗三度實證；裝置收尾乾淨。**v2.2 入庫**（`94fa54a`：
  靜止閘 measure_shift 判準＋逐 observe 遙測 survey_tick
  ＋SURVEY_TICKS 80；coverage.py 零改動；1525 passed／ruff
  綠；設計決定 16 條＋五爭點裁決備案 decisions.md，導覽
  docs/reviews/scan-quiescence-v2_2-review.md）。**紀律：下一
  輪複驗同款定位中斷簽名再敗＝連兩輪，停下問使用者。驗收標準＝
  定位中斷率降到個位數（非零）；首要觀察 settle.waits 分佈。**

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
  0 cell（東西各燒滿 8 把平移未到邊）→ pinch 裁定推翻改搬遷；
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
