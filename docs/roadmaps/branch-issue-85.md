# Branch roadmap: issue 85, the formulas in their own package

> Type: working—deleted at merge

## Where the branch stands

The branch 'issue-85-formula-package' starts from 'dev' (692f511),
after the merge of #84. No code has moved yet; this document holds
the placement assessment the user asked for on 2026-08-28.

Issue: #85. Branch: issue-85-formula-package. Status: awaiting-review.

## Change summary

| Commit | What |
|---|---|
| 7002b69, db3ac4e, f99e68f | This file: the assessment, the ordering behind #86, the rebase |
| 043a5d5 | The formulas move to 'engine/battle/formula' over 'Side'; the adapters in 'board'; the differential test on 'Side' |
| 0648762 | 'unit', 'pilot', 'mech', 'weapon' private in 'board': the differential harness no longer builds them |
| feea212, 6a23324 | The artifact and the map; four comments that index files or narrate a plan dropped |

    engine/battle/formula   side.go, damage.go, hit.go, strike.go, rules.go
                            and their tests. Imports 'math' alone.
    engine/battle/board     the adapters 'attackerSide', 'defenderSide',
                            'debuffBonus', 'defenseMultiplier',
                            'strikeDamage', 'strikeHitProbability';
                            'maxSupportAttackers' in resolve.go and
                            'enRegenPercent' in turn.go; no 'math' call
                            left; every type private

'formula' exports 'Side', the damage chain ('BaseDamage',
'CombatBaseDamage', 'DamageScale', 'FinalDamage', 'CriticalDamage',
'ExpectedDamage'), the hit chain ('HitRatePercent',
'HitProbability'), 'StrikeDamage', 'StrikeHitProbability',
'DefenseMultiplier', and the eight formula constants. 'board'
exports 'Board', its contract methods, 'Apply', 'Advance' and the
three 'Decode*' constructors, nothing else.

## Call chain

    board.resolve / forecast / response_attacks
      attackerSide(unit, weapon) -> formula.Side   PilotAttack = pilot.AttackFor(weapon)
      defenderSide(unit)         -> formula.Side   PilotAttack 0, never read
      debuffBonus(unit)          -> the bonus term
      defenseMultiplier(stance, unit) -> formula.DefenseMultiplier(defending, shielded)
      strikeDamage(...)          -> formula.StrikeDamage(power, a, d, NoTerrainCorrection, bonus, 0, defense)
      strikeHitProbability(...)  -> formula.StrikeHitProbability(accuracy, a, d, dodging)
    differential.formulas_test builds formula.Side from the fixture sides

## Verification

- Gates green at 043a5d5 and 0648762 (the editor's runs); a separate
  run at the last commit is recorded when it lands.
- 'git diff f99e68f --stat -- tests/fixtures' is empty: no golden
  changed, no number moved.
- The main session read 'formula/side.go', listed every comment of
  'formula' and 'board', the exported surface of both packages, and
  'go list -deps' of both.

## Contention points

1. **'Side' field names.** 'MechAttack' and 'MechDefense' where
   combat-formulas.md writes UnAtk and UnDef, because the map
   forbids "unit attack" for a mech value. The map row 'formula
   side' carries the symbol binding.
2. **Two orchestration constants stayed in 'board'**
   ('maxSupportAttackers', 'enRegenPercent') against the issue
   text, on the criterion the user gave: orchestration apart from
   formulas.
3. **Board-side copies of three tests** cover the adapters
   ('defenseMultiplier', 'debuffBonus', 'attackerSide') beside the
   formula-level tests over 'Side'. They test the mapping, not the
   arithmetic; delete them if the user reads them as duplication.
4. **'DefenseMultiplier(defending, shielded bool)'** replaces
   'StanceMultiplier(stance, unit)': the formula reads two facts,
   and the map from a stance and a shield to those facts is the
   board's.

## Deferred

- Issue #80 replaces the constant terrain correction with the
  dispatch over weapon abilities; the warning on 'board.strikeDamage'
  marks the call.
