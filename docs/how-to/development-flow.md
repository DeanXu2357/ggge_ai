# Development flow

> Type: how-to—must match the current workflow

This document defines the task flow: one GitHub issue is one task,
one task gets one branch, and every session develops in a worktree.
The user does all merges and closes all issues.

Two skills are the executable form of this flow: '/start-task'
executes the session start checklist, '/finish-task' executes the
completion steps. CLAUDE.md points every session at them. This
document stays the authority; the skills follow it.

## Roles

- The user assigns issues, reviews branches, merges, and closes
  issues.
- The main session orchestrates: it plans, updates the issue, runs
  live verification, and delegates to subagents.
- Subagents do scoped work. See "Subagent placement".

## Branches

- 'main' is the stable branch. The user merges 'dev' into 'main' in
  batches.
- 'dev' is the long-lived integration branch. Task branches start
  from 'dev' and merge into 'dev' after user review.
- A task branch has the name 'issue-N-slug'. One issue, one branch.
- No session checks out 'dev'. The primary checkout holds it, so git
  blocks a second checkout.

## Primary checkout and worktrees

The primary checkout is /home/poyu/workspace/project/ggge_ai. It
rests on 'dev' by default. Sessions do not develop there. It hosts
two untracked files (both in .gitignore, both only at this path):

- docs/record/device.lock — the device lock.
- docs/record/device-state.md — the device state file.

Every session develops in a worktree under
/home/poyu/workspace/project/ggge_ai-worktrees/:

- New task:
  `git worktree add ../ggge_ai-worktrees/issue-N-slug -b issue-N-slug dev`
- Resume a branch whose worktree is gone:
  `git worktree add ../ggge_ai-worktrees/issue-N-slug issue-N-slug`
- After the merge: remove the worktree, then delete the branch.

The user is free to check out any branch in the primary checkout when
no worktree holds it. The untracked device files survive branch
switches.

## Issue protocol

The user assigns an issue to a session. The issue body holds a state
block:

```
## Session state
branch: issue-N-slug
roadmap: docs/roadmaps/branch-issue-N.md
status: planned | in-progress | awaiting-review
```

Session start checklist ('/start-task' executes it), in order:

1. Read the issue in full, including all comments.
2. When the state block names a branch: set up the worktree for that
   branch, then read the branch roadmap. When it does not: create
   the branch, the worktree, and the roadmap, then fill the state
   block and set status to in-progress.
3. For a device task: read the device state file, then acquire the
   device lock.

A TODO found mid-task becomes a new issue, opened with the
issue-writer agent. It does not extend the current scope.

## Branch roadmap

- Path: docs/roadmaps/branch-issue-N.md. Type line:
  `> Type: working—deleted at merge`.
- The 'working' document type is a branch-scoped working document.
  It is not a record. It dies with the branch.
- During development the roadmap holds the resume point and the
  progress log.
- At review time the roadmap is the review artifact. It must then
  hold: the change summary, the call chain, and the contention
  points. There is no separate review guide file.
- After user approval the session deletes the roadmap in a final
  commit. The deletion comes before the merge.

## Device access

- One device task runs at a time. The user enforces this at
  assignment time. Code-only tasks run in parallel freely and skip
  adb entirely.
- Acquire: before the first adb call, check
  /home/poyu/workspace/project/ggge_ai/docs/record/device.lock.
  When the file is absent, write it: issue number, branch, ISO
  timestamp.
- Foreign lock: do not touch the device. Send a Discord
  notification. Stop. Never take a lock you do not own.
- Release: at session end, update the device state file first, then
  delete the lock.
- The device state file holds the current snapshot only: screen
  name, cursor, running processes, monitors. Run evidence stays in
  data/runs/.

## Completion

'/finish-task' executes steps 1 to 5.

1. Gates pass for code changes: `uv run pytest -q` and
   `uv run ruff check src tests scripts`. Attach evidence for
   changes to 'battle/vision.py' or 'scripts/sweep_scan.py'.
2. Run a code review on the branch.
3. Rework the roadmap into the review artifact.
4. Comment the change summary on the issue. Set status to
   awaiting-review.
5. Send a Discord notification.
6. The user reviews.
   - Approve: the session deletes the roadmap; the user merges the
     branch into 'dev' and closes the issue; remove the worktree and
     the branch.
   - Reject: the user comments on the issue; the next session
     resumes from the session start checklist.

## Subagent placement

| Step | Agent |
|---|---|
| Issue creation and triage | issue-writer |
| Recon before planning | Explore |
| Implementation plan | Plan |
| Non-trivial code edits | code-editor |
| Live verification | Main session with Monitor (0808 ruling: no live-tester) |
| Notification | discord-notify skill |

## Communication standards

| Link | Standard |
|---|---|
| Session to subagent | ASD-STE100 English. Fixed prompt template: goal, files, constraints, pitfalls, acceptance test, report format. |
| Subagent to session | ASD-STE100 English. Structured facts. No interpretation baked in (0724 ruling: unbiased reader). |
| Issue title, body, comments | American English, writing discipline. |
| Branch roadmap | English, ASD-STE100 style. |
| Commit message | CLAUDE.md rules, checked by the commit-msg hook. |
| Discord notification | Traditional Chinese permitted. |
