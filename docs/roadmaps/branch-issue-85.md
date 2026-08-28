# Branch roadmap: issue 85, the formulas in their own package

> Type: working—deleted at merge

## Where the branch stands

The branch 'issue-85-formula-package' starts from 'dev' (692f511),
after the merge of #84. No code has moved yet; this document holds
the placement assessment the user asked for on 2026-08-28.

## What the code is today

Three classes of code live in 'engine/battle':

1. Types. 'model.go' holds 22 types. Data types: 'Cell', 'Size',
   'Footprint', 'Bounds', 'RadiusRange', 'Faction', 'WeaponCategory',
   'Weapon', 'Stance', 'Debuff', 'Skill', 'Pilot', 'Mech', 'Unit',
   'Decision', 'ResponseAttack', 'Terrain', and the small enums. One
   behaviour type: 'Board', with 14 methods. 'Pilot.AttackFor' and
   'Unit.HasENFor' are the only methods of the data types that a
   formula reads.
2. Formulas. 'damage.go' (formulas 1 to 11), 'hit.go' (the hit
   chain), 'rules.go' (ten constants and 'StanceMultiplier'), and
   the formula half of 'strike.go' ('StrikeDamage', 'debuffBonus',
   'StrikeHitProbability'). 179 lines. What they read from the
   types: 'Weapon.Power', 'Weapon.Accuracy', 'Pilot.AttackFor',
   'Pilot.Defense', 'Pilot.Reaction', 'Mech.Attack', 'Mech.Defense',
   'Mech.Mobility', 'Unit.Debuffs', 'Unit.HasShield', 'Stance'.
   Nothing from 'Board', 'Footprint' or 'Decision'.
3. Orchestration. 'resolve.go', 'response_attacks.go', 'turn.go',
   'forecast.go', 'candidates.go', 'geometry.go', 'dice.go',
   'codec.go', 'clone.go', 'terrain.go', and the 'Board' methods.
   The callers of a formula: 'resolve.go' (9 sites), 'forecast.go'
   (4), 'response_attacks.go' (3), 'turn.go' (1).

The cycle the issue names: a formula package that keeps the current
signatures imports 'battle' for 'Unit', and 'battle' imports the
formula package for the numbers.

## The three placements weighed

A. Plain numbers. The formula package exports functions of floats
   ('BaseDamage(power, pilotAttack, pilotDefense, mechAttack, ...)').
   No cycle, no type dependency, the package is pure math and
   constants. Cost: positional float lists of six to eight values;
   the composition ('StrikeDamage') stays in 'battle' as glue that
   unpacks a 'Unit'.

B. A third package for the data types ('Pilot', 'Mech', 'Weapon',
   'Unit', ...). The formula package imports it; 'battle' imports
   both. Cost: 'Unit' is entangled with the board ('Alive',
   'HasENFor', 'Weapon', the charge and debuff state, and 'codec.go'
   builds it); 'Decision' and 'ResponseAttack' reference 'Stance';
   moving them is a large surgery for a ticket that promises a pure
   move, and it leaves a package of types with almost no behaviour.

C. Formula-side input structs. The formula package declares its
   own small inputs, for example 'Side{PilotAttack, PilotDefense,
   PilotReaction, MechAttack, MechDefense, Mobility}' and the
   weapon's 'Power' and 'Accuracy' as values; 'battle' adapts a
   'Unit' plus a 'Weapon' into a 'Side' at each call. No cycle. The
   names of the reference document ('攻擊方駕駛攻擊值' and the
   like) become field names, not positions. The differential case
   'formulas.json' already stores its inputs as side objects, so its
   test builds a 'Side' from the fixture without a 'Unit'.

Recommendation: C. It is A with names. The formula package depends
on nothing in 'battle', and 'battle' keeps one adapter per input.

## What moves and what stays under C

Moves to the formula package:

- The damage chain and the hit chain, over 'Side' and the weapon
  values. 'Pilot.AttackFor' stays on 'Pilot' in 'battle'; the
  adapter calls it and writes the result into 'Side.PilotAttack'.
- The rounding rule of a strike ('RoundToEven' for the goldens).
- 'DefenseMultiplier(defending, shielded bool)' in place of
  'StanceMultiplier(stance, defender)': the formula reads two facts,
  and the map from a 'Stance' and 'Unit.HasShield' to those facts is
  the caller's.
- The constants of the formulas: 'NoDefenseMultiplier',
  'NoTerrainCorrection', 'DefendMultiplier', 'ShieldMultiplier',
  'CritNormal', 'CritHighMorale', 'CritSuper', 'DodgeHitPenalty'.

Stays in 'battle':

- The adapters: 'Unit' plus 'Weapon' to 'Side'; the sum of
  'Unit.Debuffs' as the penalty term; the dodge flag to the ability
  correction; 'Stance' plus 'HasShield' to the two booleans.
- 'CounterWeapon' and 'counterFits' (weapon selection).
- Two constants that are rules of the orchestration and not of a
  formula: 'MaxSupportAttackers' (the cap of a response attack) and
  'ENRegenPercent' (the turn cycle). The issue text moves every
  constant of 'rules.go'; by the user's own criterion, orchestration
  apart from formulas, these two belong to the orchestration. This
  needs a ruling.

## Open for the user

1. The package name. Candidates in Go style: 'engine/formula'
   (singular, as 'strconv' and 'math'), 'engine/combat'. The user
   rules.
2. Placement C, or A or B.
3. The two orchestration constants: stay in 'battle' (recommended)
   or move with the rest as the issue text says.

## Resume point

Waiting for the three rulings. Then: the formula package with its
tests moved, the adapters in 'battle', the differential test on the
new import, the spec section, gates.

## Progress log

- 2026-08-28: worktree added, assessment written.
