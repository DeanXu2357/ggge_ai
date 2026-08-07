# Review 導覽：盤面掃描覆蓋模型 v2（2026-07-31）

基底 `feat/inner-goap` @ `5d1a9cb`。規格＝`docs/survey-coverage-v2.md`（0730
使用者三輪問答定案）。本批**取代**「各方向平移次數」制的覆蓋簿記，改為世界
空間的四態知識圖＋邊界旗＋待掃格導向補掃＋五層位移量測防禦＋衰效降級。純程式
碼，未碰實機。

**設計決定清單在本檔末尾**，審過再由主 session 併進 `docs/decisions.md`。

## Commit 全景

| commit | 內容 |
|---|---|
| `409fdbd` | 覆蓋模型 v2 核心：`runtime/coverage.py`＋量測雙閘＋待掃格執行器＋`StageState.swept` 淘汰 |
| `29448bc` | 格網讀取分帶多尺度（最小縮放讀得到）＋最小縮放 fixture |
| （本檔） | review 導覽＋設計決定清單 |

閘門：`uv run pytest -q` → **1506 passed, 4 skipped, 3 xfailed**；
`uv run ruff check src tests scripts` → **All checks passed**。
（基底 `5d1a9cb` 的數字未在本 worktree 複跑；roadmap 快照記的是合併樹
1470 passed＋1 flaky＝凍結層 `test_not_actionable` 的時鐘抖動。本批兩次
全跑都沒有踩到那條 flaky。）

---

## 一、呼叫鏈與執行順序

### 符號層（不變）

```
規劃器 —— 只看 board_synced
  ShowGrid       → grid_on
  CollapseRoster → roster_collapsed
  SurveyBoard    前置 grid_on ∧ roster_collapsed ∧ ¬board_synced
                 效果 board_synced（搜尋側一步到底）
                 progressed(state) == state.board_synced
```

`SurveyBoard` 的 applicable／apply／progressed 一個字都沒改。變的只有
`board_synced` 這個位元**怎麼被算出來**：v1 是「合併微步驟寫回過一次」，v2 是
「四旗全定 ∧ 界內無 UNKNOWN/STALE」（＝沒有待掃格）。

### 一個 tick 的執行順序

```
StageLoop.tick()
 └─ SurveyPerceiver.look()                       stage/survey.py
     ├─ inner.look()                             （LivePerceiver：截圖＋read()）
     ├─ 敵方相位且本回合還沒衰效 → ledger.expire()
     ├─ state.board_synced ← ledger.synced       ← Survey.complete
     └─ evidence["survey"] ← ledger.summary()    ← 逐 tick 覆蓋自述進流水帳
 └─ …規劃…
 └─ LiveExecutor.perform(SurveyBoard) → BoardDriver.survey_board()
     ├─ 還沒縮放 → zoom_out()（注入件）→ survey.reset() → 回 "zoom"
     ├─ frame = capture()
     ├─ survey.observe(frame)                    ← 無指令：只准「幾乎沒動」
     ├─ leg = survey.plan_leg()                  ← 待掃格聚類 → 目標 → 一步
     │    └─ None → "done"／"fuse"／"stuck"
     ├─ actuator.swipe(pan_gesture(leg.direction, origin, leg.reach))
     └─ survey.observe(capture(), leg)           ← 有指令：過合理範圍閘＋相位閘
        回 "sweep:<方向>"（錨不到世界時是 "blind:<方向>"）
```

### `Survey.observe()` 內部（量錯寫入的唯一防線都在這裡）

下面的「島嶼」＝定位中斷後位置不明的觀測暫存區，等重新定位才併回權威圖。

```
observe(frame, leg)
 ├─ chart is None            → _anchor()：讀格網 → WorldGrid → 吸收首幀
 ├─ adrift（剛換代）          → _isolate(reason="generation")
 ├─ odometer.feed(frame, leg.expected)
 │    ├─ measure_shift（相位相關；無特徵退單位排列比對投票）
 │    ├─ 位移小 ∧ 幀差 ~0     → 位移取準確的 0（停滯）
 │    ├─ board.envelope()     → REFUSED ⇒ BROKEN("envelope")
 │    ├─ _snap()：格線相位交叉驗證 → 對不上 ⇒ BROKEN("phase")，對得上就吸附
 │    └─ 停滯判定（有指令卻沒動）→ STALLED
 ├─ BROKEN  → _isolate()：側緩衝，**不進權威圖**
 ├─ 島嶼開著 → island.views.append() → _reanchor()
 │              ├─ 撞邊釘軸（_pin）／單位排列比對重定位（_solve）→ 整批 shifted() 併入
 │              └─ 耐心用完 → _abandon()：丟棄＋世界重開
 └─ 否則    → chart.absorb(view)＋_boundary()（連兩次停滯才釘邊界旗）
```

---

## 二、資料結構逐條對規格

| 規格條目 | 落點 |
|---|---|
| 世界錨定（turn-1 首幀＝原點、逐次平移的量測和、格線相位吸附） | `Odometer`（`offset`／`_snap`／`rephase`） |
| 知識圖四態 | `Knowledge`＋`KnowledgeMap.state`（缺席＝UNKNOWN） |
| 邊界旗（只由撞邊事件建立、幾何不衰效） | `KnowledgeMap.boundary`／`fix_boundary`；`expire()` 不動它 |
| 完成判準（建構性） | `KnowledgeMap.complete` = `bounded ∧ not gaps()` |
| 待掃格（界內、鄰接已測繪、UNKNOWN/STALE） | `KnowledgeMap.frontier()` |
| 未定方向旗＝強制待掃 | `Survey._probe()`（沒有待掃格時往未定方向推） |
| 聚類＋近者優先＋STALE 加權 | `clusters()`／`KnowledgeMap.choose()`／`STALE_WEIGHT` |
| 單次平移距離規則（≤ 無歧義範圍的一半） | `LEG_LIMIT`（由 `MAP_REGION` 推導）＋`Survey._leg()` |
| ①主里程計 | `board.measure_shift`（未改） |
| ②指令合理範圍閘 | `board.envelope` |
| ③格線相位交叉驗證 | `board.phase_residual`＋`Odometer._snap` |
| ④單位排列比對＝全域重定位器 | `board.relocalise`（＋回驗支持數） |
| ⑤撞邊重錨＝絕對參考 | `Survey._pin`（島嶼在已知邊界撞邊 → 釘該軸） |
| 島嶼側緩衝／重錨／丟棄 | `Island`／`_isolate`／`_reanchor`／`_abandon` |
| 衰效（UNIT→STALE、EMPTY→UNKNOWN、generation+1、zoomed 與邊界旗不歸零） | `KnowledgeMap.expire()`＋`Survey.expire()`；`CoverageLedger.zoomed` 不動 |
| STALE 永不出沙盤 | `KnowledgeMap.units()` 只吐 UNIT |
| journal 逐 tick（覆蓋率／待掃格聚類數／unlocalised／島嶼事件） | `Survey.summary()` → `evidence["survey"]` |

---

## 三、爭點（請優先看這幾條）

### 1. `StageState.swept` 提案：**淘汰，不換成覆蓋率記帳**

- 現況：`swept: frozenset[str]` 沒有任何 `applicable`／`progressed`／goal 讀它，
  它唯一的作用是被 `_seen()` 抄進流水帳。
- v2 的進度是逐格知識圖，壓不成一個搜尋鍵放得下的東西；換成覆蓋率整數更糟——
  A\* 的節點identity會被它切碎（覆蓋率不同的等價盤面不再重合），而
  `next_player_phase` 還得多記得歸零它。
- 「恢復點必須 `progressed` 看得見」（0730 定向）仍然成立，落點就是
  `board_synced`：它由 `CoverageLedger.synced` 供給，而 `CoverageLedger`
  是跨 tick 活著的簿記——換一個 `BoardDriver` 實例照樣接得下去
  （`test_the_driver_resumes_from_the_ledger_not_from_its_own_variables`）。
- 規格要的逐 tick 覆蓋數字改走 `evidence["survey"]`，迴圈本來就把 evidence
  整包抄進流水帳，不必動迴圈一行程式。
- 備選：(a) 保留欄位改義為「已定邊界的方向集」——名字誤導（v2 沒有「掃過某個
  方向」這回事）；(b) 改 `coverage: int` 百分比——上面說的搜尋鍵污染。兩個都比
  淘汰差。**這條請使用者裁**：淘汰是不可逆的介面縮小。

### 2. 「界內但看不到」的格：明寫退休，不當完成

實測（合成世界）發現地圖角落壓在回合橫幅（`UNIT_DENSITY_HUD_HOLES`）底下的格**從
任何推得到的鏡頭位置都看不清楚**：鏡頭夾在西邊與北邊的邊界上，橫幅在螢幕座標固定
不動。照規格字面「界內無 UNKNOWN → 完成」，這種格會讓待掃格永遠清不完。

處理：`KnowledgeMap.unreachable`。只有在「往目標的兩個軸向**此刻都頂在邊界上**」
時才退休那一格（`Survey._aim`），退休數字逐 tick 進流水帳。這是規格沒寫的情形，
我選了「明寫退休＋出聲」而不是「悄悄當成掃完」或「永遠掃不完」。

### 3. 合理範圍閘的上界：1.5× 之外多一段 2.5×「重複執行」

規格同時要求「量測落在 0~1.5× 指令」與「重複執行（2×）照量入帳」。字面 1.5× 會把
2× 判成定位中斷。實作取兩段：`≤1.5×` = `ok`、`1.5~2.5×` = `repeat`（照樣入帳、
流水帳看得到），`>2.5×` 或反號或跨軸 = `refused`。量測窗繞回誤判的值差一整個窗寬
（x 軸 1600），對 350px 的指令而言不是反號就是 ≥1250，兩段之外，擋得住。

### 4. 相位交叉驗證只驗直線軸

橫線間距隨 y 從 108 遞增到 123（縱向透視，`board.py` 既有實測條文），對橫軸取模
的相位**不是不變量**——拿它當閘會誤殺，拿它吸附會整列跳掉。所以橫軸的保護只有單次
平移距離規則（單次 ≤ 窗高/4 = 155px，遠小於無歧義範圍 310px）＋合理範圍閘。

### 5. 島嶼重錨失敗的復原＝誠實重開世界（規格的「開到最近已知邊」未實作）

規格寫「最壞復原＝開到最近已知邊歸零」。那需要一套「islanded 時改朝已知邊界
轉向」的 steering。本批取有界的替代：島嶼耐心（6 幀）用完就整批丟棄並在當下
這一幀重新錨定，代價是一次全掃，收益是永遠不會有不知道位置的觀測寫進權威圖。
撞邊釘軸（層 5 的另一半）有實作。

---

## 四、測試

| 檔 | 內容 |
|---|---|
| `tests/fixtures/synthetic_map.py` | 合成世界：畫布上畫格線與單位環，裁視口＝截圖；鏡頭夾在畫布內（撞邊是世界的性質不是腳本插旗） |
| `tests/test_runtime_coverage.py` | 38 條：四態／待掃格／聚類／邊界／衰效的單元層＋雙閘＋重定位器＋六個整段劇本 |
| `tests/test_runtime_board.py` | 格網（含最小縮放 fixture）、密度峰、位移量測、實幀系列半真實回放 |
| `tests/test_stage_survey.py` | 符號建模、微步驟名、簿記恢復、感知接縫、evidence 進流水帳 |

整段劇本（合成世界，逐格對答案）：

- **乾淨**：16 tick 收斂，5 台單位格座標與擺位一致，覆蓋率 0.989。
- **吃指令**（第 2/3/7 次手勢被吞）：照樣收斂、單位格全中——一次停滯不釘邊界旗。
- **重複執行**（第 2/5/8 次手勢走兩倍）：照樣收斂、零島嶼；跳過的帶由
  待掃格回補。
- **unlocalisable**（三張全黑幀）：隔離 → 重錨／丟棄，最終覆蓋與單位格全中。
- **鏡頭跳走**（量測窗繞回誤判的實機版）：合理範圍閘擋下 → 島嶼 → 單位排列比對重
  錨 → 併入。
- **回合交界**：UNIT→STALE、EMPTY→UNKNOWN、邊界旗保留、`units()` 立刻不吐
  STALE；下一輪島嶼重錨成功、再度收斂到同一組格座標。

0719 的九幀實幀系列是**半真實**案例：它是用舊的單次平移距離拍的（一把約 600px，
量測窗只有 620 高），縱向那幾把本來就量不準。回放斷言的不是「掃得完」，而
是**量不到的時候不會亂寫**：定位中斷一律進島嶼、島嶼帳目自洽、一輪掃描裡不會
冒出 STALE。

---

## 五、實機證據（0731 pinch 煙測）的回應

| 發現 | 處置 |
|---|---|
| 最小縮放下 `read_lattice` 讀不到（欄距 91.5／列距 86，舊帶下限 90） | `SPACING_BANDS` 分帶多尺度，細帶先試 |
| `_ridges` 的 90px 最小間距會把細格網隔行取線、湊出翻倍格距 | **細帶先試**就是防這個：粗帶只有在細帶不成立時才輪到 |
| `grid_on` 信念縮放後翻 False，恐讓規劃器中途重排 ShowGrid | 同一個改法從根解決（讀得到格網 → `read()` 的 `grid_on` 回 True）。沒有改成組合證據——那會讓「地圖上讀得到格線」不再是唯一判準 |
| 西緣地圖外星空背景的無特徵帶 unlocalised | v2 的既定路徑：定位中斷 → 島嶼 → 重錨／丟棄，不再「保留舊 offset 照樣寫」 |
| 地圖邊緣半幅虛空破壞格網均勻性閘 | `plan_leg` 在還沒錨定時照樣給一把平移（`blind:<方向>`），換個視野再讀；步名分得出來 |

新增 fixture `tests/fixtures/vision/map_scan/min_zoom_grid_20260731.{png,json}`
（來源 `data/runs/20260731-170423/frames/00013-tick0053.png` 的 `GRID_REGION`
裁切），釘住最小縮放的線位；另一條測試釘住「只有粗帶會瞎掉」。

---

## 六、設計決定清單（規格未明定、我自行裁量的每一點）

| # | 決定 | 選項與理由 |
|---|---|---|
| D1 | `StageState.swept` **淘汰**（不改覆蓋率記帳） | 見爭點 1。(a) 保留改義為邊界方向集：名字誤導；(b) 改覆蓋率整數：污染 A\* 節點 identity；(c) 淘汰＋覆蓋數字走 evidence。採 (c)。**這是介面縮小，請使用者確認。** |
| D2 | 世界模型落 `runtime/coverage.py`（新檔），`stage/survey.py` 只留符號接縫與執行器 | 知識圖與里程計是像素／幾何機制，兩層共用、與行動詞彙無關；module-map 規定 `runtime` 不得 import `stage`（這支只 import `runtime/board`）。放 `stage/` 會讓感知機制綁在內層 GOAP 上。 |
| D3 | 退休 `runtime/board.py` 的 `ScanCursor`／`BoardScan`／`walk`／`at_edge` | v2 的 `Survey`＋`KnowledgeMap` 完全取代它們的職責；留著就是兩套覆蓋真相（`unlocalised` 兩份、`cells()` 兩份）。`at_edge` 的語意搬進 `Odometer`（量一次用兩次，不再重算 shift）。 |
| D4 | 合理範圍閘三段（ok／repeat／refused） | 見爭點 3。規格兩句話互相牴觸，取「都滿足」的解法而不是二選一。 |
| D5 | 相位閘只驗直線軸 | 見爭點 4。備選是兩軸都驗但橫軸放寬容差——放寬到能容忍透視漂移之後也擋不住什麼，反而讓「有閘」變成假象。 |
| D6 | 停滯要**連兩次**才釘邊界旗 | 起手點被單位精靈吃掉的手勢與撞邊在畫面上一模一樣（`pick_pan_origin` 逐次平移重挑，第二次多半就不會再被吃）。邊界旗跨代保留，寫錯的代價是永久的，多花一 tick 換確定性。 |
| D7 | 邊界線＝「該側最外一格**看得清楚**的格」，不是地圖美術的邊 | 被螢幕邊切一半的格永遠補不完；畫進界內會讓待掃格永遠清不完。代價：最外圈半格不在界內（實機上那是鏡頭夾住時看不全的一圈）。 |
| D8 | `unreachable` 退休集 | 見爭點 2。 |
| D9 | 島嶼重錨失敗＝丟棄＋世界重開（不是無限重試，也不是實作 steering） | 見爭點 5。成本有界（一次全掃），且永遠不寫錯值。 |
| D10 | `relocalise` 除了唯一眾數還要**回驗支持數 ≥3** | 滿場二十幾台時「兩票且唯一」太便宜；重錨一錯就是整批島嶼寫進錯的世界座標——那正是模型不准存在的路徑。實幀回放下兩次重錨仍然成立。 |
| D11 | 島嶼開局先 `rephase`（把局部原點對齊世界格線相位） | 不對齊的話島與世界之間差半格，相位閘會逐幀拒收，島嶼連累積觀測的機會都沒有（實測：偏半格的島每一幀重開，73 次隔離 0 次重錨）。對齊之後偏移必然是整數格，併入不撕裂格網。 |
| D12 | 停滯時位移取**準確的 0** | `cv2.phaseCorrelate` 對零位移有 +0.5px 的系統偏差（實測 identical frames 回 `dy=0.5`），停滯一多就累成整格漂移（實測 80 tick 漂掉一整列）。判準用幀差（兩幀幾乎同一張）而不是位移量，避免把真的小位移吃掉。 |
| D13 | 回合交界＝里程計定位中斷（`adrift`），下一幀進島嶼 | 敵方回合鏡頭會被遊戲拉去演出，跨回合的位移量不出來。備選是「假設鏡頭沒動照樣接」——那是最典型的量錯寫入。 |
| D14 | 衰效在感知接縫「整個敵方相位只做一次」 | v1 靠 `and ledger.synced` 隱式冪等，掃到一半遇上敵方回合就整段不衰效。改成顯式旗標。 |
| D15 | 增益（手指行程→內容位移）逐次平移以 EMA 修正，起手 2.3 | 單次平移距離規則管的是**內容位移**，而手勢與位移的比例是裝置／縮放相關的未知數（0730 實測 250px 手勢 → 570-600px）。被邊界夾住的那一把不入帳（那不是增益變小）。範圍夾在 [0.5, 8]。 |
| D16 | 微步驟名：`zoom`／`sweep:<方向>`／`blind:<方向>`／`done`／`fuse`／`stuck` | 三種「這一 tick 沒推」的成因完全不同（掃完／保險絲／推不動），流水帳要分得出來。`blind` 前綴標「這一把平移沒有可信座標」。 |
| D17 | 格距帶取 `((60,105), (90,160))` | 見第五節。(45,160) 單一寬帶實測會讓既有 fixture 整個讀不到（間距均勻性閘被雜訊峰破壞）；三帶以上沒有證據支持。60 的下限涵蓋到 pitch 64 的更深縮放。 |
| D18 | `read_lattice` 加 `bands` 參數而不是新開一支讀取器 | 呼叫端有三個（感知的 `grid_on`、`zoom_out_max` 的收斂判定、掃描的相位閘），三個都要吃得到縮放後的格網；分兩支必然有人忘記換。 |

---

## 七、已知限制與待實機驗證

- **整批沒上過實機**（本批不碰裝置）。實機驗收歸掃描複驗輪：UC HARD 1 收斂到
  `board_synced`、`cells` 非空、格座標與 2b-2 人工普查（±1 格）對照。
- **平移次數與 tick 預算**：v2 的單次平移比 v1 短（縱向尤其：窗高 620 →
  單次上限 155px），所以平移次數會變多。合成世界（22×12 格、視野約 16×8 格）
  收斂在 16 tick；實機地圖若更大、縮放若失敗，`--survey-ticks 40` 可能不夠。
  這一輪沒有動 `SURVEY_TICKS`——實機量到之後再調比現在猜好。
- **橫軸沒有相位吸附**：`measure_shift` 每把平移有 ~0.5px 的系統偏差，縱向
  平移多的地圖會累積（合成世界 16 tick 累到 4.5px，約 1/25 格）。真正的風險
  在超長掃描；複驗輪要看 journal 的 `unlocalised` 與最終格座標對照。
- **`relocalise` 在敵回合之後的重錨**依賴「我方單位沒動」——實機上我方單位在
  敵方回合確實不動，但被擊墜的會消失。支持數門檻 3 是憑合成世界與實幀回放定的，
  實機要複核。
- **多格精靈（戰艦）與 HUD 家具的假峰**會被記成 UNIT 格（既有限制，未變）。
  陣營與真偽歸 2e 的證據分層。
- **`unreachable` 跨代保留**：它是鏡頭幾何的結論，不隨誰站哪裡改變；但如果
  縮放中途變了（例如反射誤觸），這個結論會失真。`Survey.reset()` 會清掉整張圖
  （縮放微步驟就是這樣做的），其他路徑不會。
