# Branch roadmap — issue 55: sandbox doc drift

> Type: working—deleted at merge

## Change summary

Docs-only branch. Four commits, every diff path under 'docs/'.

1. 'docs/reference/combat-formulas.md': the map attack section now
   states the implemented state — the sandbox models ammo, blast
   area, forced end with no re-act, and no interaction
   ('legal_map_attacks', '_apply_map_attack', the MAP_ATTACK branch
   of 'step'; four tests pin the behavior). The execution-layer gap
   (enemy map attack has no reaction popup, issue #23) stays as its
   own bullet. One gap stays recorded: the pilot ability that
   removes the EN and ammo cost for a turn.
2. Terrain ruling 2026-08-14 applied: one terrain value for a whole
   stage map. The calibration item in 'combat-formulas.md' and the
   stage-level row of 'docs/spec/intel-data-spec.md' now say one
   value per stage; the per-cell hypothesis is withdrawn. Live
   calibration of the values stays with issue #53.
3. 'docs/reference/terminology-map.md': twelve bindings added
   (sandbox／沙盤, scenario file／情境檔, advisor／顧問,
   expectiminimax, play mode／操作模式, edit mode／編輯模式,
   operation history／操作史, first strike／先攻, Ex weapon／Ex 武裝,
   support crew skill／支援人員技能, pilot skill／駕駛技能,
   unit skill／機體技能) plus the note that retires the name
   'solver' (it names only the deleted legacy stack; the new
   implementation is 'ExpectiminimaxAdvisor').
4. 'docs/record/decisions.md': one appended entry records the
   terrain ruling. Only the last 40 lines were read; no earlier
   entry was touched.

## Contention points for review

- The decisions.md entry is in English. The ledger tail (the 0811
  entries) is English and the 0811 ruling made new docs text
  English, so the writer matched the current style, not the frozen
  Chinese corpus. Say the word for a Traditional Chinese amend.
- Stale claims found but left out of scope:
  - 'combat-formulas.md' case 17 paragraph still says the support
    volley is a 'solver' simplification and names legacy batch 'M2'.
    The substance is issue #47 scope.
  - 'combat-formulas.md' case 8 says the tactical layer is
    「待重建」; the rebuild is now the advisor line (#44 onward).
  - 'intel-data-spec.md' support crew row says the sandbox does not
    model it — still true until issue #50.
  These are reported, not fixed; the user decides whether any
  becomes an issue.

## Verification

Docs-only gate exemption: pytest and ruff skipped per the CLAUDE.md
rule; 'git diff --name-only dev...HEAD' shows only 'docs/' paths.
Map attack facts were verified against 'sandbox/model.py' and the
four map attack tests before the rewrite.
