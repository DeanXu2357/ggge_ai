# ggge_ai 專案守則（每次工作前先讀）

自動化通關 SD Gundam G Generation ETERNAL（USB 實機 R5CRC37JBYJ，
橫向 2340x1080）。GOAP 雙層架構，Python 3.12+/uv，OpenCV 模板視覺。

## 開工順序（不可跳過）

1. 讀 `docs/roadmap.md` 最上方的暫停快照——那裡有裝置現況與恢復點。

## Delegation & model routing (applies to every session)

- adb: `ADB_LIBUSB=1` is enforced via the `env` block in
  `.claude/settings.json`. If an adb server may already be running without
  it, `adb kill-server` first, then confirm with `ps -T -C adb` that the
  `device poll` thread is gone before trusting the connection.

## 開發紀律

- 小步提交；`uv run pytest -q` 與 `uv run ruff check src tests scripts`
  全過才 commit。改 `battle/vision.py`、`scripts/sweep_scan.py` 要附驗證
  證據（實機截圖或流水帳）。
- 同一個問題連續兩次嘗試失敗就停下來問使用者，不要繼續瞎試。
- 每次收工：更新 `docs/roadmap.md` 暫停快照（裝置現況＋恢復點）再 commit。
- 只用繁體中文與使用者溝通，禁用簡體中文。程式碼不寫多餘註解。

## 常用指令

- 截圖：`uv run python scripts/capture.py`（存 assets/screenshots/，gitignored）
- 解鎖（系統鎖＋遊戲省電觸控鎖）：`uv run python scripts/ensure_unlocked.py`
- 實機唯讀探針（畫面名／AUTO／格網／目擊）：`uv run python scripts/probe_live_channel.py`
- 完整掃描輪（進場＋sweep＋棄戰）：`uv run python scripts/sweep_scan.py`（分段停點 --stop-after …）
- 面板解析驗證：`uv run python scripts/parse_panel.py <png> [--no-llm]`
- 流水帳輸出：`data/runs/<時間戳>/`（gitignored）
- 模板驗證：`scripts/verify_match.py`、裁切：`scripts/crop.py`
