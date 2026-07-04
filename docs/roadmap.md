# 進度與規劃

更新日期：2026-07-04

## 已完成

### 基礎架構（M1）
- GOAP 核心：`WorldState`（不可變、可雜湊）、`Action`（前置條件/效果/execute）、A* 規劃器（`core/planner.py`）。
- Agent 迴圈（`agent/loop.py`）：sense → plan → act → verify，含信念記憶（latch 無法直接感知的效果，如 `stage_cleared`）、「有進展就重新規劃、無進展才計失敗」的容錯策略。
- 感知/致動介面：`Perception` protocol、`AdbActuator`（landscape 2340x1080 參考座標、依實際解析度縮放）。

### 視覺辨識（M2）
- OpenCV 模板比對：manifest 驅動（`assets/templates/manifest.yaml`），16 個畫面錨點 + 約 20 個元件模板，含搜尋區域限定。
- `RecognizerPipeline`：多辨識器串接、信心度短路（為未來 OCR / Ollama LLM 辨識預留）。
- 標定工具：`scripts/capture.py`、`scripts/crop.py`、`scripts/verify_match.py`。
- 動態偵測（`vision/motion.py`）：`is_static()` 以幀差分辨可操作畫面 vs 劇情/攻擊動畫。

### 通關流程（實機驗證）
- 六個 flow action：進出擊準備 → 出擊（處理首次下載彈窗）→ 跳過劇情（MENU→SKIP，含戰鬥中劇情）→ 戰鬥等待 → 關閉結算 → 排掉獎勵鏈回到關卡列表。
- 新手教學提示框（coach-mark）以 `hint_dialog` 模板偵測並排除。
- AUTO 按鈕三態偵測（青=全自動、紅=敵回合自動、無色=全手動），argmax 模板比對。
- 導航迴圈端到端可跑；第 7~9 關已通關（但 8、9 是內建 AI 打的——這正是要修正的問題）。

## 目前問題（下一步的起點）

戰鬥階段目前依賴遊戲內建全自動 AI，違反專案核心目標：**戰鬥必須由我們的程式操作**。
已確認方向：進戰鬥後將 AUTO 切到無色（全手動），戰術 v1 用簡單啟發式。

已知技術障礙：
- 黑畫面/載入轉場輪詢太粗，錯過可操作的第一幀，內建 AI（青色 AUTO 跨關卡保留）就自己開打。
- 攻擊動畫期間 AUTO 按鈕被遮擋，probe 會回 None——讀寫 AUTO 只能在 `is_static` 的畫面上做並重試。

## 下一步：手動戰鬥控制器

1. **快速接手戰鬥開始**
   - 出擊後以次秒級間隔輪詢，穿過黑畫面/載入畫面，抓到第一個可操作的 battle_map 靜止幀。
   - 立刻把 AUTO 切到無色全手動（is_static 閘控 + 重試）。AUTO 狀態跨關卡保留，之後的關卡只需驗證。
2. **戰鬥 UI 探索與標定**（手動模式下逐步截圖）
   - 我方單位選取、移動格子、選擇武裝、目標選取、攻擊確認、待機、回合結束、單位列表。
   - 單位/敵人位置偵測可能需要顏色/blob 偵測而非模板比對（單位外觀隨編成變動）。
3. **v1 戰術啟發式**
   - 每個可行動單位：移動到最近敵人 → 攻擊 → 下一單位；無可行動單位則結束回合。
   - 全手動模式下也要推進敵方回合（點擊確認敵方行動的畫面）。
4. **整合進 GOAP**
   - 以新的 `ManualBattle` action 取代 `AutoBattle`，效果不變（battle_map → battle_result + stage_cleared），戰術細節封裝在 action 內部（或後續拆成戰鬥層子規劃器）。
5. **驗收**：第 10 關起用全手動控制器實測通關。

## 之後（延期項目）

- Ollama 多模態 LLM 辨識器、OCR 辨識器、`recognition.yaml` 執行期組態。
- 「略過」掃蕩機制解鎖後的快速重複通關路徑。
- 更聰明的戰術（地形、射程、屬性相剋）。
