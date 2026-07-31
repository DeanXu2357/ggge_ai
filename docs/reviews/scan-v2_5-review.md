# Review 導覽：掃描 v2.5 單位帳一致性小批（2026-08-01）

基底 `feat/inner-goap` @ `3760f97`（v2.4 入庫之後）。來源＝複驗輪第 4 輪
（`data/runs/20260801-071055`）的 V5 台數 FAIL：v2.4 的水平斷鏈修正決勝過關
（東西向 broken 18→0），但 journal `cells` 記了 84 筆（藍 52 紅 32），界內
`census()` 55，期望 ≈28（敵 18＋我 10）。

範圍兩個產品檔：`src/ggge_ai/runtime/coverage.py`（主要落點）、
`src/ggge_ai/stage/survey.py`（只加一個遙測欄位與它的格式化函式）。
`Survey._reanchor`／`_solve`／量測鏈（`measure_pan`／`_snap`／`rephase`／
`envelope`）**一行未動**，符號層語意零改動，`battle/` 沒碰。

**設計決定清單在第六節，爭點在第七節。** 本批對指示沒有實質偏離；三處自由裁量
（裁剪的欄位範圍、`_inside` 的 bounded 前提、遙測欄位形狀）逐條備案。

## Commit 全景

| commit | 工作 | 內容 |
|---|---|---|
| `36f7e2b` | (1) | `fix_boundary` 定線後裁掉線外的 `state`／`marks`／`charted`／`unreachable`；迴歸 2 條 |
| `1b26610` | (2) | `units()`／`sightings()` 在 bounded 時只回界內；迴歸 3 條 |
| `0cb877d` | (3) | `Survey.last_merge` ＋ driver `_record` 的 `merge` 欄位；迴歸 3 條 |
| （本檔） | — | review 導覽＋設計決定清單 |

三個 commit 各自獨立綠（每一個都在 worktree 內親跑 `tests/test_runtime_coverage.py`
＋`tests/test_stage_survey.py` 與 `ruff check`：113／116／118 passed）。

閘門（本 worktree 親跑）：

```
$ uv run pytest -q
1567 passed, 4 skipped, 3 xfailed in 223.89s (0:03:43)

$ uv run ruff check src tests scripts
All checks passed!
```

---

## 一、機制定位：84 筆是怎麼長出來的

第 4 輪的 84 筆單位格裡，**29 筆的欄座標（col 15-20）整段落在最終東界
`east=13` 之外，而南北界外一筆都沒有**。方向性是這批的關鍵證據：

- 那一輪西界兩度定案（−10 → −9），島嶼兩次重錨成功（merge delta
  `(455.0, 186.9)`、`(0.0, 164.3)`）——全是**沿欄軸**把世界座標挪過的事件。
- `KnowledgeMap` 的 `absorb()`／`expire()`／`fix_boundary()` 都只動 `state`
  （與 `charted`／`marks`），**沒有任何一條路徑會在邊界定案或重錨修正之後裁剪
  舊格**。定案前寫下的格被挪到線外，之後不會再有任何一幀覆蓋它（`covered()`
  給不出線外的格），於是永久留在圖裡。
- `units()` 讀的是 `marks` ＋ `state`，兩者都不看邊界，所以鬼影原樣進 journal；
  `census()` 走 `_scope()`（bounded 時就是界內方框），所以它看不到那 29 筆。
  **同一本簿記的兩個讀法口徑不同，這就是 84 vs 55 的差。**

界內仍膨脹（55 vs 28）是**另一個**缺陷，本批不修：重錨 delta 若寫錯，整批島
view 以錯格吸收，UNIT 滯後（v2.3）把鬼影保住。堵不住的補儀器＝工作 (3)。

---

## 二、(1) 落點與呼叫鏈：邊界定案就裁剪

```
Survey._boundary(leg, reading, view)              coverage.py（未改）
 └─ KnowledgeMap.fix_boundary(direction, view)    coverage.py:253  ← 改
      ├─ edge_cell(grid, view, direction)         （既有，未改）
      ├─ self.boundary[direction] = line
      └─ self._trim()                             ★新
            └─ 以 in_bounds() 過濾 state／marks／charted／unreachable
```

`_trim()` 用的就是既有的 `in_bounds()`（它逐方向只認已定的旗，未定的方向不設限），
所以第一次定東界時只裁東邊，其餘三面不受影響。改判走同一條路：`fix_boundary`
不區分「第一次定」與「重定」，寫完旗子一律裁一次。

**唯一的呼叫端是 `Survey._boundary`**（連兩次 STALLED 才進來），所以裁剪的觸發
頻率跟邊界旗一樣低——不是逐幀的成本。

## 三、(2) 落點與呼叫鏈：讀值側界內一致

```
KnowledgeMap.units()      ← 改：加 self._inside(cell)
 ├─ CoverageLedger.cells()          → dry_run_entry.summarize_survey 的 journal cells
 ├─ Survey.units() → summary()["units"]
 └─（測試）unit_cells()

KnowledgeMap.sightings()  ← 改：加 self._inside(cell)
 ├─ Survey._solve()  → board.relocalise(chart.sightings(), island.sightings)
 └─ Survey._agrees() → 撞邊釘軸的支持數複驗

KnowledgeMap._inside(cell)   ★新 ＝ not self.bounded or self.in_bounds(cell)
```

**`sightings()` 是重定位器的輸入，這是本批影響面最大的一處。** 三個下游後果：

1. `_solve()` 的 `relocalise(known=…)` 少掉界外 mark。界外 mark 的世界像素本身
   就是錯的（線外沒有地圖），拿它當星座錨只會把解出來的偏移帶歪，整批島嶼再以
   錯格吸收——那正是「無量錯寫入」不變式不准存在的路徑。
2. `_agrees()`（撞邊釘軸的複驗）同樣少掉界外 mark，所以複驗變嚴：支持數的分母
   只剩可信的錨。**這個方向是安全的**——複驗過不了就退回星座重定位，不會多寫。
3. 只在四旗全定之後才濾。旗子沒定滿時界內是無限大，濾了等於憑半套邊界丟掉真的
   觀測（`test_an_unbounded_chart_still_reports_every_mark_it_has` 釘住這一條，
   它是「不要過濾過頭」的守成測試，改壞了才會 FAIL）。

**寫值側刻意不動**：`absorb()` 照樣收得下界外的格。理由見設計決定 3。

## 四、(3) 落點與呼叫鏈：重錨偏移遙測

```
Survey.observe(frame, leg)            coverage.py  ← 開頭 self.last_merge = None
 └─ Survey._reanchor(leg, reading, view)
      └─ 合併成功：self.last_merge = (delta, len(island.views))   ★新

BoardDriver._read → _trace／_preserve → BoardDriver._record   stage/survey.py
 └─ "merge": _merge_row(survey.last_merge)     ★新欄位（無合併時 null）
      └─ {"delta": [x, y], "views": n}
```

`_record` 一個 tick 呼叫兩次（precheck 幀與 leg 幀各一），各自讀自己那次 observe
的結果——每次 observe 開頭清 None，所以同一次合併只會出現在一列裡。
`survey_summary` 那一筆不動（`islands` 的累計次數照舊）。

---

## 五、迴歸測試對應表

新增 7 條、擴充既有 1 條（基底 1560 passed → 本批 1567 passed）。「未修碼 FAIL」
欄是**把該處修正還原後親跑實測**的結果，不是推理。

| 工作 | 測試（檔案） | 斷言 | 未修碼 FAIL |
|---|---|---|---|
| (1) | `test_fixing_a_boundary_deletes_every_record_that_fell_outside_it`（coverage） | col 15-18 記了 UNIT＋`unreachable` 之後定 `east=13` → 界外 state／marks／charted／unreachable 全清、界內原封不動 | ✅ 實測 |
| (1) | `test_a_reversed_boundary_trims_the_strip_it_just_gave_up`（coverage） | west 改判 −10→−9 → 舊界那一欄的紀錄一起清掉 | ✅ 實測 |
| (2) | `test_the_unit_roll_and_the_census_count_the_same_cells`（coverage） | 界外 mark 寫得進 `absorb` 但不進 `units()`；`census()["unit"] == len(units())`；`sightings()` 同款 | ✅ 實測 |
| (2) | `test_a_mark_outside_the_walls_never_supports_a_re_anchor`（coverage） | 同一批 mark：未 bounded 時 `_solve()` 解得出 truth，四旗全定後 `sightings() == ()` 且 `_solve()` 回 None | ✅ 實測 |
| (2) | `test_an_unbounded_chart_still_reports_every_mark_it_has`（coverage） | 只定一面旗時一個 mark 都不濾 | —（守成：防過濾過頭） |
| (3) | `test_a_merged_island_records_the_offset_it_was_merged_at`（coverage） | 合併後 `last_merge == (delta, 1)`，delta 就是重錨解 | ✅ 實測 |
| (3) | `test_a_re_anchored_island_hands_its_offset_to_the_telemetry`（coverage） | 鏡頭跳走→島嶼→重錨的整輪掃描：**恰好一列**遙測帶 merge，掃完 `last_merge` 已清回 None | ✅ 實測 |
| (3) | `test_the_telemetry_files_one_row_per_observe_with_the_measurement`（stage，既有測試擴充） | 遙測 schema 多 `merge` 鍵；沒合併時是 null | —（schema 斷言） |

### 既有測試的修改

**一條**：`test_the_telemetry_files_one_row_per_observe_with_the_measurement`
的 `set(row) == {…}` 是逐鍵封閉斷言，加欄位就得同步加鍵（順帶加一句
「沒合併就是 null」）。其餘既有斷言、參數一個字沒改；沒有新增 fixture。

### 為什麼 (3) 的端對端測試落在 `test_runtime_coverage.py`

那一條測的是「遙測列真的帶得到 merge」，形式上屬於 stage 層。放 coverage 檔的
理由是替身：能造出「鏡頭跳走→島嶼→重錨」的 `Rig` 只有 coverage 檔那一份有
`jumps`（stage 檔的同名 `Rig` 只有 `blank`，而且世界只有兩台單位，湊不到
`RELOCATE_MIN_SUPPORT = 3`）。複製一份替身比借用一份貴，也多一個會走樣的地方。
stage 檔留 schema 斷言。

---

## 六、設計決定清單（自由裁量處逐條備案）

1. **裁剪的範圍含 `charted`，不只 `state`／`marks`。** 指示點名了
   state／marks／charted／unreachable，這裡記錄理由：`charted` 是 `frontier()`
   的種子，線外的 charted 會讓前緣去長線外的鄰居格（`in_bounds` 會擋下候選，但
   種子本身留著就是白繞一圈），而且它是「看過的格」這個幾何事實的載體——線外沒有
   地圖，說「看過線外那一格」本身就是假的。
2. **`unreachable` 的界外項一起清（指示明寫）。** 它是跨代保留的退休名單，留著
   線外的項目只會讓後續的 `gaps()`／`frontier()` 多做一次無用的集合查詢；更重要
   的是同一個理由——線外不存在的格沒有「退休」可言。
3. **寫值側（`absorb`）不加界內過濾。** 備選是讓 `absorb` 直接丟棄界外的觀測。
   不取：邊界旗**可能是錯的**（v2.4 設計決定 4 已經記過「邊界旗釘在地圖中央」
   這個失效模式，代價跨代永久），寫值側過濾等於讓一面錯旗把真觀測靜默吃掉＝
   「無聲丟失」那條路徑。裁剪只發生在**旗子剛被觀測改寫**的那一刻（有新證據），
   讀值側只是換口徑（不刪資料）。兩者都不會憑舊旗吃掉新觀測。
4. **`_inside()` 以 `bounded`（四旗全定）為前提，而不是逐方向用 `in_bounds()`。**
   指示原文就是「bounded 時只回界內」，這裡記錄為什麼那是對的：只定了一兩面旗時
   界內仍是無限大，逐方向濾會在掃描中段（第一面旗剛定、其他三面還沒）把剛觀測到
   的真單位濾掉，而那正是前緣還要拿去導航的資訊。代價是**部分定界期間 `units()`
   仍可能含界外鬼影**——但那時候還沒有「界外」可言，口徑一致。
5. **`sightings()` 與 `units()` 同一個過濾條件。** 備選是只濾 `units()`（顧 journal
   對帳）而讓重定位器照吃全部 mark。不取：界外 mark 的座標**本來就是錯的**，
   它進星座錨只會把 delta 帶歪；而且第 4 輪的界內膨脹嫌疑就在重錨 delta 上，
   讓錯座標繼續投票等於留著同一條污染鏈。
6. **`last_merge` 掛在 `Survey` 上而不是回傳值。** 備選是讓 `observe()` 回傳的
   `Reading` 多帶一個欄位。不取：`Reading` 是量測層的裁決（verdict／shift／offset），
   島嶼合併是世界模型層的事件，塞進去會讓 `Odometer.feed` 的回傳型別背上它答不了
   的東西。掛在 `Survey` 上、每次 observe 開頭清空，語意是「這一幀發生了什麼」。
7. **`merge` 的形狀是 `{"delta": [x, y], "views": n}`，無合併時 `null`。** 備選是
   永遠給一個 `{"merged": false}` 的物件。取 null：遙測的既有慣例就是「沒有就
   null」（`direction`／`reach`／`expected` 在 precheck 列都是 null），而且
   `[row for row in rows if row["merge"]]` 這種離線篩法最省事。
8. **`delta` 取一位小數（`round(value, 1)`）。** 與同一列的 `offset` 同精度。
   重錨偏移的量級是幾百 px，小數第二位沒有鑑識價值。
9. **`islands` 的累計計數不動。** `merged` 次數與逐次 delta 是兩種問題的答案
   （「斷了幾次」vs「那一次錯多少」），沒有合併成一個欄位。
10. **`_trim()` 用整批重建（dict/set comprehension）而不是逐項 `del`。** 邊界事件
    一場戰鬥只有個位數次，圖的規模是幾百格，重建的成本可忽略；逐項刪要先蒐集
    再刪（不能邊迭代邊改），程式碼反而長。

---

## 七、爭點

1. **界內膨脹（55 vs 28）本批沒修，只加儀器。** 這是指示明定的分工（「先堵得住的
   堵，堵不住的補儀器，第 5 輪量」），但要講清楚**本批修完之後第 5 輪的 cells
   仍然可能明顯多於 28**：(1)(2) 只保證「journal cells ≡ 界內 census」，不保證
   那個數字對。若第 5 輪 cells 與界內 census 對上了而數字仍是 50 上下，責任就
   完全落在重錨 delta ＋ UNIT 滯後那一組，`merge` 欄位就是下一輪的第一手證據。
2. **UNIT 滯後（v2.3）在本批之後仍然保得住界內鬼影。** `absorb()` 的
   「同一代裡已是 UNIT 的格不因為這一幀沒目擊就降級」是刻意的（0801 複驗：無條件
   鋪 EMPTY 會讓 23 個目擊只剩 10 台），而它同時也意味著**一次寫錯格的吸收會被
   保到跨代**。本批沒動它——動它要新的實機證據，而且方向相反的兩個失效（漏檢 vs
   鬼影）目前只有一組資料。
3. **裁剪只在 `fix_boundary` 觸發，重錨本身不裁。** 島嶼重錨把整批 view 以 delta
   平移吸收（`_reanchor` 的 `buffered.shifted(delta)`），但**權威圖裡既有的格
   不會跟著平移**——它們原本就寫在世界座標上。所以重錨之後不需要裁；真正落到線外
   是「重錨改變了後續觀測落點，於是邊界旗被定在別的地方」的間接後果，而那一刻
   `fix_boundary` 會裁。**這是我的推論，不是量出來的**：若第 5 輪仍看到界外 cells
   而邊界旗只定案一次，就代表還有第三條產生界外格的路徑（最可能是
   `absorb` 在旗子已定之後仍收下線外的格——見設計決定 3，那是刻意保留的）。
4. **`_agrees()` 的支持數複驗變嚴，理論上可能讓某些本來會過的釘軸退回星座重定位。**
   方向是安全的（複驗過不了只是退回，不會多寫），但它會讓 `_solve()` 多走一條
   路徑。合成迴歸沒有覆蓋到「界外 mark 剛好是釘軸複驗的支持者」這個組合——實機上
   要留意 `islands.discarded` 有沒有變多。
5. **實機未驗證。** 本批純程式碼。要進 `docs/live-verification-queue.md` 的對帳項：
   - `survey_summary.cells` 的筆數 vs `survey.cells` 的界內 census 單位數——本批
     之後這兩個數字**必須相等**，不等就是還有第三條路徑（見爭點 3）。
   - `survey_tick.merge`：每一次 `islands.merged` 遞增都該恰好有一列帶 delta。
     delta 的量級與 `boundary` 的變化對照看——第 4 輪的 `(455.0, 186.9)` 約等於
     5 欄＋2 列，若這種量級的重錨反覆出現而台數同步跳升，鑑識就定讞在重錨上。
   - `boundary` 逐 tick 的變化次數：第 4 輪西界定案兩次。本批之後每一次定案都會
     裁剪，所以 `cells` 應該在定案那一 tick 明顯下降——那個下降本身就是修正生效的
     現場證據。
   - `islands.discarded` 有沒有比第 4 輪多（爭點 4）。
