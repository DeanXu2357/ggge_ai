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
