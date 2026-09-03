# ggge_ai project rules (read before each session)

The project plays 'SD Gundam G Generation ETERNAL' automatically and
clears stages. Device: USB phone R5CRC37JBYJ, landscape 2340x1080.
Architecture: two-layer GOAP. Stack: Python 3.12+ with uv, OpenCV
template vision.

## Session start (do not skip)

1. Task sessions start from a GitHub issue. Run `/start-task <issue#>`:
   it reads the issue, sets up the worktree off 'dev', and fills the
   state block. Full contract: `docs/how-to/development-flow.md`.
   A discussion session with no assigned issue needs no worktree.
2. Never develop in the primary checkout
   (`/home/poyu/workspace/project/ggge_ai`). Never check out 'dev'
   anywhere: task branches live in worktrees under
   `/home/poyu/workspace/project/ggge_ai-worktrees/`.
3. Device state lives in the untracked file
   `docs/record/device-state.md` in the primary checkout. Device
   access requires the untracked lock `docs/record/device.lock`
   (protocol in the flow document). A foreign lock means: do not
   touch the device, notify the user, stop.

## Delegation & model routing (applies to every session)

- adb: `ADB_LIBUSB=1` is enforced via the `env` block in
  `.claude/settings.json`. If an adb server may already be running without
  it, `adb kill-server` first, then confirm with `ps -T -C adb` that the
  `device poll` thread is gone before trusting the connection.

## Development rules

- Commit in small steps. Commit only when `uv run pytest -q` and
  `uv run ruff check src tests scripts` pass. When you change
  `battle/vision.py` or `scripts/sweep_scan.py`, attach verification
  evidence: a device screenshot or a run log.
- Docs-only changes do not need the two gates above. The test: all
  diff paths are in `docs/`. Do not use the commit title as the test
  (prefixes are retired).
- When two attempts at the same problem fail, stop and ask the user.
  Do not make more blind attempts.
- At the end of a task session: run `/finish-task`. It runs the gates,
  reworks the branch roadmap into the review artifact, updates the
  issue, releases the device lock, and notifies the user.
- Communicate with the user in English. Use Chinese only when the user
  asks for a Chinese reply. When you use Chinese, use Traditional
  Chinese only. Do not use Simplified Chinese. Write the English in the
  ASD-STE100 style. Obey the three rules: 1. clarity, 2. simplicity,
  \3. brevity.
- Write new text in `docs/` in English. Do not translate the frozen
  Chinese corpus in bulk (see `docs/reference/terminology-map.md` for the
  corpus key).

### Terminology

Use one term for one concept. Do not switch to a synonym after the
first use. The term bindings, in English and in Traditional Chinese,
are in `docs/reference/terminology-map.md`. When you need the term for a
concept in the other language, look it up there. When a concept has
no entry, add the binding in the same change that introduces the
term.

### Commit message

Write commit messages with the `/commit-message` skill. Its rules apply
to every commit, also to a commit made without the skill.

Project facts the skill does not carry:

- Write in American English. Do not use a conventional-commit prefix.
- Write code identifiers and game UI words in their original form, in
  quotes ('SCREEN_CENTRE', 'relocalise', '顯示方格'). Quotes are the
  only exemption from the spelling check and the non-English check.
- Cite project sources: commit hash, issue number, run directory.

The hook `scripts/check_commit_msg.py` checks length, capitalization,
punctuation, backticks, and spelling. A rejected message prints the
reason. Install the hook one time:
`git config core.hooksPath .githooks`.

### Code comments

This section applies to all comments and docstrings in this repository.

Step 1 — existence check. Do this check before you write a comment:

- Write a comment only when the code cannot show the fact.
- Do not write a comment that explains the flow. Change the code until
  the code shows the flow.
- Do not write a comment that records the history. Record the history in
  the git commit message.
- When you are not sure, do not write the comment.

Step 2 — style for the two types that pass the check:

1. Why-comment: it explains a decision that looks wrong but is correct.
   Write why-comments in the Google developer documentation style.
2. Warning comment: it marks a solution that applies only to a special
   case. Write warning comments in the ASD-STE100 style: short
   sentences, active voice, one fact in each sentence.

### Document types

Each file in `docs/` declares its type in a label line under the
title: `> Type: <type>—<maintenance contract>`. The types and their
contracts:

- requirements: outcomes only; see the next section.
- reference: facts about the game, the device, or the data. Drift is
  a bug: when reality changes, change the document.
- spec: the authoritative description of an implemented mechanism or
  format.
- explanation: intent and boundaries. The document must carry a
  status note when reality diverges from the intent.
- how-to: steps and rules for a task. The document must match the
  current workflow.
- record: frozen and dated, or append-only. Do not retro-edit a
  record.
- working: a branch-scoped working document in `docs/roadmaps/`. It
  dies with the branch: deleted after user approval, before the merge.

Rules for reference documents:

- Write new reference text in the ASD-STE100 style.
- Accuracy comes first. State only verified facts. Mark an unverified
  statement as a hypothesis and give its source.
- When you introduce a proper noun or a technical name, add the entry
  to `docs/reference/terminology-map.md` in the same change.

### Requirements documents

Identification. A document is a requirements document when it passes
all three tests:

- The document answers "why do we build this" or "what problem does
  it solve".
- The document does not select a solution. A document that explains a
  selected solution is an explanation document, not a requirements
  document.
- The document states each requirement as an outcome. Test procedures
  and measured values belong in a spec document, not here.

Rules:

- Location: put requirements documents in `docs/requirements/`.
- Style: write new requirements documents in English, in the Google
  developer documentation style.
- Gate: `vale docs/requirements/` must report zero errors before you
  commit a change there. Install one time: put the 'vale' binary on
  PATH, then run `vale sync` at the repo root. Project words go in
  `.vale/styles/config/vocabularies/ggge_ai/accept.txt`.
- The legacy document `docs/requirements/base.md` stays in
  Traditional Chinese (frozen corpus). Vale checks only its Latin
  words.

## Common commands

- Screenshot: `uv run python scripts/capture.py` (output in
  assets/screenshots/, gitignored)
- Unlock (system lock plus the game's power-save touch lock):
  `uv run python scripts/ensure_unlocked.py`
- Read-only device probe (screen name / AUTO / grid / sightings):
  `uv run python scripts/probe_live_channel.py`
- Full scan cycle (entry, sweep, abandon battle):
  `uv run python scripts/sweep_scan.py` (stage stops: --stop-after ...)
- Panel parse check: `uv run python scripts/parse_panel.py <png> [--no-llm]`
- Run logs: `data/runs/<timestamp>/` (gitignored)
- Template check: `scripts/verify_match.py`; crop: `scripts/crop.py`
