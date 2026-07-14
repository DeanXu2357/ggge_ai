# ggge_ai

自動化通關 SD Gundam G Generation ETERNAL（`com.bandainamcoent.gget_WW`）
手機遊戲。USB/WiFi adb 實機操作（2340x1080 橫向），雙層 GOAP 架構＋
expectiminimax 戰鬥模擬器，Python 3.12+/uv，OpenCV 模板視覺。

## 開工必讀（順序固定）

1. `CLAUDE.md` — 專案守則與架構紅線。
2. `docs/roadmap.md` — 最上方暫停快照（裝置現況與恢復點）。
3. `docs/agent-architecture.md` — 架構全文。

## 文件地圖

| 文件 | 內容 |
|---|---|
| `docs/agent-architecture.md` | 雙層 GOAP、機制/內容分離、模擬器與 solver 設計 |
| `docs/stage-definition-requirements.md` | 關卡定義檔＋uid 身分制需求（待規劃） |
| `docs/combat-formulas.md` | 戰鬥公式與交戰結算順序（模擬器的規格書） |
| `docs/battle-phase-states.md` | 戰鬥生命週期（ACTIONABLE 二元模型） |
| `docs/screen-map.md` | 畫面與 UI 操作文法（座標、狀態機） |
| `docs/roadmap.md` | 進度與暫停快照 |
| `docs/archive.md` | 歷史檔案庫——被新架構取代的舊定義與演變歷程，開發時不需要讀 |

## 目錄結構

- `src/ggge_ai/` — core（GOAP 引擎）/ domain（遊戲知識）/ battle（戰鬥
  控制器、模擬器、solver）/ perception / actuation / vision
- `assets/templates/` — 畫面錨點與元素模板（manifest.yaml 登記）
- `tests/` — 離線測試（fixtures 含實機截圖回歸語料）
- `scripts/` — 截圖/裁切/驗證/戰鬥啟動/流水帳分析工具
- `data/` — 關卡 cache 與執行流水帳（runs/ gitignored）
- `secrets/` — 敏感資訊（gitignored），`*.example.json` 為格式範例
