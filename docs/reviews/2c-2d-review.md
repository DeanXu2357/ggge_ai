# Review 導覽：批 2c＋2d（2026-07-30 合併）

對照本檔 review 兩個 worktree 合併：`b24543e`（批 2c 面板解析器）
與 `abeac58`（批 2d 實機通道）。每個功能附「呼叫了哪些模組、
以什麼順序執行」的導覽與建議閱讀順序。設計決定逐條在
`docs/decisions.md` 0730 各條，此處只放對照指標。

## 本輪 commit 全景（自 673c79c 起）

| commit | 內容 |
|---|---|
| 4cefcb5 | 對帳＋`scripts/ensure_unlocked.py`（鎖屏解鎖入口） |
| 2a3fd27 | 偵察輪樣本 12 張入 fixtures＋UI 文件補記 |
| 6e7cb92／92fc485 | 快照更新＋使用者修正（EN 差異、LLM schema 定向） |
| **b24543e** | **批 2c 合併**（內含 6 個小步 commit） |
| f6e3eed | 2c 收批：LLM 預設模型改 gemma4:31b |
| 3656f47／3ee8a2f | 掃描行動定向與執行模型核可（docs） |
| **abeac58** | **批 2d 合併**（內含 6 個小步 commit） |
| 4d60ccf／9a25d14／6a6de8d | 2d 收批備案、收卡條定案、下一步序 |

---

## 批 2c：面板解析器（截圖 → 情報庫結構化資料）

### 檔案

- `src/ggge_ai/runtime/glyphs.py` — 數字字模讀取器
- `src/ggge_ai/runtime/panels.py` — 版面錨點＋數值欄解析
- `src/ggge_ai/runtime/panel_text.py` — 封閉 schema 視覺 LLM 通道
- `src/ggge_ai/stage/intel_panels.py` — 折成 `UnitIntel`
- `scripts/parse_panel.py`（手動驗證入口）、`scripts/extract_glyphs.py`
  ／`extract_panel_templates.py`（字模重建工具）
- 資產：`assets/templates/glyphs/panel/`（32 字模）、
  `assets/templates/panels/`（7 模板）、`assets/catalog/panel_terms.json`
- 測試：`test_runtime_glyphs`、`test_runtime_panels`、
  `test_panel_text`、`test_intel_panels`

### 呼叫導覽（以 `scripts/parse_panel.py <png>` 為入口）

```
parse_panel.py
  └─ panels.classify(frame)            ① 這是哪種面板？
  └─ panels.read_stat_column(...)      ② 左欄數值
  └─ panels.read_weapon_rows(...)      ③ 武裝卡逐張
  └─ panel_text.OllamaPanelTextReader  ④ 自由文字（--no-llm 跳過）
  └─ intel_panels.unit_intel_from_panels ⑤ 折成 UnitIntel
```

執行順序與每步做的事：

1. **classify**（panels.py）：對面板標題帶做模板匹配
   （`title_stage_unit`／`title_roster_unit`／`title_roster_pilot`
   三錨點 argmax）→ 判定版面族（關卡內「單位設置詳情」四分頁
   vs 強化頁），決定後續用哪組欄位錨點。
2. **read_stat_column**：按版面族的固定格位逐欄裁切 → 每格丟
   `glyphs.py`：紅通道二值化（藍字強化值的對比坑）→ 投影切分
   → 逐字模對 `assets/templates/glyphs/panel/` 分類 → 數值＋
   信心值＋delta／buffed 旗標。
3. **read_weapon_rows**：定位武裝卡列 → 每卡讀類別徽章
   （`badge_melee/shooting/awakening` 模板，**集合**可多枚）＋
   LV／RANGE（含 MAP）／POWER／EN／命中／爆擊／彈藥欄（同走
   glyphs）→ 名稱區與特效說明區只框座標（`name_region`／
   `note_region`），文字內容留給 ④。
4. **panel_text**（唯一可能碰網路的一步，測試全用假件）：
   把 ③ 框出的裁切圖 base64 進 ollama `/api/chat`，**請求帶
   `format=<JSON schema>` 做約束解碼**——schema 枚舉只含沙盤
   已實作機制；回應再過 `coerce_weapon`／`coerce_abilities`
   復驗（伺服器忽略 format 不算保證）；名稱過
   `panel_terms.json` 白名單對齊（全中或差一字唯一候選才收）；
   枚舉外的一律進 `unsupported` 附原文。
5. **intel_panels**（stage 側）：①-④ 的產物折成
   `UnitIntel`／`WeaponIntel`／`SkillIntel`；MP／faction 等
   戰場動態走 `PanelIntel.dynamics` 交還呼叫端**不進 cache**；
   讀不到的欄位記 `gaps`。

實戰時（2e 起）的呼叫者是 Inspect 行動：拍詳情頁 → 同一條鏈
（不經 script）。

### 建議閱讀順序

`panels.py` docstring → `glyphs.py`（二值化與切分的坑都在註解）
→ `panel_text.py` 模組 docstring（契約與實測數字）→
`intel_panels.py` → 測試對照 fixtures 的期望值。

---

## 批 2d：實機通道

### 檔案

- `src/ggge_ai/runtime/device.py` — `Adb`／`LiveDevice`／
  `LiveExecutor`／危險帶白名單
- `src/ggge_ai/runtime/perceive.py` — `decode`／`LivePerceiver`
- `src/ggge_ai/runtime/screens.py` — 畫面辨識（簽名 argmax、
  AUTO 三態、設定探針、幀指紋）
- `src/ggge_ai/runtime/keyguard.py` — 兩種鎖（搬自 actuation）
- `src/ggge_ai/runtime/entry.py` — 進場閘門／格線流程／棄戰
- `src/ggge_ai/runtime/reflexes.py` — 反射組＋`ScreenFix`
- `src/ggge_ai/runtime/board.py` — 格網／密度峰／平移量測／邊界
- `src/ggge_ai/stage/gestures.py` — 行動→手勢 plan
- `src/ggge_ai/stage/survey.py` — 覆蓋簿記＋掃描執行器
- `src/ggge_ai/stage/{actions,state,loop,intel,intel_panels}.py` — 擴充
- `scripts/probe_live_channel.py` — 唯讀實機探針
- 測試：`test_runtime_{screens,keyguard,device,entry,board,reflexes}`、
  `test_stage_{gestures,survey}`、既有測試擴充

### 執行順序總導覽：一個 tick 經過哪些模組

`stage/loop.py:124` `tick()` 是總指揮，順序固定：

```
tick()
  ① perceiver.look()                → runtime/perceive.py
  │    device.frame()               → runtime/device.py（Adb screencap 原生位元組）
  │    decode() → screens.classify()→ runtime/screens.py（簽名 argmax、AUTO、幀指紋）
  │    （掃描輪迴中）SurveyPerceiver 把 CoverageLedger 折進 StageState
  ② terminal？→ 直接收束
  ③ reflexes 逐一 match()           → runtime/reflexes.py
  │    命中 → executor 執行 ScreenFix（自帶手勢），本 tick 結束
  ④ 簿記 _advance_queue()           → stage/loop.py:208
  │    佇列頭 progressed(state)？彈出；applicable(state) 失效？整隊丟棄
  ⑤ 換規劃（佇列空時）plan()        → stage/planner.py（GOAP A*）
  ⑥ executor.perform(佇列頭行動)    → runtime/device.py LiveExecutor
       ├─ plans（開迴圈手勢串）      → stage/gestures.py
       └─ drivers（閉迴圈流程）      → 設定頁開關、盤面掃描等
```

以下按功能拆流。

### A. 裝置通道（device.py）

`Adb`：`ADB_LIBUSB=1` 明寫進環境 → `exec-out screencap -p` 原生
PNG 位元組直通（不重編碼，測試釘位元組相等；唯讀探針實機已驗
2340x1080）。`LiveDevice.tap(x, y, intent="")` 先過
`check_tap`：**危險帶白名單**（`DANGER_BANDS`）——AUTO 三選一帶
無任何 intent 可放行、放棄帶只認 `abandon`、右上確認帶只認
`confirm`、AUTO 開關帶只認 `auto_switch`。Keyguard（搬入
runtime，介面注入化）掛在每段操作前、30 秒節流。

### B. 感知（perceive.py＋screens.py）

`LivePerceiver.look()`：拿幀 → `decode` → `screens.classify`
（宣告式 `SIGNATURES` 模板簽名同組 argmax → 畫面名；
`read_auto_switch` 三態：暗=OFF／青=ON 待機／紅=ON 執行中，
OFF 判定加白字閘門防黑幀冒充；設定頁三像素探針；16x16 幀指紋
供看門狗）→ `Observation`。**注意：`Observation.state` 實機上
目前恆為 None**（符號讀取器歸 2e），離線測試靠假件供 state。

### C. 反射組（reflexes.py）

在 tick ③ 攔截：結束回合確認、誤入移動／武裝選擇（返回退出）、
單位詳情誤開（關閉）、前景卡死看門狗（連續 5 次同幀指紋 →
HOME→桌面圖示復原）。回傳 `ScreenFix`（自帶手勢的修正，
**不是**行動詞彙成員——收彈窗不進規劃器）。LOGIN BONUS／
公告／日期彈窗的反射已接好但**簽名缺樣**（classify 還不會回
這三個名字；收尾小批補樣中）。

### D. 進場閘門（entry.py）

`enter_stage` 程序流（非符號行動——進關前還沒有 GOAP 迴圈）：
關卡列表選關 → 出擊準備 → 出擊 (1930,970)（避開 (2001,924)
自動編制帶）→ 關卡資訊頁 **AUTO 主動確認 OFF**（`read_auto_
switch`；是 ON 才帶 `auto_switch` intent 去點）→ TAP TO NEXT
→ 入圖複核（AUTO 複讀＋格網 ground truth）→ `GateReport`
（`skipped` 視為通過，例：已被 TAP TO NEXT 推進的步）。
`abandon_battle`：☰ → 放棄 (410,860)`abandon` → 確認
(1400,865)`confirm`。每步 `expect_screen` 失敗即停不亂點。

### E. 盤面掃描（本批核心，符號行動）

符號層（`stage/actions.py`）：

- `ShowGrid`：applicable＝我方回合＋`not grid_on`；效果供給
  `grid_on`；executor driver 走設定頁流程（battle-settings-ui
  座標＋探針驗證）。
- `SurveyBoard`：applicable＝我方回合＋`grid_on`＋
  `not board_synced`（**前置條件是符號的，無降級版**）；
  progressed＝`board_synced`。
- 規劃器靠前置條件自然排序 ShowGrid → SurveyBoard；行動留佇列
  頭跨 tick 重入 perform（0730 核可的執行模型）。

執行層（`stage/survey.py` → `runtime/board.py`）每次 perform
的微步驟（恢復式，每次先感知複核再走一步）：

1. 縮放檢查（pinch 未搬，`zoom_out` 注入點留白記 skipped——
   decisions.md 0730 延後裁定）
2. 平移一腿（`ScanCursor`；起手點避單位）
3. 該幀：`board.read_lattice`（高通投影＋三重閘）→
   `find_unit_density_peaks`（密度峰單位偵測，召回 103/104）→
   吸附格心 → `measure_shift`（相位相關＋星座投票雙模態）→
   目擊合併進 `CoverageLedger`
4. 邊界判定（平移後幀不變 ≤40px＝到邊；每方向 8 腿上限）

**覆蓋簿記（0730 必答題）**：`CoverageLedger`＝權威
（run-scoped 程式內記憶）；`SurveyPerceiver` 每 tick 折進
`StageState.swept`／`board_synced` → `progressed` 可見、流水帳
可見。**衰效**：敵方回合一過全作廢＋`generation` +1 →
執行器換代整個丟掉 `ScanCursor`（防新目擊疊在作廢位移上）。
搜尋側 `apply()` 刻意不動 `swept`（規劃一步到底，狀態空間不炸）。
掃描產出只有座標＋弧色線索（`hint`），**不判陣營**——陣營解析
歸 2e 證據分層。

### F. intel 型別擴充（2c 缺口回填）

`UnitIntel` 加 pilot 三值（射擊／格鬥／覺醒）＋機體／駕駛員
LV＋SP；`WeaponIntel` 加類別集合＋`crit_pct`＋`level`；
`UnitIntel.offence_for(weapon)` 依武裝徽章選對應攻擊值
（decisions.md「組裝時依武裝類別選用」的落地）。MP／faction
走 `PanelIntel.dynamics`，**不進 UnitIntel**（動態值永不 cache）。

### 建議閱讀順序

`stage/loop.py tick()`（總順序）→ `stage/actions.py`
ShowGrid／SurveyBoard docstring → `stage/survey.py` 模組
docstring（簿記雙層與衰效理由）→ `runtime/board.py`（視覺
技法與搬遷坑注解）→ `runtime/device.py` DANGER_BANDS →
`runtime/entry.py` → `runtime/screens.py`。測試以
`test_stage_survey`（23 筆，衰效／換代／重入劇本）與
`test_runtime_device`（白名單拒點劇本）最值得對照。

---

## 待你 review 時特別看的爭點

1. `SurveyBoard` 無降級版的失敗語意（格線開不起來＝誠實停止）
   ——你定的方向，確認落地形狀符合預期。
2. 危險帶 `top_right_confirm` 一帶同時罩住「自動編制」與
   「行動選擇」（裝置層看不到畫面名，靠 intent 放行）——
   接受這個粒度嗎？
3. `accuracy = 命中%−100` 的沙盤對映（intel_panels）——
   待 forecast 對帳前先用這個假設。
4. 反射「結束回合確認永遠選左」——若該彈窗能自發出現會有
   提前結束回合風險（文件說只由結束回合鈕觸發，未實機證偽）。

## 審後裁定（2026-07-31 使用者 review）

1. 未表異議（落地形狀維持）。
2. 使用者追問引出**勘誤**（一手記憶推翻 0730 標定）：自動編制
   實在出擊鈕**左邊**下緣按鈕列（中心 (1496,1010)，兩幀像素
   定讞），(2001,924) 是出擊鈕上緣外空星空；行動選擇實測
   (2037,930) 右下角大圓鈕。修正＝新增 `auto_deploy` 帶（無
   intent 放行）罩住真正的自動編制，原帶改名
   `bottom_right_confirm`（幾何不變，罩行動選擇確認）。
   「自動編制不給按」的原則本身接受。詳 decisions.md 0731。
3. 暫用假設接受，forecast 對帳前有效。
4. **否決**：對話框選哪邊是行為選擇，不歸反射層硬規範。已拆除
   `end_turn` 反射；標定座標與紅線註記遷 `stage/gestures.py`
   停放，應答歸未來按下結束回合鈕的行動自己收。
