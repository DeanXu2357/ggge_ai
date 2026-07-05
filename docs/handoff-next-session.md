# 下次工作提示詞（HARD 2 實測起點）

把下面整段貼給 Claude Code 當第一則訊息即可。

---

任務：恢復 HARD 2 探測（E2），實戰驗證戰術地圖 v1，收集戰敗流程資料。

先讀 CLAUDE.md、docs/roadmap.md 的暫停快照、docs/agent-architecture.md，
然後嚴格照以下流程執行。每個實機動作後都要截圖看圖確認，不確定就停下來問我。

## 第 0 步：確認裝置與遊戲狀態

1. `adb devices` 確認 R5CRC37JBYJ 在線。
2. 截圖判斷目前畫面：
   - 還在 HARD 2 戰鬥中（TURN 1 我軍回合）→ 直接第 1 步。
   - 被鎖（畫面變暗或鎖頭圖示）→ 先隨便點一下喚亮，再
     `adb shell input swipe 1164 430 1164 60 350` 解鎖，截圖確認後繼續。
   - 遊戲被登出/回到主畫面 → 重新進場：關卡(1230,1050) → 主要關卡 →
     初鋼系列 → 選擇(1989,889) → 點 HARD 2 節點 → 出擊準備(1989,891) →
     出擊(2040,1030)，有下載彈窗按確認(1369,851)，簡報畫面點中央跳過。

## 第 1 步：啟動控制器（tmux 背景）

```
tmux new-session -d -s e2 "uv run python scripts/run_manual_battle.py 2>&1 | tee /tmp/e2_run.log"
```
掛 watcher（背景 bash，每 30 秒檢查一次，命中就結束並輸出 log 尾段）：
結束訊號=「controller finished」；異常訊號=「Traceback」；tmux session
消失也要視為結束。

## 第 2 步：驗證戰術地圖（看 log，前 5 分鐘內就有結論）

必須看到的訊號：
- `scout: tactical map has N enemies / M allies / K third-party`
  —— N 應該接近 10（這關敵軍 10 台）。N=0 或只有 1-2 → 掃描有問題，
  截圖對照實際畫面，檢查相位相關的 response 與座標合併。
- `tactical-map enemy at (...) (screen), camera offset (...)`
  —— 星座錨定命中，畫面外敵人成為移動目標。整場一次都沒出現的話，
  記錄下來（錨定條件可能太嚴），但不要中途改碼，先讓這場打完。
- `new turn detected (turn N)` —— 回合邊界偵測，N 應隨戰局遞增。

異常處理：controller crash → 看 Traceback 修（小修，pytest 過再重啟
tmux）；重啟後遊戲仍在戰鬥中，控制器會自己接手。

## 第 3 步：戰敗流程收集（本場的主要目的，預期會輸）

我方全滅時控制器多半不認得戰敗畫面，會走到 idle timeout（最長 10 分鐘）
才退出——這是預期行為，不是 bug。在那之前：
1. watcher 回報結束或 log 安靜下來後，立刻截圖。
2. 把戰敗結算的完整畫面序列截下來（戰敗動畫→結算→點掉後回到哪個畫面），
   每點一步截一張。
3. 從戰敗結算截圖裁出穩定錨點（畫面上固定的「戰敗/LOSE」字樣區域），
   存 assets/templates/screens/ 候選，用 scripts/verify_match.py 驗證
   對戰敗幀高分、對其他畫面低分。

## 第 4 步：流水帳分析與收尾

1. 檢查 `data/runs/<時間戳>/battle_01.jsonl`：
   - `turns` 應 >1（相位斷點修正的實戰驗證）
   - 有 `tactical_map` 事件、`move` 事件的 basis 分布
     （enemy_arc/tacmap/threat_centroid/scout_hint 各佔多少）
   - `factions` 快照的 allies 數應隨戰局遞減（被打死）
2. 用流水帳做第一次戰後歸因（人工版）：我方在第幾回合開始減員、
   擊殺了幾台、standby 原因分布——寫成簡短結論。
3. 更新 docs/roadmap.md 暫停快照（裝置現況＋下一步），commit。

## 本場之後的既定順序（別跳步）

1. 戰後歸因 v1 程式化：先只分「數值差距 vs 程式缺陷」兩類。
2. cache 匯入機制（見 agent-architecture.md「內容 cache」節）：
   schema＋載入器＋黑板匯入＋未命中回退；試點 cache 用 HARD 2 面板
   截圖手抄（assets/screenshots/20260705-1538*.png、-154019.png）。
   注意：我方機體受養成影響，cache 只記身分/基礎資料，實數現場讀。
3. 敵方資訊面板 OCR：現場讀取→黑板→寫回 cache 的完整路徑；
   OCR 數字（戰力/資金/預期傷害）共用機制。
4. 戰略迴圈（強化＋farming）→ cache 建檔腳本（本地 LLM 只轉錄文字，
   數字一律 OCR）→ 最後才做 cache 校驗。

## 紅線提醒（違反=返工）

- 結束回合對話框永遠選左「待機並結束」，絕不選右邊自動戰鬥。
- 不寫任何關卡專屬資料進程式碼；跨執行不留關卡記憶。
- vision.py 的 HSV 閾值沒有截圖證據不准動。
- 連續兩次修不好同一個問題就停下來問使用者。
