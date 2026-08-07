# 收斂到 sweep 單流程——舊堆疊刪除批導覽（2026-08-07）

使用者裁決：關卡內執行流程只留 sweep（`scripts/sweep_scan.py`＋runtime/ 堆疊），
其餘全刪。前置事實：runtime/ 對 battle/、stage/ 零 import，sweep 傳遞閉包
只咬 battle/ 四檔與 stage/ 數檔，依賴方向單向乾淨。還原點＝本 commit 的
父 commit（git 全數可回復）。

## 刪除範圍

- **src 63 檔 14,559 行**：battle/ 舊控制器鏈 21 檔（controller、live_scan、
  scout_intel、tracker、coverage_map、map_grid、map_stitch、frame_source、
  roster_calibration 等）；整包 goap/、agent/、planner/、content/、strategy/、
  domain/actions/；domain/{goals,screens,translate}；stage/{loop,run,planner,
  gestures,goals}；sandbox/{search,tactician,diagnose}；perception/llm；
  vision/motion；runtime/reflexes；cli.py、__main__.py；scripts/dry_run_entry.py。
- **tests 67 檔 14,258 行**：上述模組的連動測試＋conftest.py（只服務 agent/ 舊鏈）。

## 保留面（sweep 閉包＋工具）

battle/{faction,vision,map_view,state,settings}、stage/{actions,survey,state,
intel,intel_panels}、sandbox/{advise,model}、sim/ 整包、vision/{manifest,
pipeline,base,digits,template}、actuation/ 整包、perception/{base,adb/}、
domain/roster、app.py（scripts/ensure_unlocked.py 與 capture 通道依賴）、
runtime/ 全部（reflexes 除外）、marchkit（串流批次接線用）。

## 非刪除的修改（review 重點）

1. `tests/test_battle_sim.py`：`battle.actions.ActionKind` →
   `sim.vocab.DecisionKind as ActionKind`。原 ActionKind 的 ATTACK／
   SKILL_EN_REFILL 就是 DecisionKind 成員的字面別名，行為等價；不為一個
   enum 別名保下整個 battle/actions.py（它還掛著已刪 goap.action 的
   TYPE_CHECKING import）。
2. `tests/test_package_boundary.py`：NEW_MODULES／FROZEN 清單同步刪除面；
   `test_no_new_module_imports_a_frozen_package` 未動且通過。
3. `tests/test_stage_survey.py`：拆掉 StageLoop／planner 段落，survey 本體
   測試全留。
4. `tests/test_forecast_readers.py`：拆掉兩個 signature_distance 測試
   （helper 在已刪 content/stage_def），battle.vision 覆蓋未動。

## 爭點與後續

- `test_vision_regression.py`（CLAUDE.md 點名的 HSV 門檻回歸守衛）隨舊堆疊
  刪除；vision.py 仍有 test_vision_arcs／cards／unit_cards／turn_marker／
  forecast_readers／defeat_screen／dialog_cursor 覆蓋。CLAUDE.md 規則文字
  待同步。
- tests/fixtures/ 有部分目錄失去引用者，未清（不佔 collection，另批處理）。
- 閘門：pytest 953 passed（刪前 1780；差額全為連動刪除）、ruff 綠、保留
  腳本 --help／import 煙霧測試全過。實機能力驗證＝sweep12 完整輪（本批
  合併後執行，對照 0805 run12 基準）。
