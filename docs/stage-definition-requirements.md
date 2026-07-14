# 關卡定義檔與單位身分制——需求定案(待規劃)

定案日期:2026-07-14 晚(pilot 離線批次 M1-M7 之後的討論);狀態:
**需求已定調、尚未規劃、尚未實作**。本文件是下次規劃 session 的冷啟動
輸入,與 M8(雙行為 observer,見 roadmap)屬同一個架構動作,應合併規劃。

## 起因

1. HSV 判決確定 hub 粉紅我方弧與敵紅弧逐像素不可分(fixture
   `our_turn_hub_mixed_factions`,同幀 H7-8/S135/V202 vs H8/S136/V204),
   臨時解是 sig-confirmation 過濾(`hub_poisoned=True`)+ intel 動態預算
   (上限 12,commit b587fe2)。
2. 使用者指出臨時解的根本矛盾:**盤面不完整時 solver 是在錯誤的賽局上
   求解**(minimax 類演算法需要完整賽局);且關卡內容遊戲寫死,正解是
   「第一次掃描建檔、之後進關直接調用」,不是每次現場重讀加預算節流。
3. 使用者再指出 sig(名牌 dHash)當身分主鍵的缺陷:**同機種不同駕駛員
   數值與能力不同**(實例:HARD 2 敵方阿姆羅 vs 雜兵同開鋼彈,名牌
   相同 → sig 相同 → 現行 `acquire_stage_intel` 對已知 sig 直接跳過,
   第二台連面板都不開,駕駛差異永遠丟失)。

## 定案一:後端自建單位編號(uid)為唯一身分

- 盤面/模擬器自己發號(如 `e01`、`e02`),跨回合、跨掃描、跨進關不變;
  增援單位在定義檔裡**預先有號**。
- **sig 降級為關聯證據之一**,不再是身分主鍵。把「畫面上的觀測」關聯到
  「哪個 uid」的證據集:初始格位(定義檔)、位置連續性、sig(機種指紋,
  縮小候選集)、HP/EN 讀值、駕駛員面板(MP、能力、駕駛名)。
- specs 按 uid 掛,不按 sig 掛;開局建檔時**每台都開面板**(不做 sig
  去重),駕駛差異才抓得到。成本由定義檔吸收(每關一生付一次)。
- 既有的 sig 抖動容差(hamming ≤6,commit 099626f)保留,但只是證據層
  工具。

## 定案二:關卡定義檔(stage definition)

`data/cache/stages/<系列>/<關卡>.json` 從「機體 kit 快取」升級為
**solver 要求解的賽局完整描述**。Schema 草案:

```
├─ version: 遊戲版號
├─ layout:      # 初始盤面
│   [{uid, cell, machine(機種/名牌sig), pilot, stats, weapons, abilities}]
├─ conditions:  # 勝利/失敗條件(結構化 taxonomy)
│   {victory: [...], defeat: [...]}
└─ events:      # 條件觸發的盤面變化
    [{trigger: {kill: uid, within_turn: N, ...},
      effect: {spawn: [{uid, cell, machine, ...}] | weaken: [uids] | ...}}]
```

三類內容的取得路徑:

| 內容 | 來源 | 備註 |
|---|---|---|
| layout | 冷 cache 全量掃描 | 見定案三 |
| conditions | 出擊載入後的**關卡資訊畫面**(既有待辦「勝利條件讀取」的掛點,AUTO 硬閘門已停在該畫面)＋戰鬥中選單 | 文字→本地 LLM 轉錄成結構化條件;**taxonomy 外的條件型別照錄存檔、對 planner 惰性**(同能力 taxonomy 模式) |
| events | 第一次遊玩時**觀測記錄**(演出階段辨識的產出:認出「新敵機登場演出」→ 記 (觸發脈絡→生成位置/機種) 寫回檔)或人工/社群轉錄 | 第一次打必然盲(fail-fast 暴露),第二次起 solver 知情。實例:HARD 2「2 回合內殺阿姆羅→增援」 |

## 定案三:冷掃全量、溫 cache 校驗、預算刪除

- **冷 cache(該關第一次)**:全量掃描到完整為止——敵機數、每台 kit、
  初始佈局全部入檔。**掃不完=大聲失敗**,不是掃到哪算哪。
  `IntelBudget` 動態上限 12(commit b587fe2)**整個拿掉**;唯一保留
  wall-clock 保險(凍機考量),但超時語義=「intel 不完整→報錯停下」,
  不是默默繼續。
- **溫 cache(重複進關)**:盤面直接從定義檔載入餵 solver;現場只做
  **開局校驗**(抽查摘要卡 HP/機種/數量與檔案比對)。不符 → 整關標記
  過期 → 退回現場全讀重建檔。**畫面永遠權威**(紅線不變)。
- 全量掃描只剩三個觸發:無 cache、校驗失敗、人工 debug。
- `hub_poisoned` sig-confirmation 過濾保留,但職責縮小為「當前回合位置
  歸屬」的把關;**敵人存不存在由定義檔決定**,不再由單次掃描決定。

## 定案四:solver 吃定義檔

- `_terminal` / evaluator 改**條件驅動**:現行「一方全滅」終局測試只對
  殲滅型關卡是對的賽局;護衛型、限時型、斬首型關卡需要各自的目標函數
  (斬首關該直奔指揮官,不是農擊殺數)。
- `step()` 套用 events:搜尋樹**內部**展開「殺 e03 → 增援出現在固定格」
  「殺 e01 → 光環解除全體弱化」——solver 才能自己發現拆增援口、
  給光環機正確的擊殺優先權定價。
- 這是**純模擬版**(使用者既定目標)的先決條件:同一份定義檔離線開局,
  關卡事件以資料插入、不靠 observer 感知。

## 紅線邊界(必須劃清)

- **腳本事件**(固定觸發→固定結果)=遊戲寫死內容 → 入檔合法
  (2026-07-05 感知記憶化修訂涵蓋)。
- **敵 AI 傾向**(這關敵人偏好打誰)=統計信念 → **不入檔**,維持
  process-scoped;跨執行的關卡 AI 推斷觸碰無先驗紅線,需使用者另行簽核。
- 我方單位:定義檔/roster cache 只記身分與基礎 kit,**實際數值永遠
  現場讀**(養成影響,紅線不變)。

## 影響面(規劃時的清單起點)

- `stage_cache.py`:schema 重造(sig-keyed dict → uid 列表+conditions+events)。
- `scout_intel.py`:建檔流程語義(全量、每台開面板、失敗即報錯);
  `IntelBudget` 動態機制移除。
- `observe.py` / `tracker.py` / `reconcile.py` / `executor.py`:身分鍵
  從 sig 改 uid,sig 降證據(目標驗證改「uid → 預期 sig+預期位置」複合比對)。
- `sim.py` / `solver.py`:events 轉移規則、條件驅動 terminal/evaluator。
- `battle/controller.py`:開局校驗流程、演出階段辨識掛點(M8)。
- 對應測試全面翻新;replay harness(scripts/replay_frames.py)可用於
  觀測值回歸。

## 與 M8 的關係

M8 雙行為 observer(完整同步/反應動作/演出階段辨識/事件資料插入,
見 memory `observer-two-mode-architecture`)與本文件是同一架構動作:
完整同步=建檔與校驗的執行者;演出階段辨識=events 的觀測來源;
事件資料插入=定義檔的消費介面。**合併成一次規劃**,拆成離線優先的
里程碑(schema/sim 事件機制/條件 evaluator 可全部離線先行,實機只剩
讀取標定與校驗流程驗證)。

## 規劃時的開放問題

1. uid 發號規則與跨進關穩定性(佈局順序?格位排序?)。
2. 同格不同駕駛的辨識時機:摘要卡看得出駕駛差異嗎(MP 欄位?),
   還是一定要開詳情面板?
3. conditions taxonomy 的初版集合(殲滅/護衛/限時/斬首/到達?)與
   關卡資訊畫面的實際文字樣式(需實機樣本)。
4. events 觀測記錄的最小可行格式:第一次盲打時 observer 至少要記下
   什麼,才夠第二次重建 trigger?
5. 校驗抽查的樣本數/成本(抽幾台?只比 HP 夠嗎?)。
6. 舊 sig-keyed cache 檔的遷移或作廢。
