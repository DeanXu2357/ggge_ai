# ggge_ai 專案守則（每次工作前先讀）

自動化通關 SD Gundam G Generation ETERNAL（USB 實機 R5CRC37JBYJ，
橫向 2340x1080）。GOAP 雙層架構，Python 3.12+/uv，OpenCV 模板視覺。

## 開工順序（不可跳過）

1. 讀 `docs/roadmap.md` 最上方的暫停快照——那裡有裝置現況與恢復點。
2. 讀 `docs/agent-architecture.md`——架構紅線都在裡面。

## 架構紅線（使用者定案，違反=返工）

- **程式只內建機制，不內建內容**：關卡敵方數值、能力、範圍從畫面讀取，
  禁止寫死在程式碼。例外（2026-07-05 使用者修訂）：允許 `data/cache/`
  的「感知記憶化」內容 cache——來源必須是畫面讀取或人工轉錄的面板截圖，
  畫面永遠是權威，未命中/校驗失敗退回現場讀取。我方機體受養成影響，
  cache 只記身分與基礎資料，實際數值一律現場同步。
- **學到的信念跨執行無狀態**：黑板（RunBlackboard）只活在單一 process
  內；流水帳檔（data/runs/）只供工程分析，禁止當下次執行的先驗。
- **戰鬥必須由我們的程式操作**：結束回合對話框永遠選左邊「待機並結束」
  (997,562)＋執行 (1365,850)；**絕不選右邊自動戰鬥選項**（會把單位交給
  內建 AI）。
- 手機的圖形鎖是使用者刻意保留的，**不要嘗試關閉**。

## 視覺辨識避坑

- **主對話絕不用 Read 直接讀截圖/圖片**：圖片不得進入主對話上下文（token
  貴且污染後續每一輪）。需要目視判讀時一律開 subagent 讀圖，subagent
  只回傳文字描述，圖片留在子代理上下文。驗證優先用模板/像素探針/分類器，
  親看只留給新畫面與異常診斷（見 memory screenshot-cost-discipline）。
- 敵我判斷=單位腳下 HP 弧顏色：紅=敵、藍綠=第三方、藍=我方。
  `battle/vision.py` 的 HSV 帶域（S 100-210、V 155-255）是用實測截圖
  調出來的，**沒有新截圖證據不要動閾值**；動閾值的 PR 必須讓
  `tests/test_vision_regression.py` 全庫通過，且新增至少一個暴露該回歸的
  fixture（`scripts/curate_fixture.py`，見 #18）。
- 已知反例（2026-07-09 實測，見 `tests/fixtures/vision/hp_arc/
  our_turn_hub_pink_bug.*`）：閾值的敵方紅校準來源是「敵方回合」畫面，
  但控制器實際掃描發生在「我方回合、選單位」的 hub 畫面——這個畫面下
  未行動我方單位的弧線色相跟敵方紅幾乎相同，`find_ally_units`/
  `find_enemy_units` 在此狀態系統性誤判（0 我方、多個假敵方）。尚無足夠
  hub 畫面樣本重新校準，修前先讀 fixture 的 note 欄位。
- TM_CCOEFF_NORMED 兩個坑：會透過變暗的覆蓋層比對成功（鎖屏時模板照樣
  match）；在深色均勻區域會亂匹配高分。
- 幫 hp_arc 這類像素級色彩/形狀判斷建 fixture 時用 PNG 不要用 JPEG：
  JPEG 壓縮在色相/形狀 gate 的邊界會翻轉 blob 分類，且對品質不單調
  （q85/90/95 都會出現壓縮偽影誤判，q92/98 又乾淨，2026-07-09 實測）。
  模板比對類 fixture（分數差距通常 0.6 以上）JPEG q85 沒問題。
- 回合會**自動推進**（全單位行動完就進敵方回合，結束回合對話框不會出現），
  回合邊界用畫面上 TURN 數字的變化偵測（controller 在 `_on_our_turn` 比對
  `turn_marker`），別依賴對話框，也別數「無 label 的安靜幀」——攻擊動畫
  期間同樣會出現無 label 段落（2026-07-11 移除 `_phase_break` streak 的原因）。
- 別假設畫面會靜止：有些地圖有常駐環境動畫（雪地圖實測閒置 frame_diff
  0.016-0.024，永遠高於舊 is_static 閾值 0.015），任何「等畫面靜止再動作」
  的 gate 都會在這種地圖上永久卡死。判斷可操作性用相位 label probe（連續
  兩次一致才信），等待動畫結束用「label 回來或幀靜止」雙出口。
- 戰鬥中劇情會把 MENU 鈕左移，用 `vision.locate_story_menu` 自由位置比對，
  別用固定座標。

## 開發紀律

- 小步提交；`uv run pytest -q` 與 `uv run ruff check src tests scripts`
  全過才 commit。改 `battle/vision.py`、`battle/controller.py` 要附驗證
  證據（實機截圖或流水帳）。
- 同一個問題連續兩次嘗試失敗就停下來問使用者，不要繼續瞎試。
- 每次收工：更新 `docs/roadmap.md` 暫停快照（裝置現況＋恢復點）再 commit。
- commit 訊息附 Co-Authored-By 與 Claude-Session trailer（沿用 git log 慣例）。
- 只用繁體中文與使用者溝通，禁用簡體中文。程式碼不寫多餘註解。

## 常用指令

- 截圖：`uv run python scripts/capture.py`（存 assets/screenshots/，gitignored）
- 手動接管當前戰鬥：`uv run python scripts/run_manual_battle.py`
- 完整通關迴圈（從關卡列表）：`uv run python scripts/run_clear_loop.py`
- 流水帳輸出：`data/runs/<時間戳>/battle_NN.jsonl`（gitignored）
- 模板驗證：`scripts/verify_match.py`、裁切：`scripts/crop.py`
