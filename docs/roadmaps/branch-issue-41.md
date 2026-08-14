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

## Open points

- The facade reports no probability for the counter die and the
  support die. The server draw fills only the main hit; the other
  two keep the model default. Closing this needs new fields in the
  reaction payload, which is a facade change, so it stays out of
  this branch.
- The attacker side support volley is always on: 'Decision.support'
  defaults to true and the facade has no field for it. The page
  cannot offer the choice.
- The page stops when the phase leaves 'ally' and points at issue
  #42. It renders no enemy-phase commands, although the facade
  would enumerate them.
- Live check in a browser is still open; the tests drive the
  endpoints, not the DOM.

## Resume point

Done. Awaiting review.

## Progress log

- 2026-08-14: branch created, roadmap written.
- 2026-08-14: play mode endpoints, page interaction, dice input and
  the HTTP walk test. Gates green: 1063 passed, 4 skipped; ruff
  clean.
