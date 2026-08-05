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
| `src/ggge_ai/runtime/device.py` | 新增 `weapon_dial` 危險帶 |
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
   `sweep.anchor_northwest` 定義世界原點；再往東、往南各推一趟把 `landmarks` 補齊
   （邊界重認的第二註冊來源要它）。
2. **roster** — 對我軍／敵軍各走一次：`entry.BATTLE_MENU_TAP` →
   `roster.BATTLE_MENU_TROOP_INFO_TAP` → `roster.TAB_TAPS[faction]` →
   逐格 `roster.cell_taps(faction)` → `Scan.open_detail()`（`screens.classify`
   判是不是開出詳情頁；沒開出來＝列表盡頭）→ `roster.read_detail()` → 存幀 →
   `roster.DETAIL_CLOSE_TAP`。收工 `roster.TROOP_INFO_CLOSE_TAP` ＋
   `entry.BATTLE_MENU_CLOSE_TAP`。名冊落 `roster.json`。
3. **jump** — `jumpscan.next_target()` 挑下一台 → 同一條開列表的路 →
   `roster.DETAIL_SELECT_TAP` 跳轉 → 落點幀 `board.find_units` ＋
   `jumpscan.target_peak()` 鎖目標 → `Scan.dismiss()`（敵＝`jumpscan.blank_cell_tap`
   挑空白格；我＝`jumpscan.ALLY_DISMISS_TAP` 帶 `intent="ally_dismiss"`）→
   乾淨幀 `Scan.locate()`（`sweep.constellation_offset` 優先、`sweep.border_offsets`
   墊底）→ `grid.cell_of()` 定格 → `JumpLedger.record()`。解不出來
   `JumpLedger.fail()`，連兩敗退場記 UNRESOLVED。
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
5. **`next_target` 的「候選格」由呼叫端餵。** 落點幀看到的其他峰無法直接歸屬到某一
   個名冊序號（列表順序與地圖位置沒有已知對應），所以模組只提供
   `JumpLedger.hint(key, cells)` 這個入口，排程只問「這一台有沒有候選」，不自己發明
   歸屬規則。目前腳本尚未餵任何 hint——第一輪等於純名冊順序。
6. **`audit` 用投影複核而不是比對世界格差。** 直接比世界格差是循環論證（兩邊都是同
   一組 offset 算出來的）。改成把 B 的最終世界格投影回 A 的窗，窗內就該有一個峰；
   沒有＝至少一台錯。雙向都會各記一筆。
7. **空白格挑「離畫面中心最遠的乾淨格」**：貼著目標點下去等於在紅格裡賭。
8. **讀值用 `runtime.glyphs` 而不是 `vision.digits`。** 任務指定的
   `vision/digits.read_number` 會踩 `tests/test_package_boundary.py`（runtime 不得
   import 凍結包 `vision`）。`runtime.glyphs.read_int` 的 panel 字模在這七個欄位上
   讀數與 `read_number(invert=True)` 完全一致（29265/424/4、55/38311/148/5）。

## 留給實機驗證

- 部隊資訊分頁座標（我軍 460,440／敵軍 460,600）取自任務給的探針值，未在截圖上覆核
  （0806 兩張列表幀的分頁鈕位置與這兩點一致，但沒有點擊回饋可證）。
- 「開不出詳情頁＝列表盡頭」這條停止條件只在敵軍末列（第 4 列第 4、5 格）會用到，
  未實機跑過。
- 我方跳轉後 `screens.classify` 應該是 `battle_unit_move`；腳本目前不驗這一點，直接
  點返回。若落點是別的模式（例如已行動完的單位），返回鈕位置可能不同。
- `blank_cell_tap` 的紅色門檻（佔比 0.12、`red>90 且比 B/G 高 30`）沒有實機紅格樣本，
  只用合成幀測過。
- 四界定錨這一段的 `pan()` 不做逐手勢行程驗收（省電觸控鎖吞手勢時只會多推幾把、
  最後 Halt），與 `sweep_scan.py` 的 `pan()` 相比是刻意的簡化。
- `prepare_board()` 的格線與卡條前置條件是照 `dry_run_entry.py` 的做法補的，本身沒有
  離線測試（`entry.confirm_grid`／`screens.read_roster_strip` 各自有），整段未實跑。
