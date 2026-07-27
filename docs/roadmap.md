# roadmap

CLAUDE.md 的開工／收工紀律綁這份檔案的暫停快照。`83fce1e` 刪掉 16 份
doc（含本檔前身）後由使用者裁決重建，範圍只有**裝置現況＋恢復點**——
規格不寫在這裡（「程式碼就是規格」）。

## 暫停快照（2026-07-27 22:35）

### 裝置現況

- adb：R5CRC37JBYJ 經 USB 連線正常（`adb devices -l` 顯示 `usb:1-3`、
  `model:SM_G9900`）。`ps -T -C adb -o spid,comm` 只有 2 個執行緒、
  無 `device poll`，`ADB_LIBUSB=1` 生效。
- 螢幕：熄滅。本次截圖 `assets/screenshots/20260727-223342.png` 全黑
  （像素層級確認 min=max=0、1080x2340 直式）。**遊戲當下畫面未知**——
  本次沒有喚醒裝置，也沒有解圖形鎖（使用者刻意保留）。
- `data/cache/stages/` 空，備份在 `data/cache/stages.bak-20260723/`。

### 恢復點

- 分支 `feat/inner-goap`，tip `5ab6ef0`。`uv run pytest -q` 920 passed／
  3 xfailed、`uv run ruff check src tests scripts` 綠。
- `src/ggge_ai/bot/` 目前是**純離線骨架**：tick 迴圈、反射 router、
  符號表、mock catalog、metrics 都在，但分類器／螢幕／裝置全是
  `bot/mocks.py` 的假件，尚未接實機。`python -m ggge_ai.bot.demo`
  是唯一的端到端跑法。
- 本次完成：metrics 物件（`bot/metrics.py`）、`_record` 內的 A 層摺帳、
  `think()` 的 planner 埋點、`slept_ms` 基準錯誤修正。
- 已知未做：
  - jsonl 匯出——metrics 與流水帳都只活在 process 內，收工即消失。
  - 關卡外（關卡列表／出擊／強化）的 action 尚未進 catalog，
    catalog 目前全是關卡內詞彙。
  - 真分類器未接；接上之前 `bot/` 碰不到實機。
