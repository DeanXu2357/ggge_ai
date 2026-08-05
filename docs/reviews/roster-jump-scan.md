# Review 導覽：名冊跳轉掃描

批次目標：sweep 不再全圖推鏡找單位，改用戰鬥選單「部隊資訊」的名冊逐台「選擇」跳轉
鏡頭，配合星座／邊界重認把落點掛回世界座標。

## 檔案

| 檔案 | 角色 |
| --- | --- |
| `src/ggge_ai/runtime/screens.py` | 新增 `BATTLE_MENU`／`TROOP_INFO` 兩個畫面名與簽名 |
| `assets/templates/elements/label_battle_menu.png`、`label_troop_info.png` | 標題字模（0806 實幀裁） |
| `src/ggge_ai/runtime/roster.py` | 新：列表格座標產生器＋詳情頁讀值（兩種佈局） |
| `src/ggge_ai/runtime/jumpscan.py` | 新：目標鎖定／記帳／共現複核／排程／解除點挑選 |
| `src/ggge_ai/runtime/device.py` | 新增 `weapon_dial` 危險帶；`DangerBand.intents` 改成多值白名單，`roster_cell`／`roster_jump` 放行面板底下的假重疊 |
| `scripts/scan_roster_jump.py` | 新：組裝腳本，四段停點 |
| `tests/test_roster_jump.py` | 新：roster＋jumpscan 的離線測試 |
| `tests/test_runtime_screens.py` | 三張面板的分類 case 與互不搶案 |
| `tests/fixtures/vision/panels/*`、`tests/fixtures/vision/roster/*` | 新 fixture |

## 呼叫鏈與執行順序

`scripts/scan_roster_jump.py::Scan.run()` 四段：

1. **borders** — `entry.select_stage` → `entry.open_sortie_prep` → `entry.enter_stage`
   → `Scan.prepare_board()`（`entry.confirm_grid` 把顯示方格翻到 ON 並以地圖上讀不
   讀得出格網為唯一判準；`Scan.collapse_roster()` 讀 `screens.read_roster_strip`
   再決定要不要點 `screens.ROSTER_TOGGLE_TAP`，讀不出來就停手不盲點）
   → `Scan.pan()`（`board.pan_stroke`／`board.pan_gesture`）往西、
   往北各推到界出現，`sweep.read_borders` ＋ `board.find_lattice` ＋
   `sweep.anchor_northwest` 定義世界原點。**東界與南界不在這裡量**（見裁量 9），
   `landmarks` 出場只有 `west=0`／`north=0`，其餘由 jump 段機會主義學。
2. **roster** — 對我軍／敵軍各走一次：`entry.BATTLE_MENU_TAP` →
   `roster.BATTLE_MENU_TROOP_INFO_TAP` → `roster.TAB_TAPS[faction]` →
   逐格 `roster.cell_taps(faction)` → `Scan.open_detail()`（輪詢 `screens.classify`，
   讀到 `unit_detail` 立刻回幀；連續兩輪 `troop_info` 才算列表盡頭，輪詢用盡且兩者
   都不是才 Halt）→ `roster.read_detail()` → 存幀 →
   `roster.DETAIL_CLOSE_TAP`。收工 `roster.TROOP_INFO_CLOSE_TAP` ＋
   `entry.BATTLE_MENU_CLOSE_TAP`。名冊落 `roster.json`。
3. **jump** — `jumpscan.next_target()` 挑下一台 → 同一條開列表的路 →
   `roster.DETAIL_SELECT_TAP` 跳轉 → 落點幀 `board.find_units` ＋
   `jumpscan.target_peak()` 鎖目標 → `Scan.dismiss()`（敵＝`jumpscan.blank_cell_tap`
   挑空白格；我＝`jumpscan.ALLY_DISMISS_TAP` 帶 `intent="ally_dismiss"`）→
   乾淨幀 `Scan.locate()`（`sweep.constellation_offset` 優先、`sweep.border_offsets`
   墊底）→ `grid.cell_of()` 定格 → `JumpLedger.record()`。星座解出來的那一刻順手
   `Scan.learn_landmarks()` 補地標。解不出來 `JumpLedger.fail()`，該台退到佇列尾端
   換下一台；同一台連兩敗才退場記 UNRESOLVED。整份名冊輪完仍零已解就 Halt。
4. **settle** — `jumpscan.audit()` 共現對複核 ＋ `jumpscan.ledger_report()` →
   `coords.json`；預設 `entry.abandon_battle` 收尾。

## 量出來的關鍵常數（0806 實幀）

- 面板標題帶 `PANEL_TITLE_REGION = (1040, 65, 290, 58)`，六幀量到標題字 y 75-110
  逐幀一致；三個標題互比最高 0.405，門檻 0.85。
- 列表格距：`CELL_X0=729`、`CELL_X_PITCH=278.5`、`CELL_Y0=267`；我軍列距 245.7
  （兩列各 5），敵軍列距 193.4（四列各 5，末列不滿）。
- 詳情頁數值：`runtime.glyphs.read_int(..., ink=Ink.DARK)`（panel 字模，七個欄位
  信心 0.912-0.985）。敵方 `hp=(1180,149,155,34)`、`en=(1180,213,155,32)`、`mobility=(1250,285,85,35)`；
  我方多一列 LV，整體下移：`lv=(1180,158,155,35)`、`hp=(1180,217,155,32)`、
  `en=(1180,280,155,33)`、`mobility=(1250,352,85,35)`。
  移動力欄必須從 x=1250 起算——標籤「移動力」右緣壓到 1205。
- 陣營帶 `(1125, 325, 165, 115)`：敵方 red 0.214／blue 0.000，我方 red 0.061／
  blue 0.287，門檻 0.10 取 argmax。
- 「選擇武裝」大圓鈕鈕心約 (2085, 971) 半徑約 140；「返回」鈕心 (1798, 971)、
  右緣約 1868。

## 裁量決定

1. **「單位設置詳情」不新增畫面名。** 既有 `screens.UNIT_DETAIL` 的模板
   `elements/unit_detail_modal.png` 就是「單位設置詳情」標題字，兩張 0806 詳情幀
   `classify()` 本來就回 `unit_detail`（分數 1.000）。任務描述說它是 unknown 與實測
   不符，所以只補 `battle_menu`／`troop_info` 兩個，並加一個 case 釘住新簽名沒把
   `unit_detail` 搶走。
2. **三張面板同 group 1**（與 `UNIT_DETAIL_SIGNATURE` 同層）。它們都是蓋在地圖上、
   在系統彈窗之下的全螢幕面板，同層比 argmax 正是既有規則。
3. **manifest.yaml 不補條目。** `screens.py` 的字模一律不走 manifest（`label_*.png`
   全部都不在裡面），`tests/test_template_manifest.py` 也只吃合成資料，補了反而破壞
   既有慣例。
4. **`weapon_dial` 危險帶切在 y≥960 而不是鈕上緣 831。** 上面那一段跨畫面是關卡列表
   「出擊準備」(2035,880) 與應戰「行動選擇」確認 (2042,924)，整顆蓋下去會擋掉既有
   流程。返回鈕 (1798,971) 落在帶外（右緣 1868 < 1945），所以帶不放行任何 intent；
   `jumpscan.ALLY_DISMISS_INTENT` 保留只是讓那一下在流水帳裡自我說明。
5. **名冊面板底下的危險帶假重疊用 intent 放行，不改帶的幾何。** 部隊資訊是全螢幕
   面板，帶內的鈕在面板開著時根本點不到：我軍／敵軍首列第 4、5 格 (1564,267)、
   (1843,267) 落在 `auto_battle_tristate`，敵軍第 4 列第 1 格 (729,847) 落在
   `battle_menu_abandon`，詳情頁跳轉鈕 (1372,995) 落在 `auto_deploy`。裁量是給前兩者
   `roster_cell`、給跳轉鈕 `roster_jump`，兩個 intent 只由「面板已開」的呼叫點發出；
   地圖裸露時的格點擊（sweep 的清算點擊）照舊不帶 intent，一律擋。縮帶不可行——帶
   的幾何對應的是別的畫面上真的存在的鈕。
6. **`next_target` 的「候選格」由呼叫端餵。** 落點幀看到的其他峰無法直接歸屬到某一
   個名冊序號（列表順序與地圖位置沒有已知對應），所以模組只提供
   `JumpLedger.hint(key, cells)` 這個入口，排程只問「這一台有沒有候選」，不自己發明
   歸屬規則。目前腳本尚未餵任何 hint——實際排序等於「名冊順序＋敗了就換下一台」
   （見裁量 10）。
7. **`audit` 用投影複核而不是比對世界格差。** 直接比世界格差是循環論證（兩邊都是同
   一組 offset 算出來的）。改成把 B 的最終世界格投影回 A 的窗，窗內就該有一個峰；
   沒有＝至少一台錯。雙向都會各記一筆。
8. **空白格挑「離畫面中心最遠的乾淨格」，但先過 UI 遮罩**：貼著目標點下去等於在
   紅格裡賭；而「最遠」天生指向四角，四角全是疊在地圖上的 UI。0806 實機
   run `20260806-034815` 挑到 (2238,1011)——壓在右下「單位列表」鈕上（點了會展開卡條，
   之後每一幀的 `find_units` 都被污染），被 device 的 `weapon_dial` 危險帶攔下才發現。
   修法是 `jumpscan.UI_EXCLUSION_ZONES`（六個螢幕座標矩形：頂部狀態帶、右上
   AUTO／快進／☰、左上單位資訊卡、左側回合結束／變更配置、左下訊息列、右下單位列表鈕，
   量自 `assets/screenshots/20260806-013329.png` 與 `20260806-013000.png`），候選格心先
   過遮罩再比距離；濾完沒有候選就記 `no_blank_cell` 進流水帳並 Halt，不退回遮罩裡撿。
   **遮罩之外再問一次危險帶**：帶的範圍比可見鈕大（帶要包住鈕在各畫面的所有位置），
   0806 第五輪 run `20260806-040912` 挑到 (2199,260)——遮罩放它過了，`auto_battle_tristate`
   帶擋下來。逐一補遮罩去追帶的形狀是沒有盡頭的，所以候選改成直接問
   `device.blocked_for_map_tap`（無 intent 視角＝地圖裸露時可不可點，帶就是那條線的
   權威定義）。`sweep._tap_blocked` 也改成呼叫同一支，兩邊不再各寫一份。
   **目標鎖定不套這個遮罩**——`target_peak` 吃的是 `find_units` 的密度峰，不是我們發出的
   tap，UI 覆蓋與否不影響它是不是目標。
   格心的螢幕位置用**落點幀自己的格線相位**（`board.find_lattice` ＋
   `WorldGrid.anchor(lattice)`，offset 給 (0,0)）算，不用 `self.offset`——解除必須發生
   在 `locate()` 之前（紅格會污染密度峰），那時手上根本沒有這一幀的世界鏡位，
   `self.offset` 還停在西北角那一幀。
9. **東南地標改由 jump 段學，borders 段不再量。**
   `reach_border()` 原本用 `borders[side] + self.offset[axis]` 換算世界像素，但那一段
   完全沒有追蹤推鏡位移，`self.offset` 還是西北角定錨時的值——0806 實機
   run `20260806-022510` 因此記到 `east=1717` / `south=409`，而真值地圖 25x20、
   `col_pitch=129`，東界該在 ~3200 世界像素。錯的地標比沒有更危險：jump 段單側看到
   東界時 `sweep.border_offsets` 會拿 `1717 - 螢幕x` 當鏡位直接用。改法是砍掉那兩趟腿
   （順便省時間），改在 `Scan.learn_landmarks()` 補：**只吃星座裁決出來的 offset**
   （拿界線解出的 offset 回頭寫界線是循環論證），已有的側不覆寫、只做
   `EDGE_AGREEMENT_PITCH` 一致性檢查，對不上記 `landmark_conflict` 進流水帳。
10. **開機保護取保守版（換一台），不做「推鏡途中追蹤目標」。**
   第一台跳過去時 `ledger.references()` 是空集合，星座必然解不出；若落點又看不到界，
   就沒有任何證人。協調端提的另一個方案是推到界再用逐把平移的名義行程回推目標格——
   評估後不採用：目標在推鏡兩三把之後就出視野，回推只剩手勢名義量可用，而本專案
   0804 起的定則就是**手勢的量完全退出定位**（`coverage.Leg.expected` 的註解寫死
   「不進座標計算」）；為了開機而破例，等於把整條鏈的根建在最不可信的證據上。
   保守版改成 `next_target` 以「敗過最少次」排序：一敗就換下一台，換一台就換一個
   落點，整份名冊輪過一輪都零已解才 Halt。代價是最壞情況多跳一輪，換來根節點永遠
   由強證人（星座或界線）背書。
11. **讀值用 `runtime.glyphs` 而不是 `vision.digits`。** 任務指定的
   `vision/digits.read_number` 會踩 `tests/test_package_boundary.py`（runtime 不得
   import 凍結包 `vision`）。`runtime.glyphs.read_int` 的 panel 字模在這七個欄位上
   讀數與 `read_number(invert=True)` 完全一致（29265/424/4、55/38311/148/5）。

## 相對星座鏈（0806 第六輪之後）

絕對解起不了頭：run `20260806-042858` 四段全跑通，28 台只解出 1 台，48 筆 lost 全是
`constellation few_units`——參考集起步 0~1 台，`constellation_offset` 的 `min_match`
永遠不滿足，而邊界解只在落點剛好看得到界時成立。改成不需要世界 offset 的相對鏈：

- `jumpscan.frame_pattern(grid, peaks, target)` → `Pattern`：用**落點幀自己的**格線
  相位（`WorldGrid.anchor(find_lattice(frame))`）把每個峰對到幀內格，全部減掉目標峰
  的格。同時記 `window`（這一窗看得到的格範圍，同樣相對目標）。
- `jumpscan.match_patterns(a, b, *, min_overlap=2, margin=1)` → `PatternMatch`：候選
  平移取 a 的峰，判準是**重疊區內全覆蓋**（重疊區＝兩窗 window 相交、四邊各內縮
  margin 格），唯一解才收，兩個以上 ambiguous 拒收。回傳的 `delta` 是「b 的目標落在
  a 的座標系哪一格」。
- `jumpscan.propagate(anchors, edges, *, nodes)` → `ChainSolution`：錨點沿鏈邊雙向
  傳播；走到已有座標的節點只做一致性檢查，不一致記 `ChainConflict` 而**不覆寫**。零
  錨點時挑節點當相對原點，`anchored=False` 照樣輸出。
- `coords.json` 每筆加 `source`（`border`／`constellation`／`chain`／`unresolved`）與
  `anchored`；另加 `chain_conflicts` 清單。

### 像素→格走 `battle.map_grid`，不是固定 pitch 除法

第一版用 `WorldGrid`（固定 `row_pitch` 除法）把峰對到格，實幀重放 300 對窗只長出 3 條
邊；293 對有共同峰的窗**沒有一對完全一致**，275 對的殘差可以用「列座標差 ±1」解釋。
根因是 `WorldGrid` 自己 docstring 就寫明的事：橫線間距隨 y 遞增（縱向透視），固定
pitch 的除法必然咬掉一列。**裁決是不放寬容差**——±1 列容忍會把 `match_patterns` 的
唯一性語意變成泥巴——改走既有的逐線對格 `battle.map_grid.read_frame_grid` ／
`snap_cell`（慢，但不受透視影響）。

相依方向照 `tests/test_package_boundary.py`：`runtime` 屬新包、`battle` 在 FROZEN 名單
裡，runtime 不得 import battle。所以「幀 → 幀內格」這一步放在腳本層
（`scripts/scan_roster_jump.py` 的 `frame_grid()`／`grid_window()`／`grid_centres()`／
`grid_pitch()`，scripts 兩邊都能 import），`jumpscan.frame_pattern(cells, target, window)`
改吃已經轉好的格——純函式，離線測試也更好寫。同一個理由，`blank_cell_tap` 改吃
呼叫端算好的**幀內格心**（`centres`）與 `keep_out`／`red_half`，不再自己用 pitch 推格。

### 實幀重放（run `20260806-042858` 的 25 張 clean 幀）

| | 固定 pitch | FrameGrid |
| --- | --- | --- |
| 可用幀 | 25 | 24（`ally#1` seed spacing implausible） |
| 鏈邊 | 3 | 17 |
| 環矛盾 | 0（因為鏈根本沒接起來） | 0 |
| 最大連通塊 | 2 | **14** |

`min_overlap` 由 2 提到 **3**：門檻 2 會長出 31 條邊但撞出 8 筆環矛盾，門檻 3 剩 17 條
邊而矛盾歸零（再往上只是繼續掉邊）。14 個節點的連通塊裡有多條獨立路徑互相驗證
（`enemy#15` 由 `ally#0`／`ally#3`／`enemy#4`／`enemy#10`／`enemy#13` 五條路到達，格差
全部一致），這是鏈自己給自己的背書。

殘留：我軍那一叢彼此仍多半 `no_match`，但殘差**不再是列向的**——例如 `ally#3` 與
`ally#4` 在平移 (0,2) 下 10 格對上 8 格，剩下 3 格是 `board.find_units` 兩幀給的峰集本
身不同（同一台在一幀有峰、另一幀沒有）。全覆蓋準則對這種偵測級差異零容忍。要不要
為此再放寬，等 `find_units` 的穩定性有結論再說，不在這一批動。

### 配對判別式：比例＋領先差，不是固定的共同峰數

固定 `min_overlap` 跨輪不穩，這是兩輪實測換來的教訓：run `20260806-042858` 門檻 2 長出
31 條邊、環一致性撞出 **8 筆矛盾**，門檻 3 才歸零；但同一個 3 到了 run
`20260806-052235` 反過來把好邊砍掉一半（9 條、最大元件 6），而該輪門檻 2 的 15 條邊
一筆矛盾都沒有。安全值逐輪不同，就是在說這個量本身不是判別依據。

改成計分制：重疊區內**覆蓋率 ≥ 0.8**、最優解命中數**領先次優 ≥ 2**、命中數 ≥ 3。
唯一性語意沒有放寬——領先差就是唯一性，只是從「不准有第二解」變成「第二解要明顯
更差」。實測（run `20260806-052235` 的 24 個 pattern）：**14 條邊、0 矛盾、元件
[10, 3, 3]**（原本 9 條、元件 [6,3,2,2]）。放行的都是強證據
（`ally#5×ally#8` 12/14、`ally#8×enemy#12` 10/11、`enemy#6×enemy#12` 9/11），而領先差
擋掉了 `enemy#17×enemy#2`（命中 4/5、覆蓋率 0.80，但次優也是 4＝真的別名）。
0.75 試過會再翻倍到 23 條邊，沒有矛盾訊號背書，不採用。

### 部分軸錨定（0806 第七輪之後）

單窗要同時解出兩軸太苛：run `20260806-052235` 全場 **0 個雙軸錨**，24 筆 lost 裡 5 筆
的 `axes` 是 `['x']`、19 筆是空的——西界常入鏡、北界很少。改成逐軸收：

- `jumpscan.AxisAnchor(key, axis, value)`＝某一台在世界座標上的絕對行或列，腳本每一窗
  把 `sweep.border_offsets` 解出的**單軸**也記進帳（journal `axis_anchor`）。
- `propagate(edges, axis_anchors, *, nodes)` 先把每個連通元件當剛體排好（元件內相對
  格），再逐軸把整塊平移到世界；同軸多筆互驗，差值不同記 `AxisConflict` 而不覆寫。
- 於是 **x 與 y 可以來自不同的窗**，甚至不同的單位——只要在同一個元件裡。
- `ChainSolution.world(key)` 回 `(x|None, y|None)`、`axes(key)` 回已錨定的軸名。

`coords.json` 誠實化：孤立節點（沒有任何鏈邊）`source` 回到 `unresolved`、不寫
`relative_cell`（相對格只對自己成立，寫出去會被當座標讀）；元件內節點寫 `component`
與 `relative_cell`；`cell`（絕對格）只有**兩軸都錨定**才寫；`anchored_axes` 逐台列出已
錨定的軸——這一項不看有沒有接上鏈，量到西界就是量到了。頂層另有 `components`
（各元件大小與已錨定軸）與 `axis_conflicts`。

#### 錨定補跳：y 軸荒的結構解

y 軸荒是巡迴方式造成的：照名冊順序跳、落點落在哪就讀哪，北界很少入鏡。所以在
`tour()` 之後、終版 `settle()` 之前插一道 anchor pass——對每個 size ≥ 3 且還缺某軸的
元件，用元件內的相對座標挑**該軸最極端**的單位（缺 y 挑相對 row 最小＝最靠北，缺 x
挑最靠西），對它再跳一次。跳轉會把目標帶到畫面中心，跳最北那台就把北界拉進畫面
——這是主動去把界找出來，不是等它出現。

補跳只讀界：落幀 `read_borders` ＋ `border_offsets`，記單軸 `axis_anchor` 就走，不記
圖樣也不配對（journal `anchor_jump`）。每元件每缺軸最多 2 台（極值與次極值），兩台都
讀不到就放棄該軸、帳面維持部分錨定——那不是失敗。解除照舊走 `dismiss`。

以第七輪的資料投影（新判別式下 14 條邊、元件 [10,3,3]），anchor pass 會排出 4 個補跳
目標：元件2（10 台）缺 x → `enemy#6`／`enemy#4`、缺 y → `enemy#9`／`enemy#17`；
元件0 缺 y → `ally#3`／`ally#2`；元件1 缺 y → `enemy#14`／`enemy#15`。

以第七輪的舊資料投影：x 軸會覆蓋 10/24 台（`ally#0`＋`ally#3` 同元件互驗、`ally#4` 所在
的 6 台元件、`ally#2` 與 `enemy#16` 兩個孤立節點），y 軸一筆都沒有——輸出會是
`anchored_axes: ["x"]` 的部分錨定帳，沒有任何一台寫得出絕對 `cell`。

## 留給實機驗證

- 部隊資訊分頁座標（我軍 460,440／敵軍 460,600）取自任務給的探針值，未在截圖上覆核
  （0806 兩張列表幀的分頁鈕位置與這兩點一致，但沒有點擊回饋可證）。
- 「開不出詳情頁＝列表盡頭」這條停止條件只在敵軍末列（第 4 列第 4、5 格）會用到，
  未實機跑過。0806 run 20260806-024307 曾在第一格誤判（詳情頁轉場中途讀到
  `troop_info`），已改成連兩輪才成立，仍待實機覆核。
- 我方跳轉後 `screens.classify` 應該是 `battle_unit_move`；腳本目前不驗這一點，直接
  點返回。若落點是別的模式（例如已行動完的單位），返回鈕位置可能不同。
- `blank_cell_tap` 的紅色門檻（佔比 0.12、`red>90 且比 B/G 高 30`）沒有實機紅格樣本，
  只用合成幀測過。
- 四界定錨這一段的 `pan()` 不做逐手勢行程驗收（省電觸控鎖吞手勢時只會多推幾把、
  最後 Halt），與 `sweep_scan.py` 的 `pan()` 相比是刻意的簡化。
- `prepare_board()` 的格線與卡條前置條件是照 `dry_run_entry.py` 的做法補的，本身沒有
  離線測試（`entry.confirm_grid`／`screens.read_roster_strip` 各自有），整段未實跑。
- `learn_landmarks()` 只在星座解出來時才跑，所以東／南地標要等至少兩台定位成功之後
  才可能出現；在那之前邊界重認實際上只有西北兩側可用，夠不夠未實機確認。
- 解除敵方指定改用落點幀自己的格線相位（`board.find_lattice`），這條路徑未實跑；
  落點幀讀不出格網或紅格滿版都會 Halt。
- 「整份名冊輪完仍零已解就 Halt」的開機保護未實跑，最壞情況會白跳一整輪名冊。
