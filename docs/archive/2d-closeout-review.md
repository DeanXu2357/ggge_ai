# Review 導覽：2d 收尾小批＋scripts 清理（2026-07-30 合併）

對照本檔 review 收尾合併（含 `1e0aaa0`／`e9a094f`／`6d333fb`
三個小步 commit）與 scripts 清理 `7e006ad`。設計決定備案在
`docs/decisions.md` 0730「2d 收尾小批」「危險帶重疊」「scripts
清理」三條。

## Commit 全景

| commit | 內容 |
|---|---|
| 1e0aaa0 | 收卡條符號化＋三彈窗簽名補樣（兩者在 screens.py 交錯，併一 commit） |
| e9a094f | dry_run_entry.py 駕駛 script＋enter_stage 拆四段 |
| 6d333fb | script 掃描前自守兩個符號前置條件 |
| （merge） | 合併入 feat/inner-goap，全套 1458 passed |
| 7e006ad | scripts 清理：刪 11 支＋孤兒測試、CLAUDE.md 常用指令同步 |

---

## 功能一：收卡條符號化

### 呼叫導覽

符號層（與 ShowGrid 完全同構）：

```
stage/actions.py
  CollapseRoster   applicable＝我方回合＋not roster_collapsed
                   progressed＝roster_collapsed
  SurveyBoard      applicable 加第二前置：roster_collapsed
  Inspect.apply    作廢 roster_collapsed（點單位會彈回卡條）
stage/state.py     roster_collapsed 欄位＋next_player_phase 衰效
```

感知路（**感知權威**，不是簿記記憶）：

```
runtime/screens.read_roster_strip(frame)   三值：collapsed/expanded/None
  └─ 卡條標頭模板在「條帶頂」＝展開、「降到底」＝收合
  └─ None＝讀不出來（詳情彈窗蓋住等）——永不折成收合
runtime/perceive.read()                    每 tick 把 roster_strip 進 evidence
stage/survey.SurveyPerceiver               折進 StageState.roster_collapsed
stage/survey.BoardDriver.collapse_roster   執行器：先讀再點 (1970,780)；
                                           讀到 None 不盲點（怕把收好的又展開）
```

執行順序（規劃器自然排出）：`ShowGrid` → `CollapseRoster` →
`SurveyBoard`，各自跨 tick 重入 perform、由 progressed 判完成。

### Review 重點

- `None 永不折成收合`：0723 輪四 41 次空轉的教訓條文化
  （`screens.py read_roster_strip` docstring）。
- 換回合衰效取保守（作廢重收）；實機若證實卡條不彈回，
  `next_player_phase` 一行可拿掉（已列實機待驗）。

## 功能二：三彈窗簽名解封

`runtime/screens.py` SIGNATURES 新增 group 0（系統彈窗蓋住
一切，既有 group 全體 +1）：

| 簽名 | 判別帶 | 為什麼選這帶 |
|---|---|---|
| login_bonus | 「LOGIN BONUS」標題字 | 全語料唯一 |
| notice | 「公告」標題列 | **不用關閉鈕帶**——1002 張全掃鈕帶誤命中 100 張（單位詳情同款按鈕框），標題僅 4 張 |
| date_changed | 「前往主畫面」鈕字 | 「更新資料」標題是維護對話框共用的；鈕字既是識別也正好是反射要點的那顆 |

呼叫鏈不變：classify 吐名字 → `reflexes.py` 三個 PopupReflex
從此會命中（先前接好但啞）。fixtures 留在
`tests/fixtures/vision/popups/`（含暗幀／載入空窗態），
`test_runtime_reflexes.py` 新增真幀→classify→反射→tap 全鏈測試。
已知空窗：公告近全黑載入幀無樣本，該期間回 unknown（不猜）。

## 功能三：dry_run_entry 駕駛 script

```
scripts/dry_run_entry.py（薄：組裝＋迴圈）
  └─ runtime/entry.py  select_stage → open_sortie_prep → sortie
                        → advance_to_map（enter_stage 拆四段，
                        分段停點做在可測層）
  └─ LiveExecutor      ShowGrid／CollapseRoster／SurveyBoard
                        （--stop-after grid/survey 段）
  └─ abandon_battle    棄戰收尾（--no-abandon 可關）
  └─ Journal           data/runs/<時間戳>/dry_run.jsonl＋frames/
```

- 任何 expect／閘門失敗 → `HALT:`＋截圖路徑、退出碼 1、不再點。
- script 不跑規劃器，所以掃描前自守兩個符號前置條件（逐幀複核
  grid_on 與 roster_strip，不成立即 Halt）。
- 停點用法（給 live-tester 的指令）見 2d 收尾交付報告，
  或 `--help`。

### Review 重點

- 關卡節點 (544,872) 落在放棄危險帶 → TapRefused（已寫成測試；
  處置＝保留帶、點編號列 y~667 或人工選關，decisions.md）。
- `--stop-after stage_info` 無自動收尾路徑（abandon 需在地圖上），
  tester 要手動退。

## scripts 清理（7e006ad）

留 10 支（新架構工具鏈＋模板工作流），刪 11 支＋孤兒測試——
全數掛凍結舊包或已被取代；逐支清單與理由在 decisions.md。
CLAUDE.md 常用指令改列：capture／ensure_unlocked／
probe_live_channel／dry_run_entry／parse_panel／verify_match／
crop。注意 ensure_unlocked 仍 import 凍結 actuation/keyguard
（過渡容忍，刪 battle/ 時轉 runtime.keyguard）。

## 待你 review 時特別看的爭點

1. 卡條「換回合作廢」的保守選擇——多付一次收卡條 vs 漏收風險，
   實機證實不彈回就拿掉。
2. 危險帶 vs 關卡節點重疊的處置粒度（保留帶＋繞開 vs 帶感知
   畫面名）——批 3 外層選關落地時要重議。
3. 公告簽名的標題帶選擇（誤命中證據在交付報告）。
4. scripts 清理的去留判斷，特別是 run_manual_battle／
   run_clear_loop（操作需求改由裸 adb＋dry_run_entry 承接）。
