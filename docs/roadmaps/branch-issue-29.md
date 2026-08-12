# Branch roadmap: issue-29-document-dev-flow

> Type: working—deleted at merge

Issue: https://github.com/DeanXu2357/ggge_ai/issues/29
Base: 'dev' at 3513126.

## Resume point

The batch is complete and awaits user review. No open work remains
on this branch.

## Change summary

Two commits. First commit 74f7a15: documentation. Second commit:
activation (scope folded into this issue by the 0812 user ruling).

Documentation:

- docs/how-to/development-flow.md (new): the full flow — issue
  protocol with state block, 'dev' as integration branch, worktree
  rules, branch roadmap contract, device lock protocol, completion
  steps, subagent placement, communication standards.
- docs/roadmaps/branch-issue-29.md (new): this file, the first
  'working' document.
- docs/reference/terminology-map.md: nine new term bindings; the
  'pause snapshot' entry marked retired.

Activation:

- CLAUDE.md: session start rewritten ('/start-task', worktree rules,
  device files); end-of-session bullet now points at '/finish-task';
  document type 'working' added.
- .claude/skills/start-task/SKILL.md and
  .claude/skills/finish-task/SKILL.md (new): the executable form of
  the session start checklist and the completion steps.
- .gitignore: un-ignore '.claude/skills/'; ignore the two untracked
  device files.
- docs/record/roadmap.md deleted: the pause snapshot splits into the
  untracked device state file and the branch roadmaps. History stays
  in git.
- Untracked docs/record/device-state.md created in the primary
  checkout, migrated from the 0811 evening snapshot. Not part of the
  diff.

## Call chain

None. The batch contains no code. A grep found no reference to
'docs/record/roadmap.md' in src, tests, scripts, or .claude.

## Contention points

1. Expected merge conflict, one file: 'feat/stream-input' appends
   snapshots to docs/record/roadmap.md; this branch deletes the
   file. Resolution at the 'feat/stream-input' into 'dev' merge:
   keep the deletion. The newest snapshot content already lives in
   the untracked device state file. CLAUDE.md, .gitignore, and the
   terminology map are identical between the two lines (checked with
   git diff), so no other conflict exists.
2. The skills are advisory, not mechanical. If sessions violate the
   device lock protocol, the hardening option is a lock check inside
   the adb-touching scripts. Deferred until a violation occurs.
3. The gates ran on this batch although the code is untouched: the
   diff leaves docs/ (CLAUDE.md, .gitignore, .claude/), so the
   docs-only exemption does not apply by its own test.
