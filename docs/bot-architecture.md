# bot 新架構規格（大重寫，2026-07-27 與使用者逐題定案）

舊架構因不斷疊床架屋偏離目標，使用者裁決大重寫。新架構落在
`src/ggge_ai/bot/`，本檔是唯一規格來源。controller2 路線
（`battle/flow/`＋`flow-goap-controller2.md`）已整組移除，
其「宣告式動作＋A* 流程層」的價值主張由本架構繼承。

現有 `bot/` 骨架（`bot.py`／`action.py`／`state.py`…）是規格定案前的
草稿，**依本檔重塑**；與本檔矛盾處以本檔為準（差異清單見文末）。

## 核心不變式

1. **每拍恰好一張截圖、至多一次裝置互動、沒有純記帳的空轉拍。**
   閉環原則：動一次手，就必須重新看一眼才能再動手。一拍之內絕不
   連續執行多個裝置動作（開環巨集是禁手）。
2. **符號寫入只發生在兩個固定時刻**：感知門開在拍首（router 重算
   全部感知符號），記憶門開在 act（`Action.do` 內的 `remember`）。
   拍內其餘時間符號空間全域唯讀。act 之後符號視為過期，但過期的
   符號沒有讀者——所有讀取都發生在 act 之前。
3. **一個符號恰好屬於一扇門**。畫面能作證的事實歸感知門（view、
   obstruction、cards、panel_tab、pose…）；畫面看不見的裁定歸
   記憶門（intent、sim_ready…）。action 的 eff 對感知符號**只是
   預測、不是寫入**——decide 拿 sense 出來的事實比對，成立才 pop。
   router 對記憶符號永不觸碰。
4. **程式只內建機制、不內建內容**（沿用專案紅線）；分類器模板、
   反射表、sleep 秒數是機制層調校常數，關卡數值永遠讀畫面。
5. **選擇型對話框（兩個以上有後果的選項）與未辨識 modal 不登記
   反射 handler**——結構上不給「通用點掉」邏輯碰到它們的機會
   （結束回合對話框右鍵＝自動戰鬥紅線）。選擇型對話框一律是
   phase 枚舉成員，由計畫內的 action 明確處理。

## tick 生命週期（線性，無分支例外）

```
截圖一張
  → 分類器 → FrameReading {phase, tags}
  → router 符號表：無條件重算全部感知符號（走反射的拍也照做）
  → 有 blocking tag？        → 跑對應反射 handler（內含自己的 sleep），本拍結束
  → phase = UNKNOWN？        → 等待格（只記帳；超限裁決歸熔斷器，延後），本拍結束
  → 記帳：把「本幀已證明完成」的隊頭連續 pop 掉（0..n 步，純比對，不碰裝置）
  → 隊列空？                 → think（A* 補貨，純計算）
  → 隊頭 pre 不成立？        → replan（丟掉整個隊列重規劃，純計算）
  → 執行隊頭一次              ← 全拍唯一的裝置動作
  → 本拍結束
```

- **pop 同拍續行（定案）**：pop 與執行依據同一張新鮮截圖——這一幀
  既是「上一步完成」的證據，也是「下一步可動」的授權。省掉的只是
  「畫面沒變卻要再截一張才准動手」的空轉拍。
- **replan 同拍執行（定案）**：replan 是對已擷取符號的純計算
  （微秒級），規劃出的第一步 pre 由構造保證在當前幀成立，當拍執行。
- 「沒執行也可以 pop」是一等語意：世界或前一步順帶達成了後續步驟
  的 eff，同一幀能證明的連續完成步驟一起記帳（例：面板剛好開在
  目標 tab 時，`ToWeaponTab` 免費通過）。
- 等待格是 tick 流程的一格，**不是 action**——舊骨架 `WaitOut`
  的假 eff（「等待會產生 hub」）廢除。

## 分類器（classifier）

```
FrameReading:
  phase: 封閉枚舉 | UNKNOWN     # 流程刻意經過的畫面才是成員
  tags:  [{name, point/region, score}]   # 疊在畫面上的 UI 特徵
```

- **phase＝封閉枚舉**：hub、unit_panel、attack_confirm、
  end_turn_dialog…凡是計畫會刻意走到的畫面（含所有選擇型對話框）
  都是 phase 成員，翻成 view/phase 符號給 action 的 pre 消費，
  不掛反射。
- **tag＝疊層特徵**：skip 鈕、單鈕資訊彈窗、loading、卡條、格線、
  面板 active tab…開放集合。tag 必帶 payload（分類器找到的按鈕
  座標／區域／分數），handler 直接用，不再掃第二次畫面
  （「彈窗關閉鈕座標會浮動、不寫死」既有原則）。
- 辨識不出的 modal：phase=UNKNOWN，走等→replan→panic，**永不反射**。
- 分類器核心是純函數（一幀進、一個判讀出）。去抖 wrapper 延後
  （本作是 SLG、執行階段等玩家決策；等待格本身就是隱性去抖——
  誤讀成 UNKNOWN 的幀下一拍自我修正）。
- **capture 與 classify 是兩個接縫**（2026-07-27 使用者指正回寫）：
  `screen.capture() → frame`、`classifier.classify(frame) →
  FrameReading`，迴圈只碰這兩個組件，分類器絕不自己截圖。這樣保存
  的實機截圖可以直接餵真分類器做回歸測試（fixture 慣例沿用
  tests/fixtures/）。mock 端：MockScreen 持有假世界（frame 型別
  就是 FrameReading）、分類器＝identity。
- 同類畫面的變體編碼（如單位面板三個 tab：一個 phase＋active_tab
  tag，或三個 phase）到實作分類器時再定，兩種都能翻成同一個
  `panel_tab` 符號。

## router：同一份 FrameReading 的兩個平行消費者

反射路由**不經過符號**；兩張表互不串聯。

```
FrameReading ─┬─→ 反射表：tags → handler          （給反射弧）
              └─→ 符號表：{phase, tags} → 感知符號 （給 planner／decide）
```

### 反射表

| 欄位 | 說明 |
|---|---|
| tag | 觸發的特徵名 |
| handler(bot, payload) | 動裝置；**內含自己的 sleep**（固定秒數起步）；不寫符號——效果由下一拍截圖作證 |
| refire | `safe`（tap-through 類，同畫面再打是對的，多頁劇情連點）／`require_change`（back 類，畫面沒變就不准再打、改走等待格） |
| blocking | true＝壓過 decide，本拍只跑反射 |
| 適用 phase 集合 | **延後欄位**：v1 全 phase 都偵測，metrics 看到誤判（TM_CCOEFF 深色區亂匹配坑）再加掛載 |

- sleep 寧可偏短：殘餘轉場尾巴由等待格吸收；偏長只是浪費。之後
  依 metrics 逐 handler 升級成「短輪詢直到畫面變化＋上限」，
  不做全域機制。
- 派發語意（比對順序＝登記序先勝、refire 閘門、指紋狀態）整包封裝
  在 router 模組的 `ReflexRouter`（2026-07-27 使用者提議）：表是純
  登記資料、可共用，router 是 per-run 的有狀態外殼；迴圈只問「這幀
  你處理了嗎」。等待格不屬於 router——它看 phase 不看 tag，是 tick
  生命週期的一格。
- v1 反射表只收 tap-through 類（skip 鈕、單鈕資訊彈窗）。使用者
  原案的「常規次級 UI 用 back 返回」在 v1 由 **replan＋目錄裡的
  導航 action** 承接（次級畫面是 phase 成員，catalog 有 back
  action 就規劃得回來）——不需要「這畫面是不是非預期」的判別。
  等期望判別（延後清單 1）落地、或 metrics 顯示這類 replan 過頻，
  再把 back 升格為反射。

### 符號表

- **以符號為單位登記**，不是以 tag 為單位：每個感知符號一條總映射
  `符號 ← f(phase, tags)`，**必含 tag 缺席時的預設值**——感知符號
  每拍被當前幀完整重算，杜絕「彈窗關了但 obstruction 卡在 popup」
  的殘值 bug。
- 規則是純翻譯：無狀態、只看本幀 `{phase, tags}`、不讀
  goal／plan／記憶符號。v1 只提供宣告式組合子（phase 映射表、
  tag 存在取值），不開放任意函數——想寫 if 就是界線警報。
- **完備性測試**：catalog 所有 pre／eff 用到的符號，必屬於恰好
  一扇門且有生產者（符號表規則或某 action 的 remember）。
  沒有生產者的符號＝執行期必然 PlanNotFound，測試期就抓。

## action 契約

- 純符號 `pre`／`eff`，**不依賴畫面契約**。需要畫面特徵→分類器
  貼 tag→符號表翻譯，action 只讀符號。
- `do()`＝一次裝置互動或一次純計算，**內含自己的轉場 sleep**；
  無內部迴圈、無輪詢、無畫面判斷。分支一律用 pre/eff 宣告拆成
  多個 action（warm/cold 用互斥 pre，不用 do 裡的 if）。
- `eff` 是出口條件不是承諾：standing instruction 語意保留——
  `PanToFrontier`（eff=coverage complete）霸著隊頭每拍揮一次
  直到證據成立。
- **整備類動作用 ensure 語意**（R1 實作發現，2026-07-27 回寫）：
  pre 只綁畫面（`view: hub`），eff 設目標值，**不得**把反值寫進
  pre（`grid: off`）。原因：phase 掛載使 hub 事實在 panel 內是
  UNKNOWN，planner 沒有任何動作能從 unknown 過渡到已知值，pre 綁
  反值會讓跨畫面 replan 必然 PlanNotFound。ensure 寫法讓 planner
  在 unknown 上照樣可排；runtime 若目標已成立，證據 pop 會免費
  跳過該步，toggle 鈕不會被盲按。
- action 也帶 refire 政策（沿用舊骨架 `repeat_safe` 概念）：
  `require_change` 的 action 若 eff 未成立且幀與上次執行時相同
  （phase＋tags 未變），不重發、走等待格——防「sleep 略短→
  下一拍看到舊畫面→重發→雙開面板」。
- 思考也是 action：`SolveTactics` 佔一拍、產出戰術步驟拼接在
  自己身後（splice），可被中斷；flow 層的 think 則是隊列空時的
  補貨事件。兩種思考並存的設計沿用舊骨架。

## replan 語意

- 取代舊骨架的 `on_blocked` 三分類：**repair 拼接、
  `repair_max_cost`、`still_relevant` 全部移除**。隊頭 pre 不成立
  ＝計畫過時＝整個隊列丟掉、從當前符號重新 A*（戰術拼接一併丟，
  `SolveTactics` 重跑——被打斷後世界本來就可能變了）。
- replan 只從「phase 明確」的幀發起；UNKNOWN 走等待格。
- **詞彙完備性義務**：catalog 必須涵蓋中間態（單位已移動未攻擊、
  面板停在任一 tab…），否則人類救得回來的局面會 PlanNotFound。
  PlanNotFound＝「沒準備的情況」的誠實訊號→panic。

## panic 與熔斷

- v1 backstop＝`max_ticks`＋BotStuck（dump：符號快照＋最後幾拍
  流水＋截圖路徑）；實機上 panic 接 discord-notify 請求人工干預。
  BotStuck 只留給**即時誠實失敗**（PlanNotFound、新計畫不可執行）；
  一切門檻裁決（等太久、replan 太多）都不屬於 v1。
- **熔斷器延後、metrics 先行**（使用者定案；2026-07-27 再確認：
  等待格的預算與超限 panic 同屬熔斷家族，v1 不做、迴圈內不養
  計數器）。未來形：「自上次 progress 以來的 replan 次數 ≥ N」→
  panic；「連續同 tag 反射 M 次未回到預期」→升級 replan；「連續
  wait:unknown ≥ W」→panic。計數全部從流水帳導出，落地時不需
  回頭改埋點。

## metrics／TickRecord

唯一事實來源＝tick 流水帳；**程式裡不散落可變計數器**，一切計數
是流水帳的導出值。記帳不佔生命週期（2026-07-27 使用者提議）：
`_step` 每個出口回傳 TickOutcome，外層 recorder 一次摺成
TickRecord——單一寫入點，生命週期本體零 ledger 碼；將來要接第二個
觀察者就掛在同一個點。每拍一筆：

| 欄位 | 內容 |
|---|---|
| tick | 序號 |
| phase／tags | 分類器輸出 |
| symbols | 拍首重算後的符號快照 |
| outcome | `executed`／`reflex:<tag>`／`wait`／`replan`／`panic`／`done`（結構化 tag，可組合：replan＋executed 同拍） |
| popped | 本拍記帳掉的步驟名列表 |
| head／plan | 執行了誰＋剩餘隊列 |
| duration_ms／slept_ms | 本拍耗時與 handler/action 內睡眠（sleep 進了流水帳才有數據可調） |
| progress | 累積觀測進度鍵（熔斷的分母） |

輸出沿用 `data/runs/` jsonl 慣例，僅供工程分析；熔斷只讀 process
內流水帳（「流水帳不當跨執行先驗」紅線）。

## 與現有 bot/ 骨架的差異（重塑清單）

1. `on_blocked`／`_repair`／`repair_max_cost`／`still_relevant`
   移除→replan 一元化。
2. `decide` 改同拍續行：pop 後繼續判新隊頭、replan 後當拍執行；
   「popped／blocked 拍不執行」規則廢除。
3. `act` 的 `_settle_left`／`_last_action`／`settle_ticks` 機制
   移除→do() 內 sleep＋action refire 政策。
4. `MockSensor` 換成 mock 分類器（輸出 `{phase, tags}`）＋符號表；
   `sense_update` 的呼叫端變成 router。
5. `WaitOut`／假 eff 廢除→等待格；`ClearObstruction` 轉反射
   handler；`ReachHub` 等導航動作留在 catalog（replan 用）。
6. `TickRecord` 擴欄位（上表）。
7. 兩張表＋完備性測試新增。

## 延後清單（記錄保留實作彈性，v1 不做）

1. **期望判別**：需要動作歷程供分類結果判斷「非預期中斷 vs 正常
   流程」——保障 robustness，但前提是基礎實作正確，v1 不碰。
2. 反射表「適用 phase 集合」掛載欄位（metrics 見誤判再加）。
3. 分類器去抖 wrapper（metrics 的 replan 原因統計再回頭）。
4. 熔斷器（metrics 先行，規則見上）。
5. 固定 sleep→短輪詢升級（逐 handler、依 metrics）。
6. back 反射（v1 由 replan＋導航 action 承接，見反射表節）。
