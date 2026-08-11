# 界定先行批次導覽（veil 硬閘＋plan_pan 優先序，0811）

裁示來源：`docs/decisions.md`「（0811）掃描邊界界定順序」——「邊緣界定應該是要
最先做完的，不能假定有真值檔可以參考」。實錘案例 run 20260811-092754：南界
landmark 未定案前，`plan_window` 把圖外的 row-20 十二格排進點擊佇列，每格
~6.5s no_feedback 逾時，共浪費 ~72s 並在盤外留下 unsure 殘帳；而肇事窗的存證幀
上 `read_borders` 已經讀到 south:785.0（換算世界 1738.6，與最終 landmark 完全
一致）。問題不在看不見界線，而在「看得見但票數未滿」期間 `plan_window` 只認定案
界線。

本批兩項互補修正：修 1 讓看得見的界線**這一窗**就止血，修 2 讓推鏡順序把四界先
定完。兩者都不動 landmark 三票紅線。

## 修 1：可見界線硬閘（veil）

### 呼叫鏈

```
SweepRun.tour()                          scripts/sweep_scan.py:403
  frame = self.neutral()
  borders = sweep.read_borders(frame)          ← 這一幀讀一次，下面兩個都吃它
  self.witness(frame, borders)                 ← 目擊入票；票滿才寫 landmark/界線
  veil = sweep.provisional_bounds(             src/ggge_ai/runtime/sweep.py
             ledger.grid, self.offset, borders, ledger.boundary) or None
  plan = sweep.plan_window(..., veil=veil)     ← 越界的格：不 tap/不 blocked/
                                                  不 inferred/不 chart
  journal.record("window", ..., veil=veil)
```

### 執行順序（同一幀之內）

1. `read_borders(frame)` — 這一幀目視到的終止邊（螢幕像素）。
2. `witness(frame, borders)` — 先跑。票滿就寫 `ledger.boundary`，那一側之後歸
   `in_bounds` 管。
3. `provisional_bounds(grid, offset, borders, known=ledger.boundary)` —
   只補**帳本還沒有**的那幾側：`world = screen + offset[axis]`（axis 慣例與
   witness 同：west/east 取 0、north/south 取 1），索引走既有
   `border_cell(grid, side, world)`（終止邊往界內半格）。已在 `known` 的側不回
   值——landmark 定案的界由 `in_bounds` 管，veil 只補缺口。
4. `plan_window` 枚舉迴圈，在既有
   `if cell not in targets or not ledger.in_bounds(cell): continue` 的同一處加
   `if veil is not None and not _within(cell, veil): continue`。

### 方向符號只有一份

`SweepLedger.in_bounds` 的 limits 表抽成模組層 `_within(cell, bounds)`
（west: col < 界／east: col > 界／north: row < 界／south: row > 界，缺的側不設
限）。`in_bounds` 現在是 `return _within(cell, self.boundary)`，veil 檢查用同一
個函式，沒有第二份符號表。

### 為什麼「不 chart」是關鍵

四界未定時 `SweepLedger.pending()` 收的就是 `charted`。越界的格只要被 chart 過
一次，就會永久混進 pending 佇列，之後每一窗都被當待裁決重排——止血必須止在
chart 之前。`WindowPlan` 欄位沒有動：跳過的格不進任何欄位。

### 語意紅線

veil 是**單幀讀數**，只用來「這一窗不點」：不寫 `ledger.boundary`、不寫
landmark、不做任何永久裁決。跳過即自癒——該格下一窗會重新被枚舉；讀數是噪音就
會被之後的窗翻回來。

### 順手的省算

`witness` 改成 `witness(frame, borders=None)`，`None` 才自己 `read_borders`。
四個呼叫點（`confirm` / 標記錨定 / `relocate` / `pan` 的 pan_exhausted 分支）
本來各自就算過 borders，一併傳入，同一幀不再掃兩次邊。

## 修 2：plan_pan 界定先行

`plan_pan` 簽名不變。`not ledger.bounded` 時，在現行 pending 邏輯**之前**插入：

```
for side in (heading, flipped, "south", "north"):
    if side in pinned or side in ledger.boundary:  continue
    return (side, side if side in HEADINGS else flipped)
```

即 (1) heading 自己的界缺 →(heading, heading)；(2) 另一橫向的界缺 →(它, 它)；
(3) south 缺 →("south", flipped)；(4) north 缺 →("north", flipped)。被 `pinned`
的側跳過；四側都不缺、或缺的都被 pinned，就落回現行 pending 邏輯，行為與改前
逐字相同。`_more_that_way` 沒動。

效果：西北角歸零後先沿北帶推東把東界定案，接著沿東側下潛把南界定案（途中經過
的窗照常清算——搬標記本來就要點格），四界齊了才回頭蛇形清界內剩餘 pending。

## 爭點（要使用者裁的兩處取捨）

### 一、veil 單幀即生效 vs landmark 三票紅線

三票制的理由是「地標一次目擊就凍住的代價是永久的」（0805 那輪 east 被一次置中
反推寫錯，其後 96 次一致目擊都撞成 clash）。veil 沒有繞過它：它不入帳、不可
凍住、下一窗重算。代價是**一次假邊讀數會讓那一窗漏點幾格**；那幾格沒有被記成
任何裁決，下一窗照樣重新枚舉，所以是延遲不是漏檢。反方向的保守寫法是等兩票才
開 veil——沒採，因為肇事窗當下就已經讀對了，等票就是等 72s。

### 二、pan 優先序：橫向優先 vs 就近優先

現在的順序（heading → 另一橫向 → south → north）刻意讓橫向排在前面，貼合「沿
北帶推東到底、再沿東側下潛」這條實際跑過的路徑。它不看「哪一側比較近」——四界
未定時鏡位到各側的距離本來就是未知數（那正是要去量的東西），拿推斷的距離排序等
於用未知量做決策。代價是某些起始鏡位下會多走一段冤枉路。north 排最後是因為歸零
點在西北角，north 幾乎總是最早定案的那一側。

另一個沒做的選項：界定期間乾脆不清算（純推鏡）。沒採——搬標記本來就要點格，
路過的窗順手清算是免費的，而且不清算會讓 `strandings` 保險絲誤以為沒有進展。

## 測試

`tests/test_sweep.py` 新增五支：

- `test_a_seen_border_becomes_a_provisional_bound_only_where_the_ledger_has_none`
  —— 換算走 `border_cell` 語意（終止邊往界內半格），已在 known 的側不回值。
- `test_a_provisional_border_keeps_the_window_plan_off_everything_beyond_it`
  —— veil 之下的列不進 taps/blocked/inferred，也不進 `ledger.charted`／
  `pending()`；veil 之上照常。
- `test_a_window_plan_without_a_veil_charts_and_taps_exactly_as_before`
  —— `veil=None` 與現狀逐欄位相同（既有 window 測試未改動即為佐證）。
- `test_the_last_missing_border_outranks_a_backlog_of_pending_cells`
  —— west/east/north 已知、south 未知、且 heading 方向界內還有大量 pending →
  回 ("south", flipped)，證明界定壓過 pending。
- `test_a_pinned_missing_border_hands_the_pan_plan_back_to_the_pending_cells`
  —— 缺界方向被 pinned 就落回 pending 邏輯，且不因此寫界線。

`tests/test_sweep_scan.py` 兩處 `run.witness` 假件改收 `borders` 參數。

## 待實機驗證

- veil 在真幀上的讀數品質：離線測試餵的是合成 borders，`read_borders` 對真幀的
  假陽性率沒有在這批量到。要看的是 journal 新欄位 `veil` 與最終
  `ledger.boundary` 對不對得上（單位是格索引，可直接比）。
- 修 2 改變的是整輪推鏡路徑，總時長／總點擊數要跑一輪全盤才知道。預期少掉的是
  南界定案前那段圖外格逾時（~72s 量級），但界定先行本身可能多走一段推鏡。
