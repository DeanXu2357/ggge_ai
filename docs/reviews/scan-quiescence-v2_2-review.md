# Review 導覽：掃描靜止閘＋遙測小批（v2.2，2026-08-01）

基底 `feat/inner-goap` @ `3238d2c`（v2.1 修正批入庫之後）。來源＝0801 首輪實機
複驗 `data/runs/20260801-033746/` 的 FAIL：40 tick 打滿 `synced=false`、西邊界未
定、**14 次 BROKEN(phase) 定位中斷（36% 的平移次數）**、6 座島因再次定位中斷被丟
棄＝14 個觀測流失。

範圍三個檔：`src/ggge_ai/stage/survey.py`、`scripts/dry_run_entry.py`、
`tests/`（三支）。**`src/ggge_ai/runtime/coverage.py` 一個字都沒動**（量測層剛過
v2.1 審，本批刻意不引入第二個變因）；`runtime/board.py` 也沒動。符號層語意零改動：
`SurveyBoard` 的回傳步驟名、行動詞彙、`Survey`／`Odometer` 的行為一律照舊。

**設計決定清單在第五節**，審過再由主 session 併進 `docs/decisions.md`。

## Commit 全景

| commit | 工作 | 內容 |
|---|---|---|
| `74717a9` | (1) | 取幀靜止閘 `BoardDriver._settled_capture()`＋三條迴歸＋既有測試的截圖序號換算 |
| `dbfa995` | (2) | 逐 observe 遙測 `survey_tick`＋五條迴歸 |
| `f66d34c` | (3) | `SURVEY_TICKS` 40→80 |
| （本檔） | — | review 導覽＋設計決定清單 |

閘門（本 worktree 親跑，輸出見第六節）：`uv run pytest -q` →
**1525 passed, 4 skipped, 3 xfailed**；`uv run ruff check src tests scripts` →
**All checks passed**。基底 `3238d2c` 的數字是 1517 passed，本批 +8 條全部來自新
的迴歸線。

---

## 一、缺陷鏈與 root fix

主 session 診斷定讞的機制鏈，逐環對應到修正落點：

```
_pan(leg)                                   swipe(reach≈150-260px, PAN_DURATION_S=0.7)
  └─ sleep(PAN_SETTLE_S=1.5)                ← 重手勢的慣性滑行拖得比這個久
capture()                                   ← 舊碼：滑行中的幀，直接進 observe
  └─ Survey.observe(frame, leg)             量到的位移偏小，但 envelope 0~1.5x 放行
（下一 tick）
capture()                                   ← 舊碼：殘餘滑行 22.5-40px
  └─ Survey.observe(frame)   expected=None
       └─ envelope(shift, None)             magnitude < EDGE_SHIFT_PX(40) → OK
       └─ Odometer._snap()                  |residual| > PHASE_TOLERANCE×pitch(22.5) → None
            └─ Reading(BROKEN, "phase")     ← 14 次就是這裡
```

窗口寬度只有 `22.5 < |殘餘| < 40` 這 17.5px：小於 22.5 相位閘吸得回來，大於 40
合理範圍閘會直接拒收（一樣是定位中斷，但那是另一種故障）。定位中斷本身的恢復機制
照設計運作（`islands.merged=8`、重錨偏移全是 180/270/360px 的整欄），問題純粹是
頻率——40 tick 的預算被燒光。

**Root fix 落在取幀，不在量測**：滑行中的幀本來就不該被 observe 收下。

行號對應本批 HEAD（`f66d34c`）的 `src/ggge_ai/stage/survey.py`。

| 落點 | 改動 |
|---|---|
| `survey.py:57-66` | 新常數 `SETTLE_POLL_S=0.25`／`SETTLE_QUIET_PX=3.0`／`SETTLE_ROUNDS=4`，以及遙測用的 `PRECHECK_PROBE`／`LEG_PROBE` |
| `survey.py:150-156` | 新 `SettledFrame`（frame＋waits＋quiet 的回傳載體） |
| `survey.py:234-250` | 新 `BoardDriver._settled_capture()` |
| `survey.py:206, 218` | `survey_board` 兩處取幀改走 `_settled_capture()` |
| `survey.py:8-12` | 模組 docstring：感知複核那一句補上「等畫面靜止再收」 |

`show_grid`／`collapse_roster` 的取幀**不動**——它們讀的是固定 UI 位置，沒有
里程計，滑行對它們沒有語意。

靜止判準用**相位相關的位移量**而不是 `frame_difference`：單位待機動畫逐幀都在動，
幀差永遠安靜不下來（會把 `SETTLE_ROUNDS` 每次燒滿＝每 tick 多 4 張截圖還是收到
髒幀）；滑行是全域同調位移，相位相關量得到、待機動畫量不到。

`shift.known == False`（相位信賴度低＋單位排列比對湊不出票，例如地圖外無特徵的
星空背景）視為靜止收幀：量不出來不是「還在動」的證據，而下一步 `Survey.observe`
自己會把它判 BROKEN（`unmeasurable`）隔離進島嶼——島嶼＝定位中斷後位置不明的觀測
暫存區，等重新定位才併回；在取幀這一層硬等只是白燒截圖。

---

## 二、呼叫鏈

```
LiveExecutor.perform(SurveyBoard)                 runtime/device.py（未改）
 └─ BoardDriver.survey_board()                    stage/survey.py
     ├─ ticks += 1
     ├─ _settled_capture()                        ★新：capture → sleep → capture
     │    └─ board.measure_shift(f1, f2)             → magnitude < 3.0 或 known=False 才收
     ├─ Survey.observe(frame)                     coverage.py（未改）
     ├─ _trace("precheck", None, reading, settled) ★新：遙測
     ├─ Survey.plan_leg()
     ├─ _pan(leg, pick_pan_origin(前置複核幀的目擊))
     ├─ _settled_capture()                        ★新
     ├─ Survey.observe(frame, leg)                coverage.py（未改）
     └─ _trace("leg", leg, reading, settled)      ★新

DryRun.build()                                    scripts/dry_run_entry.py
 └─ survey_drivers(..., telemetry=lambda r: journal.record("survey_tick", **r))
```

遙測那一路的落點：`survey.py:167-169`（docstring）、`:178-179`（`telemetry`／`ticks`
兩個新欄位）、`:208, 220`（兩個發射點）、`:252-264`（`_trace`）、`:266-302`
（`_record`）、`:318-337`（`survey_drivers` 多一個 `telemetry` 參數）；
`scripts/dry_run_entry.py:64-66`（`SURVEY_TICK` 常數）、`:321-327`（接線）。

`_trace` → `_record` 分成兩層是為了「遙測失敗不得影響掃描主流程」：`try` 包住
建構＋寫入的整段，例外只記一次 warning，`survey_board` 照常回傳微步驟名。

### 行為面的外顯差異（主 session 併回時值得盯）

1. **每 tick 的截圖次數由 2 張變成 4 張起跳**（每次取幀 f1＋f2）。滑行未停時
   每多等一輪多 1 張，單次取幀上限 5 張。實機成本粗估：80 tick × 4 張 × ~0.4s
   ≈ 128s 截圖，加上靜止閘的 sleep 80×2×0.25s = 40s。
2. **每 tick 多兩筆 journal 紀錄**（`survey_tick`）。80 tick ≈ 160 筆，
   `dry_run.jsonl` 從約 120 行長到約 450 行。
3. **`BoardDriver` 多兩個欄位**（`telemetry`、`ticks`）。`ticks` 只算「真的做了
   observe」的呼叫——`zoom` 那一 tick 不計。

---

## 三、遙測欄位表（`kind: "survey_tick"`）

每 tick 兩筆：`probe="precheck"`（前置複核幀，無指令）與 `probe="leg"`（pan 後幀）。
`plan_leg()` 回 None 的那些 tick（done／fuse／stuck）只有 precheck 那一筆。

| 欄位 | 型別 | 意義 |
|---|---|---|
| `tick` | int | 這一輪掃描的第幾個有效 tick（zoom 那 tick 不計） |
| `probe` | `"precheck"` / `"leg"` | 哪一次 observe |
| `direction` | str / null | leg 的方向；precheck 為 null |
| `reach` | float / null | 手指行程（螢幕像素）；precheck 為 null |
| `expected` | [dx, dy] / null | 指令預期的內容位移（世界像素，帶號）；precheck 為 null |
| `verdict` | str | `accepted` / `stalled` / `broken` |
| `reason` | str | BROKEN 時是失敗原因（`phase`／`envelope`／`unmeasurable`／`generation`／`no lattice`），否則是合理範圍閘等級（`ok`／`repeat`）或 `anchor` |
| `shift.dx` `shift.dy` | float | 量到的內容位移（螢幕像素） |
| `shift.magnitude` | float | 同上的長度——**A5 的核心量測** |
| `shift.confidence` | float | 相位相關的響應值／排列比對的票數比 |
| `shift.source` | str | `phase` / `constellation` / `still` / `none` |
| `offset` | [x, y] | 這一幀之後的里程計偏移（世界 ＝ 螢幕 ＋ offset） |
| `island.open` | bool | 島嶼緩衝開著沒 |
| `island.views` | int | 島內已攢幾幀 |
| `islands` | dict | `isolated`／`merged`／`discarded`／`reset` 四計數器快照 |
| `settle.waits` | int | 靜止閘等了幾輪（1 ＝ 第一輪就靜） |
| `settle.quiet` | bool | 最後是真的靜下來，還是重試用盡硬收 |

「40 tick 打滿還沒 synced」這類問題，靠 `shift.magnitude` × `direction` 就能算出
逐次平移的實際行程與增益，`settle.waits` 的分佈則直接回答「滑行到底有多久」。

---

## 四、迴歸測試對應表

新增 8 條（`tests/test_stage_survey.py` 7 條＋`tests/test_dry_run_entry.py` 1 條）。

| 工作 | 測試 | 斷言 |
|---|---|---|
| (1) | `test_the_scan_waits_for_the_glide_to_stop_before_it_takes_the_frame` | 滑行 40px→15px→停：等 3 輪才收幀，共 4 張截圖，naps 全是 `SETTLE_POLL_S` |
| (1) | `test_a_frame_that_never_goes_quiet_is_observed_anyway` | 永不停的滑行：`waits == SETTLE_ROUNDS`、`quiet=False`、**照樣回傳一張幀** |
| (1) | `test_an_unmeasurable_frame_counts_as_quiet_and_is_handed_straight_on` | `known=False` 立刻收幀（`waits == 1`），交給下一步處置 |
| (2) | `test_the_telemetry_files_one_row_per_observe_with_the_measurement` | 3 tick → 6 筆、`probe` 交替、`tick` 成對；欄位集合逐層對死；precheck 的 leg 三欄全 null；leg 的位移量 > `EDGE_SHIFT_PX` |
| (2) | `test_the_telemetry_reports_how_long_the_quiescence_gate_had_to_wait` | 合成世界瞬時靜止 → `waits` 全是 1、`quiet` 全真 |
| (2) | `test_the_telemetry_lands_in_the_journal_as_numbers_not_strings` | 走真的 `Journal` 來回一趟，數值欄位仍是 `float`／`int`（不是被 `default=str` 悄悄字串化） |
| (2) | `test_a_failing_telemetry_sink_never_stops_the_scan` | 水槽拋例外時微步驟照舊、手勢照打 |
| (2) | `test_the_assembled_run_pipes_the_survey_telemetry_into_the_journal` | `build()` 真的把水槽接到 journal 的 `survey_tick` |
| (3) | `test_the_default_survey_budget_is_the_raised_one` | 既有測試，`40` → `80` |

### 既有測試的修改（capture 次數假設）

`tests/test_runtime_coverage.py` 的 `Rig.blank` 數的是**截圖次數**，而靜止閘讓
每一次 observe 花掉兩張圖，所以第 k 次 observe 拿到的是第 2k 張：

| 測試 | 舊 | 新 |
|---|---|---|
| `test_an_unlocalisable_frame_is_isolated_and_never_written_blind` | `blank=(9,10,11)` | `blank=(18,20,22)` |
| `test_an_island_that_never_re_anchors_is_dropped_and_the_world_restarts` | `blank=(3,)` | `blank=(6,)` |

映射是嚴格的 ×2，因為合成世界瞬時靜止（相同兩幀的相位相關回 0.5px < 3.0）＋
空白幀那一對量不出位移（`known=False`）——兩種情形都在第一輪過閘，所以每次取幀
恰好 2 張。被送進 observe 的幀序列與修改前**逐幀相同**，斷言本身一個字沒改。
`Rig` 的 docstring 補上了這條換算，下一個人不必再推一次。

---

## 五、設計決定清單（自由裁量處逐條備案）

1. **靜止判準用 `board.measure_shift` 的 magnitude，不用 `frame_difference`。**
   指示明寫，這裡記下理由備查：待機動畫讓幀差永遠不安靜，滑行則是全域同調位移，
   只有相位相關分得開這兩者。
2. **三個常數放 `stage/survey.py` 而不是 `runtime/board.py` 的常數區。** 備選是
   放 board.py（`EDGE_SHIFT_PX` 等閾值的鄰居）。取前者：它們規範的是「執行器怎麼
   取幀」這條策略，board.py 至今是純像素機制模組，而且本批想讓量測層的 diff 保持
   為零。**若主 session 認為閾值該與 `PHASE_TOLERANCE` 同處一室，搬過去是純移動。**
3. **`SETTLE_QUIET_PX = 3.0`。** 下界由相位相關對零位移的系統偏差決定（實測相同
   兩幀回 `dy=+0.5`），上界要遠小於相位閘容差 22.5px。3.0 給了 6× 的雜訊餘裕又留
   7.5× 的安全距離。滑行速率粗估 ~12px/0.25s，所以它分得出滑行與靜止。
4. **`SETTLE_POLL_S = 0.25`／`SETTLE_ROUNDS = 4`（指示的建議值原樣採用）。**
   最壞情況一次取幀 5 張圖、1.0s 額外等待；典型情況 2 張圖、0.25s。
5. **重試用盡照樣收最後一幀**，不是拋錯也不是回 None。指示明寫；記一次 warning
   讓實機 log 看得到「這一幀是硬收的」，而 `settle.quiet=false` 讓事後也分得出來。
6. **`SettledFrame` 用 frozen dataclass 而不是三元組。** 備選是回 `tuple`。取
   dataclass：`waits`／`quiet` 兩個數字在呼叫端要一路帶到遙測，位置參數會讀不出
   誰是誰。它是回傳值載體，不是新的抽象層。
7. **`quiet` 與 `waits` 分開記，不用 `waits == SETTLE_ROUNDS` 推斷。** 第 4 輪
   剛好靜下來與第 4 輪還沒靜是兩件事，編碼在同一個數字裡會誤導事後分析。
8. **遙測走注入的 callback，不是 driver 內部攢 trace 由 Runner 沖。** 指示兩者
   皆可。取 callback：(a) 沒有「誰負責清空緩衝」的所有權問題，長戰鬥不會攢出一條
   無界清單；(b) 「失敗不得影響主流程」只需要一個 try 包住發射點；(c) `steps`
   那條既有清單維持它原本的語意（符號自述），不被量測資料稀釋。
9. **`_trace`／`_record` 分兩層，`try` 包住整段（含 record 建構）。** 備選是只包
   `telemetry()` 呼叫。取前者：建構本身也可能爆（未來加欄位時），而掃描不該因為
   一個觀察者而停。
10. **`islands` 四計數器每筆都記，不是只在 tick 尾記一次。** 指示允許「只在
    tick 尾記一次」。取每筆：本批要回答的正是「14 次定位中斷落在 precheck 還
    是 leg」，計數器逐筆才對得上是哪一次 observe 觸發的隔離。成本是每 tick 多 8
    個整數。
11. **`tick` 由 `BoardDriver.ticks` 自己數，不從 Runner 傳入。** 備選是 Runner 把
    迴圈索引塞進來。取前者：驅動型行動在正式迴圈（`StageLoop`）裡沒有「掃描第幾
    tick」這種外部索引，計數器留在驅動器上兩條路徑才一致。`zoom` 那一 tick 不計，
    因為它沒有 observe，記進去會讓 tick 與 observe 對不上。
12. **`reason` 一個欄位同時承接 gate 等級與 BROKEN 原因。** 那正是
    `coverage.Reading.reason` 的既有語意（ACCEPTED 時放 `ok`／`repeat`，BROKEN 時
    放失敗原因），本批不另立第二個欄位去複製它。
13. **數值一律先 `round` 再進遙測**（位移 2 位、offset／reach／expected 1 位、
    confidence 3 位）。原始 float 的尾數在 jsonl 裡佔掉大量寬度而沒有資訊。
14. **`survey_tick` 這個 kind 名定在 `scripts/dry_run_entry.py`（`SURVEY_TICK`）
    而不是 survey.py。** 驅動器只吐 dict，「這批資料在流水帳裡叫什麼」是 Runner
    的事——換一個 Runner（例如正式 `StageLoop`）可以用別的 kind。
15. **`show_grid`／`collapse_roster` 不走靜止閘。** 指示明寫；理由是它們讀固定 UI
    位置、不餵里程計，滑行對它們沒有語意，多兩張截圖是純成本。
16. **`SURVEY_TICKS = 80`，`LEG_BUDGET = 200` 不動。** 指示明寫。tick 預算是
    「這支 script 願意跑多久」，平移次數保險絲是「單一回合內失控的上界」，
    兩者不同層。

---

## 六、閘門輸出（本 worktree 親跑）

```
$ uv run pytest -q
1525 passed, 4 skipped, 3 xfailed in 209.83s (0:03:29)

$ uv run ruff check src tests scripts
All checks passed!
```

基底 `3238d2c` 在同一個 worktree 是 1517 passed, 4 skipped, 3 xfailed（跑時
202.23s）。靜止閘讓每次 observe 多一張截圖與一次 `measure_shift`，整套測試多花
約 8 秒——合成世界瞬時靜止，每次取幀都在第一輪過閘。

---

## 七、爭點

1. **靜止閘只降污染率，不保證零污染（誠實聲明）。** 滑行速率衰減到 <3px/0.25s
   之後閘就放行，殘餘位移仍可能累積幾個像素。它遠小於 22.5px 的相位閘容差，但
   「BROKEN(phase) 歸零」不是本批能保證的事——**驗收標準應該是定位中斷率明顯下降
   （14/40 把平移 → 個位數），不是 0**。

2. **`SETTLE_QUIET_PX = 3.0` 與 `SETTLE_ROUNDS = 4` 沒有實機標定。** 3.0 的下界
   有離線證據（相同兩幀回 0.5px），上界靠推理；4 輪（最長 1.0s 額外等待）夠不夠
   蓋住實機滑行的尾巴則完全沒量過。**下一輪實機複驗請優先看 `settle.waits` 的
   分佈**：若大量落在 4 且 `quiet=false`，就是輪數不夠（或該把 `PAN_SETTLE_S`
   一起調），若幾乎全是 1，反而要懷疑閘沒抓到滑行、該把門檻壓低。

3. **截圖成本翻倍未在實機量過。** 每 tick 4 張起跳 × 80 tick，加上滑行時的額
   外輪數。0801 那一輪是 40 tick／168 張圖跑完全程；本批粗估 80 tick 需要 320+
   張。若整段掃描的牆鐘時間變得不可接受，第一個該砍的是「precheck 幀也走靜止
   閘」——但那一幀正是 14 次定位中斷的發生地，砍掉等於退回原點。**替代省法是把
   `PAN_SETTLE_S` 從 1.5 降下來，讓靜止閘接手等待**（閘量得到什麼時候該收，固定
   sleep 量不到），本批沒有動它，因為那會同時改兩個變因。

4. **`coverage.py` 有一處看起來可疑但本批沒動（依紀律停在這裡標爭點）。**
   `Odometer.feed` 判 BROKEN(phase) 之後，`self.previous` **不更新**——下一幀會
   拿更舊的那張當基準。主圖那條路徑上這是對的（定位中斷後幀進島嶼，島嶼自己帶
   新的 `Odometer(previous=frame)`），所以不是缺陷；但滑行情境下同一個 odometer
   若連續兩次 BROKEN，第二次量的是跨兩幀的位移，合理範圍閘的「同軸倍率」會用
   單次平移的 expected 去衡量兩次平移的位移。0801 的流水帳裡連續 BROKEN 出現過
   兩次（`isolated=14` 對 `merged=8`），**要不要在量測層補一條「BROKEN 也推進
   previous」的規則，請主 session 裁示**——本批依指示對 `coverage.py` 零改動。

5. **實機未驗證。** 本批純程式碼。需要排進 `docs/live-verification-queue.md`：
   - 同一關同一節點重跑 `dry_run_entry --survey-ticks 80`，比對
     `unlocalised`／`islands.isolated` 與 0801 的 14／14。
   - `survey_tick` 的 `settle.waits` 分佈（爭點 2）與 `shift.magnitude` 的逐次
     平移值（A5 的原始問題：一把平移到底移了多少、增益學得對不對）。
   - 西邊界能不能在 80 tick 內定下來（0801 是唯一沒定的旗）。
