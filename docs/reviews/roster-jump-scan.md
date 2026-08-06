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
| `src/ggge_ai/runtime/jumpscan.py` | **改寫**：敵方攻擊範圍菱形／我方移動範圍菱形／march 計格帳／接力帳與回填／排程／解除點挑選 |
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
   - `Scan.land()`：`close_panels()` → 開列表 → `roster.DETAIL_SELECT_TAP` 跳轉 →
     `await_map()` 確認面板真的收了 → `steady()` 等鏡頭落定＝**落點幀** →
     `read_signature()` 讀左上單位卡拿目標自己的 `name_sig` → 依陣營分兩條：
     **敵方**＝落點幀讀攻擊範圍紅菱形（`jumpscan.attack_cells` →
     `jumpscan.attack_centre`）＝目標格，再 `Scan.dismiss()`（`jumpscan.blank_cell_tap`
     挑空白格）→ 乾淨幀，兩張幀的格網相位要對得上（`same_view`）；
     **我方**＝`Scan.land_ally()`，落點幀必須是 `battle_unit_move`，直接讀移動範圍
     （`jumpscan.range_marks` → `jumpscan.diamond_centre(半徑=移動力)`）＝目標格，
     再按返回鈕退出，**一下地圖都不點**。
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

- 目標端＝跳轉之後**系統自己畫出來的範圍**的中心：敵方是攻擊範圍紅菱形
  （`attack_centre`，半徑未知，取最小包覆），我方是移動範圍菱形（`diamond_centre`，
  半徑＝名冊讀到的移動力）。兩者都不需要我們對地圖點任何一下。
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

8. **視圖讀不出來一律重拍重讀，絕不沿用推鏡前那張。** 0806 第九輪實機第一台 march 就
   CRASH：`pan()` 回 `None` 之後 `continue`，下一輪開頭 `bounded(view.grid, …)` 拿著
   `None` 炸 `AttributeError`。修法是把「當前視圖」與「推鏡結果」分成兩個名字，迴圈開頭
   看到 `None` 就 `Scan.look()` 重拍（journal `march_reread`），還是讀不出來才計 lost；
   鏡頭已經動了，舊視圖的格號全部作廢，**沒有沿用這個選項**。同型路徑（`land()` 的乾淨
   幀、`dismiss()` 的落點幀）一併補上重讀一次再放棄，`land()` 重讀後指定標示的比對改用
   重讀那張幀（`land_reread`／`dismiss_reread`）。離線回歸：pan 連續 `None` 到
   `MARCH_LOST_LIMIT` 應該記 `march_failed` 而不是 crash；重讀讀得出來就繼續走。

## 0806 第十四輪：march 的標記接力、移動模式洩漏、格網重用（run `20260806-130539`）

全程跑完並棄戰收尾，**首次產出正確的絕對座標**：march 三台（敵 (6,4)／(9,4)、我 (3,4)）與
真值檔完全一致——精度定讞。覆蓋只有 3/28，三個缺陷：

### 1. march 的標記撐不過兩把推鏡

`march_lost` 65 筆，**48 筆倒在第 2 把、16 筆倒在第 1 把**（`seed_marker` 本身很健康：44 次
裡 41 次 `empty`）。舊寫法是「種一顆標記，等它快被推出視野（`leaving()`）才重種」，也就是
要求同一顆標記活過好幾把推鏡；而敵群在 x 6-23，西推要 5-20 把。

修法照抄 `scripts/sweep_scan.py` 的 `carry_marker`（十二輪實戰過的那套）：

- **每一把推鏡之前都在前緣重種**（`Scan.carry_marker()`），不是等它快掉出去。往西推時內容
  往東走，所以新標記種在畫面**最西側**的乾淨格（`seed_marker(toward=…)` ＋ `FRONTIER_SORT`）。
  重種發生在同一幀內（鏡位沒變），計格帳不受影響——下一把的 `before` 用新標記在這一幀的格。
- **搬不動就沿用舊的，但舊的必須在這一幀上找得到**（`find_marker` 找不到就是那顆標記沒了，
  等同 sweep 的 `drop_stale_marker`）。
- **推鏡行程夾上硬上限**（`Scan.stride()` ＝ `sweep.stride_cap`，margin ＝
  `sweep.MARKER_KEEP_PITCH`）：推完標記必須還在視野內。`Scan.pan()` 因此收 `reach` 參數，
  不再每次都推滿 `PAN_MAX_REACH`。
- `leaving()`／`MARCH_RESEED_PITCH` 退場——「等它快掉出去」這個問法本身就是錯的。

### 2. 移動模式洩漏（安全問題）

`ally#2` 在 `range_fit` 之後 `relay_probe` 回 `empty`，接著 `seed_marker` 三連 `mistap`，
三次都是 `battle_weapon_select`——返回鈕退出之後**沒驗狀態就繼續點**，選取殘留讓下一下開了
武裝選單（誤攻擊的前哨）。

修法：所有 map tap（`seed_marker`／`ask_identity`／`dismiss` 的空白格）前面加硬閘
`Scan.ready_for_map_tap()`——`screens.classify` 必須是 `battle_map`，不是就 `escape_map()`
收乾淨再問，最多三輪；收不乾淨就記 `map_tap_blocked` 並放棄這一台，**絕不在未確認的狀態下
點地圖**。

### 3. 乾淨幀讀不出格網就沿用擬合那張

我方那一叢圖示很密，返回之後的乾淨幀常常 `seed spacing implausible`，而做擬合的移動模式幀
反而讀得出來——`land_failed` 10 筆多半是這樣，把已經到手的格白白丟掉。修法：乾淨幀讀不出
格網時**沿用移動模式幀的格網**（`grid_reused`，鏡頭沒動所以格號通用），乾淨幀只當 march／
relay 的起點畫面。敵方那條路同理（解除只是把紅範圍收掉，鏡頭不動）。

### 未做：東界反推 x（提案，待裁決）

任務單提的「landed 已見東界就從東界反推 x」需要先知道 `cols`，而附加條件「同輪內某台同時
定過東西兩界」幾乎不可能成立——一張幀同時看到東西兩界代表整張地圖塞得進畫面，那就根本不用
march。可行的等價寫法是：**某台已解出 x 的單位，其幀內同時看得到東界**，則
`cols = x + (東界欄 − 該台欄) + 1`，之後其他台看到東界就能反推。這是另開一個座標來源，本輪
沒有任何實測資料可校（run14 的三台 march 成功幀都沒有東界），所以列為提案不實作——寧可先讓
標記接力把覆蓋撐起來，再看還缺不缺這條捷徑。

## 0806 第十三輪：敵方定位改讀攻擊範圍（run `20260806-121910`）

18 台敵方 `landed` 全部 `target=null`、41 筆 `jump_failed`。**根因不是門檻，是機制選錯了**：
以「落點幀 vs 乾淨幀的變化」找指定標示（`designation_cell`）在敵方身上必敗——敵方跳轉會把
**整片攻擊範圍染紅**（20-37 格），解除之後整片一起消失，於是幾十格的變化量一樣大，領先差
永遠不成立（第十二輪把「滿版取離中心最近」那條退路刪掉之後，結果就是清一色 `None`）。

改法：**不再比兩幀的差，直接讀落點幀上遊戲畫的紅範圍**——那是以該台為中心的菱形，中心
就是它站的格。與我方那條路同一個原理，只是形狀與已知條件不同：

| | 我方 | 敵方 |
| --- | --- | --- |
| 證據 | 可抵達格徽章（稀疏，圖示會蓋掉） | 攻擊範圍實心紅（近乎完整） |
| 半徑 | 已知＝名冊的移動力 | 未知（移動力＋射程，名冊讀不到） |
| 判準 | 硬條件（全部落在半徑內）＋預測面積最小 | **最小包覆半徑**，並列再比面積 |
| 函式 | `jumpscan.diamond_centre` | `jumpscan.attack_centre` |

### 實幀重放（36 張 `jump:enemy:*:landing`）

- 紅格偵測沿用既有的 `red_fraction`，門檻 `ATTACK_FILL_MIN = 0.35`：**範圍內的格量到 0.5
  以上、範圍外不到 0.05**，0.35 落在那條溝的中間。UI 遮罩先濾——左上單位卡的 HP 紅條就
  疊在地圖上層，不濾每張都會多出兩三格假紅。
- **36/36 解出中心，零 `None`、零 miss**；每一張的中心都與「跳轉把目標帶到畫面中心」這個
  獨立線索一致（`snap_cell(SCREEN_CENTRE)`），兩條互不相干的證據對上了。
- **判準之所以是最小包覆半徑**：先試過 IoU（預測與觀測的交聯比），最佳與次佳只差
  0.027-0.03——菱形夠大時往旁邊挪一格幾乎不損失重疊，那是另一種 ±1。改用最小包覆半徑之後
  **36/36 都由半徑本身唯一裁決**（次佳中心一律要多一格半徑：25 格 vs 36-37 格的預測面積），
  面積與 `prefer` 兩個後備判準一次都沒有被用到。
- 這 36 張裡有 24 張的 `bounds` 看得到界，修好之後這些台可以直接單軸 march。

`designation_cell`／`own_marks`／`Scan.dismissed` 一併拆除——兩個陣營現在都讀「遊戲自己畫的
範圍」，幀差那條路連同它招來的「自家標記污染」問題一起退場。

### 另外兩件

- **`ally_grid_shifted` 放寬**（`scan_roster_jump.same_view`）：原本要求兩張 FrameGrid 的
  線位逐條全等，三次 `range_fit` 成功全被作廢，實際上只是格線偵測在邊緣多裁／少裁一條。
  比較的目的只是「鏡頭沒被拉走」，所以改成只問**原點相位差 < 半格**；格號一律以做擬合的
  那張幀為準（返回後的幀只用來確認鏡頭沒大位移，不參與格號計算）。敵方那條路也套同一支。
- **截圖逾時重試一次**（`Camera.screenshot`）：`adb exec-out screencap` 30 秒
  `TimeoutExpired` 直接滅團（0805 一例、本輪一例，通道 2.5 秒就恢復）。只對
  `TimeoutExpired` 重試（間隔 2 秒）——那是「這一下沒回來」，掉線是 `RuntimeError`，照樣
  往上拋；截圖唯讀且冪等，重試不會多按到任何東西。journal 記 `capture_retry`。

## 0806 第十二輪：名冊段的淡入轉場（run `20260806-120326`）

`enemy#16` Halt「詳情頁讀不出陣營帶」。證據幀 `frames/00032-tick0092.png` 的內容完全正常，
但整張是**淡入轉場中的半透明幀**：`screens.classify` 回 `unit_detail`（字模比的是形狀，
形狀還在），陣營帶區的平均 BGR 卻是 (206.5, 192.7, 194.1)——泛白、沒有顏色，紅／藍佔比
雙雙 **0.000**。同一張幀的 HP／EN／移動力也**一起讀成 None**，所以這不是陣營帶專屬的問題，
是「`classify` 過了不代表這一頁畫完了」。前 15 台過關只是轉場比輪詢快。

修法（`Scan.read_entry()`）：`classify=unit_detail` 之後、讀值之前先 `steady(DETAIL_REGION)`
等讀值區停下來，再讀；讀不出陣營帶**或數值讀不齊**都重拍重讀，最多三次，仍失敗才 Halt
（journal `detail_retry`）。`Scan.steady()` 因此收了 `region` 參數——地圖用它等跳轉的鏡頭，
面板用它等淡入，同一個問題同一把尺。

`DETAIL_REGION = (1100, 120, 700, 320)` 一次涵蓋陣營帶與四個數值欄。穩定閘的門檻沿用
`CAMERA_STEADY_FRACTION`；**真正的保險是重試**——run12 只留下同一張幀存了兩次，淡入到底
有多慢無從量起，而三次重試各自重拍（每次至少 0.6 秒）比任何單一門檻都難被慢淡入騙過。

（附記：`enemy#14/#15` 的 61506/83811 與 `enemy#16` 的 109440/750 是這一輪的新面孔，大數字
本身不是字模異常。）

## 0806 第十輪實機診斷（run `20260806-103335`）

戰果：ally#3 全程成功——落點幀同時見西界與北界，兩軸 `legs=0` 直接定 `[2,3]`，機制本體
可行。三個壞掉的地方，根因都在**幀的時序與我們自己留下的痕跡**，不在門檻：

1. **落點幀是跳轉「前」的鏡位。** ally#0 四次落地的 FrameGrid 完全相同
   （`cols0=720`、pitch 130.1/120.0），但 `designation_cell` 給出 (3,4)/(2,4)/(4,5)/(4,3)
   ——不是 ±1，是四個不相干的格。親看 `00035`（落點）與 `00036`（乾淨）：**兩張根本不是
   同一個鏡頭**，地圖區變化量 0.37。固定 `JUMP_SETTLE_S=1.5` 拍到的是面板剛收、鏡頭還沒
   跳的那一瞬。修法：`Scan.steady()`——連兩張地圖區變化 < `CAMERA_STEADY_FRACTION`(0.06)
   才算落定（實幀量：同鏡位 0.007-0.04、跳轉途中 0.15-0.37）。
2. **贏得比對的是我們自己的填色。** ally#4 的落點幀 `00055` 上有上一台種的青色選取格，
   乾淨幀裡它被我們自己的解除點搬走——`designation_cell` 選中的 (0,3) 正是那一格
   （px 1046,441 對上截圖裡的青色格）。修法：`designation_cell(exclude=…)`，把解除點的格
   與（有色簽時）兩張幀上找得到的填色格排除。
3. **我方跳轉沒有任何指定標示。** `00055` 已經是跳轉後的鏡位，畫面卻是純 hub 地圖
   （訊息列「請選擇欲行動的單位。」，沒有移動範圍、沒有紅圈）。也就是**我方的目標端目前
   沒有可讀的定位點**——這一項不是 bug，是機制缺口，待裁決（見下）。
4. **誤下移動指令的實證。** ally#4 兩次 `relay_probe` 與兩次 `seed_marker` 連四下
   `verdict=none`；`classify_tap` 沒有 `selected=` 背書，點到我方進了移動態它分不出來，
   於是下一下格點擊就是真的移動指令。旁證：該台第二趟的詳情頁**只剩一顆置中的「關閉」**
   （`00057`），沒有「選擇」鈕＝那台已經行動過了。修法：任何一下 map tap 的 verdict 不是
   預期的（探針要 `card`、種標記要 `empty`）就**先按返回鈕再說**（`Scan.escape_map()`），
   絕不連點第二下。
5. **面板洩漏。** 收尾 halt「點 ☰ 之後畫面是 troop_info」的源頭就是第 4 點的後果：
   (1372,995) 點在沒有「選擇」鈕的詳情頁空處，`land()` 直接回報失敗、面板整疊留著。
   修法：`Scan.close_panels()` 逐層關閉（詳情頁→部隊資訊→戰鬥選單，最多三層），
   `open_troop_info()` 開頭一定先跑；`land()` 改成先 `await_map()` 確認面板真的收了才算
   跳轉成功，沒收就記 `jump_not_taken` ＋收面板收乾淨再回失敗。
6. `GridUnreadable` 的 WARNING 降成單行（原本整個 traceback 進 log）。

### 裁決（0806 最終）：我方的目標端＝移動範圍菱形，全程零 map tap

使用者推翻下一節的「點候選格確認」版本：我方跳轉（詳情頁「選擇」）**本來就直接進入單位
移動模式**，所以不必也不該對地圖點任何一下。新流程 `Scan.land_ally()`：

跳轉 → `steady()` → `screens.classify` 必須是 `battle_unit_move`（不是就記 `jump_not_taken`
＋`unresolved`，不點地圖）→ 就用那張移動模式幀讀高亮的可抵達格 → 菱形擬合出中心格 →
按返回鈕 (1798,971) → `await_map()` → `steady()`，並要求退出後的格線與移動模式幀**完全
相同**（`ally_grid_shifted` 否則作廢，格號不跨鏡位用）。

- **可抵達格有兩種徽章，都要收**（`jumpscan.range_marks`）：藍＝可走、紅「!」＝可走但會
  被敵方打到。實幀 `assets/screenshots/20260806-013500.png` 量：藍 45x43／填充 0.62-0.75／
  長寬比 ~1，紅 45x63／填充 0.44-0.59／長寬比 ~0.67，尺寸一律用格距的比例表示。
  **只收藍的會讓菱形缺一整側**——只用藍格的最小包覆菱形給出 (1,5)，藍紅聯集才唯一解出
  (3,4)＝那台實際站的格。右側敵方那條同色的 34x64 HUD 條靠長寬比擋掉，放它進來菱形無解。
- **擬合**（`jumpscan.diamond_centre`）：硬條件是每一個看到的可抵達格都在半徑
  `reach`＝名冊讀到的**移動力**之內（標記是遊戲畫的，不可能超出移動力；漏看不罰、多看否決）。
  貼邊時菱形被截斷、可行中心不只一個，改用「預測最少沒看到的區域」收尾（Occam：同樣的
  觀測下預測範圍愈小愈可信），仍並列才用「離畫面中心最近」當先驗，還並列就回 `None`。
  實幀（移動力 5、31 個標記、單位自己那格沒有徽章）：**可行中心唯一，就是 (3,4)**。
- 移動模式的判準沿用既有的 `screens.BATTLE_UNIT_MOVE`（該幀 `classify` 直接回
  `battle_unit_move`），沒有新開字模。
- 順手把 `designation_cell` 的「滿版就取離中心最近」退路**刪掉**——那條退路本來是為我方
  覆蓋層加的，現在我方不走它了；敵方寧可漏認也不要猜。

### （已被推翻）「點候選格開移動模式」

上一版曾實作 `ally_target()`／`ally_probe`：點離畫面中心最近的候選格，畫面進入移動模式就
算驗證。使用者裁決改走上面的零 map tap 版本後整段拆除——地圖上少一下點擊就少一次誤下
指令的機會，而移動範圍本來就把答案畫在畫面上了。

### 誤觸帳：run 級旗標

`Scan.note_state()` 在每一個 map tap 之後看一次 `screens.classify`：落進
`screens.MAP_SUBSTATES`（移動／武裝選擇／技能）而又不是當下預期的那個模式，就記一筆
`mistap`（journal ＋ `Scan.mistaps`）。`coords.json` 頂層因此有 `clean_run`（布林）與
`mistaps`（逐筆），`settle` 那一行也帶著——驗收判準的「零誤觸」從此機器查得到，不必人翻幀
（run10 誤下了一次移動指令，事後只能從詳情頁少一顆鈕反推）。接線點：`ally_probe`、
`relay_probe`、`seed_marker`。

### 巡迴順序：敵方優先（預設）

`TOUR_ORDERS` ＋ `--tour-first {enemy,ally}`，預設 `enemy`。敵 18 台是驗收大頭，而敵方那條
路（紅圈指定→點出卡→`name_sig`）才是接力鏈唯一的證人來源；我方只出得了驗證格、出不了
身分，排後面。`Scan.keys()` 的順序同時就是排程「名冊相鄰」的定義。

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
