# Review 導覽：驗證輪修正批（2026-07-31）

基底 `feat/inner-goap` @ `0106940`。五項修正對應 roadmap「2d 實機驗證輪
完成」條的五個發現，全部純程式碼、未碰實機。**設計決定清單在本檔末尾**，
審過之後再由主 session 併進 `docs/decisions.md`。

## Commit 全景

| commit | 對應發現 | 內容 |
|---|---|---|
| `f02bd6b` | ① | pinch 搬遷入 `runtime/zoom.py`＋掃描接上 `zoom_out` |
| `1d25db9` | ② | `dry_run_entry` 幀源統一：感知器與存檔共用 Camera |
| `cad22b3` | ③ | 格線設定頁探針降 advisory，地圖像素升唯一判準 |
| `6fb92d5` | ④ | `--stage-node` 必填＋選關後存右欄截圖 |
| `c6b193e` | ⑤ | 掃描預算預設 40＋`unlocalised` 入 `survey_summary` |

閘門：`uv run pytest -q` → **1466 passed, 4 skipped, 3 xfailed**；
`uv run ruff check src tests scripts` → **All checks passed**。
（基底同樣兩道：1442 passed / 4 skipped / 3 xfailed、ruff 綠。）

---

## ① pinch 搬遷＋zoom_out 注入

### 為什麼推翻原判

0730 之前的裁定是「當前縮放照樣掃得完，只是腿數變多」。實機證偽：
UC HARD 1 跑 20 tick 掃出 **0 cell**，東西兩向各燒滿 8 腿預算仍未到邊、
合併微步驟從未觸發（`data/runs/20260730-140043`）。

### 呼叫導覽

```
scripts/dry_run_entry.zoom_driver(args, camera, journal)
  └─ uiautomator2.connect(serial)            ← 與截圖／點擊的 adb 通道分開
  └─ runtime.zoom.gesture_pincher_for(u2dev) → GesturePincher
  └─ runtime.zoom.ZoomOut(capture=camera.grab, pincher=…, on_step=journal)
       └─ 交給 survey_drivers(..., zoom_out=…)

stage/survey.BoardDriver.survey_board()
  └─ ledger.next_step() == "zoom" → self._zoom()
       └─ self.zoom_out()          ← 就是上面那個 ZoomOut（沒注入就只 log 一次警告）
       └─ ledger.zoomed = True

runtime/zoom.ZoomOut.__call__()
  └─ zoom_out_max(capture=self._capture, pinch_step=self._pinch, …)
       ├─ 首幀量測 → PitchStep(0, …)
       └─ 迴圈：_pinch() → sleep(settle) → capture → measure → 收斂判定
            _pinch(): pick_pinch_center(board.find_units(最近一張幀))
                      → zoom_out_fingers(center)
                      → 四個點過 device.check_tap
                      → pincher.pinch(a, b)
```

### 搬了什麼、沒搬什麼

| 凍結層 `actuation/pinch.py` | 新 `runtime/zoom.py` |
|---|---|
| `GesturePincher`／`gesture_pincher_for` | 搬（本機唯一可行後端） |
| `zoom_out_max`／`PitchStep` | 搬（量測改吃 `runtime/board`） |
| `zoom_out_fingers`／`pick_pinch_center`／安全區與候選格 | 搬（純函式原樣） |
| `screen_to_raw`／`pinch_events`／`render_sendevent`／`SendeventPincher` | **不搬** |

不搬 sendevent 那一路的理由寫在模組 docstring：SELinux Enforcing、無 `su`、
production build 拒 `adb root`，`/dev/input/event7` 寫不進去，搬過來就是死碼；
凍結層原檔一個字沒動，舊工具照舊。

### 收斂判定的差異（審點）

凍結版的預設 `measure` 是「窄帶 `vision.grid_pitch` → 全幀
`vision.read_map_lattice`」兩段式；新包不得 import `battle/`
（`tests/test_package_boundary.py`），而 `runtime/board` 只有一個
`read_lattice`。所以新版是「`board.read_lattice` 讀得到就用格距，讀不到退
幀差 fail-soft」。影響：密集編隊把格網埋掉時會少一層救援，但 fail-soft 仍
能收斂（連兩幀幾乎不動＝停住），而縮放本來就是最佳化，最差情況只是少縮
一點。見設計決定 D1。

### 測試

`tests/test_runtime_zoom.py`（新，14 條）比照凍結層的分層：純幾何、中心
挑選、後端注入接縫（錄音機）、收斂迴圈（注入 measure/frame_change）、
組裝件行為（含「不多截一張」與「落點被拒就不注入」）。
`tests/test_stage_survey.py` 加兩條接線測：縮放微步驟會呼叫注入件、
沒有後端照樣掃得下去。

---

## ② dry_run_entry 幀源統一

### 問題

`Camera.grab()` 與 `LivePerceiver.look()` 各自 `device.screenshot()`。
`begin/end/keep` 存的是 Camera 的最後一張，`observe()` 的結構化欄位來自
Perceiver 的另一張——實測發現②：**段界存檔是陳舊幀，只有 journal 的
結構化欄位才可信**。

### 改法

Camera 升為唯一幀源，多一個 `screenshot() -> bytes` 讓它自己就滿足
`LivePerceiver` 要的 device 介面：

```
Camera.screenshot()  ← 唯一真的呼叫 LiveDevice.screenshot 的地方
  ├─ Camera.grab()          → decode，給 entry 閘門／survey 的 capture
  ├─ LivePerceiver(device=camera).look()   → Observation.frame 就是 camera.raw
  └─ Camera.keep(label)     → 存 camera.raw

DryRun.observe()  額外把這次判定用的幀存檔，路徑寫進 observed 紀錄
```

Keyguard 的 `soft_capture(camera)` 本來就走 Camera，不變。

### 測試

`test_the_perceiver_and_the_saved_frame_come_from_one_camera`（幀源計數＋
位元組相等）、`test_the_assembled_run_gives_the_perceiver_the_camera_channel`
（組裝端真的把 camera 傳進去，`--no-zoom` 所以不碰裝置）。

---

## ③ 格線設定頁探針降 advisory

### 問題

設定頁滑塊兩輪讀成未驗證，但地圖上的格線像素複驗皆過（疑截圖時機早於
UI 動畫）。滑塊是間接證據，讓它參與裁定會把跑得好好的流程擋下來。

### 呼叫導覽

```
runtime/entry.confirm_grid(capture, tap, report)      ← 唯一判準
  ├─ board.read_lattice(frame) is not None == desired → report.add("grid","ok")
  └─ 否則 set_battle_grid(...) → GridProbe
        └─ report.add("grid_setting", ADVISORY, probe.detail)   ← 永不失敗
  └─ 用完 attempts 仍讀不到格網 → report.add("grid","unverified")  ← 這才擋

stage/survey.BoardDriver.show_grid()
  └─ entry.set_battle_grid(...).detail     → LiveExecutor 記進流水帳 perform.step
```

`GridProbe(wanted, outcome, before, after)`，outcome 五值：
`already`／`tapped`／`unreadable`／`guarded`／`auto_drift`。

### 沒有放寬的地方（審點）

- **動作守衛照舊硬性**：讀不到「戰鬥分頁選著」＋「AUTO戰鬥 停在 OFF」就
  一個開關都不碰，直接從關閉鈕撤退（outcome=`guarded`）。
- 翻完滑塊後 AUTO 那一列若不再是 OFF，照樣 `log.error` 並記
  `auto_drift`；AUTO 的硬閘門仍在 `confirm_auto_off`／`confirm_in_map`。
- `ACCEPTED_OUTCOMES` 多一個 `"advisory"`——這是新的「記錄但不裁定」等級，
  只有 `grid_setting` 這一個 gate 用它。

---

## ④ select 明示化

`--stage-node` 由 `default=None` 改 `required=True`：棄戰回關卡列表游標會飄
（`docs/ui-navigation-map.md`），沿用「現在選著的那一關」會打到別關。
選關後多存一張右欄原生幀：

```
DryRun.run()
  begin("select")                     → frames select:start
  entry.select_stage(node=self.node)   → gate（trail 含 stage_node:ok X,Y）
  camera.grab(); camera.keep(...)      → frames select:right_panel   ← 新增
  end("select")                        → frames select:end
```

`runtime.entry.select_stage` 的 `node: tuple | None` 保持可選——哪一關的節點
落在哪個像素是關卡內容，不進 runtime；必填是**駕駛端**的紀律。

---

## ⑤ 掃描預算與 unlocalised

- `SURVEY_TICKS = 40`（`--survey-ticks` 與 `DryRun` 預設同源）。
- `survey_summary` 多一個 `unlocalised` 欄位，取自
  `driver.cursor.scan.unlocalised`（`ScanCursor.feed` 在位移量不出來時累加，
  並保留舊 offset——那一幀的目擊會落在錯的世界座標）。

**沒有動覆蓋簿記結構**：`CoverageLedger` 的方向腿數制原封不動，等覆蓋模型
v2 整批取代。`unlocalised` 是從既有的 `BoardScan` 讀出來的既有欄位，不是
新的簿記狀態。

---

## 設計決定清單（規格未明定、我自行裁量的點）

| # | 決定 | 選項與理由 |
|---|---|---|
| D1 | `zoom_out_max` 的預設量測只用 `board.read_lattice` 一個讀器，讀不到就退幀差 | 凍結版用 `battle/vision` 的窄帶＋全幀兩段式，但新包不得 import 凍結包（package_boundary 測試）。(a) 在 `runtime/board` 新增第二個「寬區」格網讀器、(b) 單讀器＋既有 fail-soft。採 (b)：憑空造一個沒有實測校過的區域常數是自創內容；fail-soft 本來就在，最差只是縮放少縮一點，而縮放只是最佳化。 |
| D2 | 落點名稱＝新檔 `src/ggge_ai/runtime/zoom.py`（不是 `runtime/pinch.py`，也不進 `stage/`） | 縮放是裝置手勢＋像素量測，兩層共用、與行動詞彙無關，落 `runtime` 符合 module-map（`runtime` 不得 import `stage`，這支只 import `runtime/board`＋`runtime/device`）。取名 `zoom` 而非 `pinch`：只搬了「縮放」這一個用途，sendevent 那條通用 pinch 路留在凍結層。 |
| D3 | 不搬凍結版的 `obstruction` 參數（縮放途中關掉單位詳情彈窗） | 新架構彈窗歸反射組（`runtime/reflexes`），在縮放迴圈裡再放一份是兩套真相。代價：彈窗蓋住時格網讀不到→幀差 fail-soft 會提早收斂，那一輪少縮一點，下一 tick 反射會收掉彈窗。列為已知限制。 |
| D4 | `ZoomOut` 出手前把四個手指點過一次 `device.check_tap` | pinch 走 uiautomator 注入，繞過 `LiveDevice.tap` 的危險帶白名單。候選中心本來就限制在 `PINCH_SAFE_REGION`，理論上不會踩到，但白名單是紅線設施，寧可留一道明寫的守衛（3 行）也不要有一條無守衛的注入路。 |
| D5 | ②的幀源設計＝**Camera 當 device 傳給 Perceiver**（不是把 Observation.frame 回填 Camera） | (a) 回填：`observe()` 之後 `camera.raw = seen.frame`——只補了 observe 這一條路，`perform()` 內部的 `look()` 仍是第二個真相。(b) Camera 實作 `screenshot()` 給 Perceiver 吃：所有截圖收斂到一個計數器與一個 `raw`，「單一幀源」是結構保證不是呼叫紀律。採 (b)。 |
| D6 | `observe()` 順手存幀並把路徑寫進 `observed` 紀錄 | 規格只要求「判定與存檔同一張」。多存這一張讓 journal 的每一筆結構化觀測都指得回一個檔案，事後對帳不必靠時間戳猜。成本：每次 observe 多一個檔（整段跑下來個位數）。 |
| D7 | ③ 的探針結果用 `GridProbe` 資料類別，不是回傳字串或 bool | 呼叫端有兩個（`confirm_grid` 進 report、`BoardDriver.show_grid` 進流水帳），都只需要一段自述字串；資料類別讓 before/after 兩個讀值留在結構裡，之後要對「動畫延遲」做統計不必重新埋點。 |
| D8 | `"advisory"` 加進 `ACCEPTED_OUTCOMES` 而不是「不記進 report」 | 不記＝流水帳看不到探針說了什麼，等於把證據丟掉；記成失敗＝又變回裁定。第三種等級最貼合「記錄但不裁定」。 |
| D9 | ④ 只讓 CLI 必填，`runtime.entry.select_stage(node=None)` 維持可選 | 節點像素是關卡內容不進 runtime（原註解的立場）；必填是駕駛端紀律。若日後外層自動選關，node 仍由呼叫端算。 |
| D10 | `--zoom/--no-zoom` 旗標＋uiautomator2 接不上就 fail-soft 走人 | 規格只說「組裝端把實作傳入」。實機驗證需要能單獨關掉縮放做 A/B（0730 的 0 cell 是對照組），而 u2 連線失敗不該讓整段乾跑掛掉——`zoom_backend` 這筆紀錄會告訴事後的人這一輪到底有沒有縮。 |
| D11 | `⑤` 的 `unlocalised` 從 `driver.cursor.scan` 取，不進 `CoverageLedger` | 派工明令不得加深覆蓋簿記耦合。`ScanCursor.scan` 是既有欄位、合併時就是同一個 `BoardScan` 物件，所以取值不會因為合併前後而不同。 |

## 已知限制與待實機驗證

- **縮放整條路沒有上過實機**（本批不碰裝置）。要驗的是：uiautomator2 能
  連上且 `resourceId=…unitySurfaceView` 找得到元件、一次 `ZoomOut()` 之後
  地圖真的縮到最小、`zoom_step` 的 `col_pitch` 序列確實遞減後打平。
  0720 那次成功的實機縮放是凍結層同一份幾何與同一個後端，但接線是新的。
- D3 的取捨：縮放途中若彈出單位詳情，這一輪會提早收斂。
- `--survey-ticks 40` 是否夠掃完仍未知——20 tick 連合併都沒觸發，40 只是
  把「有沒有機會走到合併」的問號往後推；真正的答案在覆蓋模型 v2。
- ③ 之後，設定頁探針永遠不擋流程：如果哪天格線真的翻不動，唯一會擋的是
  `confirm_grid` 的 `grid:unverified`（連 `attempts` 次都讀不到地圖格網）。
- `select:right_panel` 只是存圖，程式仍讀不出右欄標題是哪一關；要程式自己
  確認選對關，得等右欄文字讀取（不在本批）。
