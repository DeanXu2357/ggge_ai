# 模組地圖與入口點（2026-07-29 核准）

批 0 的落地規格。包邊界與跨層契約是規劃本體，包內檔名是示意，
開發時可合併拆分。命名裁決：關卡一律採遊戲內命名 **stage**
（包名、契約、CLI 參數同）。

## 包結構

```
src/ggge_ai/
  __main__.py     入口點：python -m ggge_ai
  cli.py          goal 輸入解析、執行組裝、停止報告
  contracts.py    跨層資料契約（防飄移錨點）
  strategy/       外層 HTN
    htn.py        任務／方法分解與回溯引擎（小型手寫、領域無關）
    domain.py     領域方法：評估→出擊→刷資源→強化→再戰
    ledger.py     資源帳本：開機同步、動作效果更新、一致性探針
    assess.py     隊伍實力評估：沙盤診斷門面＋參數微調實驗
  stage/          內層 GOAP（一次 stage 攻略）
    run.py        一次攻略的生命週期：StageOrder 進、StageReport 出
    loop.py       tick 迴圈：感知→反射→簿記→規劃→至多一次操作
    planner.py    GOAP A*
    actions.py    行動詞彙（移動／攻擊／待機／應戰／主動離開…）
    intel.py      情報記錄與回寫 stage 快取
  sandbox/        戰局沙盤與搜尋
    model.py      戰局狀態與轉移（承接遊戲機制事實：公式、結算順序）
    search.py     expectiminimax
    diagnose.py   外層門面：勝率＋瓶頸類型＋缺口數值
    advise.py     內層門面：戰術定價
  runtime/        兩層共用執行底盤
    device.py     adb 截圖與觸控
    perceive.py   畫面分類與讀數（吃實機標定成果：模板、座標）
    journal.py    流水帳 jsonl（兩層共用格式）
```

## 跨層契約（contracts.py）

- **GoalSpec**：stage＋目標項目子集（clear／score／achievement／
  hidden）＋達成約束（split 分輪／single 單輪）。cli 解析、
  strategy 消費。
- **StageOrder（派工單）**：stage 識別＋本輪目標集＋觸發彈窗既定
  方針（進／不進）＋預算（tick 上限等）。strategy → stage，層界入向。
- **StageReport（回報物件）**：終局種類（勝／敗／卡死／主動離開）
  ＋本輪目標集達成情況＋情報增量。stage → strategy，層界出向；
  結算數字不在其中——外層親讀結算畫面入帳本。
- **Diagnosis**：勝率估計＋瓶頸清單（類型＋缺口數值）。
  sandbox → strategy。瓶頸分類法未定（待辦 4），先以字串佔位。

## 入口點行為

- `uv run python -m ggge_ai --stage <stage> --objectives clear[,score,…]
  --constraint split|single [--dry-run]`。goal 輸入介面細節後續設計
  （待辦 3），先以最小 CLI 立起。
- 啟動：載入設定與快取 → 帳本同步 → GoalSpec 建 HTN 根任務 →
  外層迴圈。
- 停止：誠實停止與正常完成一律落 `data/runs/<時間戳>/`——原因、
  當下狀態、兩層流水帳（需求六）。
- `--dry-run`：全假件離線跑；批 1 的驗收形態、日後回歸測試骨幹。

## 批次總覽

調查線（平行）：A 成就與隱藏報酬、B 逐關評分公式——產出先與
使用者核對再落檔。

開發線（依序）：

- 批 0 骨架：本文件的包結構＋契約＋入口點，dry-run 最小生命週期。
- 批 1 內層離線：GOAP 迴圈＋全滅型 clear goal＋行動詞彙最小集＋
  沙盤戰術定價注入＋流水帳；離線假件全流程綠。
- 批 2 內層實機首戰：簡單已通關 stage 實機整場（首戰 stage 由
  使用者屆時指定）。
- 批 3 外層骨架：clear goal 端到端「指定 stage→無人值守通關或
  誠實停止」＋資源帳本 v1。
- 批 4 補強迴路：診斷門面＋參數微調實驗＋刷／強化方法入 HTN。
- 批 5 goal 全規格：score／achievement／hidden＋分輪／單輪約束。

## 舊碼處置

- `agent/`、`domain/`、`bot/`、`app.py`：即刻凍結（新碼不得
  import）；批 1 完成刪 `bot/`，批 3 端到端通過刪其餘。
- 其餘舊包（`sim/`、`planner/`、`goap/`、`vision/`、`battle/`…）
  ＝參考材料：邏輯隨各批搬入新模組（測試同步搬寫），搬完刪舊檔
  與舊測試。過渡期舊測試照跑。

## 批 0 驗收

包結構＋契約型別＋入口點落地；`--dry-run` 跑通最小生命週期
（假帳本同步 → HTN 判無適用方法 → 誠實停止報告落檔）；
pytest／ruff 綠（既有測試不得變紅）。
