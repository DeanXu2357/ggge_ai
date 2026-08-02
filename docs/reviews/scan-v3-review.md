# Review 導覽：盤面掃描 v3——位置一律來自畫面內容（2026-08-02）

規格＝`docs/survey-anchor-v3-proposal.md`（使用者核可版）。本批把「任何一張畫面的
位置只由畫面裡看得到的東西決定」貫徹到底：不再有「上一張位置加上這次的移動量」
這條累加骨架。

> **先看第六節（爭點）與第七節（設計決定）**。有三件與提案文字不同或超出提案範圍，
> 都列在那裡，其中「補中央的定位來源優先序反轉」影響面最大。

離線開發，**全程沒有碰實機**。實機第 8 輪驗收另排。

---

## Commit 全景

| commit | 工作 |
| --- | --- |
| `11f6422` | v3 骨架：`runtime/coverage.py` 重寫、`stage/survey.py` 接線、合成世界加虛空外圍 |
| `007459f` | 測試改寫到 v3 語意＋四條骨架迴歸、術語清理、本導覽 |

閘門（親跑，worktree `agent-a0b70753e1278d749`）：

```
1592 passed, 4 skipped, 4 xfailed in 236.42s
All checks passed!            ← ruff check src tests scripts
```

相對基底 `9d072c7`，測試檔淨少 60 個、淨增 32 個 `def test_`（多數是同一件事改寫成
v3 語意的重寫，不是純粹刪除）：整批消失的是島嶼、里程計、增益學習、釘軸與合併那幾
組——機制退場，案例跟著退場。逐檔對照見第八節。

---

## 一、一個 tick 的執行順序（`BoardDriver.survey_board`）

外層契約與 v2 完全相同：一次呼叫至多一個微步驟，`drivers()` 介面不變。

```
survey_board(action, observation)
 ├─ 還沒縮放 → _zoom() → 回 "zoom"（縮放改比例，整個世界作廢重來）
 ├─ _settled_capture()                     等畫面靜下來再收幀（未改）
 ├─ _read(precheck, leg=None, …)           → Survey.observe(frame)
 ├─ Survey.plan_leg()                      → 這一把往哪推；None ＝ 沒得推
 │    └─ None → "done"／"fuse"／"stuck"
 ├─ stance = Survey.stance                 ← 一定要在 plan_leg 之後讀
 ├─ _pan(leg, pick_pan_origin(...))        送出平移手勢（未改）
 ├─ _read(leg, leg, _settled_capture())    → Survey.observe(frame, leg)
 └─ 回 f"{stance}:{leg.direction}"         例：zero:west／tour:east／fill:north
```

微步驟名從 `sweep`／`blind` 換成 `zero`／`tour`／`fill`（`STANCE_STEPS`），
`done`／`fuse`／`stuck`／`zoom` 不變。流水帳讀者（`scripts/replay_run.py`）只吃通用
欄位，不必改。

---

## 二、一幀怎麼定位（`Survey.observe`）

```
observe(frame, leg)
 ├─ still = _unchanged(previous, frame, leg)      畫面到底有沒有動（只回布林）
 │    ├─ 兩幀幾乎逐像素相同                        → 沒動
 │    ├─ 相位相關量得到位移                        → 量到多少算多少
 │    ├─ 量不出來且沒有指令                        → **當作動過**
 │    └─ 量不出來但有指令 → null_check 判「確定沒動」才算沒動
 ├─ _tally(leg.direction, still)                  推不動的次數；連兩次記下夾點
 ├─ stance == zero → _zeroing(frame)
 │    ├─ 兩個方向都還沒連兩次推不動 → 回 ZEROING（一格都不寫）
 │    └─ 都推不動 → _anchor(frame, view)
 │         ├─ 角落那兩側一條終止邊都看不到 → 不敢認，退一步再來（ZERO_TRIES）
 │         ├─ 已有舊圖而角落與舊地標矛盾 → _forget()（整張作廢重來）
 │         ├─ 沒有舊圖 → read_lattice → WorldGrid.anchor
 │         └─ located = (frame, (0,0))；stance → tour
 └─ 否則 _place(frame, still)
      ├─ _locate(...)
      │    ├─ _from_landmarks(view, "x") / (…, "y")
      │    │    同軸兩側都看得到而差超過半格 → 丟棄（edge_mismatch）
      │    ├─ 兩軸都讀得到 → 座標定案（source=edge）
      │    ├─ _recall(...)  ← 只補讀不到地標的那一軸
      │    │    ├─ 畫面沒動且上一張定位成功 → 沿用它（source=still）
      │    │    ├─ _drift：跟最近一張定位成功的幀量重疊區位移（source=drift）
      │    │    └─ _constellation：單位排列比對回已記目擊（source=match）
      │    ├─ 直線軸沒有地標時走 _snap（格線相位交叉驗證＋吸附），對不上就丟棄
      │    └─ _corroborated：重疊區量到的位移要和候選座標對得上（半格內）
      │         量不出重疊位移時退回 null_check（只問「這個位移是不是根本沒發生」）
      ├─ 解不出來 → _discard()：unlocalised+1、知識圖一格不動、連丟三張推回角落
      └─ 解得出來 → chart.absorb(placed) → _learn_edges(placed) → located 更新
```

**地標**（`Survey.landmarks`）＝四側地圖終止邊的世界像素。定位成功的幀看到哪一側就
記哪一側；往後任何一幀看得到同一側，那一軸就是 `地標 − 它在螢幕上的位置`。第一次
記下就不再改。

---

## 三、階段機（`plan_leg`）

| 階段 | 推什麼 | 何時換階段 |
| --- | --- | --- |
| `zero` | 依序往西、往北，用得到的最大手指行程 | 兩個方向都連兩次推不動＋角落至少一側看得到終止邊 → 錨定 → `tour` |
| `tour` | 東 → 南 → 西，每側推到終止邊進畫面或連兩次推不動 | 三個方向都走完 → `fill` |
| `fill` | 朝待掃格聚類推（`_aim`），沒得挑就往還沒定界線的方向探（`_probe`） | 沒有待掃格且四面界線都定 → `plan_leg` 回 None |

`_aim` 算的是「把目標格**推進偵測帶**還差多少」（`_needs`），不是「離視野中心多遠」；
目標已在帶內卻仍是缺口＝壓在 HUD 挖洞底下，改算挪出洞的最小一步（`_escapes`）。
兩者都推不動才把那一格退休（`unreachable`，明寫進流水帳）。

---

## 四、保留／降級／退場對照（提案第三節）

**原樣保留**：單位偵測與密度峰、格線讀取（含象限窗）、地圖終止邊偵測（含 v2.10 的
邊緣位移量測）、HUD 挖洞、格子存在遮罩（EMPTY 要格線背書）、界線定案後裁剪界外
知識、同回合單位知識不因漏檢降級、跨回合衰效、四態知識圖與待掃格補掃、影像複驗、
平移手勢與取幀靜止閘、平移次數保險絲（`LEG_BUDGET`，單回合失控保險）。

**降級**：逐步位移量測鏈 → `_drift`／`_corroborated`，只在讀不到地標的那一軸補位，
而且要過格線相位與重疊區複驗。

**退場**：
- 定位中斷後位置不明的觀測暫存區（下稱島嶼）與整套重錨：`Island`、`ISLAND_BUDGET`、
  合併雙閘、與大陸（權威圖那一側）對質、`last_merge` 遙測欄。定位不出來就丟棄。
- 增益學習（`GAIN_*`、`_learn_gain`）：改用固定比例 `NOMINAL_GAIN`，只用來換算手指
  行程，不進座標。
- 推不動次數推論界線（`fix_boundary`／`edge_cell`／`_boundary`）：界線一律目視。
- `Odometer`：整個類別移除，由 `Survey.landmarks` ＋ `_locate` 取代。

**v2.10 三爭點**：單位排列比對退居補位（爭點 1、2 影響面大幅縮小）；島嶼合併一致性
複驗隨機制移除消滅（爭點 3 結案）。

---

## 五、契約與遙測

- `CoverageLedger`：`synced`／`generation`／`cells()`／`summary()`／`expire()` 不變。
- `SurveyPerceiver`：行為不變（敵方回合衰效一次、卡條走感知權威）。
- `Survey` 介面保形：`observe(frame, leg)`／`plan_leg()`／`complete`／`anchored`／
  `units()`／`summary()`／`expire()`／`reset()`。新增唯讀的 `stance`、`offset`、
  `landmarks`。**`anchored` 的語意變了**：v2 是「有沒有錨定過世界」（`chart` 不是
  None），v3 是「現在知不知道鏡頭在哪」（最近一張定位成功的幀還在不在）。敵方回合
  過後 `chart` 照樣在，但 `anchored` 是 False——那正是 v3 要表達的狀態。目前只有
  `summary()` 與測試讀它。
- 遙測（`BoardDriver._record`）鑑識主鍵保留：`tick`／`probe`／`sequence`／`verdict`／
  `shift`／`offset`。新增 `stance`；`measure` 更名 `locate`（內容換成定位的逐步自述）；
  `island`／`islands`／`merge` 隨機制退場。
- `summary()` 新增 `stance`／`zeroings`／`landmarks`，移除 `islands`。
  `scripts/dry_run_entry.py` 的收尾 log 跟著改。

---

## 六、爭點清單（請使用者／主 session 裁示）

1. **補中央的定位來源優先序與提案文字相反**（最該盯）。提案第四節寫「定位靠格線
   相位＋已記錄單位排列，重疊區影像比對消整數格歧義」。實作把**重疊區影像比對排在
   單位排列比對之前**。理由：合成世界實測，單位稀疏的地帶排列比對會被巧合配對投出
   68px 的偏差，連環丟幀導致整輪掃不完；而提案本身就指定影像比對為消歧義手段。兩條
   路互補未變——地圖以外那片無特徵的深色背景（下稱星空）重疊區量不出來時，仍由
   排列比對接手。**若使用者要求照提案的順序，改回一行即可（`_recall` 內兩個候選
   對調），但合成世界那個「地圖比螢幕高」的案例會退回「120 tick 掃不完」。**
2. **實機地標可得性存疑**（最該盯）。0719 那九張實幀裡只有兩張讀得到終止邊（皆為
   北側），其餘七張四側都讀不到。v3 的座標全靠地標，地標讀不到就退到補位那條路。
   實機第 8 輪必須先量「四個角落各推到底時，四側終止邊各讀不讀得到」——讀不到就得
   回頭調終止邊偵測或取樣帶，而不是調 v3 的骨架。
3. **`_needs`／`_escapes` 是提案沒有的抽象**（自創，提報待核准）。提案只說「朝缺口
   推」。實作改成「算差多少才進得了偵測帶」＋「壓在 HUD 挖洞底下就算挪出洞的最小
   一步」。理由：照原寫法在合成世界出現東西向來回各 100px 的活鎖，以及把暫時被回合
   橫幅蓋到的格當場退休（退休是跨代生效的）。
4. **敵方回合後固定回西北角，不是「最近的邊」**。提案寫「推到最近的邊重新歸零」，
   但敵方回合後鏡頭在哪本來就不知道，「最近」無從算起。改成固定西北角，換來的是
   跨代同一套世界座標（界線與地標不必重學）。代價是最壞情況多推幾把。
5. **`covered` 新增半格容差**。最外那一排格子的外緣就是終止邊，座標差幾個像素會把
   它整排切掉（合成世界實測 4px 誤差讓最南一列永遠蓋不到）。放寬的風險由界線定案後
   的裁剪收拾。這是 EMPTY 蓋章條件的鬆綁，請確認可接受。
6. **推不動要確認兩輪才能退休格子**（`bumped`）。提案把「推不動次數推論界線」列為
   退場，實作照辦（界線一律目視）；但規劃層仍留「推不動就別再往那邊推」的節流，且
   要兩輪才敢退休格子——連續兩把手勢被吃掉與真的到邊分不開，認一輪就封死會整欄退休
   （合成世界實測）。
7. **角落讀不出格網時的退一步重試**（`ZERO_TRIES=3`）。提案沒有規定。用完就
   `plan_leg` 回 None → `stuck`，該回合誠實掃不完。
8. **合成世界的虛空寬度是配著取樣帶挑的**（橫 600／縱 310），與實機幾何不同。它只
   保證「四側終止邊在各自角落都讀得到」這個性質受測，不代表實機比例。

---

## 七、設計決定（供併入 `docs/decisions.md`）

| 情境 | 選項 | 採用與理由 |
| --- | --- | --- |
| 敵方回合後從哪裡重新歸零 | (a) 推到最近的邊（提案文字）(b) 固定西北角 | **(b)**。敵方回合後鏡頭位置未知，「最近」算不出來；固定角落可重現，跨代回到同一套座標，界線與地標不必重學。 |
| 補中央讀不到地標時先問誰 | (a) 單位排列比對優先（提案文字）(b) 重疊區影像比對優先 | **(b)**。稀疏地帶的排列比對會投出數十像素的偏差導致連環丟幀；提案本身指定影像比對為消歧義手段。星空背景時仍退回 (a)。 |
| 地標與比對結果衝突 | (a) 整幀丟棄 (b) 地標供該軸、比對供另一軸，合起來複驗 | **(b)**。地標是絕對量，用它否決整幀等於連確定的那一軸也丟掉；合起來對不對由重疊區複驗裁。 |
| 「畫面沒動」量不出來時 | (a) 當作沒動 (b) 當作動過 | **(b)**。(a) 會讓空白幀被判靜止、沿用上一張座標，下一張真的動過的幀就以舊座標寫進圖（合成世界實測長出兩格鬼影）。 |
| 最外一排格子被座標誤差切掉 | (a) 照舊（整排退休）(b) `covered` 給半格容差 | **(b)**。最外一排的外緣就是終止邊，數像素誤差不該讓整排永遠蓋不到；線外的由界線裁剪收拾。 |
| 瞄準待掃格的方式 | (a) 對準視野中心（v2）(b) 算「進偵測帶還差多少」 | **(b)**。(a) 在一軸已在帶內、另一軸夾在邊上時來回空推。 |
| 格子壓在 HUD 挖洞底下 | (a) 當場退休 (b) 算挪出洞的最小一步 | **(b)**。洞在螢幕座標固定，鏡頭一動格子就出來；退休是跨代生效的，不該用單一鏡頭位置的事實決定。 |
| 退休格子前要幾輪確認推不動 | (a) 一輪 (b) 兩輪 | **(b)**。連續兩把被吃掉的手勢與真的到邊分不開，認一輪就封死會整欄退休。 |
| 比對標的要不要含前一代的目擊 | (a) 含 STALE (b) 只含這一代的 UNIT | **(b)**。STALE 是敵方回合之前的站位，那些機體早就動過了。 |
| 角落讀不出格網 | (a) 無限重試 (b) 退一步重試三次後誠實停下 | **(b)**。無限重試會把整回合燒在原地；停下來是誠實的失敗，流水帳看得到 `stuck`。 |
| 定位路徑上的地標矛盾檢查 | (a) 保留 (b) 只留在歸零那條路 | **(b)**。定位路徑上該檢查是死碼（座標本來就是從地標算出來的，必然貼合）；歸零那條路的座標是被定義的，才需要跟舊地標對答案。 |
| 合成世界要不要有虛空外圍 | (a) 地圖鋪滿畫布（v2）(b) 四周包虛空 | **(b)**。v3 的座標全從目視的終止邊解出來，假世界不給邊就測不到骨架。`board.py` 的像素測試保留 (a)（`margin=NO_VOID`）。 |

---

## 八、測試改寫對照

| 檔案 | 改動 |
| --- | --- |
| `tests/fixtures/synthetic_map.py` | 地圖四周包虛空、`margin` 參數、`corner()` 輔助；`centre()` 跟著位移 |
| `tests/test_runtime_coverage.py` | 全面改寫到 v3 語意；島嶼／里程計／增益／釘軸／合併整批案例移除 |
| `tests/test_stage_survey.py` | 微步驟名、遙測欄位集合、存證水槽的觸發時機（錨定之後才談定位） |
| `tests/test_runtime_board.py` | 像素案例改用無虛空世界；實幀回放改成「錨定得起來＋收不下的幀不亂寫」 |
| `tests/test_dry_run_entry.py` | `summary["islands"]` → `summary["stance"]` |

**新增的四條骨架迴歸**（交辦單要求）：

- 角落歸零：`test_the_world_is_anchored_by_pushing_into_the_corner_not_by_the_first_frame`
- 地標定位：`test_a_frame_that_can_see_a_landmark_reads_its_position_straight_off_the_picture`
- 丟棄不累積：`test_a_frame_nobody_can_place_is_dropped_whole_and_never_accumulates`
- 敵回合重歸零：`test_an_enemy_phase_sends_the_scan_back_to_the_corner_instead_of_re_anchoring`

外加本批實測抓到的兩條：`test_an_unmeasurable_frame_is_never_called_still`（鬼影
路徑）與 `test_a_cell_stuck_under_a_hud_hole_is_aimed_out_of_it_not_retired_on_the_spot`。
