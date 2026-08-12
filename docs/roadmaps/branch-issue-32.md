# Branch roadmap: issue-32-fix-issuewriter-lang

> Type: working—deleted at merge

Issue: https://github.com/DeanXu2357/ggge_ai/issues/32
Base commit: 9e4c2d9 (dev, "Delete the branch roadmap after review")

## Change summary

`.claude/agents/issue-writer.md` hardcoded Traditional Chinese for every
issue title and body, contradicting `docs/how-to/development-flow.md:146`
("Issue title, body, comments | American English, writing discipline"). The
agent file predates the flow document and was never updated when the flow
was activated.

The fix, in `.claude/agents/issue-writer.md`:

- Replaces the Chinese-language mandate with American English, Google
  developer documentation style, citing the flow doc's Communication
  standards table as the authority.
- Keeps the existing carve-out: quoted, untranslated project vocabulary
  (應戰, 顯示方格, 字模, 名冊, 棄戰, 弧色, 格網, 早收, and the like) stays in
  its original Traditional Chinese form inside the English prose, matching
  the project's commit-message convention for code identifiers and game-UI
  words.
- Adds a "Style check before publishing" step: draft to a scratch file at
  `.claude/scratch-vale/issue-draft.md`, run `vale` on it, fix every error,
  delete the scratch file, then publish. Requested by the user directly, on
  top of the issue #32 scope.
- Translates the one Chinese-language example (the `type:fix` trigger
  condition sample) to English, so the agent's own examples model the
  language it now must write in.

Supporting config changes, found necessary by live-testing the Style check
(see Verification):

- `.vale.ini`: adds a `[.claude/scratch-vale/*.md]` section, matching the
  existing `[docs/requirements/*.md]` one. `.claude/scratch-vale/` is
  already covered by the repo's `.claude/*` gitignore rule.
- `.vale/styles/config/vocabularies/ggge_ai/accept.txt`: adds `untracked`,
  `worktree`, `worktrees` — real project vocabulary that Vale's default
  spell check does not recognize, found as false-positive errors during the
  live test.

## Call chain

No runtime call chain — this is a subagent prompt file, not application
code. The only "execution" is: main session invokes the `issue-writer`
subagent → subagent reads its own instructions → subagent drafts and
publishes a GitHub issue.

## Verification

- `uv run pytest -q`: 862 passed, 4 skipped.
- `uv run ruff check src tests scripts`: all checks passed.
- Live dogfood test: a code-review pass on this branch surfaced two
  documentation-drift findings outside issue #32's scope (README pointing
  at a deleted file; development-flow.md undercounting finish-task's
  steps). Spun those off as new issues through the freshly fixed
  `issue-writer` agent, which produced them as the first real end-to-end
  run of the new English-language + Style-check instructions:
  issue #33 and issue #34, both in American English, both correctly typed
  and labeled.
- That live run found the first version of the Style check step
  (scratch file at `docs/requirements/_scratch-issue-draft.md`) was not
  actually followed: the subagent avoided writing under `docs/`, read the
  "do not edit `docs/`" boundary as blocking it despite the carve-out note
  next to the instruction, and invented its own ad hoc Vale config outside
  the repo's tracked config instead. That is exactly the failure mode the
  Style check exists to prevent — `vale <file>` against any path outside
  every glob in `.vale.ini` silently reports "0 errors ... in 0 files," a
  false pass, not a clean draft (reproduced by hand: see below).
- Fix: moved the scratch path to `.claude/scratch-vale/issue-draft.md`,
  fully outside `docs/`, added the matching `.vale.ini` glob, and added an
  explicit sanity-check step (confirm the path matches a configured glob
  before trusting a "0 errors" result).
- Reproduced by hand after the fix, with a deliberately flawed draft
  (passive voice, "in order to", and the words "untracked"/"worktrees"):
  - Before adding the vocab terms: `.claude/scratch-vale/issue-draft.md` →
    2 errors (`Vale.Spelling` on "untracked" and "worktrees"), 2 warnings,
    1 suggestion.
  - The same file copied outside every `.vale.ini` glob (`/tmp/...`) →
    "0 errors, 0 warnings, 0 suggestions in 0 files" — confirmed silent
    false pass.
  - After adding the vocab terms: 0 errors, 2 warnings, 1 suggestion —
    matches the project's "zero errors" gate bar exactly.

## Contention points

None open. The change is a straightforward correction of a stale subagent
instruction against an already-authoritative, already-activated flow
document, sharpened by one round of live dogfooding; no design choice here
needs the user's ruling.
