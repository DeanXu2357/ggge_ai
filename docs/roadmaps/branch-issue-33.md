# Branch roadmap: issue-33-readme-doc-refs

> Type: working—deleted at merge

- Issue: https://github.com/DeanXu2357/ggge_ai/issues/33
- Base commit: 0dbe769 (dev)
- Branch: issue-33-readme-doc-refs
- Commit: c4a4800 "Point the README must-read list at live documents"
- Status: awaiting-review

## Change summary

`README.md` named the deleted file `docs/record/roadmap.md` in two
places. Commit `d541bfc` split that file into the device state file
and the branch roadmap, but did not touch the README. The change
makes both places name documents that exist.

`README.md` is the only file changed. There is no code change, so the
gates are not required; they were run anyway and both pass (862
passed, 4 skipped; ruff clean).

| Place | Before | After |
|---|---|---|
| Must-read list, item 2 | `docs/record/roadmap.md` — pause snapshot | `docs/record/device-state.md` — device state, untracked, primary checkout only |
| Must-read list, new item 3 | — | `docs/roadmaps/branch-issue-N.md` — progress and resume point of the task branch |
| Documentation map, `docs/record` row | "Pause snapshot ('roadmap.md') and decision ledger" | "Device state file ('device-state.md', not tracked in git) and decision ledger" |
| Documentation map, new row | — | `docs/roadmaps/`, type working, deleted at merge |
| Retired-documents note | `docs/archive/`, `docs/reviews/` | plus `docs/record/roadmap.md`, split 2026-08-12 |

## Call chain

There is no call chain. The change is documentation. The reference
chain it must agree with:

- `docs/reference/terminology-map.md:26` — the "pause snapshot" entry
  records the split into the device state file and the branch
  roadmap.
- `docs/reference/terminology-map.md:47` — "branch roadmap" binds to
  `docs/roadmaps/branch-issue-N.md`, deleted at merge.
- `docs/how-to/development-flow.md:32-53` — the primary checkout holds
  `docs/record/device-state.md` and `docs/record/device.lock`, both
  untracked.
- `CLAUDE.md`, section "Document types" — the type `working` lives in
  `docs/roadmaps/`.

## Contention points

1. The must-read list grew from three items to four. The alternative
   was to keep three items and name only the device state file. The
   resume point would then have no entry, and a resuming session
   would not find its branch roadmap from the README.
2. The list names `docs/roadmaps/branch-issue-N.md` with the literal
   letter `N`. No such path exists; the reader substitutes the issue
   number. The same form is used in
   `docs/reference/terminology-map.md:47` and in
   `docs/how-to/development-flow.md`, so the README matches the rest
   of the documents.
3. The documentation-map table gained a `docs/roadmaps/` row, but the
   directory exists only while a task branch is open (this branch
   creates it, and the merge deletes the file). The table maps
   document types to directories, and the must-read list now points
   into that directory, so a missing row would leave the map
   incomplete. The row states the "deleted at merge" contract to
   prevent a reader from reporting the empty directory as drift.
4. The must-read list stays in Traditional Chinese and the
   documentation map stays in English. The file is bilingual today;
   translating either part is a separate decision, not part of this
   fix.
5. A repository-wide search for `record/roadmap` finds two remaining
   hits, and both are correct. `README.md:33` and
   `docs/reference/terminology-map.md:26` name the path as history,
   not as a document to open. No other file points at the deleted
   file.
