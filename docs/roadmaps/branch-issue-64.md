# Branch roadmap: issue 64, the engagement resolution

> Type: working—deleted at merge

## Resume point

The branch stands on 'issue-63-candidates' (40b7e3a). The
resolution reads the enumeration, the support finders and the
formulas of the two branches below it. The user merges #62, #63,
then this branch, in order.

## Plan

The resolution applies one decision to the board, in the domain
package 'engine/battle'. The order of one engagement is the
contract of docs/reference/combat-formulas.md ("交戰結算順序").
The Python functions 'strike_damage', 'strike_hit_probability',
'reaction_defense', 'counter_weapon', '_apply_attack',
'_apply_support_volley', '_apply_counter', '_apply_map_attack',
'_apply_skill', '_apply_debuff' and the activation bookkeeping of
'step' in 'sandbox/model.py' are the oracle for the resulting
state only. The Go code is designed from the domain.

Rules that diverge from the Python oracle on purpose, on top of
the four of #63:

5. The attacker chooses the support attack ('Decision.Support');
   the enumeration gives both variants when a support attacker
   qualifies. Python fires every supporter on every attack.
6. An illegal move in a decision is an error, not a silent no-op.
   Python ignores an unreachable 'move_to'.
7. A destroyed unit stays on the board with HP 0; Python removes
   it at the end of 'step'. Every roster query already filters on
   'Alive'.

Not in this branch: the critical hit. The closure condition names
a critical path, but neither the reference document nor the oracle
holds a critical rate (docs/reference/combat-formulas.md, open
item "暴擊率公式"), so no chance node can carry it. Issue #48 owns
the critical roll.

Steps:

1. Domain: a 'Rules' type with defaults, decoded from the rules
   payload; the board carries it. 'Unit' gains 'ChanceSteps',
   'ChanceStepsMax', the two charge maxima, 'AttackShield',
   'InterceptionReduction', 'Debuffs'. 'Weapon' gains 'Power',
   'Accuracy', 'Blast', and the debuff it applies. 'Decision'
   gains 'Reaction *Reaction'. 'DecodeDecision' and
   'DecodeReaction'. 'Board.PhaseIndex'.
2. 'engine/battle/strike.go': 'StrikeDamage' (the rounded
   expected damage; Python rounds half to even, so Go uses
   'math.RoundToEven'), 'StrikeHitProbability' (the weapon
   accuracy, minus the dodge penalty of the rules when the
   defender dodges), the stance multiplier from the rules, the
   interception multiplier, the counter weapon of a defender.
3. 'engine/battle/dice.go': a 'Dice' interface that the resolution
   asks at each chance node (support volley, main strike,
   counter), with a 'Forced' value that holds one outcome per
   node kind. The sampled dice with a seed is #65.
4. 'engine/battle/resolve.go': 'Board.Apply(decision, dice)'
   returns the trace of the engagement and an error. It gates the
   actor through 'Activatable', moves the unit when the move is
   reachable and the weapon or the skill permits a move, then
   resolves: the attacker support volley, the main strike on the
   struck unit (the interceptor when the reaction carries support
   defense, with one charge spent on the first landed hit of the
   whole volley), the debuff on a landed hit, then, when the
   defender lives and the reaction says so, the defender support
   volley and the counter against the attacker or its attack
   shield bearer. A map attack spends ammo and EN and damages
   every foe inside the blast of the aim. A skill spends a use
   and heals or refills. The bookkeeping: a kill that leaves the
   actor alive with a chance step left gives the re-act;
   otherwise 'Acted' follows the action.
5. 'Board.Actions' gives the attack with 'Support' true and false
   when a support attacker of the actor qualifies from the firing
   anchor against the target, and 'Support' false alone
   otherwise. The reposition, the standby, the skills and the map
   attacks carry 'Support' false.
6. Differential: op 'apply', input the decision (with its
   reaction) and the forced dice, expectation the living units of
   the board after the Python 'step', compared as a list in board
   order. The boards keep the #63 constraints (one cell, one row,
   no move for the actor), and every acting faction keeps a second
   unit that has not acted, so the Python 'step' rotates no
   phase. Cases: hit and miss; defend, shield, dodge; counter hit
   and miss; the interceptor takes the whole volley and one charge
   on the first landed hit; the attacker support volley on and
   off; the defender support volley; the attack shield on the
   counter; a map attack over two victims in the row; heal and
   refill with 'ends_activation' true and false; a debuff that
   replaces a weaker one and one that does not; a kill that gives
   the re-act; the EN and the ammo bookkeeping.
7. Hand-written Go tests for the moves, the illegal move, the
   illegal action, the kept destroyed unit, and the support choice
   of the attacker.

Gates: uv run pytest -q; uv run ruff check src tests scripts; and
from 'engine': go vet ./... and go test ./...

## Progress log

- 2026-08-21: branch created on issue-63-candidates 40b7e3a; plan
  written.
