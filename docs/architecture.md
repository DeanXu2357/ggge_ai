# 專案架構設計

## 目標

自動通關 SD鋼彈G世代（`com.bandainamcoent.gget_WW`）。核心採用 GOAP（Goal-Oriented Action Planning）：給定 goal，規劃器自動從已定義的 action 集合中搜索出達成路徑，而非撰寫寫死的流程腳本。

## 語言：Python 3.12+

- perception 依賴（uiautomator2、OpenCV、OCR）皆為 Python 生態，已驗證可用
- 回合制遊戲規劃頻率低，無效能壓力；GOAP 核心只是 A* 搜索
- 主要開發時間花在調整樣板圖與 action 定義，Python 迭代最快

## 分層架構

```
┌─────────────────────────────────────────────┐
│  Agent Loop（sense → plan → act → verify）  │
├─────────────────────────────────────────────┤
│  GOAP Core                                  │
│  WorldState / Action / Goal / Planner(A*)   │
├──────────────────────┬──────────────────────┤
│  Domain（遊戲知識）   │                      │
│  screens / actions / │                      │
│  goals 定義          │                      │
├──────────────────────┴──────────────────────┤
│  Perception（介面）   │  Actuation（介面）    │
│  → GameState         │  ← tap/swipe/key     │
├──────────────────────┼──────────────────────┤
│  AdbPerception       │  AdbActuator         │
│  (uiautomator2 截圖   │  (uiautomator2       │
│   + OpenCV/OCR)      │   tap/swipe)         │
│  未來：其他實作…      │  未來：其他實作…      │
└──────────────────────┴──────────────────────┘
```

### 設計原則

1. **GOAP 覆蓋全域**：選單導航也是 GOAP action（前提 `current_screen=main_menu`、效果 `current_screen=stage_select`）。新增畫面只需補 action 定義，規劃器自動探索路徑。
2. **Perception 介面定在語意層**：回傳結構化 `GameState`（目前畫面、單位、HP、可點擊元素），影像辨識細節封裝在 ADB 實作內。未來換成封包側錄、模擬器記憶體讀取等方式時，GOAP 層不動。
3. **戰鬥智能先簡後繁**：第一版用啟發式（派最近單位、攻擊最近敵人）打通整條迴圈，之後再迭代戰術規劃。

## GOAP Core

```python
WorldState = dict[str, Value]      # 符號化事實，如 {"screen": "battle_map", "my_turn": True}

class Action(Protocol):
    name: str
    cost: float
    def preconditions_met(self, state: WorldState) -> bool
    def apply_effects(self, state: WorldState) -> WorldState   # 規劃期模擬
    def execute(self, actuator, perception) -> bool            # 實際執行

class Goal(Protocol):
    def is_satisfied(self, state: WorldState) -> bool
    def heuristic(self, state: WorldState) -> float

class Planner:
    def plan(self, state: WorldState, goal: Goal, actions: list[Action]) -> list[Action] | None
```

- 規劃器用 A*，以 action cost 總和為代價、goal heuristic 為引導
- **執行後驗證**：每個 action 執行完重新 perceive，比對實際狀態與預期效果；不符即重新規劃（replan），這是對抗遊戲彈窗、網路延遲、辨識失誤的主要手段
- 同一 action 連續失敗 N 次即中止並留下截圖與狀態 dump，供除錯

## Perception 介面

```python
class Perception(Protocol):
    def observe(self) -> GameState

@dataclass
class GameState:
    screen: ScreenId                 # 目前畫面的分類結果
    elements: list[UiElement]        # 可互動元素（id、bbox、信心值）
    battle: BattleState | None       # 戰鬥中才有：單位列表、位置、HP、行動狀態
    raw_screenshot: Path             # 原始截圖留檔，供除錯
```

`GameState → WorldState` 由一個轉換層負責（例如 `battle.enemies_alive == 0` 轉成 `{"all_enemies_defeated": True}`），讓 GOAP 只面對符號化事實。

### AdbPerception（第一個實作）

- 截圖：uiautomator2 `screenshot()`
- 辨識：交由 Vision 辨識層（見下節），AdbPerception 只負責取得影像並組裝 `GameState`
- 戰鬥棋盤解析：格子座標系標定 + 單位圖示比對

## Vision 辨識層（多辨識器架構）

辨識不綁定單一技術，定義統一的 `Recognizer` 介面，多個實作可依設定組合使用：

```python
class Recognizer(Protocol):
    name: str
    def classify_screen(self, img: Image) -> list[ScreenCandidate]        # 畫面分類
    def detect_elements(self, img: Image, query: Query) -> list[UiElement]  # 元素偵測
    def read_text(self, img: Image, region: Bbox | None) -> list[TextResult]  # 文字讀取
```

三種能力皆回傳附信心值（confidence）的結果，未支援的能力可回傳空集合。

### 實作一：TemplateRecognizer（OpenCV 樣板比對）

- 錨點樣板比對做畫面分類、按鈕定位（`assets/templates/`）
- 快（毫秒級）、座標精準、結果穩定可重現
- 弱點：樣板要人工裁切維護，遊戲改版或未見過的彈窗就失效

### 實作二：OcrRecognizer

- 讀取 HP、傷害數字、關卡名稱等文字（候選：PaddleOCR，中日文較佳）
- 只實作 `read_text`，其餘能力回傳空

### 實作三：LlmRecognizer（Ollama 多模態模型）

- 透過 Ollama API 把截圖丟給多模態模型，以 JSON schema 約束輸出（Ollama 支援 structured outputs）
- 本機已可用模型：`gemma4:31b` / `gemma4:26b` / `gemma3:27b`（皆支援影像輸入）
- 強項：
  - 零樣板成本理解任意畫面——處理沒見過的彈窗、活動公告、錯誤訊息特別有用
  - 語意層面的判斷（「哪顆按鈕是出擊」「目前是誰的回合」）
  - 遊戲風格化字體的閱讀常比傳統 OCR 穩
- 弱點與對策：
  - **座標定位不準**：一般多模態模型輸出的 bbox 不可靠。對策：(a) 讓 LLM 從樣板比對已找到的候選元素中「挑選」而非自行給座標；(b) 需要 LLM 獨立定位時，在截圖上疊加編號網格，讓它回答格號再換算座標
  - **延遲高**（秒級、31B 模型更久）：只放在 fallback 與低頻決策，不進高頻迴圈
  - **輸出不穩定**：temperature 設 0、JSON schema 約束、結果一律帶信心值進融合層裁決

### 融合策略（RecognizerPipeline）

執行時可依設定檔選擇啟用哪些辨識器與組合方式：

```yaml
# config/recognition.yaml 示意
screen_classify:
  - recognizer: template
    accept_above: 0.90        # 信心值達標直接採用
  - recognizer: llm           # 前者不達標才 fallback
    model: gemma4:26b
element_detect:
  - recognizer: template
  - recognizer: llm
    mode: arbitrate           # 樣板結果模糊時由 LLM 在候選中裁決
text_read:
  - recognizer: ocr
  - recognizer: llm
    mode: fallback
```

- **fallback 鏈**：依序嘗試，信心值達門檻即採用——常態走快速便宜的樣板比對，異常畫面才升級到 LLM
- **arbitrate**：多個候選難分高下時，把候選連同截圖交給 LLM 裁決
- **未知畫面兜底**：所有辨識器都無法分類時，由 LLM 描述畫面並建議脫困動作（例如關閉彈窗），這是 agent 異常恢復（M5）的關鍵能力
- 所有辨識結果統一落地 log（輸入截圖、各辨識器輸出、最終採用），供離線回歸與調參

## Actuation 介面

```python
class Actuator(Protocol):
    def tap(self, x: int, y: int) -> None
    def swipe(self, x1, y1, x2, y2, duration_ms: int) -> None
    def key(self, keycode: str) -> None
```

第一個實作 `AdbActuator` 包 uiautomator2。遊戲為橫向運行，座標一律以 2340x1080 基準定義，實作層在每次操作時查詢當前螢幕尺寸換算，避免裝置旋轉造成座標錯位。

## Domain（遊戲知識層）

遊戲相關定義全部集中在這層，與引擎解耦：

- `screens.py` — ScreenId 列舉與各畫面的錨點樣板對應
- `actions/navigation.py` — 選單導航 action（點擊某按鈕 → 畫面轉移）
- `actions/battle.py` — 戰鬥 action（選單位、移動、攻擊、待機、結束回合）
- `goals.py` — 如 `StageCleared(stage_id)`、`ReachScreen(screen_id)`

## 專案目錄結構

```
ggge_ai/
├── pyproject.toml
├── src/ggge_ai/
│   ├── core/                # GOAP 引擎（不含任何遊戲知識）
│   │   ├── state.py         # WorldState
│   │   ├── action.py        # Action / Goal 介面
│   │   └── planner.py       # A* 規劃器
│   ├── domain/              # 遊戲知識
│   │   ├── screens.py
│   │   ├── goals.py
│   │   └── actions/
│   ├── perception/
│   │   ├── base.py          # Perception 介面 + GameState 資料類
│   │   └── adb/             # uiautomator2 + OpenCV 實作
│   ├── actuation/
│   │   ├── base.py
│   │   └── adb.py
│   ├── agent/
│   │   └── loop.py          # sense-plan-act-verify 主迴圈、replan、失敗處理
│   └── vision/
│       ├── base.py          # Recognizer 介面、共用資料類
│       ├── pipeline.py      # 融合策略（fallback / arbitrate）
│       ├── template.py      # OpenCV 樣板比對
│       ├── ocr.py           # OCR
│       ├── llm.py           # Ollama 多模態模型
│       └── geometry.py      # 座標換算、網格疊加等工具
├── config/                  # recognition.yaml 等執行期設定
├── assets/templates/        # 各畫面錨點與按鈕的裁切樣板圖
├── tests/                   # core 規劃器可純單元測試；vision 用存檔截圖做回歸測試
├── scripts/                 # 輔助工具：截圖標定、樣板裁切等
├── docs/
└── secrets/                 # gitignored
```

## 工具鏈

- 套件管理：`uv`（lockfile、虛擬環境一體）
- 測試：`pytest`——GOAP core 與 GameState→WorldState 轉換為純函式，易測；vision 部分以既存截圖做離線回歸測試，不依賴實機
- Lint/format：`ruff`
- 主要依賴：`uiautomator2`、`opencv-python`、`numpy`、`ollama`（官方 Python client）；OCR 需要時再加

## 里程碑

1. **M1 — 骨架與 GOAP core**：規劃器 + 單元測試，不碰實機 ✅（uv 專案、core/planner A*、Recognizer 介面與 pipeline、AgentLoop、AdbActuator/AdbPerception 骨架、17 個測試通過）
2. **M2 — 畫面辨識最小集**：Recognizer 介面與 pipeline、樣板比對實作、LLM 辨識實作（Ollama）、截圖標定工具、3–5 個核心畫面的分類與按鈕偵測
   - 標定工具已完成 ✅：`scripts/capture.py`（實機截圖）、`scripts/crop.py`（裁切樣板並登記 manifest，支援 GUI 框選與 `--box` 直接給座標）、`scripts/verify_match.py`（離線驗證分類/偵測，可輸出標註圖）；樣板統一登記於 `assets/templates/manifest.yaml`（`vision/manifest.py`）
   - 實機驗證：截圖成功，遊戲為橫向 2340x1080、繁中介面
   - 待做：蒐集各核心畫面截圖並裁切錨點樣板、LLM/OCR recognizer 實作
3. **M3 — 導航打通**：從遊戲啟動 GOAP 導航到任一關卡的出擊畫面
4. **M4 — 戰鬥迴圈**：啟發式戰鬥決策，自動打完一場簡單關卡
5. **M5 — 完整通關迴圈**：戰後結算 → 回選單 → 下一關，含異常恢復（彈窗、斷線）
6. **M6+**：戰術強化、其他 perception 實作
