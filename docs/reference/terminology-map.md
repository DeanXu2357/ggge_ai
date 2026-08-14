# Terminology map

> Type: reference—drift is a bug

This file is the project dictionary. Use one term for one concept.
When you write English, use the English column. When you write
Chinese, use the Traditional Chinese column. Do not create a new
translation for a bound concept. When a concept has no entry, add the
binding in the same change that introduces the term.

New project text is English (0811 user ruling): replies to the user,
docs/, and commit messages. The frozen Chinese corpus (old entries in
docs/record/decisions.md, plus retired documents in git history)
stays in Traditional Chinese.

## Term bindings

For a metaphor term (island, mainland, ghost, starfield): define the
term at its first use in each document, then use the short form.

| English | Traditional Chinese | Meaning |
|---|---|---|
| device | 實機 | The physical USB phone R5CRC37JBYJ |
| device screenshot | 實機截圖 | A screenshot captured from the device |
| run log | 流水帳 | The structured output in data/runs/<timestamp>/ |
| pause snapshot | 暫停快照 | Retired 0812: split into the device state file and the branch roadmap; history in git (docs/record/roadmap.md) |
| resume point | 恢復點 | The step where the next session starts work |
| session start / end of session | 開工／收工 | The start and the end of a work session |
| gate | 閘門 | A check that must pass before a commit (pytest, ruff) |
| docs-only change | 純文件變更 | A change whose diff paths are all in docs/ |
| stage | 關卡 | One playable mission in the game |
| abandon battle | 棄戰 | Leave a battle through the in-game retreat flow |
| sighting | 目擊 | A unit observation recorded during a scan |
| grid | 格網 | The in-game board grid (the '顯示方格' overlay) |
| screen name | 畫面名 | The classifier label for the current screen |
| requirements document | 需求文件 | A document that answers "why" and states the problem as outcomes; see the CLAUDE.md section 'Requirements documents' |
| gain | 增益 | Standard Taiwanese engineering term (0802 ruling: retained) |
| odometry | 里程計 | Standard Taiwanese engineering term (0802 ruling: retained) |
| island | 島嶼 | The holding area for observations whose positions are unknown after a localization break; they merge back after relocalization |
| mainland | 大陸 | The trusted-position side of the knowledge map, opposite of the island |
| ghost | 幽靈 | A false item with no real counterpart on screen; name the kind: a false shift candidate, a false unit detection, or a false peak |
| starfield | 星空 | The dark background outside the map, with no grid cells. Not "sparse sightings" (0803 audit: all 20 uses mean the outside background) |
| integration branch | 整合分支 | The long-lived branch 'dev'; task branches start from it and merge into it |
| task branch | 任務分支 | The branch 'issue-N-slug' for one GitHub issue |
| primary checkout | 主目錄 | The directory /home/poyu/workspace/project/ggge_ai; rests on 'dev'; hosts the device lock and the device state file |
| worktree | 工作樹 | A git worktree under /home/poyu/workspace/project/ggge_ai-worktrees/; every session develops in one |
| branch roadmap | 分支路線圖 | The working document docs/roadmaps/branch-issue-N.md; progress log during development, review artifact at review, deleted at merge |
| device lock | 裝置鎖 | The untracked file docs/record/device.lock; serializes device access across sessions |
| device state file | 裝置狀態檔 | The untracked file docs/record/device-state.md; the current device snapshot only |
| state block | 狀態區塊 | The 'Session state' section in an issue body: branch, roadmap, status |
| review artifact | 審查對照物 | The document the user reads to review a branch; the branch roadmap at awaiting-review |
| veil | 暫定界遮罩 | The provisional border gate: the cover drawn for one frame over the cells outside the provisional bounds (provisional_bounds in runtime/sweep.py). A covered cell is not tapped, not blocked, not inferred, and not charted; the next window enumerates it again. The bounds themselves stay 暫定界格. Short form 界遮罩 after the first use. Not the coverage mask (runtime/coverage.py), and not the mask of the danger-band shapes (runtime/device.py) |
| stream frame source | 串流幀源 | The scrcpy plus v4l2 frame path in ggge_ai/stream/; selected with 'sweep_scan.py --stream', in place of the adb screenshot path |
| roster capture | 名冊採集 | Open the detail page of every unit in the '部隊資訊' roster and keep one frame for each page: runtime/roster_capture.py, the class RosterCapture, the journal events roster_capture and roster_capture_summary |
| segment | 分段 | A phase of a run, and the section of code that runs it: the members of the STAGES tuple in scripts/sweep_scan.py and the values of --stop-after ('分段停點' in the same file). This is a different sense from stage ↔ 關卡. STAGES holds both senses today: its member stage_info names the 關卡 information screen |
| settle | 幀差取樣 | Sample after the frame difference falls: await_still in runtime/settle.py polls the difference of the frames pixel by pixel (interval SETTLE_POLL_S) and takes the frame when the fraction of moving pixels goes under the threshold, or when the deadline (SETTLE_WAIT_S) arrives, whichever is first. The settle journal event records which of the two in its 'converged' field. The name does not use 收斂, because an event after a tap can be a long animation that does not become still, and the primitive releases at the deadline. Accepted alternate reading: 收斂取樣, because the release at the deadline is a defined convergence point |
| blind sleep | 盲睡 | The fixed-time wait that the settle primitive replaces. Examples: board.PAN_SETTLE_S, ROSTER_SETTLE_S and SETTLE_ROUNDS in stage/survey.py, settle_s in battle/map_view.py, ABANDON_SETTLE_ATTEMPTS and ABANDON_SETTLE_INTERVAL_S in runtime/entry.py. It measures nothing. These names keep the English word settle although they are not the settle primitive |
| projection | 透視投影 | The fixed planar homography of the board (runtime/projection.py): world isometric grid to screen grid-line positions. Not the bare word 投影, which board.py uses for the row and column sums |
| sandbox facade | 沙盤門面 | The class 'Sandbox' in sandbox/facade.py. Code outside the sandbox package uses it for every read of the board and every advance of the state. The facade aggregates and serializes only; the game logic stays in sandbox/model.py |
| decision payload | 決策酬載 | The dict that 'Sandbox.pending_decision' and 'Sandbox.reaction_options' return: the legal candidates for the pending decision, plus the 'advice' field. The 'advice' field is empty when the facade has no advisor |
| activation | 行動 | One action of one unit in one phase. It ends when the 'acted' flag of that unit becomes true |

## Legacy Chinese corpus key

The frozen Chinese corpus uses the terms below. The 0802 ruling
replaced banned direct-translation terms with them; the full ruling
tables are in this file's git history (0803 version). When new
English text needs one of these concepts, add an English binding to
the table above in the same change.

| Chinese term | Meaning |
|---|---|
| 合理範圍閘／合理範圍檢查 | The check that a measured shift has the same axis and sign as the command, with an upper bound on the ratio |
| 佐證來源／多路佐證裁決／無佐證 | Independent measurement sources (grid phase, unit arrangement, correlator, map edge) that confirm each other; accept a result only on agreement |
| 單位排列比對 | Matching the relative positions of on-screen units as a pattern; used for relocalization after a localization break |
| 邊緣回彈 | The camera bounce the game applies at the map edge |
| 待掃格 | An in-bounds cell next to the mapped area, not yet scanned; "no 待掃格" means the scan is complete |
| 定位中斷 | One step of the dead-reckoning chain has an untrusted measurement; later positions cannot attach to the world map |
