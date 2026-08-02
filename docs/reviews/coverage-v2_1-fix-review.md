# Review 導覽：覆蓋模型 v2.1 缺陷修正批（2026-08-01）

基底 `feat/inner-goap` @ `747908b`。來源＝0731 深夜重審定讞的六缺陷（4 high），
四支復現腳本存在 `data/review-repros-20260731/`（gitignored，本批**未改動**它們）。

範圍只有 `src/ggge_ai/runtime/coverage.py` ＋ `tests/test_runtime_coverage.py`
＋本檔。符號層（`stage/survey.py`、`stage/actions.py`）與凍結層（`battle/`）一個
字都沒動——所有修正都在 `Survey`／`Island`／`KnowledgeMap` 的內部，沒有任何介面
被迫變動（唯一的簽名變更 `Survey._pin` 是私有方法，全庫沒有其他呼叫端）。

**設計決定清單在本檔第四節**，審過再由主 session 併進 `docs/decisions.md`。

## Commit 全景

| commit | 缺陷 | 內容 |
|---|---|---|
| `c2a3a3d` | 1＋5 | `expire()`／`reset()` 歸零 `legs`，`reset()`／`_abandon()` 清 `clamps` |
| `6436c7d` | 2 | `_whole_cells` → `_whole_columns`：只吸附欄，列保留量到的原值 |
| `3d5f41e` | 3 | 島嶼釘軸要連兩次停滯；pins 路徑加支持數複驗 `_agrees` |
| `01881b2` | 4 | 退休格改取聚類內離質心最近的成員格 |
| `da6a396` | 6 | `Island.sightings` 近鄰去重 |
| （本檔） | — | review 導覽＋設計決定清單 |

閘門（本 worktree 親跑，輸出見第五節）：`uv run pytest -q` →
**1517 passed, 4 skipped, 3 xfailed**；`uv run ruff check src tests scripts` →
**All checks passed**。

---

## 一、六缺陷的修正落點

行號對應本批 HEAD（`da6a396` 之後）的 `src/ggge_ai/runtime/coverage.py`。

### 缺陷 1（high）：legs 保險絲跨代累積

| 落點 | 改動 |
|---|---|
| `coverage.py:82-84` | `LEG_BUDGET` 註解改寫成「單一回合的上限」 |
| `coverage.py:572` | `Survey.expire()` 加 `self.legs = 0`（在 `chart is None` 早退之前） |
| `coverage.py:847` | `Survey.reset()` 加 `self.legs = 0` |
| `coverage.py:813-833` | `_abandon()` **不**歸零，理由寫進 docstring |

`expire()` 的歸零放在早退之前：還沒錨定的世界同樣每回合重開一輪掃描，沒有理由
讓它繼承上一回合的平移次數。

### 缺陷 2（high）：島嶼合併的列整格捨入

| 落點 | 改動 |
|---|---|
| `coverage.py:800-812` | `_whole_cells` → `_whole_columns`，y 直接回傳 relocalise 的原值 |
| `coverage.py:772` | `_solve()` 的呼叫點跟著改名 |
| `coverage.py:396-402` | `Island` docstring：「偏移必然是整數格」限定成**欄** |

x 仍然吸附整欄——那條保證來自 `_isolate()` 對島嶼種子做的 `rephase`（相位閘只
驗直線軸），跟這個缺陷無關，不能一起拿掉。

### 缺陷 3（high）：島嶼單次 STALLED 釘軸＋pins 繞過複驗

| 落點 | 改動 |
|---|---|
| `coverage.py:413` | `Island.stalls`（方向別停滯計數）新欄位 |
| `coverage.py:734-760` | `_pin(leg, reading, view)`：非 STALLED 清該方向計數，連 `STALL_CONFIRM` 次才釘 |
| `coverage.py:712-715` | `_reanchor()` 改成每一把平移都呼叫 `_pin`（不再只在 STALLED 時），非 STALLED 那條路徑才有機會清計數 |
| `coverage.py:761-773` | `_solve()`：pins 齊時先過 `_agrees`，過不了就 fall through 到 relocalise 並記一筆 warning |
| `coverage.py:775-798` | 新增 `_agrees()`：pins delta 平移島目擊，與 chart marks 逐軸半格容差配對計支持數 |

計數器掛在 `Island` 上而不是 `Survey.stalls`：島一丟棄就跟著滅，上一座島的停滯
不能拿來釘下一座島的軸。`Survey.stalls`（主圖邊界旗用）完全不受影響。

### 缺陷 4（high）：多格 pocket 的退休質心

| 落點 | 改動 |
|---|---|
| `coverage.py:551-553` | `_aim()` 退休格改成 `_nearest(pocket, target)`，一次一格 |
| `coverage.py:915-921` | 新增 `_nearest()`：歐氏距離最小，平手取 `(col, row)` 字典序最小 |
| `coverage.py:524-532` | `_aim()` docstring 補上「退休的一定是聚類成員」的理由 |

單格 pocket 的行為不變（`min` 在單元素序列上就是那一格）。

### 缺陷 5（medium）：clamps 跨重置殘留

| 落點 | 改動 |
|---|---|
| `coverage.py:831` | `_abandon()` 加 `self.clamps.clear()` |
| `coverage.py:846` | `reset()` 加 `self.clamps.clear()` |

`expire()` 不清：重錨成功時世界座標系是延續的，clamp 線仍然有效；重錨失敗會走
`_abandon()` 自然清掉。

### 缺陷 6（medium）：relocalise 支持數被重複目擊灌水

| 落點 | 改動 |
|---|---|
| `coverage.py:77-79` | 新增 `DUPLICATE_SPAN = 0.5`（格距的比例） |
| `coverage.py:415-429` | `Island.sightings` 改成貪婪近鄰去重，輸入先排序保證確定性 |
| `coverage.py:430-434` | 新增 `Island._merge_radius()` |

`KnowledgeMap.marks` 以格為鍵天然去重，chart 側不動。

---

## 二、呼叫鏈影響

沒有任何跨模組介面改變。受影響的路徑：

```
BoardDriver.survey_board()                       stage/survey.py（未改）
 ├─ survey.observe(frame, leg)
 │   └─ island 開著 → _reanchor(leg, reading, view)
 │        ├─ _pin(leg, reading, view)            ★缺陷 3：每把平移都進來，連兩次才釘
 │        └─ _solve()
 │             ├─ pins 齊 → _agrees(pinned)      ★缺陷 3：新的支持數複驗
 │             │    └─ island.sightings          ★缺陷 6：去重後的票數
 │             └─ relocalise(chart, island)
 │                  └─ _whole_columns(-drift)    ★缺陷 2：y 不再吸附
 └─ survey.plan_leg()
      └─ _aim() → chart.unreachable.add(_nearest(...))   ★缺陷 4：退休成員格

SurveyPerceiver.look() → ledger.expire() → Survey.expire()  ★缺陷 1：legs 歸零
BoardDriver._zoom()   → survey.reset()                      ★缺陷 1＋5
_reanchor 耐心用盡    → _abandon(island)                    ★缺陷 5
```

行為面的三個外顯差異，主 session 併回時值得盯：

1. **`summary()["legs"]` 每回合從 0 起算**。流水帳的解讀跟著變：跨回合累計要自己
   加總。`islands` 那四個計數器仍然是整場累計（沒動）。
2. **`_probe()` 的方向輪替以 `self.legs % len(open_flags)` 起算**，legs 歸零後每
   回合都從同一個方向起手。四旗全定之後 `_probe` 幾乎不會被叫到（`open_flags`
   為空回 None），衝擊限於首回合的錨定階段。
3. **島嶼重錨變嚴**：pins 路徑多一關、單次停滯不再釘軸。合成世界的既有整段行為
   測試（`test_a_camera_jump_is_refused_then_re_anchored_by_the_constellation`、
   `test_a_turn_boundary_downgrades_the_board_and_the_next_turn_re_anchors`）全數
   照過，但實機上有可能多花幾把平移才重錨、或多走一次 `_abandon` 全掃。
   **這是本批最需要實機複驗的一點。**

---

## 三、迴歸測試對應表

新增 11 條，全在 `tests/test_runtime_coverage.py` 檔末的「v2.1 缺陷修正的迴歸線」
區塊。**修正前逐條實跑過**：11 條裡 10 條在未修正的碼上失敗（見備註）。

| 缺陷 | 測試 | 行 | 斷言 | 修正前 |
|---|---|---|---|---|
| 1 | `test_the_leg_fuse_is_a_per_turn_ceiling_not_a_whole_battle_quota` | 534 | 合成世界連跑三回合，每回合都 `synced`、都沒 `fused`，`expire()` 後 `legs == 0` | FAIL |
| 2 | `test_a_half_row_island_offset_is_merged_as_measured_not_rounded_to_a_row` | 559 | 真值 (0,60) 的島偏移解回 (0,60)；合併後的世界像素與格座標都等於真值 | FAIL |
| 3 | `test_one_stall_never_pins_an_island_axis` | 578 | 一次 STALLED 後 `pins == {}`；第二次才寫入 | FAIL |
| 3 | `test_a_leg_that_actually_moved_starts_the_island_stall_count_over` | 594 | 停滯→真的動了→停滯，仍然不釘 | FAIL |
| 3 | `test_a_pinned_offset_still_has_to_agree_with_the_recorded_sightings` | 606 | 釘錯的 (0,0) 被複驗擋下，改走 relocalise 得 (0,60) | FAIL |
| 3 | `test_pins_stand_on_their_own_when_the_island_saw_nothing_to_contradict_them` | 619 | 島上零目擊時 pins 單獨成立（**守成測試**，修正前後都過） | pass |
| 4 | `test_a_retired_target_is_always_a_cell_of_the_pocket_itself` | 655 | 退休格 ∈ pocket；EMPTY 質心 (1,1) 不入 unreachable；同一次 `plan_leg` 就挑到別團＝沒有活鎖 | FAIL |
| 4 | `test_a_pocket_no_camera_position_can_expose_retires_cell_by_cell_and_stops` | 671 | 四向全夾死時逐格退休直到 `complete`，且**不是**靠燒斷保險絲停下來 | FAIL |
| 5 | `test_a_clamp_line_from_the_old_world_never_survives_into_the_new_one` | 683 | `reset()` 後 `clamps == {}`、新世界走到 3210 不被誤判夾住 | FAIL |
| 5 | `test_abandoning_an_island_drops_the_clamps_but_keeps_the_leg_fuse` | 698 | `_abandon()` 清 clamps、**不**清 legs | FAIL |
| 6 | `test_one_unit_seen_in_three_overlapping_views_only_votes_once` | 630 | 兩台實體（其一被三個重疊 view 各看一次）去重成兩點，`_solve()` 回 None | FAIL |

備註：唯一修正前就過的是缺陷 3 的守成測試，那條本來就是「這個行為不准被新的
複驗誤殺」的護欄，不是缺陷的復現。

四支復現腳本在修正後的碼上重跑：

- `repro1_legs.py`：11 回合的 legs 由 16/26/34/…/106（單調累積）變成
  16/10/8/10/8/…（每回合各自從 0 起算，穩定在 8-10 把平移）。每回合仍然
  `synced`，`steps_tail` 與修正前逐回合相同——`_probe` 方向輪替的起點變動沒有
  外顯影響。
- `repro3_solve.py`：3a 的 merged y error 由 **−50px → 0px**；3b 的
  `island.sightings` 由三點 → 一點；3c 因 `_pin` 簽名改變而 TypeError（腳本是
  存檔證據，依指示未改）。
- `repro4_stuck.py`：4a 退休 `(1,0)`（∈ pocket）且第一次 `plan_leg` 就拿到往西
  一把平移、`legs` 前進；4b `reset()` 後 clamps 空、`_clamped("east")` 為 False。
- `repro2_ydrift.py`：**修正前後都印 ok**（見第六節爭點）。

---

## 四、設計決定清單（自由裁量處逐條備案）

1. **`expire()` 的 legs 歸零放在 `chart is None` 早退之前**。備選是放在早退之後
   （只有已錨定的世界才重置）。取前者：還沒錨定就是連格網都讀不到，那一回合更
   需要完整的平移次數額度。
2. **`_abandon()` 不歸零 legs，但清 clamps**。指示明寫不歸零 legs；clamps 一起清
   是因為 `_abandon` 會 `_anchor` 到當下這一幀，世界原點換了，舊的世界座標值失去
   意義——跟 `reset()` 同一個理由。
3. **`_whole_cells` 更名 `_whole_columns`**。備選是留原名只改行為。取更名：名字
   說「整格」而只做一軸，是下一個讀者踩坑的地方；私有方法無外部呼叫端。
4. **島嶼停滯計數放在 `Island.stalls`，`_pin` 簽名比照 `_boundary` 收 `reading`**。
   備選是放 `Survey` 上另開一個 dict，或在 `_reanchor` 內做計數只讓 `_pin` 保持
   「純寫入」。取前者：島丟棄即滅是這個計數器唯一正確的生命週期，而與 `_boundary`
   同形讓兩條停滯規則擺在一起就看得出是同一條。
5. **`_agrees` 的容差取逐軸半格**（`col_pitch/2`、`row_pitch/2`），不是
   `board.CONSTELLATION_TOLERANCE`（24px）。指示建議「半格」；逐軸而非歐氏是因為
   兩軸的格距不同（實機 128 vs 108-123）。
6. **`_agrees` 的門檻直接用 `board.RELOCATE_MIN_SUPPORT`**，不因島上目擊數少而
   放寬。備選是 `min(3, len(island.sightings))`。取前者（＝指示的「relocalise 同款
   門檻」）：放寬等於允許「一台單位背書一次重錨」，正是這個模型不准存在的路徑。
   代價寫在爭點 (2)。
7. **`_agrees` 在「島上零目擊」或「權威圖零目擊」時回 True**。指示只寫了前者；
   後者同理——權威圖沒有 marks 就沒有可矛盾之物，硬要複驗會讓空曠地圖永遠釘不了。
8. **pins 複驗失敗時 fall through 到 relocalise，不是直接回 None**。指示兩者皆可。
   取 fall through：pins 錯不代表星座也錯，多一條路能重錨就少一次全掃。
9. **`_nearest` 的距離用格空間歐氏平方，平手取 `(col, row)` 字典序**。備選是用
   `grid.centre_of` 的像素距離。取格空間：pocket 成員本來就是格，像素距離只是同一
   個排序乘上格距（非等比時才有差，而那個差沒有意義）。字典序 tie-break 讓同一個
   盤面每次退休同一格——退休是跨代生效的事實。
10. **一次 `_aim` 只退休一格**。備選是把整個 pocket 一次退休。取前者：`plan_leg`
    的迴圈上界是 `len(targets)+1`，逐格退休就保證嚴格縮小且會終止；整團退休則可能
    把「剛好推得到的那幾格」一起誤殺。
11. **去重半徑＝`0.5 × min(col_pitch, row_pitch)`**，取兩軸較小者。備選是逐軸各用
    自己的格距。取 min：同一台實體在不同 view 之間的差只有里程計的量測小數（幾個
    px），半格是很寬的護欄，沒必要為此多一個維度。
12. **島嶼沒有格網時去重半徑退回 `board.CONSTELLATION_TOLERANCE`**。備選是不去重。
    取前者：不去重＝缺陷在該路徑上原封不動地留著。實務上 `_isolate` 建的種子一定
    帶著 chart 的格網，這條只是不留無防護的分支。
13. **去重每簇保留字典序最小的一點**（先 `sorted` 再貪婪掃）。備選是取簇心平均。
    取前者：確定性最直接，而且保留的是真的量到過的一個點，不是合成出來的座標。
14. **`DUPLICATE_SPAN` 提成模組常數**而不是寫死在 `_merge_radius` 裡，跟
    `STALE_WEIGHT`／`STALL_CONFIRM` 同一個位置與註解密度。
15. **不動 `board.RELOCATE_MIN_SUPPORT`**。缺陷 6 是「票怎麼數」的問題，門檻本身
    在去重之後才第一次拿到它宣稱的語意，沒有理由同時改兩個變因。

---

## 五、閘門輸出（本 worktree 親跑）

```
$ uv run pytest -q
1517 passed, 4 skipped, 3 xfailed in 202.23s (0:03:22)

$ uv run ruff check src tests scripts
All checks passed!
```

基底 `747908b` 在同一個 worktree 的數字是 1506 passed, 4 skipped, 3 xfailed；
本批 +11 條全部來自新的迴歸線。

---

## 六、爭點

1. **`repro2_ydrift.py` 不是缺陷 2 的判別性證據。** 它在修正前後都印 `ok`：合成
   世界那半列位移在島嶼里程計裡已經被吃掉一部分，捨入前後解出來的 delta 落在同一
   格內，格座標比不出差別。缺陷 2 真正的判別性證據是 `repro3_solve.py` 的 3a
   （merged y error −50px → 0px），迴歸測試也是照 3a 的形狀寫的。**要不要為它補一
   條會在實機重現的端到端案例，請主 session 裁示**——目前的合成世界（`World.move`
   夾在畫布內、格距固定 115）造不出「島嶼 y 偏移穩定停在半列」的情境。

2. **缺陷 3 的支持數門檻對稀疏盤面偏嚴。** 島上只有 1-2 台單位、鏡頭兩軸都夾死時，
   pins 本來是唯一能重錨的路徑，現在會被 `_agrees` 擋下 → relocalise 也湊不到三票
   → `_solve()` 回 None → 攢滿 `ISLAND_BUDGET` 走 `_abandon` 全掃。這是「誠實但貴」
   的取捨，符合模型的立場，但**成本要在實機上量過才知道能不能接受**（決定 6）。

3. **實機未驗證。** 本批純程式碼，沒碰過裝置。需要排進
   `docs/live-verification-queue.md` 的項目：
   - 多回合戰鬥（≥4 回合）確認每回合 `board_synced` 都達成、流水帳的
     `survey.legs` 每回合從 0 起算。
   - 敵回合過場之後的島嶼重錨次數與 `islands.reset` 計數，對照修正前的流水帳，
     看嚴格化有沒有把重錨成功率壓下去（爭點 2）。
   - 最小縮放下 y 軸雙向夾死時的退休行為：確認退休格逐格出現在流水帳、
     `unreachable` 只長不亂跳，且掃描不再停在 `stuck`。
