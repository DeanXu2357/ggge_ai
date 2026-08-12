---
name: finish-task
description: Complete a task branch under the development flow. Runs the gates, reworks the branch roadmap into the review artifact, updates the issue, releases the device lock, and notifies the user. Use when the branch work is done.
---

# Finish a task

Do the steps in order:

1. For code changes: run `uv run pytest -q` and
   `uv run ruff check src tests scripts`. Both must pass. Attach
   evidence for changes to 'battle/vision.py' or
   'scripts/sweep_scan.py': a device screenshot or a run log.
   Docs-only batches skip this step.
2. For code changes: run a code review on the branch (the
   /code-review skill). Fix what it finds.
3. Rework the branch roadmap into the review artifact. It must hold:
   the change summary, the call chain, and the contention points.
4. Commit. Follow the commit message rules in CLAUDE.md.
5. When this session holds the device lock: update
   `/home/poyu/workspace/project/ggge_ai/docs/record/device-state.md`
   (current snapshot only), then delete the lock file.
6. Comment the change summary on the issue. Set the state block
   status to awaiting-review.
7. Send a Discord notification (Traditional Chinese permitted):
   branch, commit, review artifact path, what the user must do.
8. Stop. The user reviews, merges into 'dev', and closes the issue.
   Do not merge. After user approval, delete the roadmap file in a
   final commit, before the merge.
