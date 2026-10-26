# #109 第一版迴圈計畫

> Type: working—#109、#110、#111 在分支 `issue-109-stage-battle-loop` 上的計畫與執行清單；合併關閉 #109 前刪除

標記：［確認］＝使用者明確確認；［提案］＝Claude 提出，等使用者裁定；
［假設］＝沒有驗證的推測，附上來源。

用語：「loop agent」指跑關卡的 loop agent（#109，`src/ggge_ai_2/agent/loop.py`
的 `Agent`）。「錄影」指 `data/ui_recordings/20261014-234132`，「discovery」指
它底下的 `discovery/` 目錄。「標記」指 discovery 的 `run5/labels.jsonl` 與
`run6/labels.jsonl`（後面的列覆蓋前面的列）。

## 1. 目標與順序

- ［確認，2026-10-22］順序：
  1. 在本文件寫計畫：要辨識哪些畫面、轉移圖怎麼實作。
  2. 先做 LLM interpreter：用 Anthropic API key 呼叫 Haiku 辨識畫面。用它跑
     迴圈，測試 UiSim 的狀態轉移實作。
  3. UiSim 正確之後，改用 OpenCV 規則辨識畫面的 interpreter，用 UiSim 驗證
     OpenCV interpreter 的實作。
  4. 實作切成盡量小的單元，交給 effort medium 的 Opus 5.5 subagent 撰寫。
- ［確認］節點是 loop agent 能控制的 UI 狀態：可以從這裡選擇行動、走向目標
  畫面的錨點。loading 與展演畫面可以辨識，但是不能操作，所以是過場，不是節點。
- ［確認，2026-10-22］OpenCV interpreter 只辨識畫面元素，不讀懂畫面。先用
  共用元素縮小候選，再用差異元素決定是哪個畫面。
- ［確認］目的：確認規則、寫下規則。之後大量執行時只比對規則與觀察的差異。

## 2. 要辨識的畫面

### 2.1 重要節點（第一版辨識，17 個）

| 流程 | 畫面 |
|---|---|
| 選關 | `stage_chosen`、`series_list`、`series_stage_info`、`story_stage_list`、`sortie_prep` |
| 戰鬥 | `battle_info_preview`、`player_phase_overview`、`select_action_in_battle`、`select_weapon_in_battle`、`battle_prep_attack`、`battle_prep_response_attack`、`non_player_phase_battle_view`、`battle_main_setting`、`challenge_battle_check` |
| 結算 | `battle_score_result`、`exp_reward_result`、`drop_reward_result` |

選入的理由：loop agent 在主線上一定會停下來操作，或遊戲自己跳過去、要重新
辨識。`battle_main_setting` 是 #109 驗收 4 按「重試」的地方。
`challenge_battle_check` 在達成隱藏戰鬥條件時由遊戲跳出。

### 2.2 過場（只要認出「過場，等待」）

- `loading`：右下「Loading...」。
- 武裝動畫：右側有「SKIP」。［確認，2026-10-22］EX 武裝與設定播放動畫的一般
  武裝都有；沒看過的動畫 SKIP 是灰色，不能按。
- `simplify_weapon_anime`：沒有元素，認不出來就繼續等。
- `battle_clear_view`：中央「BATTLE CLEAR」。［確認，T11］當過場，loop agent 固定
  點空白處往下走。
- 戰鬥 HUD 被隱藏的幀：左上沒有「TURN n」框（見 2.4）。

### 2.3 延後辨識

第一版的主線不主動進去。出現時 interpreter 回傳 None，loop agent 停下並記錄差異。

- 戰鬥支線：`select_skill_in_battle`、`select_weapon_in_battle_response`、
  `battle_prep_detail`、`battle_settings_in_battle`、`win_condition_overlay`、
  `unit_detail` 群組。
- 選關支線：`ap_recovery_overlay`、`ap_recovery_item_check`（#109 不做 AP 補充）、
  `eternal_stage_list`、`event_stage_list`、`training_stage_list`、略過相關畫面、
  `roster_all_edit`、`reward_detail`、`stage_allow_list`、`damage_report`。

### 2.4 OpenCV interpreter 的元素

位置來自 discovery 的 run7、run9 按鈕框（691 幀、228 顆按鈕，比例座標）。

第一層：共用元素縮小候選。

| 元素 | 位置 | 候選 |
|---|---|---|
| 主導覽列，「關卡」選中 | 底部 | 選關 4 頁（不含 `sortie_prep`） |
| AUTO、▶▶、≡ 三鍵 | 右上 | 戰鬥類畫面；AUTO 開關也從這裡讀 |
| 「TURN n」框 | 左上 | 戰鬥地圖且 HUD 顯示中 |
| 大圓鈕 | 右下 | 選擇行動、選擇武裝、戰鬥準備（攻擊／應戰） |
| 視窗「關閉」 | 底部中央 | `battle_main_setting` 與延後的浮窗 |
| 結算「下一步」 | 右下 | `battle_score_result`、`exp_reward_result` |

第二層：差異元素。

- `stage_chosen`：沒有左上返回箭頭；「MAIN STAGE」卡片。
- `series_list`：返回箭頭；左下「CHALLENGE」「HISTORY STAGE」。
- `series_stage_info`：右下藍色方形「選擇」，「開發路線圖」在它左邊。
- `story_stage_list`：右下藍色方形「出擊準備」，位置和「選擇」相同；「開發
  路線圖」在右上。
- `sortie_prep`：沒有主導覽列；右下橘色「出擊」；右上「保存編制一覽」「編制
  詳情」「關卡詳情」。
- `battle_info_preview`：三鍵與下方「- TAP TO NEXT -」。
- 戰鬥地圖：左上標題的白字遮罩比對（下表）。
- `battle_main_setting`：「戰鬥選單」視窗，紅色「放棄」與「重試」。
- `challenge_battle_check`：紅色「WARNING」橫幅，底部「不挑戰」「挑戰」。
- `battle_score_result`：「TOTAL SCORE」與左下「損傷報告」。
- `exp_reward_result`：「REWARD」，沒有「損傷報告」。
- `drop_reward_result`：「REWARD」與右下「再次出擊」「選擇關卡」。

［確認，2026-10-22，資料歸納］戰鬥地圖的規則，以標記的穩定幀量測
（`discovery/scripts/battle_cues.py`、`discovery/scripts/title_masks.py`）：

1. 有「TURN n」框才讀標題。非我方回合穩定幀 69/69 有；非我方回合過場幀 63/72
   沒有，那些幀當過場。
2. 標題白字遮罩比對的結果：

   | 標題 | 畫面 | 對上 |
   |---|---|---|
   | 敵軍回合、隱藏軍回合 | `non_player_phase_battle_view` | 69/69，其他穩定畫面 0 幀誤認 |
   | 我軍回合 | `player_phase_overview` | 60/61 |
   | 單位移動 | `select_action_in_battle` | 115/115 |
   | 選擇武裝 | `select_weapon_in_battle` | 167/172 |
   | 戰鬥準備 -攻擊- | `battle_prep_attack` | 42/42 |
   | 戰鬥準備 -應戰- | `battle_prep_response_attack` | 16/16 |

3. 標題是「我軍回合」時看右上 ≡：亮是 `player_phase_overview`（AUTO 關 54/54）；
   暗是我方回合中的展演，等待。
4. 標題相同時看右下大圓鈕顏色（#108 的規則）：「戰鬥準備 -攻擊-」配藍色「行動
   選擇」是 `select_weapon_in_battle`（5 幀）；「戰鬥準備 -應戰-」配藍色是
   `select_weapon_in_battle_response`。

［假設］沒有解決的地方：AUTO 開時 `player_phase_overview` 的 ≡ 也是暗的（9 幀
全是 AUTO 開）；「第三軍回合」錄影裡沒有；#1113 對不上任何標題。

## 3. 轉移圖（UiSim）的實作

### 3.1 規則都寫在 `assets/ui_stages/stages.json`

［確認，T2］UiSim 只讀 `stages.json`。今天散在 discovery 的規則搬進去，discovery
只留證據：

- 每顆按鈕加 `rect`：run7、run9 按鈕框的中位數。
- 每個畫面加 `game_to`：沒有點擊、由遊戲決定的轉移。來源是
  `discovery/graph/edge_buttons.json` 中 `kind` 為「遊戲決定」且 `button` 為空的列。
- 頂層加 `caller_groups`：合併 `discovery/graph/caller_groups.json` 與
  `return_to_caller.json`。群組的出口回到打開群組的畫面。
- 每顆按鈕加 `deadline`（秒）：錄影中這條邊最長的 `gap` 乘上係數；沒有證據的
  按鈕用預設值。

### 3.2 `UiState`

［確認，T3］`UiState` 改成三個欄位：

- `screen`：新的畫面詞彙（3.5）。
- `caller`：打開目前群組的畫面，或 None。第一版只有 `battle_menu` 群組用到
  （`battle_main_setting` 的「關閉」回到打開戰鬥選單前的畫面）。
- `auto`：AUTO 開、關，或 None（不知道）。#109 驗收 4 要讀。

移除 `overlays` 與 `map_mode`：新詞彙用不同畫面表示地圖模式（`stages.json` 的
`kind` 是 `map_mode.*`）。

［確認，2026-10-22，T5］#111 要求的另外三個隱藏值（單位詳情最後開的分頁、
`battle_prep_detail` 的呼叫者、清單捲動位置）：先看 LLM interpreter 能不能從
幀上順便回答（E4）。答得出來的值就不延後。`battle_prep_detail` 的呼叫者用同一個
`caller` 欄位。

### 3.3 `Operation` 的產生

- 每顆有 `rect` 與 `to` 的按鈕產生一個 `Operation`：`gesture` 是 `rect` 中心的
  `UiTap`；`swipe_x`、`swipe_y` 是 `rect` 內的 `UiSwipe`；`deadline` 取自按鈕。
- `to` 裡的過場畫面往下解到可操作的畫面（同 `discovery/scripts/check_model.py`
  的 `resolve`）。每個解出的畫面是一個 `Outcome`。
- 進入群組：`Outcome.then.caller` 設為目前畫面。群組的出口：`then.screen` 是
  `state.caller`。
- `forbidden` 的按鈕不產生 `Operation`，它的 `rect` 進 `danger_band`。
- `dynamic` 的按鈕第一版用 `rect` 中位數的位置。［假設］單位卡片的中位數位置
  可能點到已經行動過的單位。

### 3.4 差分比對

- ［確認，T4］`Step.expected` 改成多個可接受的信念：`Operation` 的每個 `Outcome`，
  加上目前畫面的 `game_to`。觀察落在其中就算吻合。今天的單一預期在「開始
  戰鬥」這種多結果的按鈕上一定判成不吻合。
- ［確認，T4］加一種不觸控的 step「等待」：用在 `non_player_phase_battle_view`。
  loop agent 不送手勢，等到 deadline 再看畫面。
- `sync(state, observed)`：接受觀察到的畫面；`caller` 在群組內保留，離開群組
  清掉。不在預期內的觀察照樣接受，但是記成差異。
- 每一步記一列：幀序號、UiSim 的預期、interpreter 的結果、是否吻合。不吻合
  時存下那一幀（#109 驗收 2、3 的前半）。

### 3.5 畫面詞彙

- `Screen`（interpreter）與 `UiScreen`（UiSim）換成新詞彙，取代舊的 21 個畫面
  （#110 驗收 1）。兩者各自定義，loop agent 以值轉換。
- UiSim 的詞彙：選關與戰鬥流程的全部畫面，包含延後的畫面，因為轉移資料一起
  產生。interpreter 的詞彙：2.1 的 17 個畫面。
- ［提案］interpreter 另外回傳「過場」：`Situation` 加一個欄位表示過場，loop
  agent 收到過場時不規劃、不行動，直接再看下一個穩定畫面。

## 4. Interpreter

### 4.1 合約

- ［提案］`interpret(frame, candidates)`：loop agent 從信念與 UiSim 推出候選畫面
  傳進來（#110）。結果在候選外時記成模型差異。
- `Situation` 加 `auto`（AUTO 開或關）與過場欄位。

### 4.2 LLM interpreter（先做）

- 呼叫 Haiku（`claude-haiku-5-5`），用官方 Python SDK `anthropic`（新的依賴，
  ［確認，T9］要測試時使用者準備好）。
- API key：在 tmux 的行程裡用 `set -a; . ~/.config/ggge_ai/anthropic.env; set +a`
  載入成 `ANTHROPIC_API_KEY`。程式不讀檔、不印出 key。
- 提示：17 個畫面的 `zh` 與 `description`（取自 `stages.json`，用 prompt caching），
  加上候選畫面；幀縮小後送出；回答固定成 JSON：畫面名稱、AUTO、是否過場。
- 回答不在詞彙內、或回答不知道：回傳 None。每次的原始回答寫進記錄。
- ［假設］費用：一關約 300 次辨識，每次一張縮小的圖加上快取的提示。

### 4.3 OpenCV interpreter（UiSim 驗證後做）

- 每個元素一個偵測函式（2.4 第一層、第二層），各自用標記的穩定幀測試：該出現
  的畫面都偵測到，不該出現的畫面都沒有。
- 規則樹組合元素，輸出畫面。
- 離線檢查：對標記算一致率（#110 驗收 4）。
- 實機：同一套 UiSim 與差分記錄，換成 OpenCV interpreter 跑。［提案］同時讓
  LLM interpreter 在背景辨識同一幀，記下兩者不同的幀。

## 5. 跑實機需要的其他部分

- Actuator：`adb shell input tap/swipe/keyevent`，碰到 `danger_band` 就丟
  `GestureBlocked`，有逾時。
- Stream：`adb exec-out screencap -p` 輪詢；畫面固定一段秒數不變才算穩定。
- 計畫控制：選關用 `UiShiftPlan` 走到目標畫面；結算一路「下一步」，最後按
  「選擇關卡」回 `story_stage_list`。
- ［確認，2026-10-22］戰鬥先用暫時的貪婪策略（和 #105 的戰鬥計畫重疊，這裡只是
  測試用）。［提案］貪婪的定義：每一步選眼前就有進展的選項，不讀地圖、不比較
  武裝，用遊戲預選的武裝與目標。

  | 畫面 | 按鈕 |
  |---|---|
  | `battle_info_preview` | AUTO 開就先關，再點空白處 |
  | `player_phase_overview` | 第一張單位卡片 |
  | `select_action_in_battle` | 「選擇武裝」（不移動直接攻擊） |
  | `select_weapon_in_battle` | 「攻擊」；畫面沒變就「待機」 |
  | `battle_prep_attack` | 「開始戰鬥」 |
  | `battle_prep_response_attack` | 「開始戰鬥」 |
  | `non_player_phase_battle_view` | 等待 |
  | `challenge_battle_check` | 「挑戰」 |

- 執行腳本：`scripts/run_loop_v2.py`，`--interpreter llm|cv`，記錄寫到
  `data/runs/<timestamp>/`。
- 這個計畫先不做：#109 驗收 3 的 LLM 稽核抽樣、驗收 5 的停留上限與詢問 LLM、
  驗收 6 的錄影重播測試（最後單獨提交）。

## 6. 實作單元

每個單元一個職責、一個提交。完成條件都包含：`uv run pytest tests/ggge_ai_2 -q`
全部通過；`uv run pyright` 零錯誤；註解只寫 why 與 warning。

### A. 規則資料（主 session 與使用者一起做，不交給 subagent）

- A1. `stages.json` 加 `rect`、`game_to`、`caller_groups`、`deadline`（3.1）。
- A2. 補主線按鈕缺的 `to`：「重試」「放棄」「不挑戰」（T7）。

### B. 合約

- B1. `Screen` 與 `UiScreen` 換成新詞彙（3.5）。
- B2. `UiState`、`Observed`、`Situation` 的欄位（3.2、3.5、4.1）。
- B3. `Step.expected` 改成多個；加「等待」step（3.4）。
- B4. loop agent 處理過場與等待；候選畫面傳給 interpreter。

### C. UiSim

- C1. 讀 `stages.json` 成記憶體中的圖。測試用小的假 JSON。
- C2. `successors`、`advance`：按鈕到 `Operation`，過場往下解。
- C3. `caller` 的進出。
- C4. `sync`、`danger_band`、`predecessors`。
- C5. 離線檢查：重播標記的造訪順序，每一步都是 UiSim 允許的轉移（#111 驗收 4）。
  標記不在時跳過。

### D. 裝置與記錄

- D1. adb Actuator。
- D2. adb screencap Stream。
- D3. 每步記錄與差異幀。

### E. LLM interpreter

- E1. 由 `stages.json` 組提示。
- E2. 呼叫 API，解析成 `Situation`。
- E3. 離線抽查：標記中每個重要畫面取幾幀，算一致率；有費用上限。
- E4. 隱藏值（T5）：讓 LLM interpreter 順便回答單位詳情的分頁與清單捲動位置，
  用標記的幀檢查答得對不對。

### F. 計畫控制與實機

- F1. 選關與結算的目標。
- F2. 戰鬥貪婪策略（T6、T8）。
- F3. AUTO 檢查（#109 驗收 4）。
- F4. 執行腳本。
- F5. 用 LLM interpreter 跑實機，差異給使用者判，修 UiSim 或規則，重跑。
  （主 session 與使用者）

### G. OpenCV interpreter

- G1–Gn. 每種元素一個單元（2.4），各自有標記測試。
- G-rules. 規則樹。
- G-check. 對標記的一致率（#110 驗收 4）。
- G-run. 用 OpenCV interpreter 跑實機，與 F5 同一套差分記錄。

## 7. 裁定

［確認，2026-10-22］使用者沒有提到的項目照提案做：T2、T3、T4、T10、T11。

| 編號 | 題目 | 裁定 |
|---|---|---|
| T1 | `stages.json` 何時進版控 | ［確認］直接進版控。#108 的模型依 3.1 記在 `stages.json`（［提案］） |
| T2 | `stages.json` 加的四個欄位（3.1） | ［確認］照提案 |
| T3 | `UiState` 換欄位、移除 `overlays` 與 `map_mode`（3.2） | ［確認］照提案 |
| T4 | 多個預期與「等待」step（3.4） | ［確認］照提案 |
| T5 | #111 的三個隱藏值 | ［確認］先看 LLM interpreter 能不能順便回答。答得出來的值就不延後。［假設］`battle_prep_detail` 的呼叫者從幀上看不出來（#108），只能靠 `caller` |
| T6、T8 | 戰鬥策略、`challenge_battle_check` 的選擇 | ［確認］先暫時實作貪婪策略（第 5 節的表） |
| T7 | 「重試」「放棄」「不挑戰」的 `to` | 待補：先找錄影的證據；找不到的由 F5 的實機差異補 |
| T9 | `anthropic` 依賴與新 key | ［確認］要測試時使用者準備好 |
| T10 | 提交流程：subagent 實作與測試，主 session 審過後用 `/commit-message` 提交；使用者在每組（A–G）結束時審 | ［確認］照提案 |
| T11 | `battle_clear_view` 當過場並固定點空白處（2.2） | ［確認］照提案 |

## 8. 進度

| 組 | 狀態 | 提交 |
|---|---|---|
| A 規則資料 | A1 完成；A2 錄影沒有證據，由 F5 補 | `b9350d7`、`9d86830` |
| B 合約 | 完成 | `5ecf120`..`7ce5470` |
| C UiSim | 完成 | `ff8bb1b`..`ed4a940` |
| D 裝置與記錄 | 完成 | `504d1bf`..`ddb7b3d` |
| E LLM interpreter | 完成。E3：重要畫面 174/178；AUTO 改用像素判斷（E2b）。E4：分頁讀得出來，捲動位置讀不出來 | `a92c309`、`f601144`、`f9e8922`、`2c028a2` |
| F 計畫控制與實機 | F1–F4 完成（F3 的 AUTO 檢查併在 F2 的貪婪策略裡）；F5 等使用者的 key | `851ca1a`、`e447eff`、`265a4e0` |
| G OpenCV interpreter | 未開始（F5 驗證 UiSim 之後） | |

### 8.1 實作時的裁定（Claude 決定，使用者審查時可以改）

- 過場畫面是 interpreter 的畫面名稱；loop agent 把信念標成過場，反射動作等待，或在
  `battle_clear_view` 點畫面中央。
- 遊戲決定的轉移是 UiSim 的「等待」操作（沒有手勢），結果包含留在原畫面。
- AUTO 只帶進有 AUTO 按鈕的畫面；AUTO 按鈕產生切換操作。
- ［假設］五顆按鈕的位置是目測量的（`9d86830`）。
- ［提案］錄影重播剩下的 6 步列為已知的取樣落差，都在 #109 不做的流程（`ed4a940`）。
- 計畫控制不記進度：執行腳本分兩段，先以 `drop_reward_result` 為目標，再以
  `story_stage_list` 為目標。
- 「攻擊」連續 3 次沒有讓畫面改變，就改按「待機」。
- LLM interpreter 拒答、回答讀不出來、回答不是畫面名稱，都當成沒認出畫面（`None`），
  不讓實機跑中斷。回答的 JSON 先寫 `reason` 再寫 `screen`。
- `anthropic` 只裝在專案的 `.venv`（`f601144`）。
- ［確認，2026-10-24］AUTO 不問 LLM：Haiku 會把旁邊永遠是藍色的快轉鈕當成 AUTO，
  約五分之一的手動幀答成自動。改量 AUTO 按鈕內的藍色比例（閾值 0.2），
  415 幀標記對 414 幀；錯的是剛點擊時的回饋幀 #504（`2c028a2`）。
- ［確認，2026-10-25］AUTO 有三種模式：藍色全自動、紅色半自動（我方回合手動，
  敵方回合的應戰自動）、白色透明全手動。點一下照藍 → 紅 → 白循環。正常執行要維持
  全手動，`AutoOffPlan` 點到白色才確認。起因：實機第五輪
  （`data/runs/20261025-165717`）點一下從藍變紅，舊的像素判斷把紅色讀成關，
  整場戰鬥停在半自動。紅色比例的閾值 0.4 只用這一輪的 7 幀和錄影的 #503 校正；
  兩種模式的標記把 #503（紅色）標成手動。三種模式定義在 uisim（`UiAutoMode`），
  信念、`AutoOffPlan`、loop 都用這份定義；interpreter 保留自己的 `AutoMode`，由 loop
  轉換。
- 待處理（2026-10-25，使用者決定先不處理）：信念不知道 AUTO 模式時，進入有 AUTO 按鈕
  的畫面會預期 None，第一次讀到 AUTO 就對不上一次（第五輪第 18 週期）。敵方回合
  interpreter 給 None，`uisim.sync` 照抄，回到 `player_phase_overview` 也會對不上。
  ［提案］不知道模式時 uisim 給三個模式各一個結果；`sync` 讀到 None 時沿用上一個模式。
- E4（T5）：單位詳情的分頁 Haiku 讀得出來（標記的三個分頁 33/33，另 4 幀是
  「單位設置詳情」視窗的「組合資訊」分頁，標記沒有分開）。清單捲動位置讀不出來：
  同一個捲動位置一次答 top、一次答 bottom。捲動位置照 #111 延後。
- ［確認，2026-10-24］省電畫面（`power_save_lock`、`power_save_dim`）是要辨識的畫面，
  原計畫漏列。由像素規則在問 LLM 之前判斷：灰階平均 ≤ 40 且有鎖頭圖示是鎖定，
  平均 < 20 是暗屏；符合就不問 LLM。G 組沿用。
- ［確認，2026-10-24］畫面穩定的條件是連續兩幀的辨識結果（畫面與 AUTO）相同，
  不再用像素靜止（`b347c17`）。
- 案例（2026-10-24，實機第三輪 `data/runs/20261024-182741`）：編隊有不符合關卡標籤的
  單位時，按「出擊」被遊戲拒絕，畫面中央跳出提示「編制內含有不符合標籤的角色。」
  約 0.5 秒，畫面留在 `sortie_prep`。提示比兩幀一致的辨識還短，迴圈看不到，只看到
  「出擊」沒有效果。提示幀從錄影擷取，有壓縮，存在
  `data/datasets/sortie_rejected_20261024/`（含 `labels.jsonl`，不進版控）；重現
  後直接截圖的難度高，暫不補原始截圖。

### 8.2 計畫與 plan controller 成套（2026-10-25）

起因：實機第四輪（`data/runs/20261024-183527`）讀到 AUTO 開著，但 AUTO 沒有被關掉。
`StagePlanController` 借用 `DefaultPlanController` 那一套的 `UiShiftPlan` 和
`ReflexPlan`；`UiShiftPlan` 進戰鬥後仍然有效，放著「先關 AUTO」的貪婪策略一直沒被選到。

- ［確認］`Plan` 和 `PlanController` 的約定太寬鬆，零件可以隨意混用。每個 plan
  controller 配一套自己的計畫，不拆開混用。`PlanController` 改成泛型
  `PlanController[P: Plan]`，由 pyright 擋住混用。
- ［確認］`contract.py` 只放迴圈依賴的介面（`Plan`、`PlanController`、`Step`），
  各套實作都要符合。`Plan` 的約定寫在 `contract.py`：`still_valid` 是前置條件，
  沒有副作用；`next` 每週期最多呼叫一次，只在 `still_valid` 為真之後呼叫；
  `expected=()` 代表這一步不建立預測。
- ［確認］`Reflex` 和 `ReflexPlan` 只是 `DefaultPlanController` 那一套的內部介面，
  移出 `contract.py`。舊 `replan-main-loop.md` §5.12.18「plan controller 把 reflex
  固定注入計畫」只適用於這一套（`7781192` 刪除該文件）。
- ［確認］通用計畫只實作 `Plan`：`PowerSaveLockPlan`、`PassingWaitPlan`、
  `TapToContinuePlan`、`AutoOffPlan`。哪一套要用，哪一套自己轉接。各套可能忘記
  整合通用計畫，這個代價接受，靠各套的測試覆蓋。
- ［確認］`StagePlanController` 產生自己的 `StagePlan`，順序寫在 `StagePlan` 裡：
  省電鎖定 → 過場 → AUTO 關閉 → 戰鬥畫面走貪婪策略，其他畫面走 UI 路徑。
  共用的是純函式（最短路徑、操作轉成 step），不是別套的計畫物件。
- ［確認］`AutoOffPlan` 的三個狀態記在 `AutoOffPlan` 自己的欄位，不寫進信念：
  `UNTOUCHED`（當前關卡的戰鬥中沒有開過 AUTO，通常整場維持）、
  `PENDING(at)`（在 `at` 按了關閉，等確認）、`CONFIRMED`（曾經關閉並確認）。
  狀態轉換的邏輯都在 `AutoOffPlan` 自己的實作裡。確認後由 think 決定接下來的策略；
  目前沿用貪婪策略。之後戰鬥計畫判斷 lost sync 時讀這個狀態。
- ［確認］history 裡的 `AutoOffPlan` 是複製的物件。

待處理（不在這次的範圍）：

- `review` 是命名失誤：它的實際用途是把計畫和信念記進 history。迴圈也沒有把
  計畫結束的原因（達成目標、連續對不上、計畫失效）傳給 plan controller。
- 過場跳過比對、對不上的次數上限、讀不到畫面時停手，這些規則留在迴圈裡；
  過場屬於信念的合約，之後再整理。
- history 是 plan controller 的狀態，卻放在迴圈裡；一次執行跨越多個關卡時，
  誰在新戰鬥開始時重設 `UNTOUCHED`，還沒有定。
