# Branch roadmap: issue-29-document-dev-flow

> Type: working—deleted at merge

Issue: https://github.com/DeanXu2357/ggge_ai/issues/29
Base: 'dev' at 3513126.

## Resume point

The batch is complete and awaits user review. No open work remains
on this branch.

## Change summary

Docs-only batch. Two new files, one edited file:

- docs/how-to/development-flow.md (new): the full flow — issue
  protocol with state block, 'dev' as integration branch, worktree
  rules, branch roadmap contract, device lock protocol, completion
  steps, subagent placement, communication standards.
- docs/roadmaps/branch-issue-29.md (new): this file, the first
  'working' document.
- docs/reference/terminology-map.md (edited): nine new term
  bindings for the flow vocabulary.

## Call chain

None. The batch contains no code.

## Contention points

1. The 'working' document type is defined inside
   development-flow.md. The doc-type list in CLAUDE.md gains the
   type only in the activation batch. Until then the type exists in
   one place.
2. The activation-status note at the top of development-flow.md
   marks the flow as not yet active. The activation batch deletes
   the note, rewrites CLAUDE.md, adds the .gitignore entries, and
   creates the untracked device files.
3. The base 3513126 is an ancestor of 'feat/stream-input'. The
   earlier plan to discard it as a stray commit was wrong. The
   'dev' bootstrap is a fast-forward.
4. The 'pause snapshot' terminology entry stays unchanged. It
   becomes stale at activation, not before.
