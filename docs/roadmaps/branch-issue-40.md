# Branch roadmap — issue 40: sandbox query contract

> Type: working—deleted at merge

## Goal

Implement the 'Sandbox' facade and the query contract from issue
#40. After initialization, consumers outside the sandbox package
touch only the facade. 'scripts/sandbox_ui.py' becomes an HTTP and
HTML shell.

## Plan

1. New module 'src/ggge_ai/sandbox/facade.py': class 'Sandbox',
   decision payload types, aggregate action enumeration, reaction
   enumeration, read methods, act method, optional advisor slot.
2. Move serialization from 'scripts/sandbox_ui.py' into the package.
3. Reduce the script to routing and HTML.
4. Tests: aggregate output versus the piecewise enumerators; facade
   reads; the script imports only the facade.

## Resume point

All four steps are done, and the ten review findings are closed.
Gates pass. The branch is ready for a second review.

## Progress log

- 2026-08-14: branch created, roadmap written.
- 2026-08-14: 'sandbox/facade.py' added. The class 'Sandbox' holds
  the scenario products, serializes the board, aggregates the
  activation candidates and the reaction options, and applies one
  decision through 'step'. The candidate order is the concatenation
  of the piecewise enumerators, so 'advice.pricing' aligns with it.
  New test file 'tests/test_sandbox_facade.py'. Terminology map: new
  entries for 'sandbox facade', 'decision payload', 'activation'.
- 2026-08-14: 'scripts/sandbox_ui.py' is a shell now: routing and the
  embedded page only. Its single package import is the facade. The
  serialization tests moved to the facade test file;
  'tests/test_sandbox_ui.py' keeps the server smoke test and adds an
  import check that reads the script with 'ast'. Gates: 1039 passed,
  4 skipped; ruff clean.
- 2026-08-14: merged 'dev' after issue #55. The terminology table
  conflict kept both sets of rows. Finding 9 of the review: the
  binding for 'activation' moved from 行動 to 啟動, because the
  frozen corpus holds 行動 for 行動類型 and 防禦行動倍率.
- 2026-08-14: ten review findings closed. The model gained the
  public reaction enumerator 'legal_reactions', which owns the
  stance list, the shield gate, the counter gate at the post-move
  cell, and the support-defense pairing rule from
  docs/reference/battle-prep-ui.md. New public model helpers:
  'pending_units', 'counter_weapon', 'reaction_defense',
  'blast_victims'; '_apply_attack' and '_apply_map_attack' now share
  them, so resolution and enumeration cannot drift. The facade holds
  no private import. 'act' validates the candidate against the
  enumerated list and the reaction against 'legal_reactions', passes
  the dice fields through, and rejects a malformed cell. Map attack
  candidates price every unit in the blast. 'reaction_options' takes
  the attack candidate, so it reads the post-move cell, and it names
  the weapon. Gates: 1056 passed, 4 skipped; ruff clean.
