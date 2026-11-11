# #109 第一版迴圈計畫

> Type: working—#109、#110、#111 的計畫與執行清單；合併關閉 #109 前刪除

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

［假設］沒有解決的地方：AUTO 開時 `player_phase_overview` 的 ≡ 也是暗的（9 幀
全是 AUTO 開）；「第三軍回合」錄影裡沒有；#1113 對不上任何標題。

## 4. Interpreter

### 4.2 LLM interpreter

- API key：在 tmux 的行程裡用 `set -a; . ~/.config/ggge_ai/anthropic.env; set +a`
  載入成 `ANTHROPIC_API_KEY`。程式不讀檔、不印出 key。

### 4.3 OpenCV interpreter（UiSim 驗證後做）

- 每個元素一個偵測函式（2.4 第一層、第二層），各自用標記的穩定幀測試：該出現
  的畫面都偵測到，不該出現的畫面都沒有。
- 規則樹組合元素，輸出畫面。
- 離線檢查：對標記算一致率（#110 驗收 4）。
- 實機：同一套 UiSim 與差分記錄，換成 OpenCV interpreter 跑。［提案］同時讓
  LLM interpreter 在背景辨識同一幀，記下兩者不同的幀。

## 5. 跑實機需要的其他部分

- 這個計畫先不做：#109 驗收 3 的 LLM 稽核抽樣、驗收 5 的停留上限與詢問 LLM、
  驗收 6 的錄影重播測試（最後單獨提交）。

## 6. 實作單元

每個單元一個職責、一個提交。完成條件都包含：`uv run pytest tests/ggge_ai_2 -q`
全部通過；`uv run pyright` 零錯誤；註解只寫 why 與 warning。

### A. 規則資料（主 session 與使用者一起做，不交給 subagent）

- A2. 補主線按鈕缺的 `to`：「重試」「放棄」「不挑戰」（T7）。

### G. OpenCV interpreter

- G1–Gn. 每種元素一個單元（2.4），各自有標記測試。
- G-rules. 規則樹。
- G-check. 對標記的一致率（#110 驗收 4）。
- G-run. 用 OpenCV interpreter 跑實機，與 LLM interpreter 的實機用同一套差分記錄。

## 7. 裁定

| 編號 | 題目 | 裁定 |
|---|---|---|
| T7 | 「重試」「放棄」「不挑戰」的 `to` | 待補：先找錄影的證據；找不到的由實機的差異補 |
| T10 | 提交流程：subagent 實作與測試，主 session 審過後用 `/commit-message` 提交；使用者在每組（A–G）結束時審 | ［確認］照提案 |

## 8. 進度

| 組 | 狀態 | 提交 |
|---|---|---|
| A 規則資料 | A2 錄影沒有證據，由實機補 | |
| G OpenCV interpreter | 進行中：快速判斷的第一批（§8.6） | |

### 8.1 實作時的裁定（Claude 決定，使用者審查時可以改）

- ［假設］五顆按鈕的位置是目測量的（`9d86830`）。
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
- ［確認，2026-10-26］已標示資料集 `data/labeled/` 是人工判定的正本，直接編輯，沒有
  腳本重建。每一幀記 `screen`、`transition`、`auto`、`power_save`。`auto_cue` 與
  `power_save_cue` 的函式測試逐案例讀這份資料集。
- 沒做完的功能（2026-10-26，使用者裁定測試保持失敗）：
  - 點擊回饋：#504 的白色 AUTO 按鈕上疊著藍色點擊特效，`auto_cue` 讀成全自動。
  - 暗的 loading：#1745–#1747 的灰階平均 9.8–11.1，低於暗屏門檻 20，
    `power_save_cue` 讀成暗屏。［假設］實機遇到時迴圈會點畫面上方中央喚醒螢幕。
- 清單捲動位置 Haiku 讀不出來：同一個捲動位置一次答 top、一次答 bottom。
  捲動位置照 #111 延後。
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

### 8.3 地圖的單幀識讀（MG2，2026-10-26 至 10-27）

- ［確認］可識別格子：整格在畫面內、在地圖內、沒有被 HUD 蓋到的格子，範圍不必是長方形。
  可識別格子外框的左上角是 (0, 0)；其他格子不編號，不放進 `MapReading`。
- ［確認］單幀沒有陣營。單位只有 `controllable`（頭上的透明箭頭）和 `selected`（藍色選取圈）。
  單位記 `pos`、`size`（畫面上占住的長方形），不是長方形時另記其餘的格子。
  能從哪幾格選到單位，要點擊才知道，不屬於單幀。
- ［確認］測試分兩層。嚴格層：格線、可識別格子、地圖邊界，與判讀完全相等。
  容錯層：單位與標記。漏讀、多讀、兩台讀成一台，可以靠移動、選攻擊目標或特意點擊
  修正，所以單幀允許這些誤差；容錯層的判定方式等單位的修復完成後再定。
- ［確認］迴圈只放通用的流程。暫定進入關卡後，每一幀都交給 mapparser 解析；
  哪些畫面讀得出地圖資訊（例如只讀我方回合的地圖畫面）屬於 mapparser 的內部實作，
  迴圈不判斷。
- ［確認］測試只讀使用者判讀過的案例（`data/labeled/cases.jsonl` 的 `map` 欄位），
  只檢查函式自身一致性的測試不再保留。

### 8.4 探查地圖與 mapgeom（2026-11-01，討論中）

- ［確認］mapparser 判讀的可信程度分三級，另有單幀讀不到的資訊：
  - 甲：可識別格子、地圖邊界、`locate`。這是整張格線的模擬結果，要嘛全對、要嘛全錯，
    很難只對一部分。程式修到一定的正確率後就相信它，並以它為依據讀出丙。
  - 乙：`controllable`、`selected`。簡單的固定圖案辨識，有機率出錯，但正確率極高。
  - 丙：單位、佔用格、M/T/W。最不穩定。
  - 丁：單幀讀不到：陣營、單位內容、地形、從哪幾格選得到單位、伸出可識別範圍的物件的
    完整大小。
- ［確認］辨認關卡的目的是填入足夠的資料，讓 battle engine 可以開始運作，包括我方部隊的
  初始位置。關卡資料要能建檔、載入與儲存。
- ［確認］流程：戰鬥開始後，map sync planner 用 mapgeom 探查初始地圖，統合出最初的地圖
  狀態，匯入 battle engine，再交給戰鬥的 planner 和 battle engine。這段過程不下第一手。
- ［確認］mapgeom 只在探查地圖階段工作：整合多個 `MapReading`，拼出完整地圖並提供評估。
  怎麼達成評估是 map sync planner 的策略。
- ［確認］探查結束後，`MapReading` 是權威，battle engine 輔助判斷辨識結果是否合理。
  戰鬥內容是否和建模脫鉤，依據 mapparser 的判讀和 battle engine 判斷，不經過 mapgeom。
- ［確認］M/T/W 是 battle engine 差分比對的證據，mapgeom 不需要。
- ［確認］探查地圖保存證據，不保存合併後的結果。證據有兩種：每一幀的 `MapReading`
  與它的對位，以及探查紀錄（送出的動作與結果）。之後的視角可能推翻先前的對位，
  只有保留原始證據才能重新合併。
- ［確認］證據從 history 取得。history 每週期記一筆：這一週期的感知（含完整的
  `MapReading`）與交付執行的 step，取代 `review` 現在記的內容。mapgeom 是無狀態的
  模型，自己定義證據的輸入結構；map sync planner 從 history 取出探查開始以後的紀錄，
  轉成這個結構交給 mapgeom。`Belief.update` 不再呼叫 mapgeom。
- ［確認］滑動手勢不精確（手機延遲會推多或推少），所以不預測滑動量，改為量出結果：
  手勢只負責大致的方向，滑動後的那一幀由 mapgeom 依錨點重新對位，手勢向量只當弱先驗。
  錨點依可信程度：地圖邊界（甲）、填色標記、單位分布（丙）。滑動距離要留餘量，
  讓推多時錨點仍在畫面內，這是 map sync planner 的策略。
  - 填色標記沿用舊系統的經驗（`docs/how-to/live-loop-pitfalls.md` 第 9 至 13 條）：
    點空格出現填色，用它量推鏡後的位移。同一份文件也記錄了省電鎖會吞掉手勢、
    推不動不代表到了地圖邊界。
- ［確認，2026-11-10，取代 2026-11-01 的三種回覆與單位的四個狀態］mapgeom 的輸出
  只有整合結果，不輸出中間狀態：
  - mapgeom 拼合多個 `View`，以閾值解決矛盾。輸出是整張地圖上確定的內容，以及
    不確定的地方。確定有、確定沒有只是資料的內容。
  - 矛盾、不完整等狀態仍然存在於 mapgeom 內部。在閾值以下、無法判斷一致的內容，
    在輸出中當作沒有資料。
  - planner 朝沒有資料的地方探索，取得更多資料，補完整個輸出結果。
  - 往哪裡探索是 planner 的決策，不在 mapgeom 的輸出中。
  - 閾值屬於實作，不在合約中。合約只承諾：輸出中的內容都已經超過閾值。
  - 輸入是依時間順序排列的 `View` 序列。輸出要寫出最後一張 `View`（目前畫面）在
    地圖上的範圍，讓 planner 知道相對關係；也要寫出地圖的大小、關卡、回合等資訊，
    並且能表示還不知道整張地圖大小時，已經拼出的部分。
  - 關卡的資訊也由 `View` 提供。mapgeom 從 `View` 中挑出可以確定的關卡資訊拼湊。
  - 座標的原點是目前判準一致的拼合成果的左上角，和 mapparser 判讀的座標系相同。
    例：四張圖（右上、右下、左上、左下）拼成整張地圖的情境，只持有右下、左下兩張
    並判準可以接合時，y 軸沒有邊界資訊，原點仍是這兩張拼合成果的左上角。
  - 不是每次輸入都產生 `MapJudgment`。`View` 序列無法拼出閾值以上一致的成果時，
    mapgeom 回傳 None，表示不足以辨識出成果。
  - 選哪一群拼合成果，合約不規範。第一版實作的規則，要寫成程式碼的註解：
    - 一律輸出包含最後一張 `View` 的那一群，包括最後一張單獨成群的情況。
    - 最後一張的對位沒有超過閾值、不屬於任何一群時，輸出前面的成果，目前畫面的
      範圍標成不知道。
    - 只有一張 `View` 時，直接把它轉成 `MapJudgment`。
  - `View` 的格子與單位沿用 mapparser `CellReading`、`UnitReading` 的做法，但在
    mapgeom 自己的合約中另外定義結構。
  - `MapJudgment` 提供單位資料的列表。每個 `MapUnit` 帶自己的 unit id，unit id 只在
    當次的 `MapJudgment` 中有效。
  - 先移除舊合約（`align`、`merge`、`KnownMap`）的引用，維持目前實作的功能，再定義
    新合約。
- ［確認，2026-11-10］`MapReading` 另外存在 `MapReadingHistory` 物件，放在 agent 的屬性中。
  每次 `Sensed` 拿到 `MapReading` 就 insert 一筆。大量紀錄要 aggregate 還是怎麼處理，之後再做。
- ［確認］甲乙丙只存在 mapgeom 內部。判準：只隨證據改變的內容屬於 mapgeom；
  會隨策略改變的內容屬於 map sync planner（先後、手勢、點哪裡）。
- ［確認］出擊隊伍在進入關卡前設定，agent 自己把隊伍記在 belief。設定隊伍的操作流程
  還沒寫完；為了先跑通戰鬥迴圈，暫時手動設定隊伍，再把隊伍資料寫入 belief。
- ［確認］敵方單位的資料（陣營、單位內容）是同步階段探查關卡時要取得的資料。
  為此要新增查看單位詳細的流程。
- ［確認，2026-11-10］mapgeom 的合約和實作分開：
  - 合約是通用的介面：從多個 `View` 拼出整體結果。合約不記錄可信度，也不帶分數。
  - `View` 是 mapgeom 自己定義的結構，不是 history 的紀錄：回合數、phase、
    部分地圖的範圍、邊界、單位佔據的格子、無法辨識或被 UI 擋住的格子。
    map sync planner 把 mapparser 的結果轉成 `View` 交給 mapgeom。
  - 實作決定歷史 `View` 中哪些內容比較可信。目前的實作以 OpenCV mapparser 為前提：
    格線模型要多個條件同時成立才會建立，所以要嘛全對、要嘛全錯；邊界由格線模型的
    結果推出，也有一定可信度。這條依賴鏈記錄在實作裡。
  - 點擊、填色標記、建檔的關卡資料也都是 OpenCV 讀出的離散觀察，不是已知事實：
    離散的觀察無法確定行動的結果和意圖一致。
  - 格子大小不固定。格子大小由 mapparser 解讀，`View` 只用格號。
- 待做：mapparser 辨識點擊空格後的填色標記，和地形的讀取一起做。滑動後的對位依賴
  填色標記；兩者目前都還沒有實作，要新增判讀案例驗證。
- 未定：`init` 的 `victory`、`events`、`rules`、`deploy_cells` 不在地圖上，來源未定。
- 延後到下一階段：戰鬥中的對位（世界格號與畫面格號互換）。它不依賴 mapgeom，
  因為參照物是 battle engine 的盤面，不是多幀拼合。
  - ［提案］看得到地圖邊界的那一軸，用甲直接定位。
  - ［提案］有選中單位時，用乙：battle engine 知道這台單位的世界格號，畫面格號由
    `selected` 讀出，兩者相減就是位移。
  - ［提案］兩者都沒有時，拿丙的單位分布對照 battle engine 的盤面。
  - ［確認］mapparser 只能做畫面格號與點擊點互換（`locate`），它沒有地圖模型，
    單靠它不足以對位。

### 8.5 查看單位詳細與 statechart 版 uisim（2026-11-02）

- ［確認］順序：查看單位詳細的流程 → history 的形狀 → 填色標記與地形。OpenCV
  interpreter（G 組）提高優先級：要有確定性的畫面判斷，往下實作的成本才低。
- ［確認］查看單位詳細走戰鬥選單 →「部隊資訊」→ 卡片 →「單位設置詳情」。轉移
  草圖（`discovery/graph/graph.json` 的「閱讀單位」）已有每一段的幀證據：
  #544→#545→#547、#549→#550，不需要補錄。`stages.json` 缺的位置與 `to` 是轉錄
  時漏掉的。「敵軍」分頁沒有幀；辨識簡單、入口和我軍清單相同，之後補案例。
- ［確認］interpreter 只回報畫面名，畫面名是 uisim 的葉節點。`roster_list` 拆成
  我軍、敵軍兩個畫面名。
- ［確認］uisim 只保存關係，不保存狀態。堆疊放在 `UiState`，由外部傳入，
  `advance` 與 `sync` 回傳新的值；結果和從 history 重算相同。
- ［確認，2026-11-03］uisim 用自己的模型：`ChartUiSim`（`uisim/chart_sim.py`），
  型別在 `uisim/chart.py`，定義是 `uisim/chart_data.py` 的 `CHART`。節點是
  `UiScreen`，不夠時新增 `UiScreen` 的值。實作不讀 `stages.json`。
  - `chart_data.py` 是轉移規則的資料依據。`stages.json` 只給測試參考：
    `test_chart_data.py` 逐條比對兩者，刻意的差異列在測試裡。
  - 進入群組的轉移在目標寫明群組（`Target.group`），`advance` 不從入口清單
    推斷；只有 `sync` 遇到預期外的畫面時才推斷。
  - `unit_info` 沒有節點會打開，不在定義裡。
- ［確認，2026-11-03］刪除 `tests/ggge_ai_2/integration/test_uisim_recording.py`。
  #111 驗收 4 指的是這個檢查，驗收條件要另外處理（未定）。
- ［確認］不另做分頁組：分頁是普通畫面之間的轉移。
- ［確認］子狀態記憶（statechart 的 history 狀態，例如單位詳情上次停留的分頁）延後：
  - 分頁本身是畫面名，進入後 interpreter 讀得到。
  - 記憶由所有入口共用，但 `_roster` 版本和戰鬥中版本是不同畫面名，要另定對應。
  - 沒有記憶時，進入群組給多個結果，由觀察收斂。
- ［確認］`UiState`：

  ```python
  @dataclass(frozen=True)
  class OpenGroup:
      group: str
      caller: UiScreen | None

  @dataclass(frozen=True)
  class UiState:
      screen: UiScreen
      stack: tuple[OpenGroup, ...] = ()
      auto: UiAutoMode | None = None
  ```

  - `stack` 取代 `caller`：目前打開的 `caller_groups` 群組，外層在前。每一層記
    群組名與打開它的畫面；`caller` 為 None 表示不知道從哪裡打開。同一個畫面可以
    屬於兩個群組（`unit_detail_state` 在 `unit_detail` 與 `unit_info`），所以記群組名。
  - 用 tuple：`UiState` 是 `first_move` 的 dict key，欄位要不可變、可雜湊；堆疊
    深度是群組巢狀層數，目前最多 2 層。
- ［確認］堆疊規則，`advance` 與 `sync` 用同一套，依序檢查：
  1. 不變：目標是目前畫面，或最上層的群組包含目標。
  2. push：目標寫明的群組不在堆疊上時，push 一層，`caller` 是轉移前的畫面。
     ［提案］轉移前的畫面本身是這個群組的成員時，`caller` 為 None：堆疊漏了這個
     群組，例如啟動時停在戰鬥選單的「設定」。
  3. pop：其他情況，pop 到最上層包含目標，或堆疊清空。
  - 回到呼叫者：按鈕的目標包含最上層的 `caller` 時，只產生回到 `caller` 的結果；
    `caller` 為 None 時產生全部結果。
  - 先判斷不變與 push，最後才 pop：先 pop 的話，在部隊資訊點卡片會先 pop 掉外層
    的 `battle_menu`。
  - ［提案］`sync`：畫面相同時堆疊不變。觀察到的畫面是 `state` 某個操作的結果時，
    採用那個結果的 `stack`，這樣 loop 比對預期時 `stack` 一致。都不是時推斷：以
    觀察畫面為入口、不在堆疊上的群組只有一個才 push，否則照規則 3 pop。
- ［確認］跟著改：
  - 目標比對只比 `screen`：`StagePlan`、`DefaultPlanController.BATTLE_MAP`、
    `first_move`。
  - `loop.py` 的紀錄把 `caller` 換成 `stack`。
  - `predecessors` 在 uisim 外沒有呼叫者，移除。
  - `roster_list` 拆成 `roster_list_ally`、`roster_list_enemy`，互相轉移，都是
    `battle_menu` 的成員。拆分寫在 `chart_data.py`，`stages.json` 不改。
- 待做（2026-11-03 記錄）：
  - `mech_normal_info`、`pilot_normal_info`、`weapon_info` 的「關閉」：`stages.json`
    寫回到戰鬥畫面，幀 #523→#524、#531→#532、#534→#535 是回到單位詳情頁。
    `chart_data.py` 照 `stages.json` 抄。［假設，使用者］這是狀態記憶的問題，類似
    「從戰場進入單位詳情，按返回會回到戰場」。等實際運行再修。
  - 單位詳情內的分頁切換與三個內頁的進出不在 `chart_data.py`：標記資料集還沒補
    這些幀的圖片。有幀的轉移：#519→#520、#525→#526、#585→#586、#587→#588、
    #588→#589、#592→#593、#593→#594、#521→#523、#529→#531、#532→#534。
    補圖片與案例後再加轉移。
  - 量按鈕位置（標記工作）：`unit_detail_*_roster` 的「關閉」（比戰鬥版偏左）與
    「選擇」（#547、#549）；`roster_list_enemy` 的全部按鈕；四個戰鬥畫面的單位
    圖示。量到之前，模型能操作進入 `_roster` 頁，但沒有操作能離開，只能靠 `sync`。

### 8.6 OpenCV interpreter 的分層（2026-11-03）

- ［確認］分層，不推翻 §1、§2.4、§4.3 的裁定：
  1. uisim 給候選畫面（loop 的 `candidates`）。
  2. 快速判斷：只檢查有畫面檔的候選，用簡單元件。剛好一個候選通過時，回傳這個
     畫面。
  3. 完整判斷：沒有候選通過，或不只一個通過時，用規則樹（§4.3）。
  4. 讀取畫面內容是附加功能，前兩層完成後才做；AUTO 相關的讀取更後面。
- ［確認］先做快速判斷：只要分開 uisim 的候選，工作量比規則樹少。元件寫成獨立
  的檔案，規則樹之後用同一批元件組合。
- ［確認］相似的畫面同時通過時記錄下來，使用者再找更多 UI 規則加進辨識。
- ［確認］浮窗的處理是規則樹的實作細節。
- ［提案］規則樹做好之前，快速判斷決定不了時回傳 None，並記錄通過的畫面名。
  §2.3 已規定 None 時 loop 停下並記錄。
- ［提案］檔案：一個元件一個檔，放在 `interpreter/elements/`；一個畫面一個檔，
  放在 `interpreter/screens/`，寫明快速判斷用哪些元件，之後在同一個檔往下擴充。
  組合器是 `interpreter/opencv.py`。
- ［提案］測試：每個畫面檔跑 `data/labeled/` 的全部幀。自己的幀全部要通過；
  其他畫面的幀誤判通過時，列在測試的清單裡，交給使用者判。
- 第一批是戰鬥迴圈的畫面，元件取自 §2.4；圓鈕依 §8.7 改看圓鈕上的字：

  | 畫面 | 標記幀 | 快速判斷用的元件 |
  |---|---|---|
  | `player_phase_overview` | 11 | 「TURN n」框、標題「我軍回合」（不用 ≡，見下方缺口） |
  | `select_action_in_battle` | 7 | 「TURN n」框、標題「單位移動」 |
  | `select_weapon_in_battle` | 7 | 「TURN n」框、標題「選擇武裝」 |
  | `select_weapon_in_attack_prepare` | 4 | 「TURN n」框、標題「戰鬥準備 -攻擊-」、圓鈕「行動選擇」 |
  | `select_weapon_in_battle_response` | 6 | 「TURN n」框、標題「戰鬥準備 -應戰-」、圓鈕「行動選擇」 |
  | `battle_prep_attack` | 7 | 「TURN n」框、標題「戰鬥準備 -攻擊-」、圓鈕「開始戰鬥」 |
  | `battle_prep_response_attack` | 7 | 「TURN n」框、標題「戰鬥準備 -應戰-」、圓鈕「開始戰鬥」 |
  | `battle_info_preview` | 4 | AUTO、▶▶、≡ 三鍵與「- TAP TO NEXT -」 |

- 已知的缺口：
  - `player_phase_overview` 的 11 幀有 4 幀 AUTO 開，這 4 幀的 ≡ 全是暗的
    （§2.4 第 3 條的［假設］）。所以快速判斷不用 ≡，我方回合中的展演也會通過；
    標記資料沒有展演的幀，測試看不到這個混淆。
  - 標題原型有「敵軍回合」（取自 rec20261014-913、-1082），沒有「隱藏軍回合」：
    標記資料沒有它的幀。「隱藏軍回合」的幀可能被讀成「我軍回合」。
  - 共用字的標題差距小：「我軍回合」對「敵軍回合」最小差 0.15（map20261026-28、
    -58）；「戰鬥準備 -應戰-」對「-攻擊-」最小差 0.11（rec20261014-1093）。
  - 「敵軍回合」原型的幀也是測試它的幀，邊界是自己擬合的。

### 8.7 元件判例與戰鬥準備的行動選擇（2026-11-04）

- ［確認］元件測試改用逐幀人工判例，不再用畫面名推斷。`data/labeled/cases.jsonl`
  每列的 `elements` 記判例：沒有 key 是還沒判，`null` 是判不了。已判
  `turn_box`（0c4bdfd）與 `menu_key`（76a252c），標記頁由
  `scripts/build_element_label_page.py` 產生。
- ［確認］chart 的 `ScreenChart.elements` 列出畫面有的 UI 元件；在集合裡就是有。
  沒有判例幀的畫面不列元件，代表沒查過，不是沒有。
- ［確認］右下大圓鈕的字不只表示按下後的動作，也提示錯誤與防呆（例如「射程外
  攻擊」）。圓鈕判例照字分：選擇武裝、攻擊、射程外攻擊、行動選擇、發動、開始戰鬥、無。
- ［確認］戰鬥準備裡有使用者沒規劃到的畫面：
  - 「戰鬥準備 -攻擊-」按駕駛頭像，進入那位駕駛的行動選擇面板
    `select_weapon_in_attack_prepare`；面板按「技能」進入
    `select_skill_in_attack_prepare`。兩者組成群組 `battle_prep_action`。
  - 攻擊側與應戰側分開。應戰側的面板就是 `select_weapon_in_battle_response`。
  - 戰鬥準備的技能畫面和大地圖的 `select_skill_in_battle` 是不同畫面，外觀相同，
    只能從前一個畫面分辨。
  - rec20261014-927、-928、-933、-950 原標 `select_weapon_in_battle`，改標
    `select_weapon_in_attack_prepare`。錄影的 B02（`pilot_slot`）原記到
    `select_skill_in_battle`，依裁定改到面板。
- ［假設］面板的「返回」「行動選擇」回到 `battle_prep_attack`；技能畫面的「返回」
  回到面板、「發動」回到 `battle_prep_attack`。使用者看過轉移圖沒有提出異議，
  但沒有逐條確認。應戰側的面板沒有「技能」鈕（6 幀都沒有），所以沒有應戰側的技能畫面。
- ［確認，2026-11-06］圓鈕判例 222 幀（rec20261014-7 沒判；rec20261014-755 使用者
  更正為「選擇武裝」）。元件只算目前畫面能操作的：被浮窗或模糊蓋住的背景按鈕判
  「無」（rec20261014-776），判不了只用在看不出元件在不在的幀。
- 圓鈕偵測分兩步（使用者指出要先看有沒有圓形）：
  1. 圓鈕位置的圓周上有邊緣的比例 ≥ 0.8 才算有圓鈕。有圓鈕的幀最低 0.95
     （射程外攻擊），沒有圓鈕的幀最高 0.567（game_title）；模糊的 775、776 在
     0.533 以下。
  2. 有圓鈕時，6 種文字各一個模板，取分數最高的種類。
  快速判斷改用圓鈕的種類：戰鬥準備要「開始戰鬥」，兩個行動選擇面板要「行動選擇」。
- 已知的缺口：
  - 光效蓋住文字的兩幀分數低：rec20261014-1079（開始戰鬥）0.413、-1105
    （行動選擇）0.392，仍是 6 種裡最高。
  - 「發動」「射程外攻擊」各只有一幀，模板就取自那一幀。
  - 出現模板以外的字時，偵測器仍回傳分數最高的種類，不會回報不認得。
- ［確認，2026-11-06］左上標題判例 223 幀。「其他標題」是字型相同、可以辨識，但不屬於
  戰鬥流程的標題（強化清單、建造機體資訊、`stage_chosen` 等 26 幀）。戰鬥標題偵測不認
  它們，回傳沒有；這些畫面之後用別的範圍標出資訊。「技能」加了原型，取自唯一的
  rec20261014-1237。

### 8.8 選取單位的簡略資訊（2026-11-10，討論中）

- ［確認］在地圖畫面選取單位時，單位下方有藍色選取圓圈，畫面右上方出現簡略資訊，分成
  機體塊與駕駛員塊。mapparser 要讀出兩塊裡的全部資料。
- ［確認］這些資料不是丁級：簡略資訊讀不到完整的機體名稱和駕駛員名稱。單幀判讀得到
  藍色選取圓圈時，簡略資訊可以當作標記目標（選取的單位）的甲等資料。
- ［更正，2026-11-10］名字不轉成文字：`MapReading` 直接帶名字的模板（`NameTemplate`，名字
  白字的遮罩），之後需要比對時再兩兩比相似度。取代先前「傳遞時用字串」的紀錄。
- ［確認］標記資料集新增欄位記簡略資訊。先用現有的標記資料做，不夠再從候選幀裡挑出
  新的標記資料。
- ［確認］範圍：只做這個 UI 元件的判斷（有沒有簡略資訊）和讀取它提供的資訊，用來充實
  `MapReading` 的資料。不管畫面名，也不在既有流程中新增判斷。
- 判例頁：https://claude.ai/artifact/55GaWUymqv2CnzUmGHGPEo（45 幀有候選，其餘 178 幀
  Claude 看過沒有簡略資訊）。
- ［確認，2026-11-10］判例完成：頁面上的 45 幀中 30 幀有、15 幀無。其餘 178 幀頁面沒有提供圖片，
  沒有判例。右塊是機體立繪的面板（戰鬥準備的
  rec20261014-648、774 等）不是目標 UI 元件，判無；rec20261014-775、776 也判無。
  判讀前先用形狀判斷是不是目標 UI 元件，要區分「那裡剛好有 UI」和「是辨識目標」。
- 形狀判斷：機體塊左緣、駕駛員塊左緣、頭像框左緣三條直的垂直線。直線在平均水平梯度上
  是尖峰；地圖、機體立繪、選單的邊不直，沒有尖峰。判例中有面板的幀最低 7.66，沒有的最高
  1.69（rec20261014-775），門檻 5。未判的 178 幀最高 3.25（rec20261014-358）。
- 讀取（`mapparser/unit_panel.py` 的 `read_panel(image, SELECTED)`，`MapReading.panel`）：先過形狀
  判斷，再讀欄位。數字與 CHANCE STEP 用白字字形模板；圖示用色相；狀態字、DAMAGE 用整塊
  模板；名字裁下白字遮罩，直接當作 `NameTemplate` 輸出。模板由
  `scripts/extract_unit_panel_templates.py` 從判例產生；每個名字第一次出現的裁圖存成
  `name_*.png`，`names.json` 對照判例的名字文字，只給測試當標準。測試要求讀出的模板只和判例
  名字那張存檔模板相似度 ≥0.75（判例裁圖兩兩比：同名最低 0.861、不同名最高 0.556）。
  HP／EN 的預估數字疊在條上：只取跨過條底那一列（第 249 列）的字形，條的白色段和橘色
  EN 條都在這列之上結束；字左邊扁平的形狀是負號。疊字用整行文字的色彩模板，判例中只有
  「MP +0」一個。判例 30 幀的 14 個欄位全部讀對。
- ［確認，2026-11-10］目標是串起整個探查流程，並實作能做這件事的 planner。先確定 mapgeom
  整合多張 `View` 的方式，以及整理出的資訊 planner 是否有足夠的手段確定。lattice 給初始
  佔位，點擊我方單位給簡略資訊；還缺：沒有選我方單位時點敵方單位，敵方單位被紅圈選定，
  左上顯示敵方的簡略資訊（版面是右上的左右對調）。要先有判讀這兩個 UI 事實的能力。
- ［確認］點敵方單位後仍是 `player_phase_overview`：`chart_data.py` 與 `stages.json` 加
  `player_phase_overview__map_enemy_unit`，回到自己。敵方選取只當作 mapparser 讀出的資料。
- ［確認］判例 map20261026-44（`044_tap_enemy_unit.png`）：(1,2) 有單位，是紅圈選定的敵方
  單位；周圍的紅色格子是敵方單位的移動範圍。左上簡略資訊：阿雷路亞・…／墮天使鋼彈，
  圖示是灰色的 ⊖。
- 左上敵方簡略資訊的讀取（`read_panel(image, ENEMY)`，`MapReading.enemy_panel`）：兩塊的
  內部版面和右上相同，只是駕駛員塊在左、機體塊在右，所以每塊的框由右上的框平移得到（駕駛員
  塊 −1652 px，機體塊 −818 px）。灰色圖示（`PanelIcon.GRAY`）在色相判斷之後才判：低飽和、
  中等亮度的像素佔 30% 以上。
- ［確認，2026-11-10］戰鬥畫面左上顯示的攻擊目標簡略資訊，和點敵方單位時左上的簡略資訊是
  同一個 UI 元素。判例頁 https://claude.ai/artifact/NeahiQP8fmuAXw7rNDY9nZ（collection
  `enemy_panel`）裁定 33 幀：20 幀有；13 幀左塊是機體立繪，照右上的裁定算無。其餘 191 幀
  沒有裁定。
- 形狀判斷改用駕駛員塊右緣 554 與機體塊右緣 971 兩條直線。左緣在暗色地圖上很弱（面板本身
  也暗），rec20261014 的幀左緣比值只有 0.2–5；左塊是機體立繪時 554 沒有直線（最高 3.0）。
  有的 20 幀最小比值 10.7，未判的 191 幀最高 3.5，門檻 5。錄影 1932 幀中 244 幀通過，
  抽看 48 幀都有這塊資訊。
- HP、EN、MP 的字形模板只用右上判例平均：敵方面板底色深紅，字形偏粗，0、6、8、9 的內洞
  會糊掉，混進平均後右上的數字也讀錯。
- HP／EN 預估數字改用自己的字形模板（`change_*.png`，兩塊的判例一起平均），字型比 HP 數字
  窄。敵方的預估數字疊在白色條與紅色 KILL 標記上，影片壓縮讓白字在紅邊上偏粉紅：遮罩另外
  收低飽和（≤90）、高亮度（≥190）的像素；被切斷的數字依欄位把碎塊拼回去，並用完整數字的
  列範圍取字形，缺的筆畫留空不拉伸。這組門檻只在判例上試過，190／90 兩側（200／70、
  180／110）會錯 2–16 個，餘裕很小。
- 疊字多一個「KILL」模板（紅色標記，在 HP 預估數字下方第 266–294 列）。
- ［確認，2026-11-10］一幀內，右上簡略資訊屬於 `selected` 的單位，左上簡略資訊屬於
  `enemy_selected` 的單位。點一次就能從一幀確定一台單位的位置、陣營與簡略資料。
- ［確認，2026-11-10］可識別格子（甲）只保證一幀內的格號正確。多幀拼合還要相鄰兩幀的
  位移；看得到地圖邊界的那一軸用甲定位。
- ［確認，2026-11-10］看不到地圖邊界的那一軸（地圖中段）的對位先不處理。之後用點擊地圖
  空白格的判讀，以空白格當滑動後的定位點（即 §8.4 待做的填色標記）。
- ［確認，2026-11-10］mapgeom 的合約帶簡略資訊與陣營（HP、EN、陣營等）。合約的形狀要能
  辨識單位的座標。
  - `View` 不帶 `selected`、`enemy_selected`：它們只在 `MapReading` 裡用來把單位和簡略資訊
    對上。轉成 `View` 時，簡略資訊直接掛在對應的單位上。
  - `controllable` 和我方不同，保留在 `ViewUnit`，也加進 `MapUnit`。
  - 類型：紅色是攻擊型，藍色是耐久型，黃色是支援型；灰色是系統 NPC 獨有、沒有類型的類型。
    我方的類型隨隊伍組合改變，敵方固定，敵方的類型是探查地圖要取得的資料。
  - `MapJudgment` 的單位分成兩個對照：單位佔住的每一格都對到同一個 unit id
    （`unit_cells`），unit id 再對到單位的資料（`units`）。
- ［確認，2026-11-10］這次的範圍不交棒給 battle engine：battle engine 載入地圖的介面還沒做。
- ［確認，2026-11-10］mapgeom 的第一版（`mapgeom/stitch.py`）支援三種接法：形狀（佔用格的
  分布）、同一台單位（簡略資訊相同）、點擊空白格的標記。測試先畫一張大圖切成幾個範圍再拼回，
  只驗證佔位，不驗證單位資訊。
- ［確認，2026-11-10］點擊標記的對應由 map sync planner 負責：點空白格時給這次點擊一個新的
  編號，下一幀在被點的那一格讀到標記，`View` 才帶 `TapMark(格號, 編號)`；滑動後讀到的標記
  沿用同一個編號。mapgeom 只比對編號是否相同。
- ［確認，2026-11-10］滑動被當成點擊（誤觸）先不處理，等實測後看發生頻率再決定。
  - ［假設］地圖上同時只有一個標記，未驗證。
- Claude 的決定，待使用者確認：
  - 最後一張 `View` 接不上任何一張時，輸出最近一張較早 `View` 所在的那一群，`current` 是
    None；只有一張 `View` 時直接輸出它。
  - 單位佔住的每一格都確定是佔用時，才輸出這台單位；被畫面邊緣切到的單位，要等另一張
    `View` 看到整台。

### 8.9 關卡資料（2026-11-11，討論中）

- ［確認］流程：進入新關卡時，先查有沒有這一關的初始盤面資料。沒有就由 MapSyncPlanner
  探查，直到 mapgeom 產出內容確定、彼此一致的 `MapJudgment`，寫進關卡資料，再交給戰鬥的
  planner。MapSyncPlanner 是通用計畫（§8.2）。
- ［確認］直接使用關卡資料時，整份資料沒有缺漏；不直接使用時，整份資料拿來對照。
- ［確認］地形逐格記，一格可以有多個地形選項（例如陸／空、海／空），同一關裡各格不同。
  取代舊規格 `docs/spec/intel-data-spec.md` 的「地形補正逐關卡一個值」（2026-08-14）。
- ［確認］一台單位要有單位詳細頁能取得的全部資料，才算沒有缺漏。
- ［提案］結構（`stagedata/contract.py`）：地形逐格存；單位存成清單，每台記錨點格、大小、
  陣營、`controllable`、簡略資訊與詳細資料，不放進格子，也不依陣營或地形聚合。
  `UnitDetail` 的欄位等單位詳細頁的判讀再定。
- ［確認］關卡不綁定我方陣容：關卡資料只記我方出擊點（`deploy_cells`）。單位清單只放關卡
  固定的單位。
- ［確認］先不做第三方陣營。
- ［確認］出擊點有順序：遊戲依出擊欄位的順序分配格子。組合陣容時要一併設定出擊位置。
- ［確認］關卡資料有勝利條件（`victory`）與事件（`events`），細節之後再填。
- ［確認，2026-11-11］關卡資料存進 issue #92 的 PostgreSQL（`db/migrations/0008_stage`）。
  關卡資料有版本欄：遊戲改版可能改動關卡，同一關的新舊兩份資料並存。版本值的來源未定。
- ［確認，2026-11-11］關卡 id 在選關時帶入，不靠 mapparser 判讀。
- ［確認，2026-11-11］流程：選關 → 設定陣容 → 進入關卡 → 關閉 AUTO（原本開著 AUTO 時要
  重開，避免起始狀態偏移）→ 查有沒有關卡資料 → 查有沒有要求重新探查 → 決定是否交給
  MapSyncPlanner。
  - ［確認］起始狀態偏移是指 AUTO 讓我方可控制的單位做了動作。在 `battle_info_preview`
    關掉 AUTO，單位不會動；進入大地圖畫面後就無法保證。所以 AUTO 要在
    `battle_info_preview` 確認關閉成功，沒有在這裡確認關閉就重來。
  - ［確認］選關在實機上由指令呼叫者指定。
  - ［確認］關卡資料要確認一致才算存在。確認地圖探查完畢的模型是 mapgeom。
  - ［確認］重新探查的要求來自執行參數。探查結果先和舊資料差分比對，有出入就顯示錯誤。
    差分比對只在地圖探查完畢之後做。
  - ［確認］開發階段探查不中斷；成品要加上停止條件。
  - ［確認］陣容沒有派滿時，空的出擊點讀不到。實機確定派滿，這個問題先不處理。
- ［確認，2026-11-11］證據由迴圈交給計畫：`agent/contract.py` 加 `Evidence`（先只有
  `map_readings`），`Plan.still_valid` 與 `Plan.next` 都多帶 `evidence`。
  `PlanController.think` 也多帶 `evidence`，因為 `think` 要呼叫 `still_valid`。不採用把同一個
  `MapReadingHistory` 物件交給計畫的做法：`still_valid` 的答案會隨介面外的狀態改變。
- ［確認，2026-11-11］決定交給探查後，要探查完畢才進入下一個計畫；探查途中不走貪婪策略。
- ［確認，2026-11-11］因為沒有這一關的既有資料而探查時，探查結果存進 PostgreSQL。
- ［確認，2026-11-11］探查不加點擊後的等待：沒有量測過點擊後太快進入下一個判斷會不會讓
  點擊被誤判成沒有作用。
- ［確認，2026-11-11］mapgeom 的形狀比對有多個候選位移時，選吻合的佔用格最多、其次吻合
  比例最高的那一個；兩個並列第一就不接合。起因：模擬中等距排列的敵方單位讓相同鏡頭的
  兩張畫面有兩個候選位移，`_join` 改找更早的畫面，接到錯的位移。
- ［確認，2026-11-11］實際遊戲可以收起可操作單位選單的 HUD，視角可以拉到讓地圖邊界在
  畫面正中央。一直讀不到的格子交給之後的探索上限處理。
- ［確認，2026-11-11］MapSyncPlanner 只用各種輸入情境測試處理邏輯，不做模擬器。模擬器要替
  mapparser 的輸出做假設，超出計畫的職責；其餘問題留給實機。
- ［確認，2026-11-11］版本記兩個：app 的 version name，以及執行程式的版本（git commit
  的前 8 碼）。執行程式的版本只留存，不作為比對依據。
- ［確認，2026-11-11］出擊單位在隊伍組成的畫面記錄下來；之後拿地圖上的單位比對隊伍組成的
  排序，得出出擊點的順序。比對機體名稱的模板。
- ［確認，2026-11-12］目前畫面接不上其他畫面時，MapSyncPlanner 把上一次送出的滑動反過來滑，
  兩軸各加一個範圍內的隨機值（假設值：±125 px，一格），讓下一次滑動得到不同的畫面，
  避免在同一組接不上的畫面之間來回。
