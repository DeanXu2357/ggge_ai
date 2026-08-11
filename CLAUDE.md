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
- Communicate with the user in English. Use Chinese only when the user
  asks for a Chinese reply. When you use Chinese, use Traditional
  Chinese only. Do not use Simplified Chinese. Write the English in
  the ASD-STE100 style. Obey the
  three rules: 1. clarity, 2. simplicity, 3. brevity.

## Writing discipline（issue／docs／commit／對使用者的回報一律適用）

- 主動語態、點名動作者，不寫無主詞句（「應該被修正」——誰修？）。
- 一句一個概念。
- 同一概念只用同一個詞，定義一次後不換同義詞（術語見
  `docs/terminology-map.md`）。
- 代名詞換名詞：「它」「這個」「該項」指向不唯一時寫全名。
- 驗收標準與清單禁用開放式列舉（「等等」「之類的」）——驗不了。
- 前置條件與適用範圍寫在最前面，不藏在中段。

### Commit message

Write commit messages in American English. Do not use a
conventional-commit prefix.

The hook `scripts/check_commit_msg.py` checks the mechanical rules:

- Title: maximum 50 characters, capital first letter, no period at the
  end, no parentheses.
- Body lines: maximum 72 characters.
- Full message: no backticks; non-English words and British spellings
  are permitted only in quotes.

Install the hook one time: `git config core.hooksPath .githooks`.

The hook cannot check the rules below. The writer is responsible for
them:

- Write the title as an imperative sentence (Fix, Reject, Repair — not
  Fixed, Fixes).
- The title states the high-level "what": the effect of the change, not
  the file you touched. Do not write an empty title such as
  "Update queue.c".
- The body states only the "why". Do not repeat the "what" in the body.
- Write the "how" only when the mechanism had more than one option and
  the selected option is not obvious.
- Add references: commit hash, issue number, run directory, paper, or
  community source.
- Write code identifiers and game UI words in their original form, in
  quotes ('SCREEN_CENTRE', 'relocalise', '顯示方格'). Quotes are the
  only exemption from the spelling check and the non-English check.

### Code comments

This section applies to all comments and docstrings in this repository.

Step 1 — existence check. Do this check before you write a comment:

- Write a comment only when the code cannot show the fact.
- Do not write a comment that explains the flow. Change the code until
  the code shows the flow.
- Do not write a comment that records the history. Record the history in
  the git commit message.
- When you are not sure, do not write the comment.

Step 2 — style for the two types that pass the check:

1. Why-comment: it explains a decision that looks wrong but is correct.
   Write why-comments in the Google developer documentation style.
2. Warning comment: it marks a solution that applies only to a special
   case. Write warning comments in the ASD-STE100 style: short
   sentences, active voice, one fact in each sentence.

## 常用指令

- 截圖：`uv run python scripts/capture.py`（存 assets/screenshots/，gitignored）
- 解鎖（系統鎖＋遊戲省電觸控鎖）：`uv run python scripts/ensure_unlocked.py`
- 實機唯讀探針（畫面名／AUTO／格網／目擊）：`uv run python scripts/probe_live_channel.py`
- 完整掃描輪（進場＋sweep＋棄戰）：`uv run python scripts/sweep_scan.py`（分段停點 --stop-after …）
- 面板解析驗證：`uv run python scripts/parse_panel.py <png> [--no-llm]`
- 流水帳輸出：`data/runs/<時間戳>/`（gitignored）
- 模板驗證：`scripts/verify_match.py`、裁切：`scripts/crop.py`
