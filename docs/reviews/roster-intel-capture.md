# 對答案批次導覽（批A/B/C'/C/E，0810）

sweep 掃完盤面後新增「對答案」最後一步：進部隊資訊名冊逐台讀敵我詳情頁，
把機體／駕駛／武裝數值組成 UnitIntel，離線對帳後在 `data/runs/<ts>/` 產出
`scenario.json`（sandbox-scenario/1，load+build 自驗）＋`intel_report.json`。
需求裁決五點見 `docs/decisions.md`（0810 對答案條目）。

## 執行順序（一條龍）

```
scripts/sweep_scan.py
  select → prep → stage_info → map → grid → zero → sweep   （原樣不動）
  → roster 段（新）  SweepRun.collect_roster()
      RosterCapture.run()      裝置上只導航＋存幀，журnal 記 roster_capture
      dump_ledger()            帳本最終格帳 → ledger_dump 事件
  → abandon（原樣，roster 段任何失敗都不擋）
  → assemble_offline()（新，drive() 尾）
      roster_offline.run_offline(run_dir, reader=OllamaPanelTextReader.from_env())
      → scenario.json + intel_report.json（失敗記 journal 不改 exit code）
```

離線組裝可獨立重跑：`uv run python scripts/build_scenario.py data/runs/<ts> [--no-llm]`。

## 呼叫鏈與檔案

### 裝置端採集（批A＋批E）
- `src/ggge_ai/runtime/roster_capture.py`（新）：
  `RosterCapture.run` → `open_troop_info`（☰→部隊資訊）→ 每 faction
  `select_tab` → 逐格 `open_detail`（cell tap 帶 `roster_cell` intent，點前必驗
  TROOP_INFO）→ `capture_unit`（先 classify 判落地視圖→基本資訊幀→切詳情→
  三分頁幀＋武裝慢滑 `weapons_more` 幀）→ `close_to_map`（≤3 層證據驅動關回）。
  每拍走 `_shot`：settle 收斂→panel classify→哨兵讀值→keep。
- `src/ggge_ai/runtime/device.py`：還原 `roster_cell` intent 白名單
  （auto_battle_tristate／battle_menu_abandon 兩危險帶的假重疊格）。
- 0810 實機標定（批E）：`BASIC_VIEW_TAP=(1936,96)`、`DETAIL_TAB_TAPS`
  (985/1415/1835,173) 逐點驗過、`WEAPON_SCROLL` 0.8s 慢滑、
  `SHOT_RETRY_SLEEP_S=1.2`（左欄絕對值↔+delta 輪替約 2s）、駕駛頁不需要
  （駕駛六欄就在詳情左欄）、視圖有全域記憶（跨單位跨陣營）。

### 離線解析組裝（批B）
- `src/ggge_ai/stage/roster_offline.py`（新）：
  `run_offline` → `collect_captures`（journal 重放）→ `parse_unit`
  （panels.read_* 讀數字；`panel_text` 轉錄武裝名／效果句／abilities 詞條
  ——**只存字串不映射 schema**）→ `sweep_facts`（ledger_dump 優先、verdict
  重放備援）→ `reconcile`（對位鍵 (HP,EN)+faction）→ `build_scenario`／
  `build_report`。
- `src/ggge_ai/runtime/panel_text.py` 增 `PanelTranscriber` 轉錄通道
  （weapon_lines／ability_lines／stage_brief），與既有 coerce_weapon 字義
  路徑分離、後者本批不用。
- `scripts/build_scenario.py`（新薄殼）。

### sweep_scan 接線（批C'＋C）
- `sentence_shift`（我方出卡）加 `ally_readout()`：讀剛存的那張幀的右塢
  (HP,EN)，verdict 事件補 hp/en，讀不出記 None 不影響裁決。
- `STAGES`/`IN_BATTLE_STAGES` 加 roster；`--roster` 預設 True（舊行為加
  `--no-roster`）；`--stop-after roster` 可用。

## 對帳規則（reconcile）

- 敵方：詳情 (max_hp,en_max) 分組 ↔ 盤面出卡 (hp,en) 分組，精確相等才配；
  組合唯一→exact 綁格；同值互撞→同一 intel 樣板、組內格位任意指派
  （group_assigned）。
- 我方：批C' 之後出卡格也有 (hp,en)，同規則；讀不到退 arbitrary。
- NPC：本關 npc_count=0；出現則以觀測合成最小 intel（third_party、
  npc_observed_only）。
- 失敗全進 report 不 Halt：count_mismatch／unmatched_intel（進 intel 不進
  deployment）／unmatched_cell（合成 `enemy_unmatched_*` 保盤面完整）／
  unsure_cells。字模錯型（開頭插 1、8↔9）只出「近似對」提示，不自動配。
- victory/defeat：結構欄 annihilation/ally_annihilation＋source=assumed_default；
  關卡資訊畫面勝敗條件文字由 `stage_brief` 轉錄成字串進 note＋report。

## 爭點（review 時值得盯）

1. **視圖全域記憶**的處理：capture_unit 開場多讀一張幀判視圖；`open_detail`
   可能以 `panel_of==UNKNOWN`＋`screen==UNIT_DETAIL` 成立，此時會誤按一次
   切換鈕（該台 basic 頁可能拍歪，流程自癒不中斷）——首輪盯 `roster_capture`
   失敗 reason。
2. **哨兵重拍 1.2s×2 對 ~2s 輪替**：涵蓋兩個相位但非證明必中絕對值相；
   拍到 delta 幀離線會誠實進 gaps。
3. **(HP,EN) 精確配對 vs 字模錯型**：不自動配、只提示；首輪看
   count_mismatch 量再裁。
4. **abandon 依賴 close_to_map 收乾淨**：三層證據驅動關回＋頂層吞例外；
   回不到地圖時棄戰鏈會打錯位置——journal 每 tap 存證可診斷。
5. `BASIC_VIEW_TAP=(1936,96)` 距 auto_switch 危險帶下緣僅 6px，帶若加寬要回看。
