# Branch roadmap — issue 41: play mode UI

> Type: working—deleted at merge

Stacked on 'issue-40-query-contract' (user authorization
2026-08-14). Review diff: 'issue-40-query-contract..issue-41-play-mode'.

## Goal

Turn the sandbox page into a playable ally phase per issue #41:
phase-scoped commands, engagement flow with defender options, C3
dice (manual roll default, server draw on a toggle), all through
the 'Sandbox' facade.

## Plan

1. HTTP endpoints on the shell: pending decision, reaction options,
   act.
2. Page interaction: unit selection, move targets, attack targets
   with hit rate and expected damage, skills, wait, engagement
   popup with stances and support choices, dice entry.
3. Tests: endpoint round-trip through a full ally phase.

## What shipped

Endpoints on 'scripts/sandbox_ui.py':

- 'GET /api/decision' — the decision payload of the pending
  activations.
- 'POST /api/reactions' — body {candidate}; the reaction payload.
- 'POST /api/act' — body {candidate, reaction, draw}; answers
  {dice, state, pending}. A facade ValueError becomes HTTP 400 with
  the message in {"error": ...}.

Page: header with turn and phase, the pending unit list, the
candidates of the selected unit grouped by kind, the reaction
options of a selected attack, the dice controls, the reserved
advice slot, and the confirm button. The board paints the reach
cells of the selected unit and makes the reposition destinations
clickable.

Dice: manual roll is the default; each visible hit node starts at
'hit' because the model reads a missing die as a hit. The server
draw toggle sends 'draw': true and the shell draws the main hit
with the probability that the facade reports for the picked
reaction option.

## Review round 1 (2026-08-14)

Five mechanical findings, all fixed on this branch:

1. Malformed input that raised TypeError, not ValueError, escaped
   the handler and answered 500. Fixed at the source: '_as_cell'
   wraps the 'int' calls and '_candidate_key' rejects an unhashable
   field through the new '_as_scalar'. That covers '_require_legal',
   which builds its key through '_candidate_key' before the
   set-membership test. The handler still catches ValueError only.
2. A negative Content-Length made 'rfile.read' block until EOF and
   leaked the handler thread. The body reader now rejects a length
   outside 1 to 'MAX_BODY_BYTES' (one megabyte) and closes the
   connection, because the framing is broken once a declared body
   goes unread.
3. The read endpoints took no lock while an act swapped the state,
   so a reader could serialize a torn snapshot. Both take the same
   lock now.
4. The shell matched candidates on raw JSON values while the facade
   normalizes them, so string coordinates silently skipped the
   draw. The shell calls the new 'Sandbox.candidate_key' now.
5. A late reaction response could overwrite the panel after the
   user picked another candidate. The page drops a response whose
   sequence number is stale.

Finding 5 carries no endpoint test: it is browser-side logic. It
was verified out of band by running the page script in node against
a live server with a 600 ms delay injected into the first reaction
response; the panel kept the second engagement.

Three further findings are contract gaps that the user re-scopes:
the shared support die, the attacker-side support exposure, and the
absent counter and support probabilities. The dice block states
them; the page works around none of them.

## Call chain

Page load → GET /api/state (Sandbox.snapshot) + GET /api/decision
(Sandbox.pending_decision). Unit click → candidates from the
decision payload. Attack click → POST /api/reactions
(Sandbox.reaction_options with the candidate). Confirm → POST
/api/act (Sandbox.act; dice keys from the manual controls or the
server draw) → repaint from the returned state and pending payload.
Every handler holds one lock around the sandbox calls.

## Contention points for review

- The contract gaps re-scoped to the user (proposal: fold into
  issue #47): the shared support die, the attacker-side support
  exposure ('Decision.support' not surfaced), and the absent
  counter and support probabilities. The dice block carries the
  honesty note; the page works around none of them.
- Review round 1 fixed 'facade.py' (issue #40's file) at the
  source: inputs that raised TypeError now raise ValueError. No
  caller depended on the old behavior; the stacked merge order
  makes this land after #40.
- The server draw lives in the shell (input synthesis, not game
  rules); the draw probability is re-read from the facade, never
  trusted from the client.
- The conventions angle of the review died to a tooling error; the
  correctness and cross-file angles completed and their findings
  are fixed above.
- The page refuses commands once the phase leaves 'ally' and points
  at issue #42 — a UI scope gate, not a game rule.

## Verification

Gates: 'uv run pytest -q' 1069 passed, 4 skipped; 'uv run ruff
check src tests scripts' clean. Real-browser pass on the feature
commit (Chrome on the dev machine, placeholder scenario): select
a5 → reach cells paint → attack candidate → reaction options with
correct numbers (dodge lowers the hit rate, defend cuts the damage)
→ manual miss → acted, EN spent, defender HP unchanged, pending
list shrank. The fix round is logic-only and was re-verified with
the node shim (stale-response guard held under an injected 600 ms
delay). Code-only branch: no adb.

## Resume point

Done. Awaiting review.

## Progress log

- 2026-08-14: branch created, roadmap written.
- 2026-08-14: play mode endpoints, page interaction, dice input and
  the HTTP walk test. Gates green: 1063 passed, 4 skipped; ruff
  clean.
- 2026-08-14: review round 1, five mechanical findings fixed. Gates
  green: 1069 passed, 4 skipped; ruff clean.
