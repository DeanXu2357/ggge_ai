# Development flow

> Type: how-to—must match the current workflow

This document defines the task flow: one GitHub issue is one task,
one task gets one branch, and every session develops in a worktree.
The user does all merges and closes all issues.

Two skills are the entry points: '/start-task' executes the session
start checklist, '/finish-task' executes the completion steps.
CLAUDE.md points every session at them. Neither skill file holds
steps of its own. Each skill file points at a section of this
document. This document holds the steps.

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

Session start checklist. '/start-task N' does these steps in order:

1. Read the issue in full: `gh issue view N --comments`.
2. Parse the '## Session state' block in the issue body.
3. Resume, when the block names a branch: work in the worktree when
   it exists (`git worktree list`); add the worktree again when it
   is gone (see "Primary checkout and worktrees"). Read the branch
   roadmap named in the block.
4. Start, when the block names no branch: name the branch
   'issue-N-slug', with a short slug from the issue title; add the
   worktree (see "Primary checkout and worktrees"); create the
   roadmap (see "Branch roadmap"); fill the state block with
   `gh issue edit N --body-file` and set status to in-progress.
5. Device task only: read the device state file, then acquire the
   device lock (see "Device access").
6. Plan the work.

A problem found mid-task does not extend the current scope. Report
it to the user. The user decides whether it becomes a new issue.
Open the issue with the issue-writer agent only after the user
agrees.

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

'/finish-task' does these steps in order:

1. Gates pass for code changes: `uv run pytest -q` and
   `uv run ruff check src tests scripts`. A change under 'engine/'
   adds two gates, both from the 'engine' directory: `go vet ./...`
   and `go test ./...`. Attach evidence for changes to
   'battle/vision.py' or 'scripts/sweep_scan.py': a device
   screenshot or a run log. Docs-only batches skip this step.
2. For code changes: run a code review on the branch (the
   /code-review skill). Fix what it finds.
3. Rework the roadmap into the review artifact.
4. Commit. Follow the commit message rules in CLAUDE.md.
5. When this session holds the device lock: update the device state
   file, then delete the lock file.
6. Comment the change summary on the issue. Set the state block
   status to awaiting-review.
7. Send a Discord notification: branch, commit, review artifact
   path, what the user must do.

Then the session stops. It does not merge, and it does not close the
issue. The user reviews.

- Approve: the session deletes the roadmap in a final commit; the
  user merges the branch into 'dev' and closes the issue; remove the
  worktree, then delete the branch.
- Reject: the user comments on the issue; the next session resumes
  from the session start checklist.

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
