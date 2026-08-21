# Branch roadmap: issue 63, the candidate enumeration

> Type: working—deleted at merge

## Resume point

The branch stands on 'issue-62-formulas' (4af4b45), because the
enumeration reads the domain model of #61 and the formulas of #62,
and #62 waits for review. The user merges the two branches in
order.

## Plan

The enumeration is a set of board rules. It lives in the domain
package 'engine/battle' as methods of 'Board', and the server binds
the two declared commands 'actions' and 'reactions' to them. The
contract is docs/spec/battle-engine-protocol.md; the Python
functions 'legal_attacks', 'legal_map_attacks', 'legal_skills',
'reposition_moves' and 'legal_reactions' of 'sandbox/model.py' are
the oracle for the numbers only.

Three rules diverge from the Python oracle on purpose:

1. Geometry: the engine reads the orthogonal footprint distance of
   #61 ('SpanDistance', 'ReachableCells'). Python reads the king
   step.
2. No 'none' stance: the reaction list holds dodge, defend, shield
   on a unit that carries one, and one counter entry for each
   weapon that reaches. Python keeps 'none'.
3. The move permission is the field 'usable_after_move' of the
   weapon. A weapon with a false value fires from the current cell
   only. Python infers it from the kind.

Steps:

1. Domain ('engine/battle/model.go', 'codec.go'): 'Board' gains
   'Phase' and 'Turn'; 'Unit' gains 'MaxHP', 'ENMax', 'Acted',
   'HasShield', 'Ammo', 'Skills'; 'Weapon' gains 'CanCounter' and
   'UsableAfterMove'; a 'Skill' type with the fields a rule reads
   ('Kind', 'Amount', 'Uses', and the area fields). New domain
   types 'Decision' and 'Reaction' with a 'Stance' and an
   'ActionKind' enum; the codec encodes them to the protocol
   types.
2. 'engine/battle/candidates.go': 'Board.Actions(unitID)' gives
   the attacks, the map attacks, the skills, the repositions and
   the standby of one unit, in that order. An attack names one
   destination per target and weapon: the reachable anchor in the
   weapon band that is nearest to the current anchor (the
   orthogonal distance, then the squared Euclid distance, then the
   coordinate). A weapon with 'UsableAfterMove' false reads the
   current anchor alone. A reposition names, per target, the
   reachable anchor nearest to that target, plus the anchor
   farthest from the nearest target. A skill is enumerated when it
   has a use left and its effect has room (heal under max HP,
   refill under max EN); a skill whose area leaves the caster is
   not enumerated by this issue (open point).
3. 'engine/battle/reactions.go': 'Board.Reactions(defenderID,
   attackerID, attackerCell, weaponName)' per the contract. A
   support defender (same faction, alive, charges left, within its
   own move range of the defender) adds a 'SupportDefend' variant
   to dodge and to counter only. A support attacker of the
   defender (same faction, alive, charges left, within its move
   range of the defender, a non-map weapon with EN that reaches
   the attacker cell) adds a 'SupportAttack' false variant to every
   entry. A map weapon gives an empty list. A weapon that does not
   reach the defender from the cell is an error.
4. Server ('engine/server/session.go' or a new file): 'actions'
   (illegal_state when the unit is not of the current phase or
   acted) and 'reactions' (illegal_action when the weapon does not
   reach) on the loaded board.
5. Differential: a new op 'actions' and a new op 'reactions'. The
   fixtures for these ops use boards where every unit has move
   range 0 and the units stand on one axis, so the orthogonal and
   the king distance agree. The Python writer drops the 'none'
   reactions and sorts both lists by an explicit key; the Go op
   sorts by the same key. The test names the two diverging rules
   in its doc comment.
6. Hand-written Go tests for the move-dependent choices: the
   nearest band anchor, the 'UsableAfterMove' false weapon, the
   reposition picks, the support-defense pairing (a test of the
   #44 constraint), the empty list for a map weapon, and the
   determinism of the order.

Gates: uv run pytest -q; uv run ruff check src tests scripts; and
from 'engine': go vet ./... and go test ./...

## Progress log

- 2026-08-21: branch created on issue-62-formulas 4af4b45; plan
  written.
