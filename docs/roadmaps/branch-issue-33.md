# Branch roadmap: issue-33-readme-doc-refs

> Type: working—deleted at merge

- Issue: https://github.com/DeanXu2357/ggge_ai/issues/33
- Base commit: 0dbe769 (dev)
- Branch: issue-33-readme-doc-refs

## Goal

`README.md` names the deleted file `docs/record/roadmap.md` in the
must-read list and in the documentation-map table. Make both places
name the two documents that hold the pause-snapshot content now: the
device state file and the branch roadmap.

## Steps

1. Replace the must-read entry `docs/record/roadmap.md` with the
   device state file and the branch roadmap. — done
2. Correct the `docs/record` row of the documentation-map table. —
   done
3. Add a `docs/roadmaps` row for the working type. — done
4. Record the retirement of `docs/record/roadmap.md` with the other
   retired documents. — done
5. Run the gates (`pytest`, `ruff`). — done
6. Commit. — done

## Resume point

Work is complete. The branch is ready for review.
