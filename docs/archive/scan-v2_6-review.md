# Review 導覽：掃描 v2.6 影像複驗閘批（2026-08-01）

基底 `feat/inner-goap` @ `1a9cf76`（v2.5 入庫、第 5 輪判定之後）。來源＝第 5 輪
（`data/runs/20260801-080213`）的台數膨脹：journal 記 80 台，真值 ≈28（敵 18＋
我 10），而藍弧就有 52 格對我方實際 10 台。根因由使用者一手看幀診斷定讞。

範圍兩個產品檔：`src/ggge_ai/runtime/board.py`、`src/ggge_ai/runtime/coverage.py`。
`battle/` 沒碰；`stage/survey.py` 一行未動（遙測欄位沿用既有 schema，只是
`islands` 多一個計數鍵）。

**設計決定清單在第八節，爭點在第九節。** 使用者中途擴充的第四件工作（格子存在
遮罩＋終止邊目擊）在第六節。

## Commit 全景

| commit | 工作 | 內容 |
|---|---|---|
| `8f321fc` | (1)(2) | `board.null_check` 影像複驗閘＋`_constellation_witness` 接線；`board.find_lattice` 象限窗 fallback 接 `Odometer._snap`／`rephase`；迴歸 6 條 |
| `ad97d25` | (3) | 島嶼（定位中斷後位置不明的觀測暫存區，等重新定位才併回）合併的指令合理範圍閘與影像複驗閘（`Survey._admits`／`_metered`）、`islands.refused`；迴歸 3 條＋既有 2 條改寫 |
| `4df6600` | (4) | `board.read_span` 終止邊目擊、`covered()` 格線遮罩、`Survey._sight_edges`／`_edge_clash`；迴歸 5 條 |
| （本檔） | — | review 導覽＋設計決定 |

閘門（本 worktree 親跑，最後一次）：

```
$ uv run pytest -q
1583 passed, 4 skipped, 3 xfailed in 233.03s (0:03:53)

$ uv run ruff check src tests scripts
All checks passed!
```

本 worktree 基底的數字是 **1567 passed**（不是交辦單寫的 1571，基底 commit 不同），
本批淨增 16 條（新增 17、移除 1 條被改寫的）。

---

## 一、機制鏈：80 台是怎麼長出來的

三個咬合的齒輪，缺一不可：

1. **邊緣區相位閘停擺。** 掃描走到地圖北緣之後，地圖只佔畫面一角，全幀
   `GRID_REGION` 帶取樣不到六欄四列，`read_lattice` 回 None。`Odometer._snap`
   讀不到格線是**無條件放行**——於是那一段完全沒有相位交叉驗證。
   逐幀實測（`t*-precheck`／`t*-leg` 全 74 張）：t7-leg 到 t13-precheck 七幀全幀帶
   一律 None，而 `MAP_REGION` 下半窗讀得到 pitch 92-93 的格線。
2. **量測在同一段時間說謊。** t11／t12 那兩把平移的 phaseCorrelate 回 (2.0,
   0.5)／(1.3, 0.4)，response 0.10／0.096（過得了 `SHIFT_MIN_RESPONSE`），於是
   兩把都被判 STALLED。逐精靈模板比對（離線，本批的鑑識工具）量到的真位移是
   +220／+199。
   **鏡頭實際走了 400px，里程計原地不動**——同一片場景以同一個 offset 反覆吸收，
   單位因此落在錯格，而 UNIT 滯後（v2.3）把每一份鬼影都保到跨代。連兩次 STALLED
   還把西界旗釘在地圖中央。
3. **定位中斷之後的重錨把錯誤放大。** 島嶼合併偏移出現 (546, −670.3) 與四次
   +273。前者的 y 分量沒有任何指令推過（島只斷了一把東向的平移）；`relocalise`
   走的是同一個 `_constellation_shift`，而同型薩克與我方編隊是週期陣列（幀內單位
   縱距實測 90/93/96），「錯一個編隊間距」的配對投得出票數十足的幽靈位移——幽靈＝
   週期圖案錯位配對出的假位移候選，畫面上無真實對應。

**裁判已驗證**：直接影像比對分得出真移動與幽靈。t7 的真移動（單位排列比對 7
台一致 +122px）在逐精靈窗上是 4 票 moved／0 票 still；t29 的幽靈票 (−8.7, −
165) 是 0:7。

---

## 二、(1) 影像複驗閘：落點與呼叫鏈

```
board.null_check(previous, current, delta, points=None, region=MAP_REGION) -> str   ★新
 └─ 逐精靈窗 mean-abs-diff：current 的窗 vs previous 同位置（原地）／平移 delta（位移）
    回 moved／still／unclear／blind

board._constellation_witness(previous, current, region) -> Shift | None             ★新
 ├─ _constellation_shift(find_units(previous), find_units(current))   （既有，未改）
 ├─ null_check(...) == still  → Shift(0, 0, conf, "constellation:still")   ← 確定沒動
 ├─ null_check(...) == unclear→ None                                      ← 誠實不知道
 └─ moved／blind              → Shift(vote…, "constellation")             ← 照舊

board.measure_shift  ← 單位排列比對的 fallback 改叫 _constellation_witness
board.measure_pan    ← 單位排列比對這路佐證改叫 _constellation_witness；回 still 時整條格線通道讓位
```

下游一行未改：`Odometer.feed` 看到零位移但 `known` 的 Shift，走的就是既有的
STALLED 那一支（`shift.magnitude < EDGE_SHIFT_PX` ∧ `_commanded(expected)`）。
這同時解掉「待機動畫堵死同幀判定」——實機待機動畫的 `frame_difference` 5.8-12.5
恆高於 `EDGE_FRAME_DIFF`（2.5），原地幀永遠走不進靜止那一支。

### 為什麼是逐精靈窗，不是整個 MAP_REGION 取一個平均

交辦單寫的是「masked mean-abs-diff on MAP_REGION」。**整區平均實測不可用**，因為
畫面有兩層：地圖外的星空背景不隨鏡頭動、地圖層才動，整區平均由面積大的那一層說了
算。0801 實幀（整區灰階平均絕對差，位移假設／原地假設的比值，<1 代表位移勝）：

| tick | delta（排列比對的票） | 真相 | 整區比值 | 逐精靈窗 moved:still |
|---|---|---|---|---|
| t7 | (−6, +122) | 真移動 | 0.730 ✅ | 2:0 ✅ |
| t15 | (−19, −175) | 真移動（使用者看幀確認） | **1.104 ❌** | 4:0 ✅ |
| t16 | (−17, −149) | 真移動 | **0.995 ❌** | 4:0 ✅ |
| t24 | (−18, −192) | 移動了，但票值錯（真值 y ≈ −116） | **1.315 ❌** | 1:1 → unclear ✅ |
| t29 | (−9, −165) | 原地 | 1.351 ✅ | 0:7 ✅ |
| t12 | (+202, 0) | 真移動（相關器說停滯） | 0.778 ✅ | 2:0 ✅ |

整區平均分不開 t24（真移動、錯票）與 t29（原地）——1.315 對 1.351。逐精靈窗把
兩者分得乾乾淨淨，而且窗只落在地圖層，天生不吃星空。高通、梯度、色帶遮罩三種
整區變體都試過（比值分佈仍重疊），逐精靈窗是唯一分得開的。

### 四個裁決而不是三個

`NULL_BLIND`（取樣不到 `NULL_MIN_WITNESSES` 個窗）與 `NULL_UNCLEAR`（看了，兩
個假設都對不上）分開。理由是失效方向相反：unclear 該拒收（交辦單的「兩邊分數
都爛＝真的不知道」），blind 是**裁判缺席**，這時把原本收得下的量測丟掉會讓空曠
地帶整段定位中斷（合成世界的迴歸直接示範：鏡頭底下常常只有 0-1 台）。blind 一
律照舊處置。

---

## 三、(2) 邊帶格線 fallback：落點與呼叫鏈

```
board.read_lattice(frame, region, bands, minimum=(GRID_MIN_COLS, GRID_MIN_ROWS))  ← 加參數
board._lattice_bands()  ★新  = GRID_REGION 全幀帶 → MAP_REGION 四象限窗（線數門檻等比縮，下限 3）
board.find_lattice(frame) ★新 = 第一個過三重閘的帶
 ├─ Odometer._snap    ← 改（相位交叉驗證＋吸附）
 └─ Odometer.rephase  ← 改（島嶼開局對相位）
```

**沒有改的**：`Survey._anchor`（錨定要全幀帶那種取樣量才敢定格距）、
`measure_pan` 的格線通道（改它會動到量測值，本批只加閘）。29448bc 的分帶多尺度
是同一個模式的前例。

---

## 四、(3) 合併偏移兩道閘：落點與呼叫鏈

```
Survey.observe
 ├─ 非 BROKEN 且沒有島 → self.mainland = (frame, odometer.offset)      ★新
 └─ Survey._reanchor(leg, reading, view, frame)         ← 簽名多一個 frame
      ├─ island.lost = _lost(island.lost, leg.expected) ★新（島內每一把都累加）
      ├─ delta = self._solve()                          （既有，未改）
      └─ self._admits(island, delta, view, frame)       ★新
           ├─ _metered(island, delta)：|delta軸| ≤ 1.5×lost[軸] ＋ 一格
           └─ board.null_check(mainland幀, 島當下幀, 隱含螢幕位移, view.units)
                still → 拒併（島照舊攢，攢滿 ISLAND_BUDGET 就 _abandon）
```

隱含螢幕位移 ＝ `mainland.offset − view.offset − delta`（世界 ＝ 螢幕 ＋ offset
的直接推論）。`Survey.mainland` 是量測層自己留的一份：driver 的 `previous`
是 stage 層的取幀紀錄，`Odometer.previous` 在定位中斷時刻意不推進，兩者都不是
「大陸最後的權威幀」——大陸即位置可信的權威知識圖那一側，相對於島嶼。`_abandon`／
`reset` 會清掉它。

`lost` 是軸別的指令位移絕對值和，**島內每一把平移都累加**（不只定位中斷那一
把）：島內的平移即使被判 STALLED 也可能是量錯，那段位移一樣要靠合併偏移補回
來。跨島嶼繼承——島內再發生定位中斷會換一座島但沿用同一個局部原點。回合交界的島
`lost=None`＝不設合理範圍。

---

## 五、實幀重放對照表（run 20260801-080213，t1-t37）

離線重放：同樣的 74 張幀、同樣的指令（照 journal 的 direction／reach／expected），
逐 tick 比對舊碼（journal，實機當時）與本批。**第一次分歧之後兩邊的世界狀態就不同
了**，所以這是逐 tick 的裁決對照，不是等價重跑。

| tick | journal（v2.5） | replay（v2.6） | 判讀 |
|---|---|---|---|
| t11-leg | stalled/ok phase | **broken/phase** | ✅ 本批要救的那一把平移：真位移 +220px 被記成停滯，象限窗補回相位閘後誠實判定位中斷 |
| t12-leg | stalled/ok phase | **broken/phase** | ✅ 同上（真位移 +199px）。連兩次 STALLED 不再發生 → 西界旗不會被釘在地圖中央 |
| t13-prec | accepted/ok still | **broken/phase** | ✅ 前兩把平移的錯位還在 offset 裡，相位閘接著把它擋下來 |
| t23-leg | broken/unmeasurable | accepted/ok lattice:phase | 下游分歧（世界狀態已不同）；本批沒有針對這一把平移的機制 |
| t24-leg | accepted/ok constellation | **broken/unmeasurable** | ✅ 排列比對的票 (−18,−192) 被影像複驗判 unclear（真值 y≈−116），錯值不再入帳 |
| t31-leg／t32-leg | stalled／broken | broken／stalled | 下游分歧（相位閘的判定挪了一格） |

其餘 67 筆逐字相同（含全部 accepted/constellation 真的有移動的平移：t3-t7、t10、
t15、t16、t33-t35 —— **複驗閘沒有誤殺任何一次真移動**）。

島嶼帳：journal `isolated 7 / merged 7 / discarded 0 / reset 0`，replay
`isolated 10 / merged 5 / discarded 5 / reset 2 / refused 0`。journal 那七次合併
包含 (546,−670.3) 與四次 +273；replay 的軌跡裡那兩座島根本沒長出來（里程計沒有先
漂掉），所以合理範圍閘在這條軌跡上一次都沒被用到（`refused 0`）——它的效力由單元
迴歸釘住，見第七節。

**replay 的最終台數（43）不是本批的成績**：重放的平移順序是舊碼規劃的，新碼中途
重開世界之後不會重新規劃補掃，末尾那個世界只吃到序列的尾巴。台數軸只有實機一輪才
判得了，見第九節爭點 1。

### 終止邊目擊（本批第四件工作）在同一批實幀上的表現

| tick | 目擊 | 對照 |
|---|---|---|
| t3-t6、t8-t10、t13、t15-t20 | `west` | 使用者看幀確認：地圖西緣就在畫面上，左側是星空 |
| t7、t14 | `west`＋`north` | 北緣也進畫面了 |
| t30 | `south` | |
| t34-t37 | `east` | 鏡頭推到東緣 |
| t11、t12、t21-t29、t31-t33 | 無 | 地圖填滿取樣帶，沒有終止邊可言 |

一次假邊都沒有。另一個對照：t3 的西緣世界像素 ≈660，t13 是 ≈1043——差 383px
≈ t11＋t12 漏記的位移量。**目視邊自己就抓得到那段漂移**（`_edge_clash` 的證據
基礎）；在本批的軌跡裡那段漂移沒發生，所以重放全程沒有觸發 edge_mismatch。

---

## 六、(4) 格子存在遮罩＋終止邊目擊：落點與呼叫鏈

使用者中途擴充的第四件工作。架構缺口：四態知識全是**單位知識**，每一態都預設
「這裡有一格」；`covered()` 純幾何不看像素，星空虛空照樣被蓋 EMPTY 章；
`read_lattice` 讀得到的格線範圍只拿去驗相位就丟了。

```
board.read_span(frame) -> GridSpan | None                      ★新
 ├─ _lattice_bands() 逐帶試（與 find_lattice 同一個原語）
 ├─ box   ＝ 線位圍出來的螢幕矩形
 └─ edges ＝ _terminal_edges(frame, lattice, band)             ★新
      三道閘：外側取樣條高通 ≤10（絕對）、≤0.5×內側（自洽）、灰階 ≤0.75×內側（亮度）
      ＋「帶內留得下一整格」的空間閘（貼著帶緣的線不出證言）

Survey._view(frame, offset) → FrameView(lattice=span.box, edges=span.edges)   ← 改
 ├─ coverage.readable(grid, view)  ★新（＝舊的 covered，純幾何）
 │    └─ KnowledgeMap.absorb 的**目擊**准入
 └─ coverage.covered(grid, view)   ← 改（readable ∩ 有目擊那幾側的半平面）
      └─ KnowledgeMap.absorb 的 **EMPTY 毯**／edge_cell／fix_boundary

Survey.observe（大陸那一支）
 ├─ _edge_clash(view) → 不是 None 就當 BROKEN 隔離（reason `edge_mismatch:<側>`）  ★新
 ├─ chart.absorb(view)
 └─ _sight_edges(view) → 旗未定就 chart.set_boundary(direction, line)              ★新
Survey._anchor 也走 _sight_edges（turn-1 那一幀就可能看得到邊）

KnowledgeMap.set_boundary(direction, line) ★新 ＝ 定旗＋_trim()
 └─ fix_boundary（撞邊那條路）改走它 —— v2.5 的線外裁剪照樣觸發（e 交代）
```

**遮罩只切有目擊的那幾側，不是整個線位矩形。** 交辦單的字面是「格框須落在該矩形
內」，實測不可行：`GRID_REGION` 是取樣帶不是格網的邊界，拿帶緣當界會讓單幀的
EMPTY 毯從 2100×930 縮到 1600×530（約四成），掃描的平移次數跟著翻倍，而且那些被
排除的
格明明有格線、只是帶外沒去取樣。半平面版本在「格線填滿畫面」時與 v2.5 逐字相同，
只有真的看到終止邊才切——與 `_terminal_edges` 的空間閘同一條原則。設計決定 11。

---

## 七、迴歸測試對應表

新增 17 條（其中一條是既有測試改寫後的新名字），另改寫既有 2 條的替身或斷言。「未修碼 FAIL」欄是把對應修正還原後**親跑實測**的結果。

| 工作 | 測試（檔案） | 斷言 | 未修碼 FAIL |
|---|---|---|---|
| (1) | `test_a_formation_alias_vote_is_overruled_by_the_picture`（board） | 週期陣列＋同幀 → 單位排列比對投出 +一格的幽靈票；`null_check` 回 still；`measure_shift` 回零位移且 known | ✅ 實測 |
| (1) | `test_a_real_pan_still_beats_the_null_hypothesis`（board） | 真平移 150px → moved，票照收 | —（守成：防誤殺） |
| (1) | `test_the_null_check_says_nothing_when_there_is_nothing_to_look_at`（board） | 只有一台時回 `NULL_BLIND` | —（守成：防空曠地帶定位中斷） |
| (1) | `test_an_idle_animation_no_longer_blocks_the_stall_verdict`（coverage） | 幀差 > `EDGE_FRAME_DIFF` 的原地幀 → STALLED、offset 不動、source `constellation:still` | ✅ 實測 |
| (2) | `test_the_lattice_falls_back_to_a_sub_window_when_the_band_runs_out_of_lines`（board） | 只剩右下有格線的幀：`read_lattice` None、`find_lattice` 讀得到且線位都在該窗內 | ✅ 實測 |
| (2) | `test_the_sub_window_lattice_is_only_a_fallback`（board） | 全幀帶讀得出來時 `find_lattice == read_lattice` | —（守成：pitch 不該由子窗決定） |
| (2) | `test_a_frame_whose_only_lattice_is_in_a_corner_still_gets_a_phase_check`（coverage） | 同一幀：`find_lattice` 換回 `read_lattice` 時判 STALLED（舊行為），本批判 BROKEN(phase) | ✅ 實測（測試自帶對照） |
| (3) | `test_a_merge_offset_the_commands_could_not_have_produced_is_refused`（coverage） | 南向平移的島收到橫向 400px 的 delta → 拒併、`refused` 遞增、島還在 | ✅ 實測 |
| (3) | `test_a_merge_offset_within_the_commanded_travel_still_goes_through`（coverage） | 界內的 delta 照併 | —（守成：合理範圍是上界不是等式） |
| (3) | `test_a_merge_that_lands_on_a_frame_that_never_moved_is_refused`（coverage） | 同一張幀當大陸與島：三欄位移的 delta 被畫面否決，零位移過關 | ✅ 實測 |
| (3) | `test_a_camera_jump_sideways_is_refused_and_the_world_restarts_honestly`（coverage，**改寫**） | 沒被推過的軸跳 512px → merged 0／refused ≥1／reset 1，重掃後格與格的相對關係一格不錯 | —（契約改變，見設計決定 8） |
| (4) | `test_a_frame_whose_grid_stops_partway_stamps_only_up_to_the_edge`（coverage） | 西側虛空的合成幀：`covered` ⊂ `readable`，切在線位上 | ✅ 實測 |
| (4) | `test_the_lattice_mask_only_cuts_the_sides_that_were_seen_to_end`（coverage） | edges={west,north} 只切左上；沒有 edges 時與 `readable` 相同 | ✅ 實測 |
| (4) | `test_a_frame_without_any_lattice_stamps_no_empty_but_keeps_the_sighting`（coverage） | lattice=None：零 EMPTY 章、零 charted，但目擊照記 UNIT | ✅ 實測 |
| (4) | `test_a_sighted_grid_edge_fixes_the_flag_without_waiting_for_a_stall`（coverage） | 目視定旗，`stalls` 全空 | ✅ 實測 |
| (4) | `test_a_sighted_edge_that_contradicts_the_flag_isolates_the_frame`（coverage） | 里程計整整錯兩欄 → BROKEN `edge_mismatch:west`、旗不動、進島 | ✅ 實測 |
| (4) | `test_a_bright_strip_beyond_the_last_line_is_no_edge_at_all`（coverage） | 同一個框：暗虛空出證言、亮填充不出證言 | ✅ 實測 |

### 既有測試的修改（三條）

1. `test_a_camera_jump_is_refused_then_re_anchored_by_the_constellation` →
   `test_a_camera_jump_sideways_is_refused_and_the_world_restarts_honestly`。
   舊測試注入「南向平移卻橫move 900px」的鏡頭跳走，期望島嶼靠已記目擊重錨。那正是
   (3) 要擋的東西（沒有指令推過的軸不會憑空跑出幾百 px），所以契約改成「拒併 →
   誠實重開世界，一格都沒寫錯」。合併成功的路徑改由空白幀那組（`blank=(18,20,22)`）
   守成——它照樣 merged 1。
2. `test_a_re_anchored_island_hands_its_offset_to_the_telemetry` 的替身從 jumps
   換成 blank（理由同上：那條軌跡現在不合併了）。斷言一字未改。
3. `islands` 的鍵集合斷言（coverage 一條、stage 一條）加 `refused`。

### fixture 擴充（`tests/fixtures/synthetic_map.py`）

- `blind_correlator(monkeypatch)`：相位相關信賴度歸零——單位排列比對的 fallback
  唯一會被叫到的路徑，影像複驗閘要在那裡受測。
- `animated(frame, step=4)`：整幀亮度抖一階＝待機動畫的合成版（位移零、幀差過門檻）。
- `void_outside(frame, box, seed, level)`：框外換成星空虛空；`level` 調亮就是
  「框外還是地圖」，供假邊界那一條。

**交辦單提醒的 fixture 限制屬實**：`World` 的鏡頭夾在畫布內，永遠不會自己渲染邊外
虛空，所以虛空一律由 `void_outside` 疊出來。另有一個幾何限制要記：`GRID_REGION`
高 530、合成世界的 `ROW_PITCH` 是 115，四列已經吃掉 460px，**不可能同時滿足
「≥4 條橫線」與「上下留得下一整格檢驗空間」**——所以合成幀只測得到 west／east 的
終止邊。north／south 的遮罩行為由 `test_the_lattice_mask_only_cuts_the_sides_…`
（手寫 view）覆蓋，實機端由第五節的 t7／t14／t30 目擊表佐證。

---

## 八、設計決定清單（自由裁量處逐條備案）

1. **逐精靈窗取代整區平均。** 備選是照交辦單字面做整個 MAP_REGION 的 masked
   mean-abs-diff。不取的理由是實測（第二節表）：整區版把三次真移動判成原地，而且
   分不開「真移動但票錯」與「原地」。逐精靈窗仍是「把 previous 依 delta 平移後與
   current 比平均絕對差」，只是取樣遮罩換成精靈窗、聚合換成逐窗投票。
2. **窗半徑 45（半格）、票門檻 0.8、最少 2 票。** 半徑要框得下精靈連同腳下環又不
   吃到隔壁那台；0.8 是「明顯低」的門檻（0.7 會讓 t3 的真移動掉到 unclear，實測）。
3. **`NULL_BLIND` 與 `NULL_UNCLEAR` 分開。** 見第二節末。備選是全部回 unclear
   並一律拒收——合成世界的整輪掃描會因此在空曠地帶反覆定位中斷（實測：整輪
   掃不完）。
4. **取樣窗中心限在 `MAP_REGION` 內。** 備選是用 `UNIT_DENSITY_REGION`
   （單位排列比對投票的同一批峰）。不取：卡條與畫面下緣那一帶的密度峰品質差，放
   進來會把 t24 這種本該 unclear 的幀投成 still（實測 4:6），而 still 是最強的
   那個裁決。
5. **`measure_pan` 判 still 時整條格線通道讓位。** 備選是仍走 `_resolve_columns`
   把 still 當一個候選。不取：畫面說沒動就沒有 k 好裁，硬走候選反而給了指令兜底
   （`WITNESS_COMMANDED`）一個把停滯寫成整欄位移的機會。
6. **象限窗只供 `_snap`／`rephase`，不供 `_anchor`／`measure_pan`。** 前者只用線位
   （相位是 mod pitch 的量，子窗一樣驗得了），後兩者要 pitch 與小數相位，取樣量
   不足會把錯的格距寫進世界。這也讓本批維持「只加閘、不改既有量測值」。
7. **`lost` 累加島內每一把平移，不只定位中斷那一把。** 交辦單寫的是「各 BROKEN
   平移的 expected」。實測合成迴歸（相關器凍結那一條）示範了為什麼不夠：島內的平
   移被判 STALLED 但實際移動了，那段位移沒進島的局部 offset，合併偏移必須補得回
   來，上界就得包含它。跨島嶼繼承的理由同構（新島沿用舊島的原點）。
8. **鏡頭往「沒被推過的軸」跳走 → 拒併 → 重開世界。** 這是既有測試的契約改變。
   取拒併：那個 delta 只可能來自單位排列比對遇上編隊 alias，而「量錯寫入」不准存
   在；重開世界的成本有界（一次全掃），寫錯格的成本是跨代永久的。
9. **合理範圍閘同時管撞邊釘軸解出來的 delta。** 備選是只管 `relocalise` 那條路
   （撞邊是絕對參考）。不取：釘軸本身也可能釘錯（邊界旗或邊緣格量錯），而物理上
   界對兩條路一樣成立。代價是釘軸的 delta 若超界就退回攢島。
10. **`islands.refused` 是新的遙測鍵。** 拒併與定位中斷是兩個問題（「斷了幾次」
    vs「擋掉幾次」），合成一個欄位下一輪就分不出。schema 斷言同步更新。
11. **格線遮罩只切有終止邊目擊的那幾側。** 見第六節末。備選（字面照做，切整個線位
    矩形）已量過代價：單幀 EMPTY 毯縮到四成。
12. **旗已定時目視邊對不上 → 隔離這一幀，不自動改旗。** 交辦單明定，這裡記理由：
    旗錯與 offset 錯當場裁不出來（旗跨代保留、offset 是這一幀的量測），自動改旗的
    代價是跨代永久的，自動改 offset 就是「量錯寫入」。備選是「多數決」（連續 N 幀
    目視邊一致就改旗）——那要新的狀態與新的失效模式，資料留給下一輪再議。
13. **目視定旗與撞邊定旗共用 `set_boundary`。** v2.5 的線外裁剪因此對兩條路一致
    生效（交辦單 e 點）。撞邊那條路保留當第二來源，沒有降級。
14. **終止邊的三道閘全是可量的。** 絕對高通上限 10、外側/內側高通比 0.5、亮度比
    0.75——都對著 0801 實幀標定（真邊外側高通 3.9-8.5 對內側 17.3-21.3；灰階
    26-34 對 43-52）。批 7 的星空假邊界前科就是只看單一絕對值。
15. **`FrameView` 多兩個欄位（`lattice`／`edges`）而不是新開一個型別。** 島嶼緩衝
    `shifted()` 用 `replace` 只動 offset，而遮罩是螢幕座標的量，天生不必跟著搬。
16. **`_view` 每幀多讀一次格線（`read_span`）。** `_snap` 已經讀過一次，兩者沒有
    共用。備選是把 span 從 `Odometer.feed` 一路傳出來——那要改 `Reading` 的形狀
    （量測層的裁決背上感知結果）。取多讀一次：一次 observe 多約 10ms，掃描一 tick
    兩次 observe，相對於 `PAN_SETTLE_S`（1.5 秒）可忽略。

---

## 九、爭點

1. **台數軸本批沒有量到。** 離線重放的最終台數（43）不是成績：重放的平移順序是
   舊碼
   規劃的，新碼中途重開世界之後不會重新規劃補掃。本批的證據只到「機制鏈的三顆
   齒輪各自被擋住了」（第五節逐 tick 對照＋單元迴歸），**台數是否收斂到 ≈28 必須
   實機一輪才判得了**。
2. **新閘把「寫錯」換成「定位中斷」，定位中斷換成世界重開的頻率會上升。** 重
   放裡 reset 2 次（舊碼 0 次）。世界重開＝那一輪全部重掃，平移次數保險絲
   （`LEG_BUDGET` 200）在單一回合內還撐得住，但實機一輪要盯 `islands.reset`
   與 `legs`。如果 reset 變成常態，下一批該做的是「開到最近已知邊歸零」那套
   steering（v2.2 就記過的更好復原路徑），不是放鬆閘。
3. **`_edge_clash` 在實幀上一次都沒觸發。** 它的正確性目前只有合成迴歸與「t3 vs
   t13 的西緣差 383px」這個間接證據。實機一輪要看 `reason` 有沒有 `edge_mismatch:*`
   ——**出現一次就是重大情報**（代表旗或 offset 有一個錯了），出現得太密則代表
   終止邊目擊的閘還不夠嚴。
4. **目視定旗會讓邊界旗定得早很多。** 實幀 t3 就看得到西緣。這是好事（早定旗＝
   早裁剪＝早收斂），但它也把「旗釘錯」的風險提前：`fix_boundary` 的線外裁剪是
   破壞性的（v2.5 設計決定 1）。目前的保護只有終止邊的三道閘。實機一輪要對照
   `boundary` 定案的 tick 與當時的畫面。
5. **`measure_pan` 的格線通道仍只吃全幀帶。** t11／t12 那兩把平移如果讓
   格線通道也用象限窗，很可能當場就量對了（單位排列比對這路佐證投 +220，
   `_correlator_credible` 會擋掉說謊的相關器）——但那會改到量測值，超出「只加閘」
   的授權。**建議列為 v2.7 候選**，要另附實幀證據與迴歸。
6. **`null_check` 對「編隊 alias 但畫面對得上」無能為力。** t33／t34 的 −244 票與
   逐精靈模板比對的 −63 票同時對得上畫面（週期陣列在畫面上就是自相似）。複驗閘只
   否決「對不上畫面」的票，整欄 alias 仍由 `_resolve_columns` 的三重裁決負責。
   這不是本批的漏洞，是分工——但它意味著**台數若仍膨脹，下一個嫌疑就是整欄 alias**。
7. **實機未驗證。** 本批純程式碼。要進 `docs/live-verification-queue.md` 的對帳項：
   - `survey_tick.shift.source` 出現 `constellation:still` 的次數與當下的 verdict
     （應為 STALLED）。
   - `reason` 出現 `phase` 的次數在北緣那一段應該明顯增加（象限窗補回相位閘）。
   - `islands.refused` 與 `merge.delta`：拒併一次就該有一列遙測，delta 的量級要與
     當時的單次平移距離對得起來。
   - `reason` 有沒有 `edge_mismatch:*`（爭點 3）。
   - `boundary` 各旗定案的 tick——目視定旗應該比撞邊早好幾把平移（爭點 4）。
   - `survey_summary.cells.unit` 對真值 28（爭點 1）。
