# Branch roadmap: issue-36-dead-review-refs

> Type: working—deleted at merge

## Goal

Issue #36: seven source comments name paths under `docs/reviews/`, the
directory the user deleted on 2026-08-11. Remove the dead pointers.

## Rules for this branch

The change is a reference cleanup, not a comment rewrite. The first attempt
(`c6e4fcb`, discarded) recovered the deleted reports from git history and
moved their derivations into the comments. The user rejected it: issue #36
changes the references to deleted material, not the content of the comments.

- Remove the dead pointer only. In most sites the pointer is a parenthetical
  naming `docs/reviews/...`; deleting it leaves a sentence that still reads
  correctly, and that is the whole edit.
- Add nothing. Do not restate a number that the comment does not already
  hold.
- Delete surrounding text only when that text fails the CLAUDE.md existence
  check on its own: it narrates the flow, or it records history.
- Keep every comment in the language it already uses. Do not translate.
- A why-comment is legitimate under CLAUDE.md. Do not delete a comment
  because it explains why.

## Plan

1. This roadmap.
2. Remove the six dead pointers in `src/`.
3. Repoint `scripts/validate_projection.py` output out of `docs/reviews/`.
4. Rework this roadmap into the review artifact; comment on issue #36.

## Resume point

Step 1 done.
