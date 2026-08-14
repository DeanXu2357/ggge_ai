# Branch roadmap — issue 55: sandbox doc drift

> Type: working—deleted at merge

## Goal

Correct the documentation drift and add the terminology bindings
from issue #55. Docs-only branch.

## Plan

1. Rewrite the map attack section of
   'docs/reference/combat-formulas.md' to the implemented state.
2. Apply the terrain ruling (2026-08-14): one terrain value for the
   whole map of a stage. Correct 'docs/spec/intel-data-spec.md' and
   the calibration list in 'combat-formulas.md'.
3. Add the terminology bindings and the 'solver' retirement note to
   'docs/reference/terminology-map.md'.
4. Append the terrain ruling to 'docs/record/decisions.md'.

## Resume point

All four plan items are done. The branch waits for review.

## Progress log

- 2026-08-14: branch created, roadmap written.
- 2026-08-14: verified the map attack facts in
  'src/ggge_ai/sandbox/model.py' ('legal_map_attacks',
  '_apply_map_attack', 'Unit.ammo', 'Weapon.blast', and the
  MAP_ATTACK branch of 'step') and in the four map attack tests of
  'tests/test_sandbox_model.py'. Rewrote the map attack section of
  'docs/reference/combat-formulas.md' to the implemented state and
  kept the execution-layer gap (issue #23). One gap stays recorded:
  the pilot ability that removes the EN and ammo cost for a turn.
- 2026-08-14: applied the terrain ruling to the calibration list of
  'docs/reference/combat-formulas.md' and to the stage-level row of
  'docs/spec/intel-data-spec.md': one value for each stage, not a
  per-cell table; live calibration stays with issue #53.
- 2026-08-14: added twelve bindings and the retired-'solver' note to
  'docs/reference/terminology-map.md'.
- 2026-08-14: appended the terrain ruling to
  'docs/record/decisions.md'.
- Gates: docs-only branch, so pytest and ruff are skipped under the
  CLAUDE.md docs-only rule. Every diff path is under 'docs/'.
