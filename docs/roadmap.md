# roadmap

CLAUDE.md 的開工／收工紀律綁這份檔案的暫停快照。`83fce1e` 刪掉 16 份
doc（含本檔前身）後由使用者裁決重建，範圍只有**裝置現況＋恢復點**——
規格不寫在這裡（「程式碼就是規格」）。

## 暫停快照（2026-07-29）

### 裝置現況

- 本輪純文件作業，未觸碰裝置。07-27 快照的狀態未重新驗證：
  當時 adb 經 USB 正常（`ADB_LIBUSB=1` 生效）、螢幕熄滅、
  遊戲當下畫面未知（未喚醒、未解鎖，使用者刻意保留）。
- `data/cache/stages/` 空，備份在 `data/cache/stages.bak-20260723/`。

### 恢復點

- 分支 `feat/inner-goap`。`uv run pytest -q` 955 passed／3 xfailed
  ＋1 flaky（`test_not_actionable` 既有計時競態、7/24 定讞、單跑綠）、
  ruff 綠。
- 架構方向定案入庫：`docs/requirements.md`（基礎需求）＋
  `docs/architecture.md`（HTN 外層＋GOAP 內層、層界＝進入關卡、
  戰局沙盤雙注入、資源帳本、事實依據的邊界）。
- 既有程式碼（含 `bot/`）全部降級為實作參考，不作為新規劃的
  推斷依據——見 architecture.md「事實依據的邊界」。
- goal 規格已定案入 architecture.md（四目標項目＋達成約束二態）。
- 批次規劃核准入 `docs/module-map.md`（批 0～5＋調查線；stage 命名
  裁決）。**批 0 骨架已整合**：contracts 四契約、SHOP 式 HTN 引擎
  （帶回溯）、入口點 dry-run 最小生命週期（假帳本同步→無適用方法
  →誠實停止報告落 run 目錄）；舊碼零改動，`test_package_boundary`
  以 AST 掃 import 機械化凍結舊包。
- 調查 A／B 定稿落檔 `docs/rewards-and-scoring.md`（裁決：成就＝
  永恆之路逐關任務；主線評分公式放棄，改假設「10 機全存活＋每機
  殘 HP > 50% → ★3」批 2 實測）。
- 下一步：批 1（內層離線）規格核可 → 派工。批 2 首戰 stage 屆時
  由使用者指定。
