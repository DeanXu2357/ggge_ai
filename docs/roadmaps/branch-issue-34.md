# Review artifact: issue-34-flow-skill-split

> Type: working—deleted at merge

- Issue: https://github.com/DeanXu2357/ggge_ai/issues/34
- Base commit: b9e060a (dev)

## Problem

`docs/how-to/development-flow.md` and the two skill files held the
same steps twice. The copies drifted: the document listed five
completion steps, `finish-task/SKILL.md` ran eight. The same drift
existed for `/start-task`: three steps against six.

Issue #34 asks for step-for-step parity between the two copies. The
user rejected that fix. Parity makes every future step change a
two-file edit and leaves the drift risk in place.

## Change summary

One copy of the steps. The document holds them. Each skill file
holds frontmatter and a pointer.

| File | Change |
|---|---|
| `docs/how-to/development-flow.md` | Header: the skills hold no steps. Issue protocol: six start steps, one per skill step. Mid-task rule rewritten. Completion: seven finish steps, then the user gate outside the numbering. |
| `.claude/skills/start-task/SKILL.md` | 43 lines to 12. Keeps the argument line; points at 'Issue protocol'. |
| `.claude/skills/finish-task/SKILL.md` | 30 lines to 13. Points at 'Completion'; keeps "do not merge, do not close". |

Two steps that #34 found missing now exist in the document: commit,
and device-lock release.

Nothing from the skill files is lost. `start-task/SKILL.md` had a
Rules block; all three rules already exist in the document — no
development in the primary checkout (Branches, Primary checkout),
the mid-task rule (Issue protocol), the subagent prompt template
(Communication standards).

## Call chain

```
CLAUDE.md
  -> /start-task N   -> SKILL.md (pointer)
                     -> development-flow.md, 'Issue protocol'
  -> /finish-task    -> SKILL.md (pointer)
                     -> development-flow.md, 'Completion'
```

## User rulings (0812 discussion)

1. Split: document holds the steps, skill files point at it. The
   other option — document holds outcomes, skill holds steps — was
   rejected.
2. Gate: one user gate, after `/finish-task`. The go-ahead the user
   gives before `/finish-task` is session traffic, not a flow step.
   The Completion section therefore ends with the gate as prose, not
   as a numbered item.
3. Scope: `/start-task` gets the same treatment, not `/finish-task`
   alone.
4. A problem found mid-task: report it to the user; the user decides
   whether it becomes a new issue; `issue-writer` opens it only
   after the user agrees. The old text opened the issue without
   asking.

## Contention points

1. **#34's closure condition no longer applies.** It asks that both
   files name the same number of steps in the same order. After this
   change one file has no steps to compare. The equivalent test:
   `git grep -c` for numbered steps in either `SKILL.md` returns
   zero, and the document holds one ordered list for each skill.
2. **Every skill run now reads a second file.** That is the cost of
   one source of truth. The user accepted it at decision time.
3. **The skill frontmatter still summarizes the steps.** The
   `description` fields say what each skill does, in prose. They are
   the search key for skill selection, so they must stay. A prose
   summary drifts slower than a numbered list, but it is not
   drift-proof.
4. **Gates ran, although this looks like a docs batch.** The diff
   touches `.claude/skills/`, so the docs-only exemption in CLAUDE.md
   does not apply. `uv run pytest -q`: 862 passed, 4 skipped. `uv run
   ruff check src tests scripts`: clean. No code review: the diff
   holds no code.
