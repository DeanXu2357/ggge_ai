# Branch roadmap — issue 40: sandbox query contract

> Type: working—deleted at merge

## Change summary

Six commits plus one merge from 'dev'.

1. 'src/ggge_ai/sandbox/facade.py' (new): class 'Sandbox' bundles
   the scenario products. Public API: 'from_scenario', 'turn',
   'phase', 'outcome', 'units', 'rules', 'events', 'board',
   'snapshot', 'pending_decision', 'reaction_options', 'act', and an
   optional advisor slot typed
   'Advisor[BattleState, Decision | Reaction]'. Consumers outside
   the package touch only the facade; 'act' and 'reaction_options'
   take plain mappings and round-trip the payload keys.
2. 'src/ggge_ai/sandbox/model.py': new public surface —
   'legal_reactions' (owns the stance list, the 'has_shield' gate,
   the counter gate, the support-defense crossing),
   'reaction_defense', 'blast_victims', 'counter_weapon',
   'pending_units', 'SUPPORT_DEFEND_STANCES';
   'find_support_attackers' gained 'foe_pos'. '_apply_attack' and
   '_apply_map_attack' call the shared helpers, so enumeration and
   resolution cannot drift. Resolution semantics unchanged: the 87
   pre-existing sandbox tests pass untouched.
3. 'scripts/sandbox_ui.py': a shell now — routing plus the embedded
   page. Its single package import is the facade (asserted by an
   ast-based test).
4. Tests: 'tests/test_sandbox_facade.py' (31 tests), three
   'legal_reactions' tests in 'tests/test_sandbox_model.py',
   adapted 'tests/test_sandbox_ui.py'.
5. 'docs/reference/terminology-map.md': bindings for
   'sandbox facade'／沙盤門面, 'decision payload'／決策酬載,
   'activation'／啟動 (with the disambiguation note against the
   frozen uses of 行動).

## Call chain

scripts/sandbox_ui.py → Sandbox.from_scenario → scenario.load.
Page request → Sandbox.snapshot / pending_decision → model
enumerators ('pending_units', 'reachable_cells', 'legal_attacks',
'legal_map_attacks', 'legal_skills', 'reposition_moves') and the
formula functions. Engagement → Sandbox.reaction_options(candidate)
→ model.legal_reactions (post-move position). Advance →
Sandbox.act(candidate, reaction) → validation against the
enumerated candidates → model.step.

## Review round

A high-effort code review returned ten findings; all are closed on
the branch (commit 'Harden the sandbox query contract'): dice
pass-through on 'act', 'support_attack' round-trip, post-move
counter legality, ValueError on illegal or malformed input, blast
pricing over all victims, the responsibility move of
'legal_reactions' into the model, no duplicated reaction options,
strict weapon resolution, the honest advisor annotation, and the
'activation' rebinding. One finding partially disputed with reason:
'Reaction' carries no dice fields; all three dice live on
'Decision'.

## Contention points for review

- Responsibility split (the point you asked to be reminded of):
  after the review round the facade holds zero game rules and zero
  private model imports; the rules the review found in the facade
  moved into 'model.legal_reactions'. Check that split.
- The support-defense pairing rule (defend/shield never pair;
  'none' unconfirmed, warning comment on 'SUPPORT_DEFEND_STANCES')
  landed here instead of issue #44, because the enumerator is the
  natural owner. The ('none', True) pair needs device confirmation
  — a live item for the calibration queue.
- 'legal_attacks' collapses each (target, weapon) pair to one
  firing cell. Enough for the UI; an advisor that wants to choose
  firing cells (#44) will need more.
- Map attack candidates report 'hit_probability: 1.0' — matches
  the model (no hit node) and the 必中 line in combat-formulas.md.
- Constructor carries a keyword-only 'scenario' parameter beyond
  the approved four arguments; 'snapshot' needs the stage header
  and 'check_outcome'.
- 'reaction_options' takes the attack candidate mapping instead of
  (attacker, defender, weapon) — one parameter serves both the
  post-move rule and strict weapon resolution.

## Verification

'uv run pytest -q': 1056 passed, 4 skipped. 'uv run ruff check src
tests scripts': clean. Code-only branch: no adb, no screenshots.
Optional eyeball check: run the viewer with
'uv run python scripts/sandbox_ui.py' on the placeholder scenario
and open the page.
