# Review 導覽：掃描 v2.10 量測佐證來源批（2026-08-01）

背景＝第 7 輪離線鑑識定讞（`data/runs/20260801-212645`，確定性重放 107 步位
元級一致）。結論是**致動沒有雙態**——53 把平移全部推動鏡頭 97-107%，沒推動畫
面的那幾把全是量測層的佐證來源不足。本批做鑑識報告的四件：**(C1) 單位排列比對
修票**、**(C2) 格網終止邊＝第三路佐證**、**(C5) STALLED 收緊**、**(C9) 遙
測儀器化**。

> **先看第六節（重放對照表）與第七節（爭點）**。對照表有一件與交辦單預期不
> 同：台數終值不是 30-45 而是 **4**，因為修正之後多了兩次世界重置——重置本身是
> 島嶼（定位中斷後位置不明的觀測暫存區，等重新定位才併回）重錨失敗的既有處置
> （C6/C7，本批明令不動）。**同一時點（t27-leg）的台數是 79 → 39**，那才是本批對
> 膨脹的實際效果；4 是重置砍掉的，不是量對之後只剩四台。

---

## Commit 全景

| commit | 工作 | 內容 |
| --- | --- | --- |
| `0b30526` | C1/C2/C5/C9 | `board` 三路佐證裁決＋`coverage` 停滯閘＋遙測；6 條新迴歸 |
| （本檔） | 文件 | 本導覽 |

四件為什麼同一個 commit：C9 的 trace 是穿過 `_constellation_shift`／
`_resolve_columns`／`_correlator_credible` 的出參，而那三個函式正是 C1／C2 改寫的
對象；C5 的閘要讀 C2 的 `lattice:edge` source。拆開的中間狀態編不出綠燈的樹。

閘門（親跑，worktree `agent-a9baad6fc3743b21c`）：

```
1599 passed, 4 skipped, 4 xfailed in 243.08s
All checks passed!            ← ruff check src tests scripts
```

基底 1593 passed／4 skipped／4 xfailed，本批 **+6 passed**（6 條新迴歸，無案例
被刪；3 條既有案例改寫，理由見第五節）。

---

## 一、執行順序（一把水平向平移的量測鏈）

```
Odometer.feed(frame, expected)
 └─ board.measure_pan(previous, current, expected, trace=detail)
     ├─ expected 沒有 x 分量 → measure_shift（precheck／縱向平移走這條，行為未改）
     ├─ read_span(previous) / read_span(current)      ★C2 改：原本是 find_lattice
     │    └─ read_lattice（全幀帶→四象限窗）＋ _terminal_edges
     │         └─ _edge_strips                        ★C2 改：外側帶不再受取樣帶約束
     ├─ _column_phase → frac（小數部分，mod pitch）
     ├─ _edge_shift(before, after, "x")               ★C2 新：終止邊佐證（絕對量）
     ├─ _phase_shift → (dx, dy, response)
     ├─ _constellation_witness
     │    ├─ _constellation_shift                     ★C1 改：seed-and-recollect＋一致性
     │    │    └─ _pairing_score                      ★C1 新：矛盾計數
     │    └─ null_check（票要先過影像複驗）
     ├─ 「確定沒動」× 終止邊 ≥40px → 兩個都不採信（source="none"）  ★C2 新
     └─ _resolve_columns(frac, pitch, expected, constellation, correlator, edge)
          佐證序：edge → constellation → phase → （都缺席才）commanded
          選的不是同一格 → None（誠實判定位中斷，紀律未改）
 ├─ 幾乎同一張幀 → _STILL
 ├─ envelope 閘（未改）
 ├─ _snap 相位閘（未改）
 └─ 量到 <40px 且有指令 → Odometer._still                ★C5 新
      ├─ source ∈ {still, constellation:still, lattice:edge} → 確定沒動 → STALLED
      └─ 否則 null_check(previous, frame, expected, reference=量到的值)
           NULL_STILL → STALLED；MOVED／UNCLEAR／BLIND → BROKEN(stall_<verdict>)
```

**沒有動到的**：`envelope`／`_snap`／`absorb`／`_sight_edges`／`_boundary`／
`_admits`／`relocalise`／`_edge_clash` 的島嶼路徑／指令兜底窗（C4，使用者待裁）。

---

## 二、(C1) 為什麼固定桶必須換掉

舊碼把每一對配對的位移量化成 `round(delta / 24)` 當桶鍵。桶邊界是絕對座標上的柵欄，
**容差內的兩個 delta 照樣可能落在柵欄兩側**：

| tick | 兩個真實配對 | 舊桶鍵 | 舊最高票 | 新（seed-and-recollect） |
| --- | --- | --- | --- | --- |
| t49 | (−129, 0)、(−130, +20) | (−5,0) vs (−5,+1) | 1 → 棄權 | 同一團，2 票 |
| t50 | (136, −11)、(125, +1) | (6,0) vs (5,0) | 1 → 棄權 | 同一團，2 票 |

鑑識報告的三個否決口統計：峰數 <2 七條、硬桶把最高票切成 1 八條、平手一條。本批
修掉中間那八條與最後那一條，第一條（畫面上真的不到兩台）不是投票法的問題。

新法：每一個 delta 當一次種子，收所有落在它 ±24px 內的 delta，收得最多的那一團勝，
取團內**中位數**（舊碼取平均，離群值會把答案拉走）。最高票並列時用
`_pairing_score`（雙向一致性）裁：配得上的對數減去「平移之後該落在偵測帶裡卻沒有
對應者」的單位數。t21 的實證是正解得 2 分、差一整欄的候選得 −3 分。

**代價**：`_constellation_shift` 從 O(n²) 變成 O(n⁴) 的比較數（25 台 → 625 個
delta → 39 萬次比較），用 numpy 的整數布林矩陣做，逐執行決定（不吃
`cv2.boxFilter` 那種平行分塊不決定性）。107 步重放整輪多不到 20 秒。

---

## 三、(C2) 終止邊是唯一的絕對量

三路佐證的性質不一樣：

| 佐證來源 | 訊號 | 會被什麼騙 |
| --- | --- | --- |
| 相關器 | 全幀灰階相位 | 格線週期（±92k 假峰）、靜態 HUD／地圖外星空背景搶峰 |
| 單位排列比對 | 單位環的相對配對 | 同型機編隊本身就是週期陣列（幀內縱距 90-96） |
| **終止邊** | 地圖的物理邊界 | ——非週期，上面兩種 alias 對它全部無效 |

### 為什麼舊碼看不到它

`_terminal_edges` 的三閘（外側安靜、暗、比內側安靜得多）本身是對的，出局的是那一
道**帶內含蓄假設**：`cols[-1] + pitch <= 取樣帶右緣` 才准出證言。第 7 輪那 18 對幀
的東緣落在 1697-1711，取樣帶到 1750——差一格的餘裕，於是東西震盪那一整段每兩幀只有
一幀出得了證言，同側邊在兩幀都讀得到的只有 1 條。

檢驗帶讀的是**原始像素**，取樣帶只是找脊的窗，兩件事。改成只受幀邊界約束之後，
逐幀實測（t49-precheck，取樣帶右緣 1750、cols[-1]=1708）：

```
外側帶寬 93（新）: beyond=(30.9, 5.6)  within=(48.2, 18.4)  三閘全過
外側帶寬 42（裁到帶內）: beyond=(39.5, 11.5) within=(48.2, 18.4)  三閘全不過
```

裁短的帶混進了地圖的最後 40px，統計值整個被拉高——**這才是舊碼那條假設真正在防的
東西，而防法應該是「帶要夠寬」不是「線要離帶緣夠遠」**。

「線到取樣帶緣為止、地圖其實還沒完」這個原本要防的情形由三閘自己擋：那種側的外側
是地圖紋理，安靜與暗兩閘都過不了（t52-precheck 的東側 cols[-1]=1738 就是這樣被擋掉
的，那一把平移修正後照舊誠實 BROKEN）。

### 邊這一路佐證的準確度（東西向 25 把平移，逐把實測）

| tick | 邊佐證量到 | 真值（R4 patch-track / R3 遮罩） | 差 |
| --- | --- | --- | --- |
| t36 | +152 | 158.5 / 164 | 6.5 |
| t37 | −176 | −182 / −184 | 6 |
| t38 | +183 | 189 / 192 | 6 |
| t39 | −175 | −183 / −184 | 8 |
| t40 | +166 | 173 / 176 | 7 |
| t41 | −172 | −180 / −180 | 8 |
| t42 | +181 | 188 / 188 | 7 |
| t43 | −175 | −180 / −180 | 5 |
| t44 | +167 | 172 / 176 | 5 |
| t45 | −175 | −181 / −184 | 6 |
| t46 | +183 | 188 / 192 | 5 |
| t49 | −124 | −128 / −128 | 4 |
| t50 | +120 | 123.5 / 124 | 3.5 |
| t53 | −266 | −271 / −272 | 5 |
| t17 | −200 | **見下** | — |

系統性偏小 3.5-8px（貼著取樣帶緣那一幀的最外一條脊會被 `_ridges` 的間距去重吃掉
幾個像素）。裁決容差是半個欄距（46px），偏差量在容差內，`_nearest_candidate` 挑得
出唯一候選。

**t17 是本批唯一一次邊佐證與 patch-track 真值不合**（邊佐證 −200，R4 中位數 −
105）。用不經任何脊機制的像素級量法定讞：列帶 y273-613 的行平均亮度，precheck 幀
在 x=628-640 由 19-27（虛空）跳到 86（格線），leg 幀在 x=429-440 跳到 69——**地圖
西緣確實從 ~640 移到 ~440，位移 −200，邊佐證是對的**。R4 的 −105 是編隊 alias（−
200 + 92 = −108），它的五票裡有兩票 −14（靜態 HUD）、一票 −195。這條反過來證實了
C2 的立論：非週期地標比精靈模板更抗 alias。

---

## 四、(C5) 停滯要有人指著畫面說沒動

第 7 輪六次 STALLED **六次都真的動了**，t13／t16／t25 的真實位移是 −172／−186／
+164——而 STALLED 照樣 absorb，那是「量錯寫入」紅線最直接的路徑，縱軸沒有相位閘
攔不住。

新閘：判 STALLED 前要有一個**指著畫面**的說法。三種算數（不必再問）：

- `still`：兩幀幾乎逐像素相同（`frame_difference < 2.5`）。
- `constellation:still`：排列比對的票已經被影像複驗判成「確定沒動」。
- `lattice:edge`：終止邊這個絕對地標量到 ~0。

都不是就當場複驗。**複驗的對手是「量到的值」不是「原地」**（`null_check` 新增
`reference`，預設 (0,0) ＝行為與舊碼逐字相同）：撞邊夾住只滑得動 20px 的幀，拿原地
當對手一定輸（環偏 20px 的窗差比對上另一塊背景還大），那不是「動了指令那麼多」的
證據。合成世界實測：

```
reference=(0,0)     moving(155)=35.44  staying=46.23 → moved   （誤判）
reference=(0,20.5)  moving(155)=35.44  staying= 0.00 → still   （正解）
```

**代價與補償**（寫進 `Odometer._still` 的 docstring）：稀疏區（鏡頭底下不到兩台）
真停滯會回 BLIND 而降 BROKEN，多繞一次島。真停滯最常發生在邊界上，而那正是終止邊
讀得到的地方，位移 ~0 時它名正言順給靜止證言，把成本吃回來——但**只在有邊的那一
側**，合成世界的 `test_a_camera_jump_sideways...` 就吃到一次 `stall_blind`。

---

## 五、(C9) 遙測欄位表

`data/runs/<時間戳>/dry_run.jsonl` 的 `survey_tick` 列新增：

| 欄位 | 內容 |
| --- | --- |
| `sequence` | 這一列對應的 `Survey.observe` 呼叫序號（從 1 起）——`merge.buffered` 的 join 鍵 |
| `span.sequence` / `span.box` / `span.edges` | 這一幀 `read_span` 的線位框與終止邊目擊 |
| `measure.path` | 走了哪一條：`lattice`／`phase`／`constellation`／`constellation:still`／`edge-contradicts-still`／`measure_shift:*` |
| `measure.span` | 兩幀的 box＋edges（量測當下讀到的，與上面那個 view 分開記） |
| `measure.frac` / `measure.pitch` | 格線相位的小數部分與欄距 |
| `measure.edge_x` / `measure.edge_y` | 逐側的終止邊讀數（`{"east": −124.0}`） |
| `measure.constellation` | `units`（兩幀峰數）、`top`（前三名 `[dx, dy, 票數]`）、`vote` 或 `veto`（`too_few_units`／`max_tally_1`／`tie`）、平手時的 `scores` |
| `measure.vote_null_check` | 排列比對票的影像複驗裁決 |
| `measure.correlator` | `dx`／`dy`／`response` |
| `measure.credible` | 相關器可信度的三分支值：`response`、`dx`、`difference`、`verdict` |
| `measure.window` / `measure.candidates` / `measure.spoken` | 合理範圍窗、窗內候選數、各路佐證所選的候選 |
| `measure.stall` | `{"source": …, "verdict": still/moved/unclear/blind}` |
| `merge.buffered` | 併進去的每一張 view 的 `{sequence, offset}` |

純觀察者紀律照舊：`trace` 是出參，`board` 那一側沒有任何裁決讀它；水槽炸了只記一次
警告，掃描照跑。

### 改寫的三條既有案例

1. `test_a_frame_whose_only_lattice_is_in_a_corner_still_gets_a_phase_check`：舊版
   在 survey 層斷言「`_snap` 放行 → STALLED」。`measure_pan` 改走 `read_span`
   之後，那個病癥在量測層就被攔下（BROKEN），survey 層看不到了——改成對
   `Odometer._snap` 直接斷言兩支（讀不到格線放行、象限窗讀得到就拒收）。
2. `test_a_camera_jump_sideways_is_refused_and_the_world_restarts_honestly`：
   `isolated == 1` 換成「envelope 造成的定位中斷恰好一次，其餘只准是 `stall_*`」
   ＋「那個 512px（四整欄）的編隊 alias 一次都沒被併進去」。理由是 C5 的已知代價
   會多一次 `stall_blind`，但那與「量到了卻閘不過」是兩件事，斷言要分得出來。
3. `test_a_merged_island_records_the_offset_it_was_merged_at` 與遙測欄位表：跟著
   `last_merge` 的形狀改。

---

## 六、離線重放對照表（合併的前提條件）

方法比照鑑識 `replay.py`：把 journal 的 `(frame, leg)` 序列重餵 `Survey.observe`，
修正前後各跑一次。修正前那一份與 journal 逐列位元級一致（0 mismatch），所以它就是
基準。

### ① 修正前 BROKEN 的 23 把平移

```
  t dir   before                     after                     measured            R4     agree   R3     cmd      source
  5 north broken/edge_mismatch:west  broken/edge_mismatch:west [-96.24, -17.09]   -17.0   4/9    -16     155.0   phase
  9 south broken/edge_mismatch:west  broken/edge_mismatch:west [ 96.28,  14.95]    14.0   2/9     16    -155.0   phase
 11 south broken/unmeasurable        broken/unmeasurable       [  0.0,    0.0 ]     3.0   3/15     4    -155.0   none
 14 south broken/unmeasurable        broken/unmeasurable       [  0.0,    0.0 ]   -13.0   8/16   -12    -155.0   none
 17 east  broken/unmeasurable        accepted/ok               [-199.0,   0.46]  -105.0★  2/5   -152    -350.1   lattice:edge
 21 east  broken/phase               accepted/ok               [-242.0,   0.51]   -57.0★  3/7   -184    -290.1   lattice:constellation
 29 north broken/unmeasurable        accepted/ok               [ -11.0, 154.5 ]   -23.0   7/17   -28     143.5   constellation
 34 north broken/unmeasurable        accepted/ok               [  -9.0, 156.0 ]   -26.0   5/11    64     155.0   constellation
 36 west  broken/unmeasurable        accepted/ok               [ 153.5,   0.51]   158.5   2/2    164     162.8   lattice:edge
 37 east  broken/unmeasurable        accepted/ok               [-176.5,   0.46]  -182.0   2/3   -184    -178.2   lattice:edge
 38 west  broken/unmeasurable        accepted/ok               [ 184.0,   0.43]   189.0   1/1    192     186.8   lattice:edge
 39 east  broken/unmeasurable        accepted/ok               [-178.5,   0.49]  -183.0   2/3   -184    -184.8   lattice:edge
 40 west  broken/unmeasurable        accepted/ok               [ 169.5,   0.52]   173.0   2/2    176     180.2   lattice:edge
 41 east  broken/unmeasurable        accepted/ok               [-174.0,   0.5 ]  -180.0   2/3   -180    -175.8   lattice:edge
 42 west  broken/unmeasurable        accepted/ok               [ 183.0,   0.47]   188.0   1/1    188     186.2   lattice:edge
 43 east  broken/unmeasurable        accepted/ok               [-174.0,   0.53]  -180.0   2/3   -180    -184.5   lattice:edge
 44 west  broken/unmeasurable        accepted/ok               [ 168.0,   0.48]   172.0   2/2    176     176.8   lattice:edge
 45 east  broken/unmeasurable        accepted/ok               [-176.0,   0.5 ]  -181.0   2/3   -184    -176.8   lattice:edge
 46 west  broken/unmeasurable        accepted/ok               [ 184.0,   0.47]   188.0   1/1    192     187.2   lattice:edge
 49 east  broken/unmeasurable        accepted/ok               [-122.0,   0.55]  -128.0   3/3   -128    -120.0   lattice:edge
 50 west  broken/unmeasurable        accepted/ok               [ 119.0,   0.49]   123.5   4/4    124     123.0   lattice:edge
 52 east  broken/unmeasurable        broken/unmeasurable       [  0.0,    0.0 ]  -119.5   3/4   -120    -120.0   none
 53 east  broken/unmeasurable        accepted/ok               [-264.0,   0.53]  -271.0   2/3   -272    -261.4   lattice:edge

救回 18 條，誠實 BROKEN 5 條
```

★ t17：R4 的 −105 已由像素級量法否定，真值 −200（第三節）。
★ t21：R4／大塊模板／全解析度掃描三路都指向 −58，本批量到 −242 —— **這是本批唯一
一筆新增的可疑寫入**，見爭點 1。

誠實 BROKEN 的 5 條：t5／t9 是既有的 `edge_mismatch:west`（旗與 offset 至少一個
錯，紀律不准當場改）、t11／t14 是縱向平移量不出來（沒有格線通道可走）、t52 的東緣
被取樣帶截斷（precheck 幀 cols[-1]=1738、帶緣 1750），三閘正確拒絕出證言。

t52 值得單獨記一筆：單位排列比對在新法下投出 (−121, −16)（3 票，真值 −
119.5，**投對了**），但影像複驗判 unclear 把它擋掉，於是整把回 none。那是既
有紀律（排列比對的票要先過複驗）的代價，不是本批新增的——舊碼在這一把平移連票
都投不出來。

**交辦單的期望是「≥15 條由邊佐證／修好的單位排列比對正確量出」——實得 18 條，其中
17 條與真值相符。**

### ② 六次 STALLED 全數不再寫進大陸（位置可信的權威知識圖那一側，相對於島嶼）

```
 13 south stalled/ok       → broken/stall_moved     shift=[0.18, -8.26]   R4=-8.0 (8/20)  R3=76
 16 south stalled/ok       → broken/stall_unclear   shift=[0.44, -0.97]   R4=-13.0 (3/9)  R3=-80
 18 east  stalled/ok       → broken/unmeasurable    shift=[0.0, 0.0]      R4=-114.0 (2/5) R3=-156
 23 north stalled/ok       → broken/stall_unclear   shift=[-0.74, 1.84]   R4=14.0 (0/6)   R3=-72
 25 north stalled/ok       → broken/unmeasurable    shift=[0.0, 0.0]      R4=-3.0 (6/16)  R3=-4
 35 north stalled/ok       → broken/stall_unclear   shift=[-0.11, 0.71]   R4=65.0 (0/8)   R3=64
```

t13／t16／t25 三條整列級量錯寫入全部關掉。t18 與 t25 走的是另一支、與 C5 無關：
t18 的單位排列比對三個候選各 2 票且一致性分數全是負的（`veto: tie`），t25 的
排列比對投出 (−11, 166) 但影像複驗判 unclear——兩條都在量測層就回 none，根本走
不到停滯閘。

### ③ 台數終值

| | 修正前 | 修正後 |
| --- | --- | --- |
| 全程峰值 | 85 | **39** |
| 同一時點 t27-leg | 79 | **39** |
| 終值 | 85 | **4** |
| 世界重置 | 1（t8，早期） | 2（t28-precheck、t38-precheck） |
| islands（isolated/merged/discarded/refused） | 23/8/14/1 | 12/7/5/9 |

**39 落在交辦單期望的 30-45 區間**（真值 ~28-29，C6 合併錯位未修所以到不了）。
終值 4 是兩次世界重置砍出來的：t23-t28 那座島 `_admits` 連拒 8 次、t35-t38 那座島
`relocalise` 一次都解不出偏移，兩次都燒完 `ISLAND_BUDGET=6` 走 `_abandon`。重置把
已測繪的地圖整張作廢、只留最後 16 個 tick 的東西震盪帶（150 格、4 台）。

**這是 C5 的直接後果**：舊碼把六次量錯的停滯照收，鏈子不斷，圖一路長到 85；新
碼誠實判定位中斷，島嶼路徑接不住，於是砍掉重練。島嶼合併機制（C6/C7）本批明令不
動，所以這個代價是**已知且預期的**，不是回歸。

### ④ 誤殺檢查（修正前 78 條 accepted）

| tick | 前 | 後 | 差 |
| --- | --- | --- | --- |
| t18-precheck | accepted/ok（`still`） | broken/`edge_mismatch:west` | 位移 0.0，裁決改變 |
| t24-leg | accepted [−4.75, 168.0] | accepted [−11.0, 160.5] | 7.5px |
| t28-leg | accepted [−7.5, 125.0] | accepted [−10.0, 135.0] | 10.0px |

其餘 75 條逐筆不變（位移差 < 5px 且裁決相同）。三筆的判讀：

- **t18-precheck**：C2 讓西側終止邊在這一幀出得了證言，於是 `_edge_clash` 發現它與
  已定的西旗差超過半格。那一幀的 offset 來自 t17 的島嶼合併 `(−91, 150.5)`，兩者
  至少一個錯——`_edge_clash` 的處置（兩個都不改、誠實隔離）本來就是為這種矛盾寫
  的。**不是誤殺，是新證言揭發的既有矛盾。**
- **t28-leg**：真值 R4 dy=128（21 票中 16 票同意，強）。舊值 125（差 3）、新值
  135（差 7）。新值與鑑識腳本 `truth.constellation`（同樣是 seed-and-recollect）
  的 137 同一族——差異是單位排列比對這個方法本身的性質，不是本批的錯，而且遠在半
  格容差內。
- **t24-leg**：真值 R4 dy=**7.5**（10 票中 7 票落在 7-8），也就是這一把平移**其實幾乎
  沒動**。前後兩版都量成 ~165（兩個列距的編隊 alias），影像複驗都判 moved 放行。
  **這是本批沒修到的既有缺陷**，見爭點 2。

---

## 七、爭點

**1. t21 量到 −242，三路真值指向 −58。** 修正後 t21 由 `lattice:constellation`
收下 −242。機制：舊碼的排列比對票是 (−236.8, −5.0)、影像複驗判 **still**，
於是整條格線通道讓位、`_snap` 拒收成 BROKEN(phase)；新法的票是 (−239.0, 0.0)
（5 個支持，最高票不並列），同一個複驗改判 **moved**，`_resolve_columns` 挑到
候選 −242。**複驗在這一幀是刀鋒上的**——票值只動了 2px，裁決卻整個翻面。但 R4
patch-track（−57/−58，3 票 0.98/0.98/0.79）、大塊模板（−58.5，6/6 同意）、全
解析度一維掃描（−58，0.925）三路一致指向 −58；一致性分數反而給 −245 最高分（2
分）。**這一幀的證據互相矛盾，我判不出誰對。** 邊這一路佐證在這一把平移缺席（西
側 cols[0]=239 貼著取樣帶左緣 150，地圖還往西延伸，三閘正確拒絕）。可能的收法有
兩條，都要使用者裁：(a) 一致性分數只當 tie-break、不當佐證來源（現況），(b) 讓
`_pairing_score` 也對**非平手**的排列比對票做一次否決（分數 ≤0 就不出證言）。(b)
會連帶影響 t29／t34 那兩把救回的縱向平移，所以我沒有自作主張。

**2. 縱軸的編隊 alias 沒有佐證來源可管（t24）。** 真值 7.5px 的一把平移被量成
165px，前後兩版皆然。縱軸沒有格線相位閘（列距隨 y 遞增，取模不是不變量），也沒
有 k 裁決，單位排列比對投什麼就是什麼；影像複驗在編隊週期上分不出 165 與 7.5。
C2 的邊佐證理論上治得了它（南北終止邊），但 t24 那兩幀只看得到東邊。**建議下一
批把 `_edge_shift(…, "y")` 接進 `measure_shift` 的縱向路徑當否決口**（本批只把
它接到 `measure_pan` 的 drift 兜底，因為交辦單把 C2 的範圍寫在 `measure_pan`／
`_resolve_columns`）。

**3. `_terminal_edges` 放寬的連帶範圍。** 這一改讓 22/107 幀多出終止邊證言（東緣
18 幀、北緣 4 幀），而 `view.edges` 同時餵給 `covered()`（EMPTY 毯的裁切）、
`_sight_edges`（定旗）與 `_clamped`（規劃層節流）。重放裡看得到的後果只有
t18-precheck 那一次 `_edge_clash`（見上），但**這是本批 blast radius 最大的一改**，
如果使用者要更保守，替代方案是給量測層一份獨立的、放寬的邊讀取，`view.edges` 維持
原判準——代價是兩套「終止邊」定義並存。我選了單一定義。

**4. 台數終值 4 而不是 30-45。** 已在第六節③說明成因（兩次世界重置）。要不要在
C6/C7 之前先給 `_abandon` 一條較軟的處置（例如保留已定的邊界旗與 charted 幾何），
待裁——本批照交辦單一行未動。

**沒有其他爭點。** 指令兜底窗（C4）依交辦單一行未動；島嶼合併三處
（`_admits`／`relocalise`／`_edge_clash` 島嶼路徑）一行未動。

---

## 八、還沒實機驗證的

本批全部是離線重放與合成世界。**要上機的是同一件事：跑一輪 `dry_run_entry`，看
`measure.edge_x` 在東西向平移的出席率**——重放用的是既有幀，實機的取樣帶邊界情形
（縮放倍率、地圖大小）會換一批數字。`measure.constellation.veto` 的分布也要看：
本批只證明了「硬桶那八條會回來」，沒證明實機新的一輪不會撞到別的否決口。
