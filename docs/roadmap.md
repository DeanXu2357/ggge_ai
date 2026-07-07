# 進度與規劃

更新日期：2026-07-08（凍結調查收束＋git 修復；修正包仍待實機驗證）

## 暫停快照（2026-07-08 凌晨，恢復點）

**裝置現況**：手機已再次拔離（壓測結束）。遊戲上次確認停在 **HARD 2
戰鬥中 TURN 1 我方回合 hub**。無程式在跑。注意：手機的
`svc power stayon true` 未還原，接回後先跑
`adb shell svc power stayon false`。

**恢復步驟**：接回手機 → `adb devices` → 截圖（可能鎖屏，swipe 1164 430
1164 60 350 解）→ 確認是否仍在戰鬥（可能被登出，屆時從關卡列表重進，
會多耗 10 體力並經過新的 stage_info 動作）→ tmux 跑 `run_manual_battle.py`
實機驗證修正包。

**2026-07-07 深夜凍結調查結論**：7/5–7/7 三次無日誌硬當機（journal 於
07-06 00:09、07-07 00:30、07-07 09:35 戛然而止）。腳本審查無失控模式；
重現測試全數陰性——純 CPU/熱（heavy 全核 burst 一小時、Tctl 峰值 71°C）、
USB adb 流量＋heavy 組合（一小時）、傳輸中拔線（kernel 乾淨零 xhci 錯誤）。
剩餘嫌疑：WiFi adb 路徑（mt7921，凍結 2、3 的實際傳輸方式，未測）與
機率性硬體（建議 memtest86+ 過夜、查 BIOS 更新）。壓測工具在
`data/stress-test/`（stress.py light/heavy、capture_loop.py，gitignored）。
另：09:35 凍結發生在 git commit 寫入途中，留下 4 個 0-byte object 與
斷頭 HEAD——已修復（branch 指回 5b6c8118、重建 index，工作樹無損；
證據存 data/stress-test/git-corruption-evidence.txt）。本 commit 的
roadmap 快照即當時未遂 commit 的內容。

**20260706 深夜實測結論（feat/inner-goap，commits 79fcc0c/5b6c811）**：
clear loop 兩處斷點＋戰鬥三次靜默 stall 全數診斷完畢：
- main_menu 模板是 RANK 2 徽章裁圖，升到 RANK 13 後 0.783 過不了 0.90
  gate → 已重裁成出擊 MAIN STAGE 鈕（79fcc0c，rank/日期不變量）。
- stall 鏈：keyguard 的鎖圖示模板在暗色靜止戰場誤匹配（TM_CCOEFF 深色
  均勻區坑）→ 解鎖拖曳劃在敵方鋼坦克上 → 打開單位設置詳情 modal →
  無 handler 靜默循環＋假相位斷點灌高內部回合數＋unit_cards_present
  誤報 True。
- 修正包（5b6c811）六項：stage_info 畫面動作（AUTO 改手動＋勝利條件
  幀存流水帳＋TAP TO NEXT，使用者多次重申的需求落地）、keyguard 全幀
  暗度第二訊號（語料 30 張真鎖幀 8.7–31.6 全保留，gate 40）、modal
  逃生口（偵測標題帶＋點關閉 (1176,992)；語料 452 幀全中零誤報）、
  unit_cards_present 拒斥 modal、回合數以畫面 TURN 數字變化佐證、
  select 後三幀 post_select_probe 儀器。132 測試全過、ruff 乾淨。

**已知未修/未驗**：
- **mystery A 未解**：第三次 stall 的 modal 在點 FIRST_UNIT_CARD 後約
  4 秒重開、無 keyguard 事件——post_select_probe 儀器已上線，等下次
  發生離線重放。
- main_menu→stage_list 沒有 planner 邊（從 main_menu 起步會 no plan；
  上次手動導航繞過）。
- AdvanceStageInfo 未實機驗證：AUTO chip 離線 probe 0.895@(1820,54)
  沒問題，但 ensure_manual_auto 的靜態幀 gate 可能被 TAP TO NEXT 閃爍
  拖到逾時（有 30s timeout，會 degrade 到戰內重試，不致卡死）。

**接續待辦**：① 恢復戰鬥實機驗證修正包 → ② 重啟 #18 視覺回歸庫
（新素材：RANK 過期模板案例、暗鎖幀、modal 正負樣本、
stage_info、20260706-233158 run 的 hub 幀）→ ③ LLM perception 讀單位
資訊（ollama；格式樣本已採：武裝、技能／能力、OP 兩分頁優先，見
memory llm-perception-unit-info）。

**舊快照（2026-07-06）**：停在選擇關卡（機動戰士鋼彈 HARD 2，★★☆，
SECRET 已奪取），體力 25/80。

**模擬器/expectiminimax 定案（2026-07-06 深夜，feat/inner-goap 分支）**：
使用者確認要**求關卡最佳解**，depth-1 不夠、後端模擬必建。已定案收錄
機制（相位制回合、擊殺再動每回合重置、敵方相位的我方防禦應對
{閃避/防禦/反擊} 是 max 節點、格子移動與路徑封鎖拆支援防禦網、敵人
同樣有再動/支援且受特殊能力放大、支援次數每相位重置）；敵方節點預設
策略模型、介面保留 min；搜尋＝anytime 迭代加深 expectiminimax（殘局
自動精確，離線解全關=加大預算）。傷害/命中公式已從社群 wiki 調查入檔
`docs/combat-formulas.md`（閃避修正等待實機標定）。全文見
agent-architecture.md「戰鬥模擬器與 expectiminimax」節。**v0 骨架已完成
（#19）**：`battle/sim.py`（SimState/step/相位輪換/charge 重置）、
`formulas.py`（公式全參數化）、`enemy_model.py`（policy/min 可插拔）、
`solver.py`（迭代加深＋置換表＋Star1；Star2 與 TT 界值精修留 TODO）；
105 測試全過。裁量記錄：切比雪夫距離；`dodge_hit_penalty=20`、
`support_defend_multiplier=0.5` 為待標定預設；技能尚未接進 solver
行動生成（step 已支援）。新任務 #18＝視覺回歸測試庫（截圖整理成
標註案例釘 vision 閾值）。下一步＝#19 的 v1（格子可達性/路徑封鎖、
敵方回合應對彈窗感知）與 controller 整合。

**架構討論定案（2026-07-06 晚，commits 1dfc800/357bfab/0dccad9，全文見
agent-architecture.md）**：內層戰鬥 GOAP（#17 主 issue，收編 #12/#13）——
BattleState 統一盤面、ActionCatalog＝畫面掃描∪能力注入（擊殺再動等編成
知識灌入）、啟動內鏈式規劃（判死用實際數值 HP 非弧比例）、第三方可控性
開戰探測；**MCTS/模擬器非禁令**（先前誤記為紅線，CLAUDE.md 已更正）；
前置條件即內容（體力管理=資料綁定前置的實例）；編成兩階段（先讀取同步）；
目標介面預留戰役。缺什麼之後再補。

**離線批次（2026-07-06 完成、已 push、已關 issue）**：
- **#15 流水帳決策事件配截圖**（da1bed3）：每個決策事件（select_unit/move/
  attack/standby/tactical_map/story_dialog/hidden_battle_warning/end_turn/
  finish）存一張縮圖 JPEG（長邊 1280、q85）到 `data/runs/<ts>/frames/
  battle_NN/`，存幀失敗軟性略過不中斷。61→65 測試。
- **#16 隱藏戰鬥 WARNING 彈窗辨識**（f3ead6d）：`vision.is_hidden_battle_
  warning`（彈窗 1.0、他處 ≤0.21、gate 0.6）＋控制器依 `hidden_battle_policy`
  決策（預設 challenge 挑戰；OCR 戰力門檻留待實機）。彈窗自帶 AUTO 鈕不碰。

**下一步＝實機驗證**（需使用者提供測試機）：跑一場含索敵與（若觸發）隱藏
戰鬥的戰鬥，驗證 #14 索敵重構（cd89b9f enemy_onscreen）與 #16 彈窗決策，
並讓 #15 的 frames 自然產生，作為 #5/#6/#12/#3 校準的第一手資料。

**任務改用 GitHub Issues 管理**：repo `git@github.com:DeanXu2357/ggge_ai.git`
（public、main）、看板 https://github.com/users/DeanXu2357/projects/2 。
本檔的「工作安排」細節改以 issue #3–#15 追蹤，見 [[github-repo-and-tasks]]。

**今日重大成果**：
- **HARD 2 含隱藏戰鬥由我們的程式全自動通關**（23:43，TOTAL SCORE 8,525
  NEW RECORD、破壞 14/14 含增援、6/10 存活、受損 43%）。流水帳
  `data/runs/20260705-232132/battle_01.jsonl`（outcome battle_result）。
- 四個戰術修正實機驗證：索敵重構（1ddc407，單位改朝世界座標敵群前進）、
  死亡台詞對話自動推進（bd6b132，本場自動處理 5 次無需人工救）、
  殘機單卡辨識（#1）、戰敗畫面辨識（#2，本場贏了未觸發但已上線）。
- 中斷落地流水帳（8350f60）。

**本場暴露、已開 issue 的缺陷**：
- #14（high）索敵 fallback 過粗：鏡頭錨定每次 miss（#6）→退到全域單一朝向
  →前排/側翼單位（如 GQuuuuuuX）走離最近敵人。**最該優先修的戰術缺陷。**
- #12（high）EN 歸零不會用 SKILL/SUPPORT 補能量，直接待機（實戰確認，
  行動列的 SKILL SP／SUPPORT EN 1/1 鈕被無視）。
- ~~#15 流水帳決策事件配截圖~~（已解，da1bed3）。
- ~~#16 隱藏戰鬥 WARNING 彈窗辨識與決策~~（已解，f3ead6d）。
- #5 掃描仍低估我方/第三方（我方 10 掃到 2–6、第三方恆 0）。**#14 的根因。**

**帳號現況**：RANK 11、資金 158,380、體力 25/80。隊伍戰鬥力 111,530
（遠超 HARD 2 建議 70,000——本 session 反覆確認敗因在程式非數值）。

**下一步（依 issue 優先序）**：先修戰術三本柱 #14（索敵 fallback）、#12
（EN/技能行動掃描）、#15（決策截圖）——這三個直接決定戰術品質；再回架構
主線 #7 歸因、#8 cache、#9 OCR、#10 戰略迴圈。

## 現行計畫

架構已與使用者重新定案，全文見 `docs/agent-architecture.md`。核心原則：
程式只內建「機制」不內建「內容」；不建關卡資料庫（跨執行無狀態）；
執行輸入只有目標關卡 + 可用的局外成長 action；關內動作空間完全開放。
不做自建模擬器/MCTS——戰術用遊戲內建預測值做 1-ply 貪婪，再升 1.5-ply
站位安全；戰略靠觀測式戰後歸因決定補強方向。

實作順序（詳見架構文件）：
1. 戰鬥流水帳 + run-scoped 黑板
2. HARD 1 探測（先第 12 關回歸驗證 62bef06，再 HARD 1 收戰敗流程與錨點）
3. OCR 數字讀取（戰力/資金/預期傷害）
4. 戰後歸因 v1（數值差距 vs 程式缺陷）
5. 戰略迴圈（goal + allowed actions、強化與 farming）
6. 行動掃描器 v1（SUPPORT/技能鈕，EN 補給）
7. 1.5-ply 站位安全評估

第 12 關全流程 SUCCESS 記錄（2026-07-04 23:36）：導航→戰鬥→劇情跳過→
結算→回關卡列表全自動，戰鬥中劇情與鎖屏皆自動處理。

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

## 鎖屏防護（2026-07-04 完成）

Samsung 閒置約 3 分鐘自動鎖屏會吞掉所有點擊，而模板仍能透過變暗的畫面比對成功，
造成長時間戰鬥（敵方回合、劇情暫停）中途卡死——第 12 關兩次全流程測試都因此失敗。
解法（`actuation/keyguard.py`）：
- 偵測：`dumpsys window policy` 的 `KeyguardStateMonitor mIsShowing`（實機驗證可靠）。
- 解鎖：KEYCODE_WAKEUP → `wm dismiss-keyguard` → 從鎖頭圖示往上拖曳（raw 座標，不隨遊戲橫向旋轉）。
- 整合：AgentLoop 每次迭代檢查；ManualBattleController 每 15 秒檢查。
- 戰鬥逾時改為活動制：總預算 60 分鐘 + 10 分鐘無活動守門（動畫算活動）。

## 戰鬥控制器 v2 改進項目

（使用者 2026-07-04 實戰觀察提出）

- **技能與支援能力運用**：v1 只會攻擊/移動/待機。實測發現單位 EN 耗盡時，
  控制器不會使用技能或支援能力補 EN，之後只能待機。單位需要知道自己可用的輔助手段：
  - 角色技能（下中 MP 圓鈕，消耗 SP，如「強勢 DAMAGE+10%」類 buff）
  - 支援能力（下中 SUPPORT 鈕，如 EN 補給 1/1、回復 HP 1/1——EN 桶/愛心圖示）
  - 機體額外技能（武裝選擇環上的「技能」鈕、變形 MANEUVER 等）
  - 決策時機：EN 不足以發動任何武裝時先補 EN；HP 低時回復；進攻前掛 buff
- 感知需求：讀取當前單位 EN/HP 數值（OCR）或至少偵測「所有武裝都因 EN 不足不可用」的狀態
  （武器輪盤圖示灰化/紅字），以及 SUPPORT/技能鈕的可用狀態（次數、SP 量表）
- ~~**主動索敵移動**~~（2026-07-04 完成）：`battle/vision.py` 的
  `find_enemy_units`/`find_ally_units` 以單位腳下的底座圓弧做敵我判斷
  （敵=紅橘弧、我=藍弧；hue + 寬扁長寬比 blob 過濾，我方紅色機體與威脅格「!」不會誤判）。
  移動模式改為：朝最近可見敵人前進（以移動範圍質心當作自身位置代理），
  偵測不到敵環才退回威脅格質心。第 12 關實機畫面驗證 6/6 敵、4/4 友、零誤判。
  尚未處理：敵人全部在鏡頭外時需要捲動地圖索敵。
- 其他既知改進：切換目標選擇最優目標（現在只吃預設）、
  武器選擇考慮傷害/EN 效率而非固定順序

## 大方向：以「完成某一關」為 GOAP 目標的全域策略層

（使用者 2026-07-04 提出；2026-07-05 細化定案於 `docs/agent-architecture.md`，
與本節出入處以架構文件為準——特別是「跨執行無狀態、不存關卡資料」原則）

GOAP 的目標設定為「完成指定關卡」，而達成手段不只遊戲內的戰鬥執行，
還包含遊戲外的資源養成。規劃器要能判斷：目前隊伍打不過這關時，
如何用遊戲外資源（強化、開發、編成調整等）改變/強化隊伍後再挑戰。

概念上是兩層 GOAP：

- **戰略層**（新增）：世界狀態含隊伍戰力、持有資源（資金、經驗值道具、
  機體/角色清單）、目標關卡難度估計。action 例如：強化機體、開發新機體、
  調整編成、重打低難度關卡賺資源、直接挑戰目標關卡。
  「挑戰失敗」是可感知的回饋，會更新戰力估計並觸發重新規劃（先養成再戰）。
- **戰術層**（現有）：關卡內的導航與手動戰鬥控制器。

前置需求：
1. 感知隊伍/資源狀態 —— 需要 OCR（讀資金、等級、戰力數值）或 LLM 辨識，
   這會把原本延期的 OCR/Ollama 辨識器變成必要項目。
2. 標定養成相關畫面：強化、開發、編成（unit_setup 深入）、機體詳情。
3. 戰力 vs 關卡難度的估計模型（可先用「推薦戰力/敵方等級」等遊戲內顯示值）。
4. 失敗偵測：戰敗結算畫面的錨點與處理流程。

**HARD 1 實測計畫**（使用者 2026-07-04 指示）：以現有控制器挑戰 HARD 1
（建議 65,000 vs 我方約 33,000，預期失敗），觀察戰敗流程並盤點缺口。
期望方向再次確認：關卡內戰鬥真的完成不了時，要能從局外成長
（強化/開發/刷資源）想辦法完成關卡——即戰略層是硬需求，不是可選項。

## 之後（延期項目）

- Ollama 多模態 LLM 辨識器、OCR 辨識器、`recognition.yaml` 執行期組態。
- 「略過」掃蕩機制解鎖後的快速重複通關路徑。
- 更聰明的戰術（地形、射程、屬性相剋）。
