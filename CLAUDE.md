# ggge_ai project rules (read before each session)

The project plays 'SD Gundam G Generation ETERNAL' automatically and
clears stages. Device: USB phone R5CRC37JBYJ, landscape 2340x1080.
Architecture: two-layer GOAP. Stack: Python 3.12+ with uv, OpenCV
template vision.

## Session rules

### Device

- adb: `ADB_LIBUSB=1` is enforced via the `env` block in
  `.claude/settings.json`. If an adb server may already be running without
  it, `adb kill-server` first, then confirm with `ps -T -C adb` that the
  `device poll` thread is gone before trusting the connection.

### Terminology

Use one term for one concept. Do not switch to a synonym after the
first use. The term bindings, in English and in Traditional Chinese,
are in `docs/reference/terminology-map.md`. When you need the term for a
concept in the other language, look it up there.

The map is a record of settled ambiguity, not a dictionary. Add a row
only when all three tests pass:

- The word is ambiguous inside this project: two readings, two
  translations, or a game UI word that differs from the common word.
- The ambiguity was settled by the user, and the row records the
  settlement so that a later session uses the same reading.
- The code and the spec cannot settle it: a Go identifier, a package,
  a file, a wire field, or a step inside one function is never a
  term.

A row holds the two names and one sentence that states the settled
reading. Do not add a Go pointer, a date, or a history to the row.
The commit message holds those. When you are not sure, do not add the row.

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
- working: an issue-scoped working document in `docs/roadmaps/`. It
  dies with the issue: deleted after user approval, before the merge
  that closes the issue. A merge of an issue that closes in parts
  keeps the document.

Rules for reference documents:

- Write new reference text in the ASD-STE100 style.
- Accuracy comes first. State only verified facts. Mark an unverified
  statement as a hypothesis and give its source.
- When a document settles an ambiguous word, add the row to
  `docs/reference/terminology-map.md` in the same change. The tests
  are in the Terminology section.

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
