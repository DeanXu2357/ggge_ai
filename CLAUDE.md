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
- 純文件變更免跑上面兩道閘門。判準是 diff 路徑全落在 `docs/`，不是看
  commit 標題（前綴已廢除）。
- 同一個問題連續兩次嘗試失敗就停下來問使用者，不要繼續瞎試。
- 每次收工：更新 `docs/roadmap.md` 暫停快照（裝置現況＋恢復點）再 commit。
- 只用英文或繁體中文與使用者溝通，禁用簡體中文。程式碼不寫多餘註解。

## Writing discipline（issue／docs／commit／對使用者的回報一律適用）

- 主動語態、點名動作者，不寫無主詞句（「應該被修正」——誰修？）。
- 一句一個概念。
- 同一概念只用同一個詞，定義一次後不換同義詞（術語見
  `docs/terminology-map.md`）。
- 代名詞換名詞：「它」「這個」「該項」指向不唯一時寫全名。
- 驗收標準與清單禁用開放式列舉（「等等」「之類的」）——驗不了。
- 前置條件與適用範圍寫在最前面，不藏在中段。

### commit message（美式英語，不用 conventional 前綴）

機械規則由 `commit-msg` hook 判定（`scripts/check_commit_msg.py`：標題
50 字元、內文 72 字元、首字大寫、無句點、無括號、無 backtick、非英文與
英式拼法只准出現在引號內）。安裝一次：
`git config core.hooksPath .githooks`。以下是 hook 判不了、寫的人要負責的：

- 標題用祈使句（Fix／Reject／Repair，不是 Fixed／Fixes）。
- 內文寫 what 與 why；how 只在機制有多種選擇、選了哪一種不明顯時才寫。
- 附上參照：commit hash、issue 編號、run 目錄、論文或社群出處。
- 具體描述變更，不寫 "Update queue.c" 這種等於沒說的標題。
- 程式識別字與遊戲 UI 詞照原樣寫並加引號（`'SCREEN_CENTRE'`、
  `'relocalise'`、`'顯示方格'`）——引號是拼字與非英文檢查的唯一豁免口。

## 常用指令

- 截圖：`uv run python scripts/capture.py`（存 assets/screenshots/，gitignored）
- 解鎖（系統鎖＋遊戲省電觸控鎖）：`uv run python scripts/ensure_unlocked.py`
- 實機唯讀探針（畫面名／AUTO／格網／目擊）：`uv run python scripts/probe_live_channel.py`
- 完整掃描輪（進場＋sweep＋棄戰）：`uv run python scripts/sweep_scan.py`（分段停點 --stop-after …）
- 面板解析驗證：`uv run python scripts/parse_panel.py <png> [--no-llm]`
- 流水帳輸出：`data/runs/<時間戳>/`（gitignored）
- 模板驗證：`scripts/verify_match.py`、裁切：`scripts/crop.py`
