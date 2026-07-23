# 同步盤面流程強化：架構討論＋委派迴圈執行計畫

2026-07-23 稍晚（純規劃 session，未碰裝置）。承接批8（roadmap 07-23 暫停
快照「恢復點＝批8」）——本文件把批8 的四項範圍擴充，並記錄促成這個擴充的
架構討論，供下個 session 直接接續執行。**這是批8的正式規格文件，批8 的
todo 以此檔為準，roadmap 暫停快照只保留指標。**

## 架構討論結論（為什麼要做這個重構）

使用者提出的問題：關卡內是否也該套 GOAP，讓「畫面該按什麼」變成規劃而不是
寫死流程；如果套，跟既有的戰術層 solver（expectiminimax）疊起來會不會變成
病態的多層巢狀。

結論（三個規劃器，各管各的狀態空間，不是同一顆疊三次）：

| 層 | 狀態空間 | 機制 | 回答的問題 |
|---|---|---|---|
| 戰略層 | 資源/進度述詞 | GOAP A*（`goap/planner.py`） | 接下來做哪件大事 |
| 流程層（view action） | 畫面述詞 | 同一顆 GOAP A*，另一個實例 | 怎麼把畫面弄到能執行意圖的狀態 |
| 戰術層 | BattleState 盤面 | expectiminimax solver | 這場仗怎麼打 |

`agent/loop.py` 的 `AgentLoop` 本來就是流程層 GOAP 的範本（screen 述詞、
act→verify、計畫外畫面觸發 replan）——這次的落地方向是把同一個 pattern
下沉到戰鬥內部，用在同步盤面這條前置流程（`_scout` 觸發的：回到 hub →
收合單位列表 → 開格線 → zoom 到底 → 覆蓋掃描 → 關格線），而不是整個
`_on_our_turn`（單位選取/攻擊決策仍是 solver 職權，不進 A*）。

replan 的觸發方式：**每層各自重新感知、各自檢查自己的 goal，沒有跨層呼叫**。
回合推進會讓流程層的 `due()`/`mark_*` 述詞（timeline.py）在下次進場時重新
不滿足，因此自然重規劃，不是戰術層通知流程層。`battle/reconcile.py` 記的
是傷害預測 divergence，**明文紅線是永不否決分派**（roadmap 07-19：「timeline
只記帳回報 divergence 永不否決分派——畫面權威紅線」）——它不是、也不該是
任何 replan 的觸發點。真正合法的流程層 replan 觸發點是流程層自己的
effect-verify 失敗（例如 `validate_stage` 回傳 `report.ok=False`、identify
星座定位失敗）。

## 具體發現：批8同一類 bug 已經被複製貼上三次

批8 的診斷（`unit_cards_present` 讀 False 卻分不清「真的收合」還是「彈窗
蓋住讀不到」，導致輪四 41 次循環）往前追一步發現：`is_unit_detail_modal`
觸發時「點掉再重試」的邏輯**已經被寫了三次**：

1. `controller._clear_scan_obstruction`（controller.py ~1540-1551）
2. `live_scan.CoverageScanSource._clear_obstruction`（live_scan.py ~595-604）
3. `map_view.return_to_top` 內的 modal 分支（map_view.py ~138-141）

`UNIT_DETAIL_CLOSE = (1176, 992)` 甚至有兩份獨立宣告（`map_view.py:35` 與
`controller.py:93`，同值但沒有單一事實來源）。唯一**沒有**這層保護的呼叫點
正是輪四摔倒的 `_set_unit_list_open`／`map_view.collapse_unit_list`——不是
巧合，是同一類「特例修一個、下一輪冒出另一個」的模式在真的重複發生。

## 執行模式（每輪固定流程，委派迴圈）

1. **主 session** 為該輪寫 dev-plan（目標／已知事實／紅線／驗收標準）。
2. **主 session** 開工前 `git worktree prune`／`git worktree remove` 清掉
   已合併的孤兒 worktree，避免新 opus subagent 掛到過期分支
   （見 memory `delegation-execution-model` 實務坑①）。
3. **Agent（opus，`isolation: "worktree"`）** 依 dev-plan 修改、跑
   `uv run pytest -q` 與 `uv run ruff check src tests scripts`、commit。
4. **主 session** 驗證：讀 diff、在該 worktree 重跑全套 pytest/ruff、對照
   驗收標準逐條打勾、確認 `battle/vision.py`／`battle/controller.py` 的
   改動附了離線證據（新 fixture 或會重現歷史失敗的回歸測試）；通過後
   merge 進 `feat/inner-goap`（主工作目錄，非 worktree 內）。
5. **Agent（sonnet，主工作目錄、真實裝置）** 依 `docs/live-test-plan.md`
   慣例上機跑，戰鬥前先 discord-notify 通知使用者；結果（通過/失敗、
   根因、流水帳路徑、螢幕證據）回報主 session。
6. **主 session** 把結論寫回 `docs/roadmap.md` 暫停快照／
   `docs/live-verification-queue.md`，決定下一輪範圍。**同一問題連續
   兩輪失敗就停下來問使用者**（CLAUDE.md 既有紀律），不無限自轉。

裝置同時間只允許一個 agent 操作；round 內 opus 與 sonnet 不會同時碰裝置，
因為 sonnet 的上機驗證排在 merge 之後。

**已知限制（本次規劃 session 實測踩到）**：`Agent` 工具的 subagent 派遣
額度（`CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION`）預設每 session 20 個，
一天的委派迴圈重度使用（一輪至少 opus+sonnet 兩個，多輪很快打頂）會在
單一 session 內用盡且不會重置，需要新 session 才能重新取得額度。**開工
前務必先確認/調高這個額度**（見 memory `delegation-execution-model`
實務坑④）。

## Round 1：收斂三份重複的 modal 清除邏輯＋補上收合列表的漏洞（＝批8 落地，範圍擴充）

批8 原定四項全部收進本輪，外加上面發現的重複收斂：

**新增（本次規劃發現）**：
- 在 `map_view.py` 新增單一事實來源的 `clear_obstruction(perception,
  actuator, frame, *, sleep) -> frame`（把現有三份 `is_unit_detail_modal`
  → tap `UNIT_DETAIL_CLOSE` → sleep → recapture 的邏輯收成一個函式，
  語意不變）。
- `controller._clear_scan_obstruction`、
  `live_scan.CoverageScanSource._clear_obstruction`、
  `map_view.return_to_top` 的 modal 分支，三處改呼叫這一個函式。
- 刪除 `controller.py:93` 那份重複的 `UNIT_DETAIL_CLOSE`，改從
  `map_view` import（`scout_intel.py`/`live_scan.py` 現有的 import 鏈不動）。

**批8 原定四項**：
1. **觀測三值化**：`vision.py` 新增 `unit_list_state(frame) →
   "expanded"/"collapsed"/"unknown"` 像素探針（切換鈕位置：展開
   ▽(1970,780)、收合 ▲(1970,1010)；輪四截圖
   `data/runs/20260723-165948/frames/battle_01/t0001_turn1_unit_detail_modal.jpg`
   可當 unknown/收合態 fixture）。`unit_cards_present`／`count_unit_cards`
   的既有消費者（`_set_unit_list_open`、`map_view.collapse_unit_list`）
   改吃三值，`unknown` 永不當「已收合」的答案——遇到 `unknown` 先呼叫
   新的 `clear_obstruction` 再重讀，不直接判定「無單位可選」。
2. **handler 前提契約**：`_on_our_turn`（controller.py ~867）在下「無可
   行動單位」結論前，若列表狀態是 `unknown`，先修復（清障礙＋重新展開）
   再讀，不直接走去點結束回合。
3. **`END_TURN_BTN` 離線診斷**：對照輪四截圖判斷 `(275,182)` 這個座標在
   「列表收合態」下實際點到什麼；只在有截圖證據時才改座標（CLAUDE.md
   紅線：沒有新截圖證據不動閾值/座標），否則維持現狀並標記待 live probe。
   這項不阻塞本輪其餘項目，可視時間排到下一輪。
4. **absence-audit**：全庫掃一遍「布林讀值把『讀不到』和『真的沒有』混成
   同一個 False」的同型 vision 讀值（`unit_cards_present` 是本次的具體
   案例，audit 找其他可能同款的探針，不代表都要在本輪修完——記錄成
   後續 issue 即可）。

### 涉及檔案
- `src/ggge_ai/battle/map_view.py`（新 `clear_obstruction`／`unit_list_state`
  消費、`collapse_unit_list` 改吃三值）
- `src/ggge_ai/battle/vision.py`（新 `unit_list_state` 探針）
- `src/ggge_ai/battle/controller.py`（刪重複常數、`_clear_scan_obstruction`
  改轉呼叫、`_set_unit_list_open`／`_on_our_turn` 改吃三值）
- `src/ggge_ai/battle/live_scan.py`（`CoverageScanSource._clear_obstruction`
  改轉呼叫，呼叫端簽名不變）
- `src/ggge_ai/battle/scout_intel.py`（確認 `UNIT_DETAIL_CLOSE` re-export
  鏈不受影響，預期零改動）

### 測試（沿用既有 fake perception/actuator 慣例，無需裝置）
- `tests/test_map_view.py`：`clear_obstruction` 與 `unit_list_state`
  三態分類（沿用檔內既有 `FakePerception`/`_stub_vision` pattern）。
- `tests/test_zoom_scan_precondition.py` 或新檔：`_set_unit_list_open`
  在收合中途被 modal 打斷時能自我修復，直接對照輪四失敗場景寫成回歸測試
  （`unit_cards_present` 讀 False 但實際是 modal 蓋住，不得被判定為
  「已收合」）。
- `tests/test_controller_modal.py`：`_on_our_turn` 在 `unit_list_state`
  為 `unknown` 時不得直接下「無可行動單位」結論。
- 既有 `tests/test_coverage_scan.py`、`tests/test_coverage_hint.py`、
  `tests/test_coverage_map*.py` 應維持全綠不動（`_clear_obstruction`
  行為不變、只是轉呼叫）。
- 全庫：`uv run pytest -q`（目前基準 810 passed/3 xfailed）與
  `uv run ruff check src tests scripts` 全綠。

### 驗收標準
- `UNIT_DETAIL_CLOSE` 只有一份宣告，其餘全部 import。
- 三處 modal 清除邏輯改為呼叫同一函式，行為（座標、sleep、重截）不變。
- 輪四那個具體失敗場景有專屬回歸測試且會在修復前對現有程式碼失敗、修復後轉綠。
- `_set_unit_list_open`／`collapse_unit_list`／`_on_our_turn` 三個消費者
  都不再把「讀不到」跟「真的沒有」混成同一個布林值。

### 上機驗證（sonnet subagent，即排定中的「輪五」冷探索協定）
沿用 `docs/live-verification-queue.md` 已寫好的下輪協定，不用重新設計：
1. 開跑前把 `data/cache/stages/` 移到 `data/cache/stages.bak-20260723/`。
2. `GGGE_INTEL=1 GGGE_STAGE_ID="最終驗證 STAGE EX-2 IF VS全裝甲鋼彈"` 啟動
   `scripts/run_manual_battle.py`（戰鬥前先 discord-notify）。
3. 重點觀察：(a) 是否終於能通過回合入口進到覆蓋掃描主體（輪四從未到達）、
   (b) 收合列表過程若真的被誤觸打斷，是否自我修復而非誤判無單位、
   (c) 覆蓋掃描主體本身能否收斂（批7 修復後仍是零實機驗證）。
4. 產出：`data/runs/<timestamp>/battle_01.jsonl`＋螢幕證據；結果不論成敗
   都回寫 `docs/roadmap.md` 暫停快照與 `docs/live-verification-queue.md`。

## Round 1.5：identify 疊層安全化（輪五敗因修復，2026-07-23 深夜主 session 定讞）

### 根因（run `data/runs/20260723-234149/`，主 session 流水帳＋程式碼複核定讞）

1. `scout_intel._identify_at`（~126-132）verdict 讀不到時**對同一座標盲目
   重試 tap**，重試之間沒有任何畫面狀態檢查。
2. **未行動我方單位 tap 後結構性不出 banner**——遊戲機制：tap＝選取進
   「單位移動」模式（這正是我們自己 activation 流程操作單位的方式）。
   identify 的互動模型假設「tap 單位→摘要卡停靠」普遍成立，漏掉這個
   已知機制。turn-1 的 45 個候選含 9 台未行動我方機，不修必重演 9 次。
3. 疊層上的盲目重試有**誤操作風險**：第二 tap 落在該單位腳下＝移動模式
   內點自己的格，疑似確認原地移動並開出選擇武裝（輪五末幀
   `t0135_turn1_finish.jpg` 雙疊層鐵證）。
4. 雙 dock 拒判是 faction.py:32-34 早已預警的幾何共用（武裝選擇右面板＝
   右 dock 同幾何）；零猜測政策本身運作正確，缺的是它前面的狀態閘門。

### 範圍

1. **視圖狀態閘門**：identify 的每次嘗試改為「驗證 hub → tap → settle →
   capture → 先 `map_view.classify_frame`（經 perception.probe）再談 dock」：
   - `unit_move`／`weapon_select`（我方機被選中的子狀態）→ **verdict=
     ALLY**——遊戲機制證據：只有我方未行動機 tap 會進移動模式（第三方
     不可操作、敵機出摘要卡）；記 side=`unit_move`、score=1.0，脫出疊層
     後 continue。faction 停靠邊仍是權威通道；move-overlay 是機制證據
     新通道**不是猜測**，依據記入 faction.py docstring。
   - `hub` → 照舊 dock 讀取（雙命中拒判語意保留）。
   - 其他狀態 → 先脫出再重試；**任何重試前必須先驗證已回 hub，絕不在
     疊層上重複 tap**。
2. **脫出機制**：優先重用/擴充 `map_view.return_to_top`（現有
   RETURN_BUTTON probe 對 unit_move 疊層是否有效，以輪五末幀驗證；並查
   `executor.py` pilot 流程既有取消路徑）。**行動安全紅線：脫出過程絕不
   tap 地圖格（移動模式下點格＝下移動指令），只准點專用取消/返回 UI
   元素，每步 act→verify。**
3. `_read_summary_at`（enemy 路徑）同款防護；classify/escape 能力從
   controller 接進 `survey_stage`（新參數、保持 fake 可測）。
4. **回歸測試（先紅後綠）**：
   - fake 驅動：候選 tap 出 unit_move view → 必須判 ALLY、絕不在疊層上
     重 tap（斷言 taps 序列）、脫出後才處理下一候選；舊碼在此測試下會
     盲重試並 SurveyIncomplete。
   - 真幀 fixture：`t0135_turn1_finish.jpg`（unit_move＋weapon_select
     疊層）過 DockBannerIdentifier 釘住雙命中→None；過 classify 閘門讀出
     子狀態（模板比對類，JPEG 可）。
5. 次要（有幀證據才修、不阻塞）：index 0 name=「戰鬥」轉錄診斷
   （`FORECAST_LEFT_NAME_REGION` 在 survey 詳情 modal 的適用性，幀
   t0131~t0134）；證據不足記 issue。

### 紅線
- 不碰 `CoverageScanSource`／`coverage_map.py` 掃描演算法本體（本輪首次
  實機收斂、不疊變因）。
- 不碰 `_on_our_turn` 之後的 solver 職權。
- 基準 824 passed／3 xfailed 只增不減＋ruff 綠。

### 驗收標準
- 舊碼會失敗的疊層回歸測試轉綠（先紅後綠有紀錄）。
- `_identify_at`／`_read_summary_at` 不存在「未驗 hub 就重 tap」路徑。
- 脫出全程無地圖格 tap（測試斷言）。
- 上機驗證＝輪六：同冷探索協定；**開場殘留疊層（單位移動＋選擇武裝）
  應被脫出機制自癒——本身就是第一個驗證點**。

## Round 1.6：navigator 生命週期＋late-arrival 歸位（輪六敗因修復，2026-07-24 凌晨主 session 定讞）

### 根因（run `data/runs/20260724-004440/`，主 session 讀碼確認、皆確定性）

- **A（identify 前置崩潰）**：`CoverageScanSource.nudge()`（live_scan.py
  ~567）寫 `self._nudges += 1`／`self._last_nudge`，但這些欄位只在
  `collect()`（~216）初始化；`controller._navigator()`（~1502）每次 new
  全新實例供 `survey_stage` 的 `bring_to_view()` 用、從不跑 `collect()`
  ——目標點不在畫面內時首次 `nudge()` 即 `AttributeError`，Python 進程
  整個掛掉。輪五兩個候選恰在畫面內僥倖未踩。既有測試對真實
  `bring_to_view()`→`nudge()` 路徑零覆蓋（全部注入 `_identity_view` 假件）。
- **B（late-arrival 跳過 scout，既有缺陷被批8 引爆）**：`_on_our_turn`
  的 late-arrival 分支（~925-935）直接 tap `FIRST_UNIT_CARD`，跳過
  happy path 的全部前置（`timeline.on_turn_read` 回合簿記、
  `_snapshot_factions`、`board_belief`、`_scout`、
  `_ensure_stage_definition`、`_refresh_sig_positions`、
  `_consult_advisor`）。批8 修復使「收合態開場」必然流經此分支：輪六
  開場「諸耶・吉爾 (EX)」被直接選取並真實攻擊一次（合法操作、非
  AUTO，但浪費行動且簿記缺漏）。

### 範圍

1. **A 修法（嚴格限定生命週期，不碰演算法）**：把 `nudge()`／
   `bring_to_view()` 路徑依賴的可變走圖狀態（`_nudges`、`_last_nudge`，
   及該路徑實際觸及的其他 collect-only 欄位，以讀碼為準）移到
   `__post_init__` 初始化；`collect()` 保留原地重置（行為位元級不變）。
   **frontier／回復協定／integrate 邏輯零改動**（批7 紅線不破）。
2. **B 修法（單一路徑）**：把 happy path 的 cards-present 處理抽成單一
   內部 helper；late-arrival（含批8 修復後重讀）改走同一 helper——
   選單位之前必經回合簿記與 scout 閘門，不再有第二條「直接選卡」路徑。
   有界重入（一次），避免卡條閃爍造成迴圈。
3. **回歸測試（先紅後綠）**：
   - A：全新 `CoverageScanSource`（fake capture/swipe/tap）直接
     `bring_to_view()` 一個需要 nudge 的目標——舊碼 AttributeError、
     新碼正常；**不得用 `_identity_view` 假件繞過**。
   - B：收合態開場 → 批8 修復 → 卡片出現 → 必須先跑 scout 閘門
     （斷言 `_scout`／`on_turn_read` 在 `select_unit` 之前），舊碼直接
     select 會失敗。
4. 附帶回寫：既有 `survey_stage` 測試全用 `_identity_view` 的盲區記入
   測試註解或 audit 清單。

### 紅線
- `CoverageScanSource` 只准動狀態初始化位置；掃描演算法本體零改動。
- 不碰 `_on_our_turn` 之後的 solver 職權；helper 抽取＝行為歸位、非新流程。
- 基準 831 passed／3 xfailed 只增不減＋ruff 綠。

### 驗收標準
- 全新實例 `bring_to_view()` 需 nudge 的路徑不再崩潰（真實路徑回歸測試）。
- `_on_our_turn` 只剩一條選單位路徑，late-arrival 必經簿記＋scout 閘門。
- 先紅後綠有紀錄；`collect()` 行為不變（既有覆蓋掃描測試全綠不動）。
- 上機驗證＝輪七：同冷探索協定，identify 應通過 `bring_to_view` 進入
  逐台分流（Round 1.5 的 `side="unit_move"` 通道在此輪才真正受測）。

## Round 1.7：敵機選取殘留防禦＋定位飢餓煞車＋refused 存證（輪七敗因修復，2026-07-24 主 session 定讞）

### 根因（run `data/runs/20260724-012023/`；流水帳＋讀碼＋影像鑑識三方交叉定讞）

**症狀簽名**：任何朝未知領域的 nudge（北 8、東 48）全數 localize_refused、
任何退回覆蓋區的回復（南、西）全數 relocated，從錨定第一推（t=26.5）開始
方向無關；全場僅 3 次「成功」定位且 offset 跳 7/10 格、west 邊 11→4→1→
終局 11 翻動＝偽定位；110 nudges 燒完預算 outcome=budget。

**根因＝敵機選取殘留態從掃描開始前就在場**（影像鑑識：t0005 幀左上已有
「史列加・羅 vs G-3鋼彈」比較 HUD＋紅色威脅範圍色塊，數值與 t0228／6 分
鐘後截圖逐像素凍結）：
- 亮色 HUD（螢幕錨定，x0-40%/y0-25%）壓在星空區→污染批7 亮度濾波與
  全幀格線外插；紅色範圍色塊（世界錨定）染紅一片格子→污染地形指紋。
- 螢幕錨定內容在鏡頭移動時投「offset=(0,0)」假票：低重疊外推幀被假票
  壓過→refused；退回高支持度覆蓋區真票佔優→relocated。與輪六（乾淨幀、
  首擊 71%）對照成立。
- 此殘留態對 `is_unit_detail_modal` **全盲**（2340×1080 截圖
  `assets/screenshots/20260724-013030.png` 實測 False）；成因未定
  （pinch 手指路徑誤觸敵機為主嫌），**任何一輪都可能復發**。

**連帶機制缺口（讀碼確認）**：①`collect()` 填圖迴圈 refused 路徑
`continue` 繞過 stuck 計數、`_recover` 不寫回任何狀態→無煞車，唯一出口
是外層預算（110 nudges ≈ 9 分鐘）；②refused 幀零存證（本次鑑識被擋在
這裡）；③流水帳存幀是 1280×591 縮圖，校準探針不能直接跑。

### 範圍

1. **選取殘留偵測器**：`vision.enemy_selection_active(frame) -> bool`，
   校準樣本＝`assets/screenshots/20260724-013030.png`（全解析度正樣本，
   裁 fixture 入庫）；負樣本＝既有乾淨 fixture корpus（含輪六 t0084 升採樣）。
   偵測目標選比較 HUD 資訊條（結構化高對比、螢幕錨定）；單樣本過擬合
   風險記入 fixture note＋缺樣清單（下輪實機順手補第二正樣本）。
2. **解除機制**：障礙清除鏈擴充——順序＝unit_detail_modal（tap 關閉）→
   選取殘留（**空地 tap 解除**：復用 `pick_pinch_center` 的 max-min
   clearance 選無單位空點，tap 後重截驗證偵測器轉 False，一次重試後
   fail loud）。接線點：掃描前置（錨定之前）＋填圖迴圈 refused 路徑
   （進 `_recover` 前先查一次障礙，清掉就重試 placement 不消耗回復）。
3. **定位飢餓煞車**：連續 K 次主向 refused（不論回復成功與否、期間零
   integration 進展）→ `SurveyIncomplete("localization starving: ...")`
   誠實早停（K 取 6，預期 <90 秒回報 vs 本輪 9 分鐘）。**不動
   frontier／integrate／localize 語意**；只加 refused 簿記＋早停出口。
4. **refused 存證**：前 3 次＋之後每 20 次 refused 存原生解析度幀
   （ledger 既有縮圖管線之外的診斷存檔，路徑入 ledger 事件欄），abort
   時的 coverage_report 附 refused 統計欄。
5. 附帶：`survey_abort` 訊息帶 refused/relocated 統計。

### 紅線
- frontier／integrate／localize／回復方向選擇的演算法語意零改動；煞車
  只在「先前必然燒預算」的路徑上新增誠實早停。
- 空地 tap 解除必須經 clearance 選點＋tap 後驗證，絕不點單位/UI。
- 偵測器閾值需 fixture 佐證；單正樣本風險明文記錄。
- 基準 834 passed／3 xfailed 只增不減＋ruff 綠。

### 驗收標準
- 013030 正樣本＋乾淨負樣本全數正確分類（fixture 測試）。
- fake 驅動：選取殘留在場→掃描前置偵測並解除→定位恢復（舊碼無此
  防禦，測試先紅後綠）；殘留無法解除→fail loud 不進錨定。
- fake 驅動：連續 refused K 次→SurveyIncomplete 早停（舊碼燒滿預算，
  先紅後綠）；正常收斂路徑（輪六型）行為不變（既有 coverage 測試全綠）。
- refused 存證：fake 迴圈驗證存檔節流（3＋每 20）與 ledger 欄位。
- 上機驗證＝輪八：開場若殘留在場應被前置防禦清掉；掃描應恢復輪六型
  收斂並繼續往 identify；若再退化應 <90 秒帶完整證據回報。

## Round 1.8：地形指紋共識化＋refused 遙測（輪八敗因修復，2026-07-24 主 session 定讞）

### 根因（run `data/runs/20260724-023014/`；原生診斷幀離線實驗鏈定讞）

輪八 Round 1.7 兩防禦實戰生效（殘留一次解除未復發、煞車 130 秒誠實
早停），新敗因＝east 死鎖：最後真實進展（t=86.7）後 east 全 refused／
west 回復全 relocated，starved 中止，east 邊未註冊。主 session 用三張
原生 refused 診斷幀做的離線實驗鏈：
1. 幀本身完全可讀（格線 24×12、east 截止緣 x≈1866、5 單位峰、無殘留）。
2. 乾淨地圖上互相定位＝edge_pin (0,0) 完美成功。
3. 強制純投票路徑＝margin 10.0／fraction 1.0 輕鬆過門檻（門檻 2.5/0.5）。
4. `_search_range` 覆蓋全域無偏置。
→ 幀、計分器、搜尋皆健康，**病灶＝run 中累積的地圖態**。結構缺口：
`CellMap.integrate()` 的地形指紋 `self._terrain[gcell] = fp` **無條件
覆寫（last-write-wins）**——單位證據有 support 共識（批2），地形沒有；
一次勉強過門檻的錯位整合（t=86.7 margin=4.5 vs 門檻 2.5）可改寫上百格
參考真相，其後誠實幀對腐化參考在任何候選 offset 都湊不出 margin →
永久 refused。本輪 16 次整合（含 10 次 relocation 整合）任一次錯位即
觸發此病。輪七的同款「外推 refused／回復 relocated」簽名在殘留清除後
仍複發＝同一結構缺口的第二例證。

### 範圍（兩項，皆可離線驗證）

1. **A refused 遙測**：refused 的 `LocalizeReport` 已載 margin／
   unit_hits／terrain_fraction（read 得到、沒記）——`refused_frame`
   ledger 事件補這三欄＋當幀 `obs.edges` 可見性；`scan_recovery
   localize_refused` 事件同步補。零行為變更。
2. **B 地形指紋 first-write-wins＋衝突計數**：`integrate()` 地形改
   首見保留（後見只填新格、不覆寫既有格）；同時計數本次整合中「既有
   指紋與來幀指紋不合（依 `TERRAIN_MATCH` 距離）」的格數，記入
   `frame_localized`／`scan_recovery` 事件新欄 `terrain_conflict`——
   高衝突整合＝錯位即時警訊（下輪遙測直接定讞）。**單位 support、
   計分閘門、frontier、steering、回復方向全部零改動。**

### 紅線
- 只動 `integrate()` 的地形寫入策略與 ledger 欄位；localize 各閘門
  數值與語意不動。
- 正常收斂 run（同視野重寫＝指紋近同）行為等價；行為分歧只發生在
  「錯位改寫」情境＝本 bug 本身。既有 coverage 測試全綠且不修改。
- 基準 852 passed／3 xfailed 只增不減＋ruff 綠。

### 驗收標準
- 輪八情境蒸餾回歸測試（先紅後綠）：正確地圖上疊一次錯位整合 →
  誠實同視野幀定位；last-write-wins 下 refused（紅）、first-write-wins
  下正常定位（綠）。
- terrain_conflict 計數測試：錯位整合報高衝突、同視野重整合報零衝突。
- refused 遙測欄位測試（fake 迴圈斷言欄位齊全）。
- 上機驗證＝輪九：同冷探索協定。**若輪九仍在掃描主體失敗，依 CLAUDE.md
  紀律停下問使用者**（該層將計連續兩輪修復嘗試未過），不再自行開輪十。

## Round 1.9：identify 臨場複驗＋失敗存證（輪九敗因修復，2026-07-24 主 session 定讞）

### 根因脈絡（run `data/runs/20260724-031546/`）

輪九掃描主體決定性 PASS（552/552、10 nudges、0 refused、首擊 100%、
四邊全註冊）＝Round 1.8 完全生效；terrain_conflict 常值 44-71 揭露
星空指紋固有雜訊——LWW 時代每次整合都在改寫 ~50 格參考，解釋了歷輪
首擊率漂移（32%/71%/23%），FWW 凍結參考後 100%。**該欄位健康基準修正
為「太空圖常值 40-70」**，不是錯位警訊（錯位警訊＝顯著高於本關常值）。

identify FAIL 於 index 5/31：tap (1263.0,419.0) 三次重試無 banner、
非 SELECTION_SUBSTATES（Round 1.5 閘門未觸發＝新簽名）。census 31 候選
vs 標準答案 27 台＝**池含 ≥4 幽靈候選**。兩假說症狀相同：(a) 幽靈候選
（掃描期弧/密度偵測假陽性過 support 門檻）；(b) `TacticalMap.locate()`
星群平移錯位使 tap 落空地。現行 ghost-drop 只在「貼近已知我方」時放行
（`ghost_of_ally`），遠離我方的幽靈無路可退→fail loud。identify 失敗
路徑零存幀（同 Round 1.7 前的 refused 觀測性缺口）。

### 範圍

1. **tap 前臨場複驗（treats both 假說）**：`_identify_at`／
   `_read_summary_at` 在 no-banner 重試耗盡前，對 tap 當下的幀跑單位
   偵測（`find_unit_density_peaks`）檢查 tap 點半徑內（一格 ≈95px，
   常數化）有無單位峰：
   - **無峰**＝當下負面視覺證據 → 候選以 `survey_phantom`
     reason=`no_unit_at_tap` 帶證據 drop，survey 繼續（認識論同「邊界
     只在看見時成立」——看了、確實沒有，非猜測）。
   - **有峰但偏離 tap 點** → snap-to-peak 重 tap 一次（半徑內最近峰的
     實際像素位置）；成功讀 banner 照常，仍無 banner → fail loud
     （零猜測不變）。snap 只做一次；mis-attribution 風險（貼鄰單位）
     以半徑 <1 格控制並記入 ledger（`snap_tap` 事件含原/新座標）。
2. **identify 失敗存證**：no-banner 失敗（drop 或 fail loud 前）存原生
   解析度診斷幀（沿用 `ledger.save_diag_frame`，首 3 張＋每 10 次），
   事件記幀路徑。
3. **不碰**：`TacticalMap.locate()`／dock 閘門／`SELECTION_SUBSTATES`
   閘門（Round 1.5）語意——錯位假說待輪十的診斷幀定讞後再議。

### 紅線
- 零猜測政策不變：drop 必須有「當下無峰」的視覺證據；有峰無 banner
  仍 fail loud。
- 座標/閾值只引入「一格半徑」常數（由 cell_size 95px 推導、註明依據）。
- 基準 864 passed／3 xfailed 只增不減＋ruff 綠。

### 驗收標準（先紅後綠）
- 幽靈候選（tap 點無峰）→ 帶證據 drop、survey 繼續；舊碼 fail loud（紅→綠）。
- 偏位真單位（峰在半徑內）→ snap 重 tap 後讀到 banner；舊碼三次原點重試失敗（紅→綠）。
- 有峰、snap 後仍無 banner → fail loud（零猜測保留，測試釘住）。
- 診斷幀節流與 ledger 欄位（fake 迴圈斷言）。
- 上機驗證＝輪十：identify 應消化 31 候選池（預期 ~4 幽靈 drop 有據、
  其餘讀出）、首次觸發 unit_move 通道、`survey_complete`＋定義檔匯出
  →續跑暖掃。identify 若再敗＝該層計連續兩輪修復未過，停下問使用者。

## Round 1.10：錨定證據閘門＋anchor phase 煞車（輪十敗因修復，2026-07-24 主 session 定讞）

### 根因（run `data/runs/20260724-035547/`；探針鑑識定讞）

輪十掃描主體全新簽名崩壞：anchor 後 0 次 `frame_localized`、98 nudges、
14 次 recovery 全 exhausted、margin 幾乎全 null。探針鑑識：
- **anchor 幀（t0005 升採樣）units=0**——鏡頭停輪九收工的東北角空曠區，
  幀內只有東/北緣＋均勻星空，無任何單位峰。
- diag 幀 d2/d3 同樣 units=0（西緣可見、無單位）；d1 `observe_frame`
  =None 且偏暗（34.5 vs 正常 48.9，疑省電鎖變暗過渡，次要）。
- 機制：均勻星空地形讓多個候選 offset 近同分→margin 崩（首拒 1.0＜
  2.5）；回復幀同無單位→配不回參考；anchor phase 外層 west 8 vs 回復
  east 48 的不對稱預算造成淨東漂 +40，脫離重疊窗後 margin=null 永久
  迷航。輪九同版程式滿分＝起始位置恰有單位入鏡；**結構缺口＝錨定參考
  無證據閘門，零單位參考在太空圖上不可定位**。anchor phase 無煞車，
  56 nudges 空燒（fill loop 的 STARVE_LIMIT 管不到它）。

### 範圍

1. **錨定證據閘門**：`collect()` 錨定前檢查幀單位峰數 ≥
   `ANCHOR_MIN_UNITS=1`（常數化、註明依據：單位星座是定位證據主幹，
   零單位＋均勻地形＝不可定位參考）。零單位時**朝地圖內裡尋找單位**：
   方向由幀內可見截止緣推導（見東緣→往西、見北緣→往南；皆不可見→
   依 `find_unit_density_peaks` 全幀掃描的質心方向；再不然固定順序
   試探），有界推進（復用 `ANCHOR_MAX_NUDGES` 額度），每步重讀峰數；
   預算耗盡仍零單位 → `SurveyIncomplete("anchor without units")` 誠實
   中止。**方向只來自畫面證據、不進座標計算（定案 1 不破）。**
2. **anchor phase 煞車**：與 fill loop 相同的連續零進展計數
   （`STARVE_LIMIT` 復用），anchor phase 連續 K 次 refused＋recovery
   exhausted → 誠實 `SurveyIncomplete`，不再 8×6 空燒漂移。
3. **不碰**：fill loop 語意、`coverage_map.py`、Round 1.9 identify 鏈。

### 紅線
- 方向推導只用畫面證據（可見邊/峰質心），不做座標幾何。
- 基準 870 passed／3 xfailed 只增不減＋ruff 綠；既有 coverage 測試
  全綠不修改。

### 驗收標準（先紅後綠）
- 零單位起始世界：閘門引導至有單位區後成功錨定（舊碼直接錨定→迷航
  starve；新碼收斂）。
- 全圖無單位世界：預算耗盡誠實中止（不漂移空燒）。
- anchor phase 連續失敗 → K 次即停（舊碼 8×6 空燒，紅→綠）。
- 有單位起始（輪九型）→ 行為不變（既有收斂測試全綠）。
- 上機驗證＝輪十一：**掃描主體若再敗（任何簽名）＝該層在錨定議題上
  連續兩輪未過，停下問使用者**；PASS 則 identify（Round 1.9 首戰）
  →暖掃連跑。

## Round 2（草案，待 Round 1 上機結果回報後由主 session 重新規劃細節）

方向：把 `_scout` 裡 `if self.timeline.due("full_scan", ...)` 這段目前寫死
的直線流程（回到 hub → 收合列表 → 開格線 → zoom 到底 → `collect()` → 關格線，
controller.py ~1397-1458）升格成宣告式 Action／Goal，重用既有
`goap/planner.py` 的 A*（`goap/action.py` 的 `Action`/`Goal`，不需新機制，
外層 `AgentLoop` 已經是同一顆 planner 的另一個實例）：

- 狀態空間：`map_view.classify_frame` 現有的 `VIEW_STATES` 詞彙
  （hub/modal/settings/unit_move/...）＋新增 `unit_list`（expanded/
  collapsed）、`grid`（on/off）、`zoom`（max/not_max）述詞。
- Action 集合：`ReachHub`、`CollapseUnitList`、`EnableGrid`、`ZoomToMax`、
  `RunCoverageScan`（包住現有 `CoverageScanSource.collect()`，內部機制
  不變）、`ReleaseGrid`，每個都是 precondition/effect＋act-verify
  （鏡照 `AgentLoop.run()` 現有模式）。
- 好處：新的意外畫面（劇情彈窗、設定頁誤入）只需要新增一個 Action，
  不用巡查 N 個手寫迴圈各補一次；這是本輪要解的具體技術債的根治，
  不只是繞過症狀。
- 範圍與驗收標準留待 Round 1 的上機結果出爐後、由主 session 針對實際
  發現的失效模式重新寫 dev-plan（避免在 Round 1 結果未知時過度設計）。

## 風險與邊界

- 兩輪都不碰 `CoverageScanSource`／`coverage_map.py` 的掃描演算法本體
  （frontier/回復協定/惡意世界收斂測試）——那條線批7 才剛鎖死、仍是零
  實機驗證，不應該在同一輪疊加變因。
- 兩輪都不碰 `_on_our_turn` 之後的單位選取/攻擊決策（solver 職權），
  只動「這回合機制前提是否滿足」這段。
- Round 1 的三處呼叫端改動（controller/live_scan/map_view）都是「轉呼叫
  同一函式」而非「改變行為」，離線測試應該能在不看真機的情況下把回歸
  風險壓到很低；真正需要上機才能驗證的只有「三值化後 `_on_our_turn`／
  `_set_unit_list_open` 的決策分支是否真的接住輪四那種場景」。

## 現況與待續點（2026-07-23 本次規劃 session 收工）

**已完成**：
- 本文件的架構討論與 Round 1/Round 2 規劃已與使用者核准
  （plan 檔 `~/.claude/plans/opus-subagent-composed-moler.md`，內容與本檔
  一致，本檔為 git 版永久記錄）。
- Worktree 整理：`git worktree list` 原有 16 個孤兒 worktree（歷史批次
  T1-T10／批1-8 留下），逐一核對 branch tip 是否已是 `feat/inner-goap`
  的祖先後，**15 個確認已合併並清除**。**1 個未合併、刻意保留未動**：
  `.claude/worktrees/agent-a6dfce2035d900d36`，branch
  `worktree-agent-a6dfce2035d900d36`，tip `8b1b6df`（commit message：
  「#26 批4後續: LLM 定位 probe B——弱版 patch 選擇器 vs 確定性基準，
  裁決皆不可行（只量測不接線）」），內容為
  `docs/llm-localize-probe-b.md`＋`scripts/llm_localize_probe_b.py`＋
  `tests/test_llm_localize_probe_b.py`（純新增檔案，跟主線無衝突）。
  **待使用者決定**：併入主線（純測量報告，本身已裁決「不接線」，併入
  價值主要是保留分析過程）、或直接捨棄這個 worktree/branch。

**卡點（本次規劃 session 未能執行）**：
- Round 1 的 opus dev subagent dev-plan 已經寫好（內容＝本檔「Round 1」
  整節），但**尚未派出**——`Agent` 工具的 subagent 派遣額度在規劃階段的
  Explore 呼叫就已經 20/20 用滿（額度似乎是這個 session 稍早的批次工作
  累積用掉的，不會在同一 session 內重置）。

**下一步（新 session 接續）**：
1. 開工前先確認/調高 `CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION`（見 memory
   `delegation-execution-model` 實務坑④）。
2. 直接照本文件「Round 1」小節派出 opus subagent（`isolation: "worktree"`，
   dev-plan 內容即本檔 Round 1 整節的展開版——上一個 session 已經寫好完整
   prompt，可從對話記錄或本檔重建，不需要重新設計）。
3. 主 session 驗證（pytest+ruff+diff 審查）→ merge 進 `feat/inner-goap`。
4. 派 sonnet subagent 依「上機驗證」小節跑輪五冷探索協定。
5. 結果回報後決定 Round 2 範圍，或視失敗模式停下問使用者。
6. 順手處理上面「待使用者決定」的孤兒 worktree。

裝置現況與批7 之前的所有既定事實不變，見 `docs/roadmap.md` 07-23 暫停
快照本節。本次規劃 session 全程未碰裝置、未修改任何 `src/`／`tests/`
程式碼，只做了唯讀探索與上述 worktree 清理（git 操作，非程式變更）。
