# ggge_ai

自動化通關 SD Gundam G Generation ETERNAL（`com.bandainamcoent.gget_WW`）
手機遊戲。USB/WiFi adb 實機操作（2340x1080 橫向），雙層 GOAP 架構＋
expectiminimax 戰鬥模擬器，Python 3.12+/uv，OpenCV 模板視覺。

## 開工必讀（順序固定）

1. `CLAUDE.md` — 專案守則與架構紅線。
2. `docs/record/roadmap.md` — 最上方暫停快照（裝置現況與恢復點）。
3. `docs/explanation/architecture.md` — 架構方向與邊界。

## Documentation map

Each `docs/` directory holds one document type; each file declares
its type in a label line under the title (see CLAUDE.md, section
'Document types').

| Path | Type | Content |
|---|---|---|
| `docs/requirements/` | requirements | Why we build this; outcomes only |
| `docs/reference/` | reference | Facts about the game, the device, and the data (UI maps, combat formulas, terminology) |
| `docs/spec/` | spec | Authoritative descriptions of implemented mechanisms |
| `docs/explanation/` | explanation | Intent and boundaries |
| `docs/how-to/` | how-to | Rules and steps for live-loop work |
| `docs/record/` | record | Pause snapshot ('roadmap.md') and decision ledger ('decisions.md') |

Retired documents live in git history only (former `docs/archive/`
and `docs/reviews/`, both deleted 2026-08-11).

## 目錄結構

- `src/ggge_ai/` — core（GOAP 引擎）/ domain（遊戲知識）/ battle（戰鬥
  控制器、模擬器、solver）/ perception / actuation / vision
- `assets/templates/` — 畫面錨點與元素模板（manifest.yaml 登記）
- `tests/` — 離線測試（fixtures 含實機截圖回歸語料）
- `scripts/` — 截圖/裁切/驗證/戰鬥啟動/流水帳分析工具
- `data/` — 關卡 cache 與執行流水帳（runs/ gitignored）
- `secrets/` — 敏感資訊（gitignored），`*.example.json` 為格式範例
