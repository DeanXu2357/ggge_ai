# Branch roadmap: issue 82, the prologue of a board command

> Type: working—deleted at merge

## Where the branch stands

The branch 'issue-82-open-command' starts from 'dev' (b16a103),
after the merge of #65 (3f04d86). Issue #82 waited for that merge,
because #65 gave the helper its fourth and fifth caller.

## Scope

The helper 'boardOf' in 'engine/server/session.go' takes the name
'openCommand' and gives the decoded request back as a value. Five
call sites change. No wire message changes, and no behavior changes.

## Resume point

Planned. The rename is next.

## Progress log

- 2026-08-27: worktree added, roadmap written.
