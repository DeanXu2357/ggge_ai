# Review 導覽：名冊跳轉掃描

批次目標：sweep 不再全圖推鏡找單位，改用戰鬥選單「部隊資訊」的名冊逐台「選擇」跳轉
鏡頭，再把落點掛回世界座標。

**0806 定位機制重做（本輪）**：跨窗圖樣配對整組拆除，改成「每一步都有定位點」的
relay／march 兩條路。理由與拆除清單見〈拆除：無標記的跨窗圖樣配對〉。

## 檔案

| 檔案 | 角色 |
| --- | --- |
| `src/ggge_ai/runtime/screens.py` | `BATTLE_MENU`／`TROOP_INFO` 兩個畫面名與簽名 |
| `assets/templates/elements/label_battle_menu.png`、`label_troop_info.png` | 標題字模（0806 實幀裁） |
| `src/ggge_ai/runtime/roster.py` | 列表格座標產生器＋詳情頁讀值（兩種佈局） |
| `src/ggge_ai/runtime/jumpscan.py` | **改寫**：指定標示定格／march 計格帳／接力帳與回填／排程／解除點挑選 |
| `src/ggge_ai/runtime/board.py` | `find_units` → **`find_unit_screen_hints`**（純改名＋首行語意：啟發式候選，輸出螢幕像素座標，不是已驗證世界座標） |
| `src/ggge_ai/runtime/device.py` | `weapon_dial` 危險帶；`DangerBand.intents` 多值白名單，`roster_cell`／`roster_jump` 放行面板底下的假重疊 |
| `scripts/scan_roster_jump.py` | **改寫**：四段停點改成 prepare／roster／jump／settle |
| `tests/test_roster_jump.py` | 離線測試：指定標示、march 計格、接力回填不動點、排程、互驗 |

## 呼叫鏈與執行順序

`scripts/scan_roster_jump.py::Scan.run()` 四段：

1. **prepare** — `entry.select_stage` → `entry.open_sortie_prep` → `entry.enter_stage`
   → `Scan.prepare_board()`（`entry.confirm_grid` 把顯示方格翻到 ON；
   `Scan.collapse_roster()` 讀 `screens.read_roster_strip` 再決定要不要點
   `screens.ROSTER_TOGGLE_TAP`，讀不出來就停手不盲點）。
   **四界巡迴整段砍掉**：世界原點的定義改由 march 自己拿（`FrameGrid.west_bound`／
   `north_bound` 的那一幀，幀格 0 就是世界 0），不再需要開場推到西北角，也不再有
   `WorldGrid`／`landmarks`／`offset` 這條線。
2. **roster** — 與前一版相同：`entry.BATTLE_MENU_TAP` →
   `roster.BATTLE_MENU_TROOP_INFO_TAP` → `roster.TAB_TAPS[faction]` → 逐格
   `roster.cell_taps(faction)` → `Scan.open_detail()`（輪詢 `screens.classify`；連續兩輪
   `troop_info` 才算列表盡頭）→ `roster.read_detail()` → `roster.json`。
3. **jump** — `jumpscan.next_target()` 挑下一台 → `Scan.visit()`：
   - `Scan.land()`：開列表 → `roster.DETAIL_SELECT_TAP` 跳轉 → **落點幀**（帶指定標示）
     → `read_signature()` 讀左上單位卡拿目標自己的 `name_sig` → `Scan.dismiss()`
     （敵＝`jumpscan.blank_cell_tap` 挑空白格；我＝`jumpscan.ALLY_DISMISS_TAP`）→
     **乾淨幀** → `read_frame_grid` → `jumpscan.designation_cell(落點幀, 乾淨幀, 格心)`
     ＝**目標格**。
   - 路徑 A `Scan.relay()`：`jumpscan.probe_order()` 用密度峰**只挑要點哪一格** →
     `Scan.ask_identity()` 點該格心 → `sweep.classify_tap` 判 CARD → `read_signature`
     拿鄰居身分 → `JumpLedger.relay(key, sig, 幀內格差)`。點到我方（SHIFTED）＝鏡頭被
     拉走，整幀格號作廢，按返回鈕、這一台改天再來。
   - 路徑 B `Scan.march()`：`Scan.seed_marker()` 在乾淨空白格種標記（`sweep.classify_tap`
     驗收 TAP_EMPTY 才算數）→ 往西逐把 `Scan.pan()` ＋ `board.find_marker` ＋
     `snap_cell` 記 `jumpscan.MarchLeg(before, after)`，標記快出視野就在同一幀重種 →
     `FrameGrid.west_bound` 為真時 `jumpscan.march_world(target, legs, border_cell=0)`
     ＝世界欄。跳回同一台重置鏡頭，往北同樣拿世界列 → `JumpLedger.anchor(..., "march")`。
   - 每台成功後跑一次 `ledger.settle()`，讓新座標把等著的接力帳往下推。
4. **settle** — `JumpLedger.settle()` 回填到不動點 → `jumpscan.audit()` 同幀對互驗 →
   `jumpscan.ledger_report()` → `coords.json`；預設 `entry.abandon_battle` 收尾。

## 定位的硬規格（使用者裁決）

相對偏移的**兩個端點都必須是驗證過的格**：

- 目標端＝跳轉指定狀態下**系統標示**的那一格，從帶高亮的落點幀讀出來
  （`designation_cell` 比對落點幀與乾淨幀的變化；解除不移動鏡頭，所以兩幀共用格網）。
- 鄰居端＝**我們點下去而且真的出卡**的那一格。點擊座標落在格 c、卡開了，記的就是格
  c；卡沒開這一格就不算，換一格。
- `find_unit_screen_hints` 的候選點只准拿來排「先問哪一格」（`probe_order`），一律不
  進座標計算。同幀 `FrameGrid` 只負責把兩個**點擊／標示座標**換算成格號。

## 拆除：無標記的跨窗圖樣配對

拆掉 `jumpscan.Pattern`／`match_patterns`／`propagate`／`ChainEdge`／`ChainConflict`／
`ChainSolution`／`AxisAnchor`／`AxisConflict`／`needy_axes`／`axis_frontier`／
`anchor_pass`／`JumpLedger.link`／`hint`／`candidates`／`target_peak`／`world_cells`，
與 `tests/test_roster_jump.py` 裡對應的全部 case（git 歷史留著）。

**理由（使用者裁決）**：那是無標記的圖片比對——兩窗之間沒有任何一端被點擊或系統標示
驗證過，靠的是密度峰集合的形狀自洽。實測也是這樣壞的：峰偵測跨輪不穩讓邊產率在
14↔7 之間震盪、圖碎裂成多個元件、絕對座標 0/28。計分制（覆蓋率＋領先差）只是把不穩
定的量再包一層，沒有改變「證據等級不合格」這件事。

一併退場的還有 `sweep.constellation_offset`／`sweep.border_offsets`／
`sweep.anchor_northwest` 在這支腳本的用途（`sweep.py` 本身不動，`sweep_scan.py` 還在
用）。保留：`blank_cell_tap`（解除還要用，改成建在新的 `clean_points` 上）、
UI 遮罩、危險帶 intent、`JumpLedger`（改造成新帳形）。

## 量出來的關鍵常數（0806 實幀，未改）

- 面板標題帶 `PANEL_TITLE_REGION = (1040, 65, 290, 58)`；三個標題互比最高 0.405，門檻 0.85。
- 列表格距：`CELL_X0=729`、`CELL_X_PITCH=278.5`、`CELL_Y0=267`；我軍列距 245.7
  （兩列各 5），敵軍列距 193.4（四列各 5，末列不滿）。
- 詳情頁數值：`runtime.glyphs.read_int(..., ink=Ink.DARK)`。敵方 `hp=(1180,149,155,34)`、
  `en=(1180,213,155,32)`、`mobility=(1250,285,85,35)`；我方多一列 LV，整體下移。
- 陣營帶 `(1125, 325, 165, 115)`：敵方 red 0.214／blue 0.000，我方 red 0.061／blue 0.287。
- 「返回」鈕心 (1798, 971)、右緣約 1868。

## 裁量決定（本輪新增）

1. **世界原點改吃 `FrameGrid` 的 `west_bound`／`north_bound`。** 舊路是
   `sweep.read_borders` 的界線像素再換算成欄，roadmap 記的「±1 欄軸錨矛盾」就是那個
   換算與 FrameGrid 相位差半格。`read_frame_grid` 自己就會把格線修剪到界線上並回報
   「這一側貼到界了」，所以界那一幀的**幀格 0 直接就是世界 0**，中間沒有換算。
2. **march 的行程量完全不參與定位。** 一把推鏡只產生一筆 `MarchLeg(before, after)`
   ——標記在推鏡前後的幀格索引，兩者都由 `snap_cell` 對格。手勢名義量照舊只用來決定
   推多遠（`board.pan_stroke`），不進帳。重種標記不另記一筆：重種發生在同一幀內，
   鏡位沒變，下一把的 `before` 用新標記的格即可（離線測試釘住這一點）。
3. **接力帳以 `name_sig` 為鍵，不是名冊序。** 點開鄰居時我們只知道它是誰，不知道它是
   名冊第幾台；名冊序是靠「跳轉落點幀上目標自己的卡」學進 `identities` 的。所以
   `Relay(key, via=sig, delta)` 可以在 `via` 還沒有座標時先記，`settle()` 反覆套用到
   不動點。
4. **回填衝突不覆寫。** 已經有座標的一端只記 `RelayConflict`——我們不知道哪一筆錯。
   `audit()` 在最終帳面上把每一筆接力再驗一次（含兩端各自獨立解出來的對子）。
5. **排程「緊鄰已解優先」。** 名冊相鄰的同勢力單位大概率地圖相鄰，鄰居入鏡機率高，
   路徑 A 才划算。第一台必然沒有已解單位可接，直接走 march 當種子。
6. **`coords.json` 只有絕對格或 `unresolved`。** 相對格與元件編號全部退場——相對格只
   對自己成立，寫出去會被當座標讀。
7. **`find_units` 改名 `find_unit_screen_hints`。** 名字要說出它是啟發式候選、輸出的是
   螢幕像素座標，避免再被當成已驗證的世界座標用（本輪的錯誤正是從這裡長出來的）。
   常數 `UNIT_DENSITY_*` 不動。

## 留給實機驗證

- **`designation_cell` 的門檻沒有實幀證據**（`DESIGNATION_MIN_CHANGE=0.25`、
  `MIN_LEAD=0.15`、`SATURATED=0.75`、`RADIUS=260px`），只用合成幀測過。敵方紅圈應該是
  強訊號；**我方那一格最不確定**——移動範圍是整片覆蓋，走的是「滿版時取離畫面中心最近」
  這條退路。第一輪實跑要拿 `jump:*:landing` 與 `jump:*:clean` 兩張幀離線重放校門檻。
- **我方跳轉的落點幀有沒有單位卡**（`read_signature` 讀不讀得到 `name_sig`）未證。讀不到
  時我方只能當接力的**目標端**，不能當 `via`。
- **鄰居出卡之後怎麼收掉卡**：目前用 `clear_card()` 點一個乾淨空白格，比照解除敵方指定
  的做法；未實跑。若點空白格收不掉卡（或反而選了別的東西），要改走 `map_view` 那條
  strict escape。
- **`sweep.classify_tap` 在這支腳本沒有 `selected=` 背書**（那條路綁 `battle.map_view` 的
  ViewGate），我方被點到時只能靠幾何位移判 `TAP_SHIFTED_UNSURE`；漏判的話會拿一張鏡頭
  已經被拉走的幀繼續算格。第一輪要看 `relay_probe` 的 verdict 分佈。
- **march 的推鏡把數**：`MARCH_LEGS=40`、`MARCH_RESEED_PITCH=1.5` 格都是估的；一台走兩軸
  可能要好幾分鐘，28 台全靠 march 是不可接受的成本——接力命中率是這條設計能不能成立的
  關鍵指標，第一輪就要量。
- 「名冊順序與跳轉一一對應」「部隊資訊分頁座標」「開不出詳情頁＝列表盡頭」等前一版留下
  的項目照舊。
