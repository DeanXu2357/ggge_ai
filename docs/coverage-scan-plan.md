# 覆蓋驅動掃描重寫計畫（#26 批3：serpentine 退役）

狀態：**已執行完畢（2026-07-23，批1~批5）**。全庫 786 passed／3 xfailed／
0 skipped、ruff 綠；serpentine 退役、cache bounds 預載落地、LLM 第三層
no-ship 休眠。實機驗證輪見 [live-verification-queue.md](live-verification-queue.md)
佇列 1。
執行模式：協調者管線（主 session 計畫 → Opus subagent worktree 分批開發 →
主 session 審核 → sonnet subagent 實機驗證）。

## 1. 背景：2026-07-23 凌晨實機失敗的根因

流水帳 `data/runs/20260723-005301/battle_01.jsonl`；詳細分析見 issue #26
留言與 [map-scan-survey.md](map-scan-survey.md)（07-23 段的「垂直漂移污染」
說法經流水帳複核**不成立**，批5 更正——18.2 是 corner 錨定前座標，錨定時
camera 已歸零，row 腿實際垂直漂移僅 0.5px）。實際因果鏈：

1. **偵測器域錯配（根因）**：T3 前置把 full_scan 工作點改到最小 zoom，
   但 `LiveScanSource._find_units` 仍用 battle-zoom 校準的弧形偵測器，
   27 台單位只普查到 2 台。為最小 zoom 特製的 `find_unit_density_peaks`
  （九幀 recall 104/104）只接在離線 map_stitch，live 鏈路未接——此缺口
   07-20 已登記在 #26 待辦（「controller 尚未接 min-zoom 偵測器」），
   批2 cutover 與 T3 交會時漏接。**分類：已定義、已離線實作、整合漏項**。
2. **量測鏈全崩（衍生）**：pool 稀疏使 landmark 重定位繳白卷、
   `measure_arc_shift` 同組偵測器同瞎，量測全落到 phase correlation——
   而 phase 在「格線開啟的最小 zoom」已被離線裁定不可用（週期紋理假鎖、
   07-20 從拼接管線整條移除），該裁定未搬進 live。
3. **south 假邊界（症狀）**：`south_step` 四次嘗試僅量到 11.5px、
   `_at_edge` 以「量測位移 vs 手勢量」推論出南邊界，serpentine 只掃兩排
   收工。「拖曳被吃」與「phase 假鎖」兩機制無法離線裁定，但都通向同一
   假邊界。west/north/east 的判定在 min-zoom 幾何下（23×96.5≈2220 vs
   視口寬 2340）很可能為真；假的只有 south（24×92≈2208 vs 視口高 1080）。
4. **下游污染**：2 地標 `pool.locate` 假鎖跳 335px、survey 讀出假名
   「戰鬥」、第二台無橫幅 → `SurveyIncomplete` fail-fast 正確攔截，
   `turns:1` 未浪費回合。
5. **離線測試蓋不到**：`test_live_scan.py` 的 `_World` 用抽象點位與無雜訊
   相機，偵測器域外行為與手勢雜訊皆不在被測範圍。

## 2. 使用者定案（2026-07-23，本計畫的設計紅線）

1. **手勢量全面退出座標計算**——不當量測、不當先驗、不當 tie-break。
   手勢只是「把鏡頭推走」的操作，卡頓/掉包/被吃只損失時間、永不污染
   座標。
2. **幀間關聯只用相對關係資料**：單位星座＋逐格地形指紋＋邊界目視。
   位移量測（phase correlation／arc shift／手勢假設）從掃描路徑退役。
3. **掃描改覆蓋驅動**：以格為單位記覆蓋帳，由「哪些範圍還沒看過」反推
   下一步，迴圈補圖至帳目閉合。地圖大小是掃描產出（首訪）或 cache 先驗
   （回訪，畫面仍權威）。
4. **邊界只在「看見」時成立，永不從「推不動」推論**——`_at_edge` 類
   機制整批退役。
5. **LLM 視覺輔助為定位階梯第三層**：注入式（`from_env()`，None=該層
   不存在）、輸出只是假設、確定性 patch 驗證過門檻才碰座標、上線前先
   離線 probe 量測能力。
6. **偵測器域匹配**：full_scan（最小 zoom）注入 `find_unit_density_peaks`；
   `_scout_local`（battle zoom）維持弧偵測不動。

## 3. 架構分層

```
視覺原語（vision.py，純函式）
  ├─ find_unit_density_peaks         既有不動；由迴圈注入使用
  ├─ read_map_lattice（新，擴充自 read_grid_lattice）
  │    全幀格線外插＋「格網截止緣」＝邊界目視證據
  └─ cell_fingerprints（新）          逐格地形指紋（Lab 均色＋亮度統計）

幀觀測（新，純函式）
  └─ observe_frame(frame, detect) → FrameObservation
       格線、入鏡邊、單位（px＋格位）、逐格指紋、威脅格

全域地圖帳（新模組 battle/coverage_map.py，純狀態）
  └─ CellMap：bounds（格）/units/terrain/covered
       localize(obs)   → 整數格偏移 | None（唯一定位機制）
       integrate(obs, offset)
       frontier()      → 下一目標區 | None
       to_tacmap()     → 下游相容匯出（TacticalMap＋px bounds）

操作（笨函式，不含判斷）
  └─ nudge(direction)：避單位起點、單次 swipe、settle；不量測不解讀

迴圈（battle/live_scan.py 重寫 → CoverageScanSource）
  └─ Phase A 錨定 → Phase B 補圖 → 完成/SurveyIncomplete
```

## 4. 定位階梯（localize）

1. **邊界硬約束**：幀內看見西邊 → 欄偏移絕對釘死（西邊＝第 0 欄）；
   角落入鏡 → 偏移完全確定，免投票。
2. **格特徵投票＋裕度**：枚舉剩餘候選偏移，逐格計分。權重配置經批2
   實測修正（2026-07-23）：**distinctive 地形匹配比例是裕度載體**
   （TERRAIN_WEIGHT=15），單位命中降為佐證＋證據下限（unit≥3 或地形
   比例≥0.5）——因為出擊編隊是格規則的，單位票（連同像素差）在錯誤
   偏移下會自對齊（pt6 實證），off-formation 地形不會；此修正同時讓
   定位不再需要 map_grid 的 pan 方向 hint（手勢衍生、紅線禁用）。
   最高分未以 `LOCALIZE_MARGIN`（=2.5）拉開第二名 → 拒判。
   **寧可不定位，不可猜**。
3. **LLM 輔助（注入時才存在）**：向 `LlmScreenReader` 送當前幀＋最後
   定位成功幀，要求指認兩幀共通地標及各自格座標（定案 6 欽點用法的
   live 化）。回覆換算偏移假設後：兩幀宣稱位置各裁 patch 做確定性比對
   （過絕對門檻）＋與已見邊界一致性檢查，通過才採信並記
   `source=llm_assist`；不過視同失敗。**LLM 字面輸出永不直接碰座標**。
   **批4 現況（2026-07-23）：no-ship**——tier 已按強版落地並上鎖護欄，但
   probe 實跑顯示本機 gemma 生產預設 0/8 exact、係統性回 (0,0)（毫無位移
   訊號），生產**不注入 llm**、迴圈與純確定性版 bit 級一致；換到有能力的
   模型時只需一行 `llm=self.llm` 並重跑 probe 覆核（見
   [llm-localize-probe.md](llm-localize-probe.md)）。
4. **None → 回復協定**（§5）。

## 5. 掃描迴圈

**前置不變**：T3 序列（退頂層 → 開格線 → 拉最遠 → `zoom_at_max` 驗證，
兩輪不過=SurveyIncomplete）。有定義檔 cache 時預載 bounds 當覆蓋帳框架
（批5）；實掃見到的邊與 cache 矛盾 → 作廢預載、退回探索。

**Phase A 錨定**：目標＝一張西邊＋北邊同時入鏡的幀。缺哪條邊就朝那個
方向 nudge → 截圖 → observe，直到看見（純目視、預算 `ANCHOR_MAX_NUDGES`）。
地圖小於視口時開場即完成。

**Phase B 補圖迴圈**：

```
while nudge 預算未盡:
    target ← map.frontier()
    │  優先序：未見邊方向（南/東外推）＞ 已知框內最大未覆蓋區
    │  None → 四邊皆見＋無未覆蓋格 → 完成 ✓
    dir ← 最後定位成功幀的偏移 指向 target（信念只選方向，不進座標）
    nudge(dir)（保守短推：可定位性優先於效率）；截圖；observe
    off ← map.localize(obs)
    ├─ 成功 → integrate；覆蓋帳前進
    └─ None → 回復協定：朝最近已知邊連續 nudge 直到見邊 → 絕對重錨
              （預算 RELOC_MAX_NUDGES）
    卡死偵測：連續 STUCK_LIMIT 輪覆蓋零前進 → 換方向/換起點；仍卡 → 中止
預算盡而帳未平 → SurveyIncomplete fail-fast
```

**nudge 起點選擇**：沿用 `PAN_ORIGIN_GRID` max-min clearance，但 clearance
對象改為注入偵測器的峰值（修復「對隱形單位無效」）。誤觸彈窗防禦
（`_clear_obstruction`）不變。

**ledger 事件**：`nudge{dir,origin}`、`frame_localized{offset,margin,source,
edges,new_cells}`、`scan_recovery{reason,nudges}`、`coverage_report{cells,
covered,holes,bounds,legs}`。僅供工程分析（既有紅線）。

## 6. 下游相容與退役清單

**相容（下游一行不改）**：
- 完成後 `to_tacmap()` 匯出 `TacticalMap` pool（格位×pitch 還原 px 世界
  座標、保留 px 精修）＋ px bounds dict；survey／identify／seed／sim
  介面不變。
- **bring_to_view 同源改造**：survey 逐台導航改「nudge → localize →
  目標入鏡即停」，不再用 pan_leg 量測（順帶消滅 07-23 的 335px 假跳，
  即原案例三的主要病灶）。

**退役**：`pan_leg` 量測鏈、`_at_edge`、`SCAN_EDGE_RATIO`、serpentine
路線、`_snap_bound`、掃描路徑上的 `measure_camera_shift`／
`measure_arc_shift` 使用。保留：`_scout_local`（battle zoom，本輪不動）、
`map_stitch`／`read_board`（離線分析工具）。

## 7. 測試計畫（全部先於上機）

素材：`tests/fixtures/vision/map_scan/ex2if_20260719/`（九幀 PNG＋
ground_truth＋standard_answer：27 台、23×24、格距、我方指認）。

1. **原語**：全幀格線與截止緣（邊界真值幀）；指紋穩定性（同格跨幀）；
   透視失真容忍（畫面周邊 ~1.5 格，邊界量測取中央帶幀）。
2. **定位**：九幀兩兩配對以已知偏移為真值；**遮掉單位格只留地形**重驗
   （零單位密度最壞情境）；人造週期佈局驗裕度拒判；邊界硬約束案例。
3. **迴圈**：合成惡意世界（吃拖曳／隨機幅度／延遲到帳／掉包——手勢量
   與世界座標完全解耦）驗收斂、回復協定、預算 fail-fast；07-23 失效
   模式（稀疏偵測＋起點壓單位）做成永久回歸。
4. **端到端**：離線 replay 對標準答案——27 台、23×24、覆蓋 100%。
5. **接線**：controller cutover wiring＋偵測器注入斷言。
6. **LLM 層**：transport fake 驗假設-驗證-拒判三路；None 注入=行為與純
   確定性版 bit 級一致。

## 8. 批次拆分與驗收條件

| 批 | 內容 | commit | 驗收（實際） |
|---|---|---|---|
| 批1 | 視覺原語：`read_map_lattice`（全幀＋截止緣）、`cell_fingerprints`＋fixtures | `932eb4f` | 原語測試綠；九幀邊界真值全中 ✓ |
| 批2 | `FrameObservation`＋`CellMap`（localize 第 1-2 層／integrate／frontier／to_tacmap） | `de1b0f1`／`83a257b` | 配對定位真值全中；遮單位純地形定位過；裕度拒判過；標準答案端到端（27 台／23×24／覆蓋≥95%）過 ✓ |
| 批3 | `CoverageScanSource` 迴圈＋回復協定＋controller cutover（含 bring_to_view）＋退役清單執行 | `984c95e`／`bbd0960` | 惡意世界收斂；07-23 假南邊界回歸鎖死；全庫測試＋ruff 綠 ✓ |
| 批4 | LLM 第三層：`scripts/llm_localize_probe.py`（九幀已知偏移測 gemma 地標對應準確率、報告落檔）→ 依結果定強弱版接線 | `e6849e2`／`8000baf`／`2b673f9` | probe 報告落檔（gemma 0/8 exact→**no-ship**）；fake transport 測試；None 注入等價性 ✓ |
| 批5 | cache bounds 預載＋文件回寫（map-scan-survey 07-23 根因更正、roadmap 快照、live-verification-queue、本檔狀態）＋未提交 docs（mp-tension A7 段）一併 commit | `18ee1be`＋文件收尾 | hint 加速／矛盾丟棄／無 cache 等價／schema 往返／controller 讀取（15 測）綠；文件一致；佇列更新 ✓ |

最終全庫：**786 passed／3 xfailed／0 skipped**、`ruff check src tests scripts`
全綠。

每批：Opus worktree 開發 → 主 session 審核（`uv run pytest -q`＋
`uv run ruff check src tests scripts` 全綠、驗證證據）→ 合併。批4 不擋
主線（前三批獨立完整）。

## 9. 實機驗證（修復後，登記 live-verification-queue）

- 同活動關冷掃全鏈路重跑（佇列 1 重排）：驗手勢方向推動有效性、覆蓋
  收斂 legs 數、邊界目視偵測四邊全中、survey 接續至 identify。
- 附帶確認：`_scout_local`（turn-2+）實際 zoom 狀態——若遊戲停留最小
  zoom，local scout 有同款偵測器錯配（既存疑問，非本輪引入）。
- 順手補拍缺樣本清單（見 live-verification-queue）。

## 10. 開放旗標（不擋本計畫）

- `MERGE_RADIUS` 70 vs min-zoom 格距 92 的誤併裕度偏薄——cell 空間整合
  後身分以格為單位、大幅緩解；`to_tacmap()` 匯出時留意。
- LLM probe 若顯示 gemma 格座標能力不足 → 降階弱版（地標描述＋方位，
  patch 驗證承擔全部定位）；probe 結果落檔後定案。
- 「單位密度過低且無邊入鏡且地形均勻」的理論死角：不假裝不存在——
  靠地形指紋使其極罕見、裕度規則使其可偵測、回復協定使其傷害有界，
  最終 SurveyIncomplete 兜底。
- **批1 旗標（換地圖家族需複驗）**：`read_map_lattice` 的截止緣（邊界目視
  證據）與 `cell_fingerprints` 的暗程／暗尾閘門是用**太空圖家族**（ex2if
  星圖）樣本校準的；換地圖家族（雪地／地面）色彩與亮度分布不同，閾值
  很可能要重調，上機前先補該家族的邊界真值幀與同格跨幀指紋樣本複驗
  （CLAUDE.md 紅線：沒有新截圖證據不動閾值）。
