---
name: start-task
description: Start or resume work on a GitHub issue under the development flow. Sets up the worktree off 'dev', the state block, the branch roadmap, and the device lock. Use at session start when the user assigns an issue.
---

# Start a task

Argument: the issue number N (example: /start-task 31).

Do the steps in order:

1. Read the issue in full: `gh issue view N --comments`.
2. Parse the '## Session state' block in the issue body.
3. When the block names a branch, resume:
   - The worktree exists (check `git worktree list`): work there.
   - The worktree is gone:
     `git worktree add /home/poyu/workspace/project/ggge_ai-worktrees/<branch> <branch>`
   - Read the branch roadmap named in the block.
4. When the block names no branch, start:
   - Name the branch 'issue-N-slug'. Make the slug short, from the
     issue title.
   - `git worktree add /home/poyu/workspace/project/ggge_ai-worktrees/issue-N-slug -b issue-N-slug dev`
   - Create `docs/roadmaps/branch-issue-N.md` with the type line
     `> Type: working—deleted at merge`, the issue URL, the base
     commit, and the resume point.
   - Fill the state block (branch, roadmap, status: in-progress) with
     `gh issue edit N --body-file`.
5. Device task only:
   - Read `/home/poyu/workspace/project/ggge_ai/docs/record/device-state.md`.
   - Check `/home/poyu/workspace/project/ggge_ai/docs/record/device.lock`.
     Absent: write it — issue number, branch, ISO timestamp. Foreign:
     do not touch the device; send a Discord notification; stop.
6. Plan the work. The full contract is
   `docs/how-to/development-flow.md`.

Rules:

- Never develop in the primary checkout. Never check out 'dev'.
- A TODO found mid-task becomes a new issue via the issue-writer
  agent. It does not extend the current scope.
- Write prompts to subagents in ASD-STE100 English with the template:
  goal, files, constraints, pitfalls, acceptance test, report format.
