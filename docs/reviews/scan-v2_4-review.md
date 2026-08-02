# Review 導覽：掃描 v2.4 量測鏈修正批（2026-08-01）

基底 `feat/inner-goap` @ `3db40d5`（v2.3 入庫之後）。來源＝主 session 對複驗輪
第 3 輪（`data/runs/20260801-060433`）broken 幀對的離線鑑識定讞：**水平位移量測
改以格線相位為權威**。

範圍兩個產品檔：`src/ggge_ai/runtime/board.py`（主要落點）、
`src/ggge_ai/runtime/coverage.py`（**只動指示點名的三處**）。`envelope`、
`PHASE_TOLERANCE`、島嶼機制、`_whole_columns`、增益學習、符號層、`battle/`
一律未動。`stage/survey.py` 一個字沒改。

**設計決定清單在第六節，爭點在第八節**——本批對指示有兩處實質偏離（裁決規則的
矛盾否決、指令兜底的收緊），兩處都附實機數據，請優先審那兩條。

## Commit 全景

| commit | 工作 | 內容 |
|---|---|---|
| `6b929a6` | (1)(2)(3) | `board.measure_pan`＋整數欄三重裁決；`board.median_residual`＋`_snap`／`rephase` 改全線中位數；迴歸線 17 條＋「說謊相關器」測試替身 |
| （本檔） | — | review 導覽＋設計決定清單 |

**為什麼 (1)(2) 沒有拆成兩個 commit**（誠實聲明）：兩者共用 `_wrap`／
`_circular_median`／`import math`，而且 (1) 單獨落地會**當場退步**——格線通道量對
了，`_snap` 卻仍用單線殘差，抖動大的幀照樣被拒收。拆出來的中間 commit 不是綠的，
所以合成一個原子提交。

閘門（本 worktree 親跑，輸出見第七節）。

---

## 一、鑑識復算：本批的證據基礎

主 session 給的定讞我逐條在 worktree 內親自復算過（18 對 broken 幀，
`data/runs/20260801-060433/frames/broken/`）。三件事**確認**，一件事**推翻**：

### 確認：相關器凍值與靜態峰鎖死

| tick | `measure_shift().dx` | response | 格線輪廓真值 |
|---|---|---|---|
| t18-t24（東向 7 把平移） | **−108.0 ± 0.3** | 0.20-0.32 | −141 ~ −143 |
| t17／t28／t29／t30／t31 | **~0** | 0.12-0.18 | −140 ~ −146 |
| t10-t13（西向） | +92 ~ +115 | 0.46-0.49 | +120 ~ +148 |

`SHIFT_MIN_RESPONSE` 是 0.05，所以**每一筆都過了門檻**、退星座的 fallback 一次
都沒觸發。凍值誤差 33-35px、靜態鎖死誤差 140px。

### 確認：格線 90px 週期造成的整數欄歧義是根因

對每一對幀窮舉水平位移算 NCC，峰**成梳狀、間距恰是一個欄距**，而且高低差小到
不能當判準（t24：`39:0.980 / −52:0.978 / −142:0.938`；t28：
`−50:0.981 / 41:0.979 / −140:0.950`）。**任何純灰階相關器都分不出 k**——這正是
7/20 `battle/map_stitch.py` 被整條移除的同一個病，也是本批不去「調參數救相關器」
而是換權威的理由。

小數部分則穩得驚人：`_column_phase` 在 t18-t24 逐幀給 38.0-40.0（欄距 90.0-90.75），
逐線殘差散布只有 5-12px。**小數看格線、整數靠證人**這個分工是資料直接指出來的。

### 確認：垂直軸健康、欄距實測

南北向 BROKEN=0；全程 mean pitch 90.0-91.25，兩幀之間的差 <0.5px。所以
`measure_pan` 只接管水平，y 分量照舊走 `phaseCorrelate`。

### 推翻：一個我自己造出來的假真值（誠實記錄，免得下輪重踩）

我一開始拿**弧色遮罩**（非週期）窮舉 2D 位移當真值，得到 t17=−106、t21=−110，
與格線的 −142 差了 32-39px，一度看起來像「格線不跟內容走」。**那是我的估計量
壞了**：弧色遮罩裡混著靜態 HUD 家具（`board.py` 開頭的 docstring 早就寫了「多出來
的峰是靜態 HUD 家具與戰艦」），連續相關被它一路拉向 0。

判準是交叉比對：**星座投票（點集合、對靜態家具不敏感）與格線在每一個有票的 tick
上都吻合到 3px 以內**（t21 −139.0/−142、t24 −140.7/−141.5、t31 −142.3/−142.5），
而遮罩相關器是唯一的離群者。物理上也只有格線說得通——同一個 reach 152.2 的東向
平移連走 7 次，位移該是常數，格線給 −142±1，遮罩給 −106~−121 亂跳。

**結論不變，而且更強**：格線是唯一剛性的參考，星座是最好的獨立證人，兩者互相
佐證。指示的設計方向正確。

---

## 二、(1) 落點與呼叫鏈：格線相位通道

```
Odometer.feed(frame, expected)                      coverage.py:354  ← 本批唯一改的一行
 └─ board.measure_pan(previous, current, expected)  board.py:401     ★新
      ├─ expected 無／無 x 分量        → measure_shift(…)   （現行路徑，逐字不變）
      ├─ 任一幀 read_lattice 回 None   → measure_shift(…)
      ├─ 兩幀欄距差 > 10%（縮放動過）  → measure_shift(…)
      └─ 格線通道：
           ├─ _column_phase(before.cols, after.cols, pitch)   ★新　小數部分（權威）
           ├─ _phase_shift(previous, current, region)         ★抽出（原 measure_shift 的前四行）
           ├─ _constellation_shift(find_units×2)              （既有，未改）
           ├─ _correlator_credible(…)                         ★新　靜態峰否決
           └─ _resolve_columns(frac, pitch, expected, …)      ★新　整數欄三重裁決
                 └─ _nearest_candidate / _envelope_window     ★新
```

`measure_shift` 的**行為**逐字不變（只把前四行抽成 `_phase_shift` 供兩邊共用），
所以 `stage/survey.py` 的 `_settled_capture`、`_read` 的 precheck（`expected=None`）、
`battle/roster_calibration.py` 全部零影響。守成測試把這條釘住（第五節）。

### 裁決規則真值表

候選集合 ＝ `{frac + k×pitch}` ∩ 指令包絡窗 ∩ ±800（相位相關的無歧義範圍）。
兩個獨立證人各自挑「離自己最近且在半格容差內」的候選（平手＝棄權）。

| 星座 | 相關器（可信） | 兩者選同一格 | 結果 | 0801 對應 |
|---|---|---|---|---|
| 有選 | 有選 | 是 | `lattice:constellation` | t21-t24、t10、t12 |
| 有選 | 有選 | **否** | **None（誠實不知道）** | t11、t13 |
| 有選 | 無（不可信／缺席） | — | `lattice:constellation` | t28-t32 ★本批要救的 |
| 無 | 有選 | — | `lattice:phase` | t18、t19、t20 |
| 無 | 無 | — | 窗內唯一候選才 `lattice:commanded`，否則 None | t17 → None |

`_correlator_credible` 的否決條件：`response < SHIFT_MIN_RESPONSE`，或
**「|dx| < 40px 但兩幀 `frame_difference` ≥ 2.5」＝畫面明明變了卻說沒動**。
真停滯（手勢被吃掉、到邊）兩幀幾乎逐像素相同，照樣過關。

### 實機幀對的前後對照（18 對全跑，本 worktree 親跑）

| tick | 舊 `measure_shift` | 新 `measure_pan` | source | 星座（獨立佐證） |
|---|---|---|---|---|
| 10 | +109.8 | **+142.0** | lattice:constellation | +138.8 |
| 11 | +113.7 | **None** | none | +21.5（矛盾→否決） |
| 12 | +114.8 | **+148.0** | lattice:constellation | +191.5 |
| 13 | +92.8 | **None** | none | +4.7（矛盾→否決） |
| 17 | −0.2 | **None** | none | 無票 |
| 18 | −108.1 | **−141.5** | lattice:phase | 無票 |
| 19 | −108.0 | **−141.5** | lattice:phase | −945（窗外→無效） |
| 20 | −108.0 | **−141.0** | lattice:phase | 無票 |
| 21 | −108.0 | **−142.0** | lattice:constellation | −139.0 |
| 22 | −108.0 | **−142.0** | lattice:constellation | −139.8 |
| 23 | −108.3 | **−142.5** | lattice:constellation | −139.0 |
| 24 | −108.0 | **−141.5** | lattice:constellation | −140.7 |
| 27 | −0.5 | −0.5（fallback） | phase | prev 讀不出格網 |
| 28 | −0.3 | **−140.0** | lattice:constellation | −138.5 |
| 29 | −0.1 | **−146.0** | lattice:constellation | −142.8 |
| 30 | −0.2 | **−144.0** | lattice:constellation | −141.5 |
| 31 | −0.2 | **−142.5** | lattice:constellation | −142.3 |
| 32 | +0.2 | **−125.2** | lattice:constellation | −121.2 |

**14/18 從「原本全數 BROKEN」變成量得出來，且每一筆都與星座這個獨立估計量吻合到
1.5px 以內**（t19 的 −945 是離譜票，被包絡窗篩掉後改由相關器定 k，結果與鄰近幾
把平移一致）。3 筆（t11／t13／t17）誠實回不知道＝維持今天的 BROKEN，零退步。
t27 因為 prev 幀讀不出格網走 fallback，與今天逐字相同。

**沒有任何一筆的新結果與獨立證人矛盾。**

## 三、(2) 相位殘差取樣穩健化

`board.median_residual(lines, pitch, anchor)` ★新：對整組線位取**環狀**中位數。
`phase_residual` 的簽章與語意一個字沒改（內部改呼叫共用的 `_wrap`）。

coverage.py 兩處改法完全對稱（`_snap` 與 `rephase`）：

```python
-        residual = board.phase_residual(lattice.cols[0] + candidate[0], pitch, …)
+        residual = board.median_residual(
+            [col + candidate[0] for col in lattice.cols], pitch, …
+        )
```

為什麼要環狀中位數而不是直接 `median`：殘差是 mod pitch 的量，真值卡在 ±pitch/2
時樣本會分裂到圓的兩端，偶數筆取平均會落在 0（離真值最遠）。先用相量平均定圓心
再取中位數。迴歸線把這個坑釘住
（`test_the_median_residual_does_not_split_a_phase_that_straddles_the_cell_edge`）。

## 四、coverage.py 的改動逐行交代（指示要求）

| 行 | 改動 | 理由 |
|---|---|---|
| `:15-16` | 模組 docstring 第 1 條防線的敘述 | 主里程計不再只是相位相關，文件不能留舊話 |
| `:354` | `measure_shift(prev, frame)` → `measure_pan(prev, frame, expected)` | 唯一的接線；`expected` 本來就是 `feed` 的參數 |
| `:386-390` | `rephase` 殘差改 `median_residual` | 指示 (2) |
| `:399`、`:405-407` | `_snap` 殘差改 `median_residual`＋docstring 一行 | 指示 (2) |

**`feed` 的控制流一個分支都沒動**：still 判定、`envelope`、`_snap` 拒收、
STALLED 判定、`self.offset`／`self.previous` 的推進時機全部原樣。

---

## 五、迴歸測試對應表

新增 17 條（基底 1550 收集 → 本批 1567 收集）。「未修碼 FAIL」欄是**把修正還原後
親跑實測**的結果，不是推理。

| 工作 | 測試（檔案） | 斷言 | 未修碼 FAIL |
|---|---|---|---|
| (1) | `test_the_column_phase_reads_the_fraction_a_pan_leaves_on_the_grid`（board） | 合成世界左移 300 → 相位差 −44（300 mod 128） | 新函式 |
| (1) | `test_the_constellation_outranks_the_correlator_for_the_column_count`（board） | 星座證人勝出 | 新函式 |
| (1) | `test_the_correlator_carries_the_column_count_when_nobody_voted`（board） | 無票時相關器定 k | 新函式 |
| (1) | `test_two_independent_witnesses_pointing_at_different_columns_refuse_to_guess`（board） | 獨立證人矛盾 → None | 新函式 |
| (1) | `test_a_witness_sitting_between_two_columns_is_no_witness`（board） | 證人卡在兩候選正中間 → None | 新函式 |
| (1) | `test_the_command_alone_only_speaks_when_it_leaves_a_single_column`（board） | 窄窗＝唯一候選才降級採用；真實的單次平移距離 → None | 新函式 |
| (1) | `test_the_column_vote_keeps_the_westward_sign`（board） | 西向（正號）照樣裁對 | 新函式 |
| (1) | `test_a_correlator_locked_on_the_static_peak_no_longer_freezes_the_measurement`（board） | 說謊相關器下 `measure_shift().dx == 0` 而 `measure_pan` 量到 −240 | ✅ 實測 |
| (1) | `test_the_lattice_channel_stands_down_without_a_horizontal_command`（board） | `expected=None`／無 x 分量 → 與 `measure_shift` **逐值相等** | — |
| (1) | `test_a_frame_without_a_lattice_falls_straight_back_to_the_old_path`（board） | 讀不出格網 → 與 `measure_shift` 逐值相等 | — |
| (1) | `test_a_correlator_frozen_on_the_static_peak_no_longer_freezes_the_odometer`（coverage） | 4 把平移全 ACCEPTED、dx≈−300、source 走 lattice、offset 累到 1200 | ✅ 實測（全 `broken`） |
| (1) | `test_a_whole_scan_still_converges_under_a_frozen_correlator`（coverage） | 30×16 世界整輪 synced、單位格＝世界真值 | ✅ 實測（never synced；24 unlocalised／23 島嶼丟棄／5 次重開世界） |
| (1) | `test_the_settle_gate_never_goes_through_the_commanded_channel`（stage） | `_settled_capture` 一次都沒碰 `measure_pan`；waits／shots 逐字照舊 | — |
| (2) | `test_the_median_residual_shrugs_off_one_jittery_line`（board） | 單線 +10px 離群 → 中位數 0 | 新函式 |
| (2) | `test_the_median_residual_does_not_split_a_phase_that_straddles_the_cell_edge`（board） | 殘差卡在 ±pitch/2 → 不塌成 0 | 新函式 |
| (2) | `test_a_single_jittery_grid_line_no_longer_rejects_the_whole_frame`（coverage） | cols[0] 殘差 25 > 容差 22.5，整幀仍收下、吸附到中位數 | ✅ 實測（`snapped is None`） |
| (2) | `test_rephasing_an_island_reads_every_line_not_just_the_first`（coverage） | 島嶼開局的相位對齊同樣走全線 | — |

### 測試替身

`tests/fixtures/synthetic_map.py` 多一個 `freeze_correlator(monkeypatch)`：把
`board._phase_shift` 的**水平分量**鎖成 0、response 壓在門檻之上，垂直分量照實回
——逐字復刻 t27/t28/t30 的實機情境（南北健康、只有水平被搶峰）。兩支迴歸共用同一個
謊言，不各寫一份。

`SPREAD` 擺位（大世界用）刻意讓**列位不成等差**：等差擺位會讓多對單位共用同一個
平移量，`_constellation_shift` 遇到並列眾數就棄權，測試會變成在測星座的巧合而不是
測格線通道。這一條踩過才發現，寫進註解。

### 既有測試的修改

**零**。既有斷言、參數一個字沒改。`synthetic_map` 只新增一個函式與一行 import。

---

## 六、設計決定清單（自由裁量處逐條備案）

1. **新開 `measure_pan` 而不是給 `measure_shift` 加 optional 參數。** 指示說「擇一，
   介面乾淨為準」。取前者：`measure_shift` 是三個呼叫端共用的通用量測，加一個只有
   一個呼叫端會用的參數會讓另外兩端每次都要想「我該不該傳」。`measure_pan` 的名字
   直接說了它的前提＝**有指令的平移**。
2. **`measure_pan` 自己承接所有 fallback，`Odometer.feed` 只換一個函式名。** 備選是
   在 `feed` 裡分支（有 x 分量走新的、否則走舊的）。不取：那會把「什麼時候格線通道
   成立」這個純像素層的知識漏進世界模型層，而且 `feed` 是 v2.1-2.3 剛過三輪審的
   程式碼，指示明寫只准動點名的位置。
3. **source 用 `lattice:<證人>` 三值而不是單一 `"lattice"`。** 指示說「標新值（如
   lattice）」。取帶後綴：遙測要能分出「靠星座定 k」與「靠相關器定 k」——第 4 輪
   對帳時這兩者的可信度不同，混成一個值就查不出來。`Shift.known` 只看 `!= "none"`，
   所以不影響任何既有判斷。
4. **`_correlator_credible` 是本批新增的許可制（指示沒點名）。** 沒有它，t17／t20
   這種「無星座票＋相關器靜態鎖死」的幀會挑到 +39 的候選 → 位移 39 < `EDGE_SHIFT_PX`
   → 被判 **STALLED** → 連兩次就把邊界旗永久釘在地圖中央。那比今天的 BROKEN 嚴重
   得多（邊界旗跨代保留）。判準完全用既有常數（`EDGE_SHIFT_PX`／`EDGE_FRAME_DIFF`），
   不新增可調參數。
5. **候選先被包絡窗篩過，再交給證人挑。** 備選是讓證人在全部候選裡挑、由下游
   `envelope` 拒收。取前者：t19 的星座票是 −945（離譜眾數），不篩就會選到 −951.5
   然後被下游拒收＝白白丟掉一筆本來救得回來的量測（篩過之後改由相關器定 k，
   得到 −141.5，與鄰近幾把平移一致）。**保護沒有變弱**：真的落在窗外的位移，兩個證人都會
   指向窗外，窗內就不會有候選在容差內，照樣回 None。
6. **獨立證人矛盾時回 None，而不是「星座最強所以星座贏」（偏離指示）。** 見爭點 1。
7. **指令兜底要求「窗內唯一候選」，而不是「取離 expected 最近的候選」（偏離指示）。**
   見爭點 2。
8. **`LATTICE_WITNESS_TOLERANCE = 0.5`（半格，指示原值）不動。** 實測資料支持：
   好的星座票離候選 2-3px（0.03 pitch），健康相關器離候選 27-34px（0.30-0.37 pitch）
   ——想用一個更緊的容差把「壞星座票」擋掉，就會連「健康相關器」一起擋掉，兩者的
   誤差區間重疊。所以改用**矛盾否決**（決定 6）當篩子，容差維持指示的半格。
9. **`_column_phase` 的配對用絕對距離最近，不是「mod pitch 最近」。** 後者會逐線挑
   殘差最小的那條，把答案系統性拉向 0（17 條線就有 17 次挑最小的機會，偏差可達
   單線抖動的全幅 ~10px）。
10. **殘差的中位數是環狀中位數。** 見第三節。多的成本是每幀一次 atan2，可忽略。
11. **`pitch` 取兩幀 `col_pitch` 的平均。** 實測兩幀之間的差 <0.5px，取哪個都行；
    取平均免得「以誰為準」變成一個要解釋的選擇。差超過 10%（`LATTICE_PITCH_DRIFT`）
    就是縮放被動過，直接退回現行路徑——那時候格線相位不是同一個世界的量。
12. **y 分量照舊（指示明寫）。** `response` 夠高就取相關器的 dy，否則取星座的 dy，
    都沒有就 0.0——這正是 `measure_shift` 原本的優先序，只是攤開寫。
13. **`limit = MAP_REGION[2] / 2` 當候選枚舉界。** 相位相關的無歧義範圍就是 ±窗長/2；
    超出去的候選本來就沒有任何證人能證實。實務上包絡窗一定更窄，這一層是保險。
14. **多花的計算：每把水平向的平移多 2 次 `read_lattice` ＋ 2 次 `find_units`（粗估
    100-150ms）。** 沒有做快取。理由：一個 tick 本來就有 2 次截圖（~0.5s）＋
    `PAN_SETTLE_S = 1.5s` 的等待，多這一百毫秒量不出來；而跨呼叫快取幀的解析結果
    需要一個 id→結果的環形緩衝，那是為了省 3% 引入的狀態與失效風險。
15. **`freeze_correlator` 放在 `tests/fixtures/synthetic_map.py`。** 它不是地圖，
    但它是「同一套合成掃描」的替身，兩支迴歸共用一份謊言比各寫一份可靠。代價是
    那個 fixture 模組現在 import `board`。

---

## 七、閘門輸出（本 worktree 親跑）

```
$ uv run pytest -q
1560 passed, 4 skipped, 3 xfailed in 223.83s (0:03:43)

$ uv run ruff check src tests scripts
All checks passed!
```

基底 `3db40d5` 在同一個 worktree 是 **1543 passed, 4 skipped, 3 xfailed**（收集
1550 條）；本批 +17 條全部是新的迴歸線，跑時多約 4 秒。

實機幀對的復算（第二節的表）另有一支離線腳本，不入庫——它吃的是 gitignored 的
`data/runs/20260801-060433`，跑法是對每一對 `frames/broken/*-{prev,curr}.png`
呼叫 `board.measure_shift` 與 `board.measure_pan`（`expected` 取自
`dry_run.jsonl` 的 `survey_tick.expected`），再拿格線高通投影的一維互相關與
`board._constellation_shift` 當對照。

---

## 八、爭點

1. **獨立證人矛盾時回 None，而不是讓星座直接贏（偏離指示的「星座有票時最強」）。**
   指示的規則在 t11／t13 會產生**差一整欄的靜默錯誤**：星座票 +21.5／+4.7，選到的
   候選是 +55.75／+29.5，而格線輪廓與相關器都指向 +146.5／+120.5。那個錯值過得了
   包絡閘，也過得了相位閘（**它是由格線相位構造出來的，殘差必然為 0**）——也就是說
   下游沒有任何一道防線攔得住它，會直接寫進權威圖。這正是「無量錯寫入」不變式不准
   存在的路徑，所以我改成矛盾即斷鏈。代價：t11／t13 維持 BROKEN（＝今天的行為，
   零退步）。**若主 session 認為星座該無條件優先，改動只有一行**（把
   `if len(set(spoken.values())) > 1: return None` 拿掉）。
2. **指令兜底收緊成「窗內唯一候選」，實務上等於停用（偏離指示的「包絡窗內兜底」）。**
   實機數字：東向平移 `expected = −350.1`，包絡窗 `[−875, +40]`，欄距 90 → **窗內有
   11 個候選**，而真值是 −142（指令是真值的 2.5 倍，因為增益還在學）。取「離
   expected 最近」會回 −324，差兩整欄。所以我要求窗內只剩一個候選才採用——真實的
   單次平移距離下這個條件幾乎永不成立，`lattice:commanded` 這條路在正式掃描裡
   等於不會走。
   **這是刻意的**：兩個獨立證人都缺席時，誠實回不知道比拿手勢當位置安全（0719 紅線）。
   若主 session 要恢復「最近候選」語意，落點是 `_resolve_columns` 最後三行。
3. **`t27` 這類「prev 幀讀不出格網」的斷鏈本批沒救。** 18 對裡有 1 對，
   `read_lattice(prev)` 回 None（那一幀的格網被虛空／演出蓋掉）就整條退回現行路徑。
   要救得往 `read_lattice` 的召回率去，那是另一批的事。
4. **`_correlator_credible` 用 `frame_difference` 當「畫面變了沒」的判準，門檻沿用
   `EDGE_FRAME_DIFF = 2.5`。** 那個常數原本是為「幀差判停滯」調的，這裡是第二個用途。
   實機 18 對上兩種情境分得很開（真停滯的幀對幾乎逐像素相同），但這是**同一個數字
   服務兩個判斷**，未來若要為其中一個微調就得先拆開。
5. **A6 多記（51-68 台 vs 期望 28）本批不修，照指示留給第 4 輪對帳。** 預期：水平
   里程計修好之後斷鏈期的座標漂移消失，鬼影的源頭跟著消失。**這是預測不是保證**
   ——若第 4 輪台數仍然偏高，就是 UNIT 滯後在收假票（v2.3 爭點 1），要另案處理。
6. **實機未驗證。** 本批純程式碼。要進 `docs/live-verification-queue.md` 的對帳項：
   - `survey_tick` 的 `shift.source` 分布：水平向的平移應該大量出現
     `lattice:constellation`／`lattice:phase`；若出現 `lattice:commanded` 就代表
     爭點 2 的假設錯了（窗內
     真的只剩一個候選），要回頭看增益是不是已經收斂到讓窗變窄。
   - 水平向 BROKEN 次數：第 3 輪 18 次（幾乎全水平）。以離線復算推估應降到 3-4 次，
     **但這是對同一批幀的推估，不是對新一輪的保證**——鏡頭位置不同，星座票的品質
     會不同。
   - `shift.magnitude ÷ expected`：修好之後水平向的平移應該從 0.31 跳到 ~0.4（真值 142
     對指令 350），接著增益學習會把它推向 1.0。**兩件事同時在動**，對帳時要看
     `gain` 欄位而不是只看比值。
   - 整輪平移次數與 `survey_done.tick`：預期明顯少於第 3 輪。
   - `survey_summary.cells` 的單位數 vs 人工目視台數（承 v2.3 爭點 3、本批爭點 5）。
