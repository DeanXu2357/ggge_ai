# LLM 定位 probe 報告（覆蓋掃描第三層，#26 批4）

產出工具：`scripts/llm_localize_probe.py`（可重跑，會覆寫本檔的機械版；本檔
為 2026-07-23 實跑後的**策展版**，數據表與工具輸出一致，另補重量級模型逾時
發現、根因分析、裁決與接線決定）。ollama @ `http://localhost:11434`，
temperature 0，每對 1 次。

## 方法

- 素材：`tests/fixtures/vision/map_scan/ex2if_20260719/` 九幀（格線已開、
  最小 zoom），批2 實測真值偏移鏈。
- 每對連續幀**兩張圖同一訊息**送 LLM（`LlmScreenReader.localize_pair`，走
  生產編碼路徑：長邊縮到 1280＋JPEG q85；prompt 即 `live_scan.LLM_LOCALIZE_PROMPT`，
  probe 逐字沿用），要求指認兩幀共通地標、回報各自 0 基格座標（左上可見格線
  起算）。
- 宣告偏移＝`(col1-col2, row1-row2)`，對真值鏈；exact 相等＝correct，另記誤差
  向量與延遲。
- 真值鏈：pt1→2 `(1,-5)`、2→3 `(0,-5)`、3→4 `(-1,-5)`、4→5 `(0,-2)`、
  5→6 `(5,0)`、6→7 `(0,6)`、7→8 `(0,5)`、8→9 `(-1,5)`。

## 受測模型

機上 `/api/tags` 的 gemma 系：`gemma4:latest`（生產預設，8B）、`gemma3:27b`、
`gemma4:26b`、`gemma4:31b`。

- **`gemma4:26b` / `gemma4:31b` 排除**：先前全掃在 240s/call 逾時下跑 25 分鐘
  只產出連續 `TimeoutError`（見 probe log），本機推論吞吐不足以在合理預算內
  回一次兩圖請求。判定「本機不可用」，未納入準確率統計（逾時＝無資料，不是
  0 分）。
- 實測完成：`gemma4:latest`、`gemma3:27b`（皆 responsive，延遲見下表）。

## 逐對結果

### gemma4:latest（生產預設）

正確 **0/8**、平均 |誤差| 4.79 格、平均延遲 5.3s。

| 幀對 | 真值 | LLM 偏移 | 誤差 | 判定 | 延遲 | 地標 |
|---|---|---|---|---|---|---|
| pt1→pt2 | (1, -5) | (0, 0) | (-1, 5) | wrong | 9.0s | Blue unit with yellow accents (likely a mobile suit) |
| pt2→pt3 | (0, -5) | (0, 0) | (0, 5) | wrong | 4.3s | Green submarine/ship |
| pt3→pt4 | (-1, -5) | (0, 0) | (1, 5) | wrong | 5.1s | Blue unit in the center-right |
| pt4→pt5 | (0, -2) | (0, 0) | (0, 2) | wrong | 4.4s | Blue unit (Gundam) |
| pt5→pt6 | (5, 0) | (0, 0) | (-5, 0) | wrong | 4.8s | Blue unit (Gundam) |
| pt6→pt7 | (0, 6) | (0, 0) | (0, -6) | wrong | 4.8s | Blue unit (Mobile Suit) |
| pt7→pt8 | (0, 5) | (0, 0) | (0, -5) | wrong | 4.9s | Blue unit in the bottom right corner |
| pt8→pt9 | (-1, 5) | (0, 0) | (1, -5) | wrong | 4.7s | Blue Gundam unit (bottom left) |

### gemma3:27b

正確 **0/8**、平均 |誤差| 4.79 格、平均延遲 2.3s。

| 幀對 | 真值 | LLM 偏移 | 誤差 | 判定 | 延遲 | 地標 |
|---|---|---|---|---|---|---|
| pt1→pt2 | (1, -5) | (0, 0) | (-1, 5) | wrong | 6.5s | green enemy unit |
| pt2→pt3 | (0, -5) | (0, 0) | (0, 5) | wrong | 1.7s | red enemy unit |
| pt3→pt4 | (-1, -5) | (0, 0) | (1, 5) | wrong | 1.7s | blue mobile suit with a shield |
| pt4→pt5 | (0, -2) | (0, 0) | (0, 2) | wrong | 1.7s | orange warning sign |
| pt5→pt6 | (5, 0) | (0, 0) | (-5, 0) | wrong | 1.6s | red unit |
| pt6→pt7 | (0, 6) | (0, 0) | (0, -6) | wrong | 1.7s | red gundam |
| pt7→pt8 | (0, 5) | (0, 0) | (0, -5) | wrong | 1.7s | red mobile suit |
| pt8→pt9 | (-1, 5) | (0, 0) | (1, -5) | wrong | 1.7s | red unit with a shield |

## 分析

- **系統性 (0,0)**：兩個 responsive 模型在**全部 16 對**都回報「地標在兩幀
  的同一格」——`frame1==frame2`。JSON 一律可解析、也確實各挑了一個地標
  （地標描述本身多半合理），但**完全感知不到鏡頭平移**：模型把每幀的格網
  當獨立座標系、回同一格號，等同於「沒動」。
- **唯一一次 |誤差|≤2（pt4→pt5）是巧合**：真值 `(0,-2)` 剛好離 `(0,0)` 最近
  的一對；不是定位能力，是「永遠回 (0,0)」撞上最小位移對。故弱版（約略方位
  承載）也無實質訊號可用。
- **根因（幾何）**：最小 zoom 下整張圖橫向近乎全入鏡（23 欄×約96.5px≈2220
  對視口 2340），單格約 96px；生產編碼縮到長邊 1280 後單格僅約 53px。要在
  這種密格上數到「第 15–19 欄／跨平移對的列位移」超出這幾個本機模型的
  空間計數能力。縱向雖只約 11 列，模型同樣回 (0,0)，顯示問題不在格數多寡而
  在**跨幀位移的量化**本身。

## 裁決：**不上線（no-ship）**

依據：生產預設 `gemma4:latest` 0/8 exact、平均誤差 4.79 格、且係統性回 (0,0)
（毫無位移訊號）；`gemma3:27b` 同構失敗；重量級 `gemma4:26b/31b` 本機逾時
不可用。強版（信格座標）無從成立，弱版（地標＋約略方位承載定位）也因「永遠
(0,0)」而無可用素材。**probe 素材不足以支撐任何上線變體**——這是計畫第 10
節明列的正當結論。

## 接線決定：tier 已實作＋護欄＋測試，但**生產休眠（僅留接縫）**

- LLM 第三層已按強版落地並上鎖護欄（`CoverageScanSource._llm_assist`：
  兩幀宣稱格各裁 patch 過 `LLM_PATCH_MIN` 的 TM_CCOEFF_NORMED、平坦 patch
  以材質下限直接拒、偏移過 `CellMap.verify_offset` 邊界一致；`force=True`
  越 60s 限流）。因此**即使未來換上會亂猜的模型，錯誤假設也只會被 patch/
  邊界護欄擋下→走回復，永不污染座標**。
- **控制器不注入 llm**（`controller._navigator` 維持 `llm` 預設 None）：
  `_place` 在 `self.llm is None` 時跳過 tier，迴圈與純確定性版 **bit 級一致**
  （批3 惡意世界 8 測 llm=None 全綠即證）。接縫（注入欄位＋seam 方法＋測試）
  就緒，換到有能力的模型時只需一行 `llm=self.llm` 並重跑本 probe 覆核。
- 附帶落地（與裁決無關、獨立有用）：`localize_report` 診斷路徑讓
  `frame_localized` ledger 記真實 `margin`/`source`（edge_pin／vote／
  llm_assist）；`verify_offset` 公開護欄。

## 給批5／未來的備註

1. 換模型再評估：本機若裝上更強的視覺 LLM（能回兩圖相對格位），重跑
   `uv run python scripts/llm_localize_probe.py --models <tag>`；≥6/8 exact
   再考慮把 `llm=self.llm` 接進 `controller._navigator`（強版直接可用）。
2. 弱版（search 型）另需改 `_llm_assist`：目前護欄裁在「LLM 宣稱格」上，屬
   強版；若某模型能「指對地標但數錯格」，需改成「以地標 patch 在對幀寬域
   模板搜尋」承載定位（plan 第 10 節弱版）。本輪 probe 顯示無此中間態，故未
   實作。
3. `gemma4:26b/31b` 逾時是本機吞吐限制，非模型能力結論；換機或給更長預算可
   另測，但不擋本計畫。
