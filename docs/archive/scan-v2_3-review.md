# Review 導覽：掃描 v2.3 小批（2026-08-01）

基底 `feat/inner-goap` @ `ac82338`（v2.2 入庫之後）。來源＝掃描複驗輪第 2 輪
（`data/runs/20260801-042733` 與 `20260801-044436-phaseB`）的主 session 鑑識
結論：兩件實機定讞的正確性缺陷（A6 單位漏記、增益學習死鎖）＋一件根因未定的
定位中斷只補存證＋一件效率修。

範圍四個檔：`src/ggge_ai/runtime/coverage.py`（**只動 `absorb` 與 `_learn_gain`
兩個方法**）、`src/ggge_ai/stage/survey.py`、`scripts/dry_run_entry.py`、
`tests/`（三支）。**量測鏈（`Odometer.feed`／`_snap`／`envelope`／相位）一個字沒
動**——水平向定位中斷的根因未定讞前不碰；`runtime/board.py` 也沒動。符號層語意零
改動：`SurveyBoard` 的微步驟名、行動詞彙、`Survey`／`Odometer` 的介面一律照舊。
`battle/` 凍結層沒碰。

**設計決定清單在第六節**，審過再由主 session 併進 `docs/decisions.md`。

## Commit 全景

| commit | 工作 | 內容 |
|---|---|---|
| `633f6be` | (1) | `KnowledgeMap.absorb` 同代 UNIT 滯後＋迴歸 4 條 |
| `adeffe7` | (2) | `Survey._learn_gain` 入帳條件改判＋迴歸 3 條 |
| `536a951` | (3) | BROKEN 原生存證水槽＋`--dump-survey-frames`＋迴歸 8 條 |
| `b192c0c` | (4) | `DryRun.sweep()`：synced 就收工＋迴歸 2 條 |
| （本檔） | — | review 導覽＋設計決定清單 |

閘門（本 worktree 親跑，輸出見第七節）：`uv run pytest -q` →
**1543 passed, 4 skipped, 3 xfailed**；`uv run ruff check src tests scripts` →
**All checks passed!**。基底 `ac82338` 在同一個 worktree 是 1525 passed，本批
+18 條全部來自新的迴歸線。

---

## 一、(1) A6 單位漏記：缺陷鏈與 root fix

主 session 的鑑識：離線在 `frames/00012-tick0037.png` 親跑 `board.find_sightings`
得 **23 個目擊（12 紅 10 藍 1 青）**，但整輪掃描最終只記 **10 台（7 藍 3 紅）**。
目擊機制本身沒壞，壞在簿記：

```
KnowledgeMap.absorb(view)                  coverage.py:209
  ├─ seen = covered(grid, view)            這一幀整格看得清楚的格
  ├─ for cell in seen:
  │     state[cell] = EMPTY                ← 舊碼：無條件
  │     marks.pop(cell)                    ← 舊碼：無條件
  └─ for sighting in view.units:           本幀的目擊再蓋回 UNIT
        state[cell] = UNIT
```

任何一幀漏檢那一格（弧被精靈／特效遮住、密度峰沒過門檻），先前記下的 UNIT 就被自
己抹掉。定位中斷期間的座標誤差再放大一輪：島嶼（定位中斷後位置不明的觀測暫存區，
等重新定位才併回）合併進來的 view 帶著半格偏移，鋪出去的 EMPTY 毯蓋掉的是**隔
壁**那些正確的 UNIT 格。

**Root fix ＝ 同代滯後**（`coverage.py:209-241`）：`seen` 裡已經是 UNIT 的格跳過
EMPTY 重置與 `marks.pop`，本幀若有目擊則照常更新 mark。

機制理由（寫進 docstring）：**掃描發生在我方回合，敵單位這段時間不會移動**，
所以「這一格看得清楚卻沒目擊」是偵測漏，不是離開的證據。單位離開的合法證據
只有跨代——`expire()` 把 UNIT 降成 STALE 之後，同款的 view 照常把它蓋成 EMPTY。
**STALE 的語意一個字沒改**，`UNIT→STALE` 仍然只發生在 `expire()`。

外顯代價（誠實聲明，見爭點 1）：同一代裡誤判出來的 UNIT 格也一起被保住，直到
下一次 `expire()`。

## 二、(2) 增益學習死鎖：缺陷鏈與 root fix

第 2 輪遙測（`survey_tick` 逐次平移）：

| 方向 | measured | expected | 比值 |
|---|---|---|---|
| 南 ×9 | 51.5px | 155px | 0.33 |
| 東西 | ~110px | ~350px | ~0.31 |

最小縮放下的真實增益約 **0.76**，`GAIN_DEFAULT` 是 **2.3**——三倍高估。而
`_learn_gain` 的撞邊保護是：

```python
if measured < 0.5 * wanted:      # 舊碼
    return
```

`measured/wanted` 恆是 1/3 < 1/2 → **這條保護恆真 → 增益永遠學不到 → 每一把
平移都照著錯的增益超推**。自我封閉的死鎖：越高估越學不到，越學不到越高估。

**Root fix**（`coverage.py:677-696`）：入帳條件改為「`verdict == ACCEPTED` 且
`measured >= board.EDGE_SHIFT_PX`」——真的動了就學。撞邊污染改由三件既有機制
自癒：

1. 真撞邊時 `shift.magnitude < EDGE_SHIFT_PX` 已經被 `Odometer.feed` 判 STALLED，
   而 STALLED 進不了增益帳（新條件第一關）。
2. `GAIN_BLEND = 0.5` 的指數混合：半推半就的那一把只帶走一半權重，下一把就修
   回來。
3. `GAIN_RANGE = (0.5, 8.0)` 夾住極端值。

**定位中斷的平移不會污染**：`Survey.observe` 在 `verdict == BROKEN` 時就 `_isolate` 並
提早返回，`_learn_gain` 根本沒被呼叫（迴歸 `test_a_broken_leg_never_reaches_the
_gain_ledger` 把這條路徑釘住）。

合成情境的收斂實測（真實增益 0.76、起手 2.3，逐次平移的 measured/commanded）：

```
0.33 → 0.50 → 0.67 → 0.80 → 0.89 → 0.95 → 0.97 → 0.99 → 1.00
```

六把平移內 travel ≈ commanded。**這同時是效率修**：每一把都走到指令要的距離，
同一輪掃描的平移次數會明顯下降（第 2 輪南向 9 把平移只走了 3 把的距離）。

## 三、(3) BROKEN 原生存證：呼叫鏈

第 2 輪兩輪共 **37 次 BROKEN(phase)**，幾乎全在 east/west（南北 0-1 次）、靜止閘
`settle.waits` **100% ＝ 1**（v2.2 的滑行假說出局）。剩下的兩個候選假說——**量測
系統性欠讀**（靜態 HUD 混進量測窗把相位峰拉向零）與**相位參考漂移**——遙測的
數字分不出來。**本批不猜不修，只補存證**讓下一輪的資料能離線定讞。

```
BoardDriver.survey_board()                      stage/survey.py
 ├─ _settled_capture()                          （v2.2，未改）
 ├─ _read("precheck", None, settled)            ★新：把 observe 與兩個觀察者收攏
 │    ├─ Survey.observe(frame)                  coverage.py（量測鏈未改）
 │    ├─ _trace(...)      → telemetry(record)   （v2.2，未改）
 │    ├─ _preserve(...)   → evidence(record, previous, frame)   ★新
 │    └─ self.previous = settled.frame          ★新：執行器自己留的上一幀
 ├─ Survey.plan_leg() / _pan(leg, …)
 └─ _read("leg", leg, _settled_capture())

DryRun.build()                                  scripts/dry_run_entry.py
 └─ survey_drivers(…, evidence=SurveyFrames(journal, dump=…), dump_frames=…)
      └─ SurveyFrames.__call__(record, prev, curr)
           ├─ verdict == BROKEN → _pair()  → frames/broken/…-{prev,curr}.png
           │                              → journal "survey_broken"
           └─ dump                → _dump() → frames/survey/t<tick>-<probe>.png
```

**上一幀為什麼由執行器自己留**：`Odometer.feed` 判 BROKEN 時刻意**不推進**
`self.previous`（定位中斷的處置是呼叫端的事，量測層只負責誠實），所以量測
層的 previous 未必是時間上的前一張。存證要的是時間序上相鄰的那一對，所以
`BoardDriver.previous` 是自己的欄位——`coverage.py` 的 previous 語意一個字沒改。

落點：`survey.py:167-175`（docstring）、`:187-189`（三個新欄位）、`:215/:228`
（兩處改走 `_read`）、`:260-268`（`_read`）、`:284-302`（`_preserve`）、
`:356-379`（`survey_drivers` 兩個新參數）；`dry_run_entry.py:72-79`（常數）、
`:119-186`（`SurveyFrames`＋`_slug`）、`:355-360`（旗標）、`:425-431`（接線）。

### 存證的檔案佈局

```
data/runs/<時間戳>/
  dry_run.jsonl                       ← survey_broken 逐筆（含 saved 與兩個路徑）
  frames/broken/t37-leg-phase-prev.png
  frames/broken/t37-leg-phase-curr.png
  frames/survey/t37-leg.png           ← 只有 --dump-survey-frames 才有
```

`survey_broken` 欄位：`tick`／`probe`／`direction`／`reason`／`saved`／`prev`／
`curr`（超過上限時 `saved=false`、兩個路徑為 `null`，事件本身仍逐筆入帳）。

## 四、(4) synced 提前結束

第 2 輪實測 **29 把平移就 synced**，剩下的 50 tick 每 tick 兩張截圖全是白燒
（約 100 張圖、~40 秒截圖 I/O ＋ 25 秒 settle sleep）。完成判準是建構性的，
達成之後再跑一 tick 不會讓它更完成。

survey 迴圈抽成 `DryRun.sweep()`（`dry_run_entry.py:251-263`）：`ledger.synced`
為真就記一筆 `survey_done`（`tick` ＋ `budget`）並回傳花掉幾個 tick。抽成方法
的理由是**可測**——整段 `run()` 要走完四道進場閘門才到得了掃描，測不到那個迴圈。

---

## 五、迴歸測試對應表

新增 18 條。「未修碼 FAIL」欄標的是**在本批的修正被 stash 掉之後親跑實測**的
結果，不是推理。

| 工作 | 測試（檔案） | 斷言 | 未修碼 FAIL |
|---|---|---|---|
| (1) | `test_a_seen_unit_survives_a_later_frame_that_simply_missed_it`（coverage） | 先看到 UNIT，後續無目擊的 view 覆蓋同格 → UNIT 與 mark 都留著 | ✅ 實測 |
| (1) | `test_a_fresh_sighting_on_the_same_cell_still_updates_the_mark`（coverage） | 同格本幀有目擊 → mark 換成本幀量到的世界像素與 hint | — |
| (1) | `test_a_stale_cell_is_downgraded_by_an_empty_view_because_the_enemy_did_move`（coverage） | `expire()` 之後同款 view → 降 EMPTY、marks 清空（既有語意不變） | — |
| (1) | `test_a_scan_that_misses_units_on_some_frames_still_ends_with_all_of_them`（coverage） | 合成世界每 3 次 observe 漏檢一次：單位數單調不減、收尾格座標＝世界真值 | ✅ 實測（單位數序列 `[4,3,1,3,4,0,…]` ＝ A6 簽名） |
| (2) | `test_a_three_fold_overestimated_gain_is_learned_down_within_a_few_legs`（coverage） | 真實 0.76 對預設 2.3：兩軸各 6 把平移內 measured/commanded 從 <0.4 收斂到 >0.85，增益 <1.0 | ✅ 實測 |
| (2) | `test_a_leg_that_hit_the_map_edge_never_teaches_the_gain`（coverage） | STALLED 不入帳；同一把平移判 ACCEPTED 就入帳，值＝`GAIN_BLEND` 混合 | ✅ 實測 |
| (2) | `test_a_broken_leg_never_reaches_the_gain_ledger`（coverage） | 走 `observe` 真實路徑：BROKEN → 增益逐字不變 | — |
| (3) | `test_a_broken_reading_hands_both_frames_to_the_evidence_sink`（stage） | 定位中斷交出 (record, prev, curr)；record 帶 tick／probe／direction／reason；prev 非空 | — |
| (3) | `test_the_evidence_sink_stays_silent_while_the_chain_holds`（stage） | 三個 tick 都 ACCEPTED → 水槽零發射 | — |
| (3) | `test_dumping_survey_frames_hands_over_every_observe_in_order`（stage） | 傾印時逐 observe 發射、順序 precheck/leg 交替、**prev 恰是上一次的 curr**（執行器自己的鏈） | — |
| (3) | `test_a_failing_evidence_sink_never_stops_the_scan`（stage） | 水槽拋例外 → 微步驟名照舊、手勢照打 | — |
| (3) | `test_a_broken_pair_lands_on_disk_as_two_full_frames`（dry_run） | 檔名 `t7-leg-no_lattice-{prev,curr}.png`、`saved=true`、讀回來的圖尺寸不變 | — |
| (3) | `test_the_very_first_observe_has_no_previous_frame_to_keep`（dry_run） | prev=None → 流水帳的 `prev` 是 null、curr 照存 | — |
| (3) | `test_past_the_pair_ceiling_the_break_is_journalled_but_not_photographed`（dry_run） | 23 次定位中斷 → 23 筆流水帳、只有 20 筆 `saved=true`、磁碟上 40 個檔 | — |
| (3) | `test_an_intact_reading_is_only_photographed_when_dumping_is_on`（dry_run） | 非 BROKEN：預設不留檔也不記帳；`dump=True` 才寫 frames/survey/ | — |
| (3) | `test_the_assembled_run_wires_the_evidence_sink_and_the_dump_flag`（dry_run） | `build()` 真的接上水槽；旗標同時吃到 driver 與水槽兩側 | — |
| (4) | `test_the_survey_loop_stops_the_moment_the_board_is_synced`（dry_run） | 第 3 tick synced → `sweep()` 回 3、留下 `survey_done{tick:3,budget:20}` | — |
| (4) | `test_the_survey_loop_still_spends_the_whole_budget_when_it_never_syncs`（dry_run） | 永不 synced → 燒完預算、沒有 `survey_done` | — |

### 既有測試的修改

**零**。既有 1525 條一條都沒改斷言，也沒改參數。兩支測試替身各多一個選項欄位
（`Rig.blind`／`Rig.blank`），預設值讓既有用法逐字不變。

---

## 六、設計決定清單（自由裁量處逐條備案）

1. **UNIT 滯後只在 `absorb` 這一層做，不新增第四種「疑似離開」狀態。** 備選是
   加一個「連續 N 幀沒看到才降級」的計數器。取前者：四態知識圖的語意是使用者
   定案的，加第五態要另案；而「我方回合敵不動」這條機制讓 N=∞（整代）本來就是
   正確答案，計數器只是把它參數化成一個沒有證據可定的數字。
2. **誤判的 UNIT 也一起被保住，本批不加反制。** 這是滯後的代價（爭點 1）。備選
   是「目擊要連兩幀才升 UNIT」。不取：那會讓只被掃到一次的格永遠升不上去
   ——漏記（A6 的原病）比多記貴，因為多記的那一格下一代就會被 `expire()` 洗掉。
3. **`fresh` 的計算位置不動**（仍在寫入前算）。它回報的是「這一幀新覆蓋了哪些
   格」，與滯後無關；目前沒有呼叫端讀它，改語意等於憑空造規格。
4. **`_learn_gain` 的下限用 `board.EDGE_SHIFT_PX` 而不是新常數。** 指示明寫。
   理由備查：這個數字在整個量測層就是「動了沒」的門檻（`Odometer.feed` 判
   STALLED、`envelope` 判無指令幀都用它），再造一個同義常數會讓兩處各自漂移。
5. **`verdict != ACCEPTED` 擋在 `measured` 判斷之前。** 兩個條件在實務上高度重疊
   （STALLED 的定義就是位移 < `EDGE_SHIFT_PX` 且有指令），但**語意不同**：
   verdict 是量測層的裁決，measured 是這一把平移的原始量。兩條都留，讓「STALLED
   不入帳」這件事在程式碼裡是明寫的，不是從別的常數推出來的。
6. **`GAIN_DEFAULT = 2.3` 不動。** 備選是直接改成 0.76（第 2 輪量到的實值）。
   不取：那是**內容**（那一關那一個縮放層級的實測值），寫死進程式碼違反紅線；
   起手值的職責只是「第一把平移不超出無歧義範圍」，而修好的學習機制六把平移
   內就收斂。
7. **`GAIN_BLEND`／`GAIN_RANGE` 不動。** 收斂速度已經夠（六把平移），調快只會讓
   單一髒量測的權重變大。
8. **存證水槽走 callback 注入，與 telemetry 同一個模式。** 指示明寫。理由備查：
   `stage/survey.py` 不該知道 run 目錄、PNG 編碼或流水帳 kind 名——那是 Runner
   的事，換一個 Runner（正式 `StageLoop`）可以完全不接。
9. **兩個水槽各包各的 `try`，各自建構一次 record。** 備選是共用一份 record 省一
   次建構。取前者：遙測炸了不該連帶讓存證失效（反之亦然），而 record 建構本身也
   在 try 裡（沿用 v2.2 的決定 9）。代價是定位中斷那幾次多建一個 dict。
10. **`dump_frames` 是 driver 的旗標，`dump` 是水槽的旗標，兩者由同一個 CLI 參
    數餵。** 看起來冗餘，但職責不同：driver 決定**何時發射**，水槽決定**寫成哪
    一種檔**。合併成一個的話，水槽就得對 BROKEN 的幀多寫一份 survey/ 副本（或讓
    frames/survey/ 缺掉定位中斷那幾張＝重放序列不完整）。
11. **`BoardDriver.previous` 存的是 ndarray 引用，不是複本。** 幀在 driver 手上是
    唯讀的（`observe` 之後沒人改它），複製一張 2340×1080×3 只為了保險是 7MB／幀
    的浪費。
12. **存證存 `cv2.imencode` 重編的 PNG，不是裝置原始位元組。** 幀在 driver 那一層
    已經是解碼過的陣列，拿不到原始位元組；要拿得到就得讓 `Camera` 保留一個
    id→bytes 的環形緩衝，那是為了「位元組相同」而引入的脆弱耦合。PNG 無失真，
    **像素逐點相同**，離線重放量測要的正是像素。若主 session 認為必須是裝置那
    一份位元組（例如要驗截圖通道本身），改法是讓 `Camera` 存 raw、driver 改吃
    `(bytes, ndarray)` 對——本批不做，因為那會動到感知通道的介面。
13. **`BROKEN_PAIRS = 20`（指示的值原樣採用）。** 上限擋的是 80 tick 全程
    定位中斷時把 run 目錄塞爆（40 張全解析度 PNG ≈ 60-120MB）。超過只記流水帳，
    所以**定位中斷次數的統計不受上限影響**，只有取樣的圖有上限。
14. **超過上限時仍逐筆記 `survey_broken`（`saved=false`）。** 備選是安靜跳過。
    不取：`survey_tick` 那邊本來就有 verdict，但 `survey_broken` 是「該不該去看
    圖」的索引，缺一筆會讓事後對帳以為那次定位中斷沒發生。
15. **`reason` 進檔名前用 `_slug` 洗過**（`no lattice` → `no_lattice`）。檔名不
    准帶空白，否則事後的 shell 一行流就得處處引號。
16. **`frames/broken/` 與 `frames/survey/` 是 `frames/` 的子目錄，不是平輩目錄。**
    `rotate_runs` 打包整個 run 目錄，所以兩種放法都會被收進 tar；取子目錄是為了
    `frames/` 底下就是「所有的圖」這條直覺不被打破。
17. **`_write` 自己包 `try` 並回 `None`。** driver 那一層已經有一層 try，這一層
    是為了「prev 寫失敗但 curr 寫成功」時流水帳仍記得住哪一張存在。
18. **survey 迴圈抽成 `DryRun.sweep()` 而不是原地加 `break`。** 純粹為了可測——
    `run()` 要走完四道進場閘門才到得了掃描，原地 break 測不到。`sweep()` 回傳
    花掉幾個 tick，讓測試不必去解析流水帳就斷言得了。
19. **`survey_done` 這個 kind 名定在 script（`SURVEY_DONE`），不在 stage 層。**
    同 v2.2 決定 14：「這件事在流水帳裡叫什麼」是 Runner 的事。
20. **`SURVEY_TICKS = 80` 不動。** 提前結束之後它回到它本來的職責＝**上限**。第
    2 輪的 29 把平移是修好增益之前的數字，修好之後只會更少，但西側補掃與定位中斷
    殘餘仍需要裕度。

---

## 七、閘門輸出（本 worktree 親跑）

```
$ uv run pytest -q
1543 passed, 4 skipped, 3 xfailed in 211.90s (0:03:31)

$ uv run ruff check src tests scripts
All checks passed!
```

基底 `ac82338` 在同一個 worktree 是 `1525 passed, 4 skipped, 3 xfailed in
209.68s`。+18 條全部是本批的迴歸線，跑時多約 2 秒。

---

## 八、爭點

1. **UNIT 滯後把誤判也一起保住（誠實聲明）。** 密度峰在特效／爆炸／選單陰影
   上假命中一次，那一格就會維持 UNIT 到這一代結束。舊碼會被下一幀洗掉，新碼不
   會。**取捨的理由是不對稱**：漏記一台敵人 → 戰術層拿到錯的盤面去規劃；多記一
   台幽靈（假命中生出、畫面上沒有對應實體的單位）→ 多算一次威脅（保守方向）。
   但**下一輪複驗要對帳的正是這件事**：`survey_summary` 的 `cells` 數量若明顯超
   過人工目視的台數，就是滯後在收假票。
2. **水平向定位中斷的根因本批沒動也沒修。** 37 次 BROKEN 仍會照樣發生，只
   是這次會留下幀。**驗收標準不該包含「定位中斷率下降」**——本批對量測鏈零
   改動，唯一可能的間接影響是增益修好之後每把平移的位移變大（相位相關的訊噪
   比反而變好）。下一輪拿到 `frames/broken/` 之後的離線工作：對每一對幀親跑
   `board.measure_shift`，看量到的值與遙測記的是否一致（一致＝量測本身欠讀，不一
   致＝取幀與量測之間有東西動過），再對 `read_lattice` 的相位逐對比。
3. **A6 修好之後單位數會上升，但「上升到多少才對」沒有地面真相。** 第 2 輪的
   23 個目擊是**單幀**的數字（含重複計數與第三方單位），不是全圖的台數。下一輪
   請人工目視點一次台數作為對照——否則「10 → 20」是修好了還是收了假票，分不出來。
4. **`--dump-survey-frames` 的成本沒在實機量過。** 80 tick × 2 張全解析度 PNG ≈
   160 張 ≈ 250-500MB，加上每張 `cv2.imencode` 的時間（粗估 30-80ms，掃描一輪多
   5-13 秒）。**建議只在要做離線重放的那一輪打開**，常規複驗不用開——定位中斷存證
   預設就會留，那才是 A5/A7 的主要證據。
5. **`DryRun.sweep()` 的提前結束只影響這支 script，不影響正式迴圈。**
   `StageLoop` 走的是 `progressed(state)`，本來就掃完即彈；這裡修的是 script
   自己的固定 tick 迴圈。
6. **實機未驗證。** 本批純程式碼，四件工作全部要進 `docs/live-verification-queue.md`：
   - 同一關同一節點重跑 `dry_run_entry`（不加 `--dump-survey-frames`），比對
     `survey_summary.cells` 的單位數與人工目視台數（爭點 3）。
   - `survey_tick` 的 `shift.magnitude` ÷ `expected`：第一把平移仍應是 ~0.33，
     **第 5-6 把之後要接近 1.0**（增益學到了）；若仍恆在 0.33，就是還有第二個
     死鎖點。
   - 整輪平移次數與 `survey_done.tick`：修好增益之後預期明顯少於第 2 輪的
     29 把。
   - `frames/broken/` 的幀對數量與 `survey_broken` 的筆數（後者才是真實的
     定位中斷次數）。
