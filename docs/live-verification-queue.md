# 實機驗證佇列

2026-07-21 使用者定調：**需要實機的驗證工作一律記錄在此，不阻塞離線架構
與實作**。adb 恢復後由主 session 依優先序排程，裝置任務序列化（同時間只
允許一個 agent 操作裝置）。每項完成後把結論回寫 roadmap／相關文件，並從
本佇列移除。

**執行順序與現場操作腳本（含 BLOCKING 攔截點）見
[live-test-plan.md](live-test-plan.md)**——本檔是案例登記簿，那份是 run-book。

## 前置：裝置連線恢復

- 2026-07-21 檢查：`adb devices` 顯示 `no permissions`——依經驗為重開機後
  seat0 ACL 歸屬問題，桌面實體登入一次即解（不是 udev 問題）；roadmap
  07-20 另記過一筆手機端 unauthorized，若登入後仍不通，需在手機上重新
  授權 USB 偵錯。
- 恢復後先 `uv run python scripts/capture.py` 確認截圖鏈路，再開始排程。
- 重跑戰鬥前 `discord-notify` 通知使用者（roadmap 既有指示不變）。

## 佇列（依優先序）

### 1. #26 覆蓋驅動掃描 survey identify 全鏈路實戰輪（重寫後）

- 內容：`CoverageScanSource` 覆蓋驅動走圖 → 逐台點擊分流（FactionIdentifier
  停靠邊判陣營）→ 完整星座點名 → 定義檔匯出。整條鏈路重寫後未經實機。
- 成功判準：survey_complete；陣營判定零猜測（雙命中拒判有紀錄）；
  `identity.seed` 完整星座點名成功；戰局可正常接續或放棄。
- 場地：活動關戰局仍停 TURN 1 our-turn hub（可放棄退體力）。
- **2026-07-23 凌晨第一輪（serpentine cutover）結果：survey_abort（未過）**
  ——根因＝偵測器域錯配（弧偵測 battle-zoom 校準 vs T3 最小 zoom 工作點，
  #26 07-20 已登記漏接），非「垂直漂移污染」（該說法已被流水帳複核推翻，
  見 [map-scan-survey.md](map-scan-survey.md) 更正段）。**修復已落地：
  覆蓋驅動重寫（批1~批5，serpentine 退役、min-zoom `find_unit_density_peaks`
  注入、cache bounds 預載）**，見 [coverage-scan-plan.md](coverage-scan-plan.md)。
- **2026-07-23 輪二（覆蓋驅動重寫後首跑）結果：FAIL 於 T3 前置（未進
  覆蓋掃描主體）**，run `data/runs/20260723-145815/`。前置兩輪 pinch 收斂
  正常（frame-diff 46→0.22px），但 `vision.zoom_at_max` 十六次量測全讀不到
  格線 → 誤判 undecidable → `SurveyIncomplete`。根因離線鐵證：`zoom_at_max`
  只走窄帶 `read_grid_lattice`，中央量測窗被密集編隊蓋掉（ex2if pt2 同款）；
  批1 的全幀 `read_map_lattice` 九幀照讀 col_pitch 100/93。**修復已落地
  （批6）：`zoom_at_max` 窄帶讀不到退全幀 `read_map_lattice` col_pitch 判定
  （語意/閾值不變）；pinch 中心改每步動態選無單位空地（`pick_pinch_center`
  max-min clearance，取代寫死 (1170,500)）；`zoom_step`／`battle_grid` ledger
  事件補存幀＋`zoom_step.source` 增 map_lattice。** 見
  [coverage-scan-plan.md](coverage-scan-plan.md) §5。
- **2026-07-23 輪三（純冷探索協定首跑）結果：FAIL 於覆蓋掃描（0 nudge
  即 survey_abort）**，run `data/runs/20260723-154731/`，主因幀
  `assets/screenshots/20260723-154959.png`。
  - **T3 前置 PASS**（批6 修復實戰生效）：`zoom_step.source=map_lattice`
    全程、首輪即確認到頂進入覆蓋掃描主體，批6 寬帶 fallback 過關。
  - **新敗因＝三層連鎖，批7 全數離線修復**：
    - **異常A（主因，`vision._map_edge` 南北偽陽性）**：此關西側地圖邊界
      在畫面內（west=1153，subagent 目視裁定 x<1153 全是星空，已存 fixture
      `tests/fixtures/vision/map_scan/west_in_view_20260723.png`＋sidecar）。
      seed/walk 越過真實西緣、在左側星空種出 7 條幽靈直格線（x=679..1092）；
      這些條帶整條皆暗，餵進邊界票源後每條在搜尋起點附近投假邊界，7 票
      過門檻→north==south==573（cy 起點值），且 573 深陷已偵測列線 span
      (71..1075) 內部卻從未自洽檢查。**實測推翻原「格內自然間隙」假設**
      （真實直格線垂直strip連續明亮、不產生格內暗run；假票只來自地圖外
      星空條帶）。批7 修法：亮度濾波（只有 central-band 達 `MAP_EDGE_LIT_MEAN`
      的格線可投票／界定 span）＋起點錨到最近格線＋自洽 gate（截止點不得
      落在該軸格線 span 內部）。九幀真值表不變、west=1153 保留。
    - **異常B（連鎖＋防線缺口，`coverage_map`/`live_scan`）**：north==south
      使 `integrate()` 列過濾互斥、`_covered` 恆空；`frontier()` 開頭把
      「無資料」當「完成」→ 主迴圈 0 nudge outcome=complete 跳出，只靠
      `_finish` 的 `_all_edges_seen` 事後攔成 SurveyIncomplete。批7 修法：
      `frontier()` 語意分離（空覆蓋＋已整合觀測＝raise `MapStateInconsistent`），
      迴圈映成 `SurveyIncomplete("map state inconsistent: ...")`、outcome
      誠實命名（不叫 complete）。
    - **異常C（附帶，controller `_scout`）**：abort 路徑格線留 ON——finally
      在 intel pending 時跳過 `_release_battle_grid()`，但 SurveyIncomplete
      後 intel 不會跑。批7 修法：collect 拋例外時無條件 release，正常成功
      ＋intel pending 才維持「留給 intel 收尾」。
  - **pitch 觀察旗標（不動標準答案）**：本幀 `read_map_lattice` 讀
    col_pitch≈94／row_pitch≈91，vs ex2if 標準答案 98.7／93.1 差約 5%。
    屬同關不同 zoom 相位/透視的正常浮動（九幀 pitch 測試容差 ±7 內），
    **僅記為觀察，不調整標準答案或閾值**；輪四留意若差距擴大再查。
  - **給輪四**：異常A/B/C 已離線修復，需重跑同一冷探索協定驗證覆蓋掃描
    主體能收斂（本輪三卡在 0 nudge，主體從未真正跑過）。
- **2026-07-23 輪四結果：FAIL 於回合入口（`_on_our_turn`），覆蓋掃描
  完全未觸達**，run `data/runs/20260723-165948/`（41 次循環零進展後依
  「同一問題不二次嘗試」紀律手動中止，裝置零損耗）。
  - 根因：輪三殘留的**收合單位列表**（輪三 abort 跑在批7 之前、未釋放）
    使 `vision.unit_cards_present`（只掃底部卡條帶）系統性回 False，
    `_on_our_turn` 誤判「無可行動單位」→ tap `END_TURN_BTN=(275,182)`
    ——該座標在此狀態實際開出**單位比較 modal**（疑似誤標；證據幀
    `data/runs/20260723-165948/frames/battle_01/t0001_turn1_unit_detail_modal.jpg`）
    → modal 自動關閉 → 回收合態，循環。畫面同時持續顯示「請選擇欲行動
    的單位」＝遊戲認定仍有單位可選的直接反證。
  - 認識論定性：`unit_cards_present` 的 False 把「讀不到（收合）」與
    「真沒有（展開且空）」壓成同一值——absence of evidence 被當
    evidence of absence，與掃描定案「邊界只在看見時成立」同款錯誤。
    相位分類器層無責（`ACTIONABLE our_turn 0.98` 判定正確）；缺的是
    handler 內「子狀態前提」的驗證。
  - **批8（修訂版，2026-07-23 與使用者定案，待開工）**：①觀測三值化
    ——新 `unit_list_state(frame) → expanded/collapsed/unknown` 像素探針
    （切換鈕位置：展開 ▽(1970,780)、收合 ▲(1970,1010)；輪四截圖可當
    收合態 fixture），`unit_cards_present` 消費者改吃三值、收合/unknown
    永不得當語意答案；連帶修 `_set_unit_list_open` 自身同款混淆（展開
    但卡條真空被誤讀成收合）。②handler 前提契約——`_on_our_turn` 下
    「無可行動單位」結論前，前提不滿足先修復（展開）再重讀。
    ③END_TURN_BTN 離線診斷（輪四截圖），有證據才改座標，否則標 live
    probe；回合本會自動推進，此鈕必要性一併檢視。④absence-audit：全庫
    掃「False 混合前提不成立」的同型 vision 讀值。
  - 批7 三項修復＋掃描主體（nudge／frontier／回復協定）經輪四仍為
    **零實機驗證**；輪五協定不變（冷探索、`GGGE_INTEL=1 GGGE_STAGE_ID`）。
  - 裝置末態：TURN 1 hub、0/15、格線 ON＋列表收合殘留（批8 主修會自癒）、
    modal 已手動關、cache 空（備份 stages.bak-20260723）。
- **前置（2026-07-23 規劃 session 新增）**：批8 修訂版規格與委派迴圈
  執行計畫已落檔 [scan-flow-robustness-plan.md](scan-flow-robustness-plan.md)
  ——下面這輪冷探索協定就是該計畫 Round 1 的上機驗證步驟，**須等 Round 1
  的程式修改合併進 `feat/inner-goap` 後才執行**，不要在批8 落地前單獨重跑
  （會重現輪四同一個卡點）。
- **2026-07-23 輪五結果（Round 1＝批8 合併 `2eeed9c` 後首跑）：FAIL 於
  identify（歷來最深進度，覆蓋掃描主體首次實機收斂）**，run
  `data/runs/20260723-234149/`（135 行事件＋16 幀）。
  - **回合入口自癒 PASS**（批8 實戰生效：輪四收合殘留開場自動修復，
    41 循環卡點不再重演）。**T3 前置 PASS**（三次 `zoom_step` 全
    `source="grid"` 一次到位，未觸發寬帶 fallback）。
  - **覆蓋掃描主體首次實機收斂（批7 三修復實戰生效）**：`coverage_report`
    cells=506／covered=494／holes=12／unreachable=2／nudges=50／
    outcome=`unreachable_only`（覆蓋率 97.6%，靠 frontier 自然收斂非撞
    預算牆）。bounds west=9／east=32／north=-9／south=13 → 24 欄×23 列，
    與標準答案 23×24 量級一致（軸序對應待暖掃比對）。效率觀察：首擊
    定位成功率約 32%（`scan_recovery` 34 次），記調校候選、非敗因。
  - **identify 2/45 台後 FAIL**：index 0 判敵並完整讀出（sig=
    `682a6a6a2aea1a29`；name 轉錄「戰鬥」疑雜訊，記次要診斷）、index 1
    判我方（right dock 0.996）。index 2（screen≈716,575）tap 中**未行動
    我方單位進入移動模式**、無 banner；`_identify_at` 盲目重試同座標，
    第二 tap 疑似確認原地移動並開出選擇武裝（末幀
    `t0135_turn1_finish.jpg` 雙疊層）；雙 dock 拒判（faction.py:32-34
    幾何預警命中）3 次後 `SurveyIncomplete("no summary banner")`。
  - **根因（主 session 流水帳＋程式碼定讞）**：識別迴圈缺視圖狀態閘門
    ——`scout_intel._identify_at` 重試前不檢查畫面狀態；而**未行動我方機
    tap 後結構性不出 banner**（遊戲機制：tap＝選取進移動模式），45 候選
    含 9 台未行動我方機，不修必重演。盲目重試在移動模式內有誤操作單位
    的實際風險。修復＝**Round 1.5**（見
    [scan-flow-robustness-plan.md](scan-flow-robustness-plan.md)）。
  - 裝置末態：TURN 1「單位移動＋選擇武裝」疊層（艾格沙貝被選中、未確認
    任何行動）、格線已由 abort 路徑釋放（批7 生效）、cache 空、定義檔
    未匯出（依設計不寫部分定義檔）。
- **2026-07-24 輪六結果（Round 1.5 合併 `e6a8520` 後首跑）：FAIL 於
  identify 前置 `bring_to_view()`，Round 1.5 目標驗證點未觸達；但覆蓋
  掃描主體 100% 收斂**，run `data/runs/20260724-004440/`（87 行、14 幀）。
  - 開場前置：遊戲省電觸控鎖吞掉前兩次返回 tap（模板穿透變暗覆蓋層
    誤 match，CLAUDE.md 已知坑），`Keyguard.dismiss_game_lock()` 解除後
    一次返回即回 hub。
  - **意外事件**：收合態開場經批8 修復後流進 late-arrival 分支——該
    分支直接選卡**跳過回合簿記與 `_scout`**（既有缺陷），「諸耶・吉爾
    (EX)」被真實攻擊一次（合法操作非 AUTO；`[SIM-SKIP]` 無校準）。
    第二次進 `_on_our_turn` 才走 happy path 跑掃描。
  - **覆蓋掃描主體**：`coverage_report` cells=552／covered=552／holes=0
    ／unreachable=0／nudges=28／outcome=`complete`（**100%，優於輪五
    97.6%**）；首擊定位率 71%（輪五 32%）；bounds west=14／east=37／
    north=-7／south=17（span 23×24 與輪五一致，原點相對）。
  - **崩潰**：`survey_stage` 進 `bring_to_view()` 星座重錨即
    `AttributeError: 'CoverageScanSource' object has no attribute
    '_nudges'`（live_scan.py:567）——`_nudges` 只在 `collect()` 初始化，
    `_navigator()` 每次 new 新實例；候選需挪鏡頭即必炸（輪五僥倖）。
    identify 零事件、定義檔未匯出。真實 `bring_to_view()`→`nudge()`
    路徑既有測試零覆蓋（全 `_identity_view` 假件）。
  - 修復＝**Round 1.6**（scan-flow-robustness-plan.md：A navigator 生命
    週期初始化＋B late-arrival 歸位單一路徑）。
  - 裝置末態：TURN 1 hub、列表展開、9/10 可行動（諸耶已行動）、格線
    已釋放（批7 finally 生效）、cache 空。
- **2026-07-24 輪七結果（Round 1.6 合併 `3a69ffd` 後首跑）：FAIL 於覆蓋
  掃描主體（前兩輪皆收斂的層首次退化），identify 未觸達**，run
  `data/runs/20260724-012023/`（229 行、僅 5 幀）。
  - Round 1.6-B 生效（開場 happy path、scout 先於選卡）；T3 PASS。
  - **掃描退化簽名**：首擊定位率 5.4%（vs 輪六 71%）；北/東外推全
    refused、南/西回復全 relocated（t=26.5 起、方向無關）；3 次偽定位
    （offset 跳 7/10 格、west 邊 11→4→1→11 翻動）；110 nudges 燒完預算
    `outcome=budget`→SurveyIncomplete。
  - **根因（三方交叉定讞）＝敵機選取殘留態**：t0005 起「史列加・羅 vs
    G-3鋼彈」比較 HUD＋紅色威脅色塊全程在場（幀證據：t0005/t0228/
    013030 逐像素凍結）；螢幕錨定 HUD 投 offset=(0,0) 假票壓過低重疊
    外推幀、紅色塊污染指紋；`is_unit_detail_modal` 對此全盲（全解析度
    實測 False）。成因未定（pinch 誤觸主嫌），任何輪都可能復發。
  - 連帶缺口：refused 路徑無煞車（continue 繞過 stuck 計數）、refused
    幀零存證、ledger 存幀為 1280×591 縮圖。
  - 修復＝**Round 1.7**（scan-flow-robustness-plan.md：選取殘留偵測＋
    空地 tap 解除鏈、定位飢餓煞車 K=6、refused 原生解析度有界存證）。
  - 裝置末態：TURN 1 hub、選取殘留（比較 HUD＋紅色塊）仍在場、格線已
    釋放、列表展開 9 卡、cache 空。**輪八開場即殘留在場＝前置防禦的
    第一個實戰驗證點，不要手動清**。
- **下輪協定（使用者指示，純冷探索）**：
  1. 開跑前把 `data/cache/stages/` 現存定義檔移到 `data/cache/stages.bak-20260723/`
     （使用者指示：測無資料探索，驗證首訪冷掃自產 bounds）。
  2. 啟動需帶 `GGGE_INTEL=1 GGGE_STAGE_ID="最終驗證 STAGE EX-2 IF VS全裝甲鋼彈"`
     ——驗證點 5（identify）與定義檔匯出只在帶這兩個環境變數時才觸發。
  3. 匯出的新定義檔應含 `map_cols/map_rows=23/24`（首訪冷掃產出、畫面權威）；
     第二輪同關重掃才驗 cache bounds 預載（`cache_bounds_dropped` 不應出現）。
  4. 存幀已開：T3 中段可交叉比對 `zoom_step`／`battle_grid` 幀（本輪失敗即因
     中段零影像），核對窄帶 vs 寬帶讀取與動態中心落點。
- **本輪要驗的點（重寫後全新，全部離線挑值待實機校準）**：
  1. **手勢方向推動有效性**：nudge 只推鏡頭不量測，卡頓/掉包只損時間；
     實機確認保守短推（`NUDGE_HALF` 250×170、700ms、settle 1.5s）真能
     推走鏡頭且下一幀可定位。
  2. **覆蓋收斂 nudges 數**：`coverage_report` 的 nudges／覆蓋率；對照
     `SCAN_MAX_NUDGES=48`（有 cache hint 時依尺寸放大）是否夠。
  3. **四邊目視偵測**：`read_map_lattice` 的截止緣四邊全中（太空圖家族
     校準，本關即太空圖）；`frame_localized` 的 `edges` 逐邊落點合理。
  4. **survey 接續 identify**：走完 → `bring_to_view`（constellation 重錨、
     無 335px 假跳）→ 停靠邊分流 → 定義檔匯出。
  5. **nudge 預算常數實機調校**：`ANCHOR_MAX_NUDGES=8`／`SCAN_MAX_NUDGES=48`／
     `RELOC_MAX_NUDGES=6`／`STUCK_LIMIT=3`／`BRING_MAX_NUDGES=8` **皆離線
     挑值**，實機依收斂表現調整。
  6. **cache bounds 預載實戰**：第二輪同關重掃時 `_navigator` 應讀到上一輪
     寫入定義檔的 `map_cols/map_rows` 當 hint（`cache_bounds_dropped` 不應
     出現＝hint 與實掃一致）。
  7. **T3 前置寬帶 fallback（批6，本輪 FAIL 的直接修復）**：`zoom_step` 幀
     的 `source` 逐步落 grid／map_lattice／frame；密集編隊幀應由 map_lattice
     讀出 col_pitch、`zoom_at_max` 過關進覆蓋掃描主體；`pick_pinch_center`
     選的中心逐步避開單位（比對存幀），全讀不到才退固定 (1170,500)。
- **附帶確認**：`_scout_local`（turn-2+ 局部掃描）的實際 zoom 狀態——若
  遊戲停留最小 zoom，local scout 用的弧偵測有同款域錯配（既存疑問，非
  本輪引入）；順手記一筆 turn-2 hub 的 zoom。
- 附帶：批A/批B（對帳資料保存）落地後，本輪同時開始累積對帳數據。

### 2. 縮放地圖獨立驗證（定案 4）

- 工具：`scripts/zoom_probe.py`（已完成：回頂層 → 開方格 → pinch 迭代
  → pitch 序列 → 關方格）。
- 已驗：GesturePincher 單次 pinch 可縮放（07-20 實機）。
- 待驗：`zoom_out_max` 收斂（連兩次 pitch 不縮判停）；方格開關往返復原；
  `map_view.ensure_max_view` 從各子狀態（選中單位／modal／卡條展開）退回
  hub；`zoom_at_max`（T1 產出的單幀辨識）與收斂迴圈結論一致。
- 成功判準：pitch 序列單調收斂到穩定值；結束時方格恢復 OFF、畫面停在
  hub；過程無誤觸單位行動。

### 3. 切格線流程獨立驗證

- 工具：T2 產出的獨立驗證腳本（讀設定 toggle 狀態 → 切換 → 地圖格線
  確認 → 復原設定）。
- 成功判準：toggle 狀態辨識與地圖格線出現/消失一致；往返後設定復原；
  誤入選單時 fail-soft 能退出。

### 4. 應戰四假設（battle-prep-ui.md §9）

- 頭像槽算術定位 tap／行動選擇 (2042,924) 估計值／武器鈕順序=spec 順序／
  SHORT 深色可用圖示 V 閘門；hit 字型缺 '3' 補樣本。
- 排程：survey 全通（佇列 1）之後，roadmap 既定順序。

### 5. 出擊機雙V偵測器 turn-1 實機輪

- 前置：偵測器離線完成（鈷藍環＋實心白VV 判別式，幀2/幀3 已 10/10）。
- 只在 turn-1 滿血未行動窗口有效（VV=可操作提示會消失、環色=HP 弧會
  變色）；陣營權威仍是停靠邊。

### 6. MAP 砲樣本蒐集（常備、被動）

- 遇有 MAP 敵機關卡：capture 移動選格畫面（兩類威脅圖示）＋該敵機武裝
  面板，存 PNG（silent-events.md 批D）。蒐到前批E 不開工。

### 7. #24／#25 殘餘

- #24 冷掃太空圖提早收工複驗；#25 掃描期格線後續（縱向透視 row 模型、
  定義檔 cells 以格線量測為權威）。

### 8. 佔格候選機制（遠期）

- 大型單位佔格＝選取時移動範圍/阻擋實測；「環心壓格線交叉點」只當疑似
  旗標。佔格權威=使用者/遊戲內驗證。

## 缺樣本清單（實機順手補拍）

- 戰鬥設定選單「顯示方格」**toggle OFF 態**截圖（T2 已掃全庫 451 張確認
  缺：ON 態兩張已入 fixture，OFF 態僅合成測試覆蓋；補拍後用
  `scripts/curate_fixture.py` 裁四探針外接框入 `vision/settings/`，PNG）。
- zoom 拉近（非最遠）且格線開啟的地圖幀（`zoom_at_max` 負樣本，若庫存
  沒有）。
- SHORT 武器「深色但可用」圖示樣本（應戰 V 閘門開放假設）。
- hit 字型含 '3' 的命中率樣本。
