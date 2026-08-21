# Branch roadmap: issue 63, the candidate enumeration

> Type: working—deleted at merge

## Where the branch stands

The branch stands on 'issue-62-formulas' (5e25add). The
enumeration reads the domain model of #61 and the formulas of
#62. Merge #62 first, then this branch.

## Change summary

The engine enumerates the legal actions of one unit and the legal
reactions of one defender, as methods of 'Board' in the domain
package 'engine/battle', and the server binds the two declared
commands 'actions' and 'reactions' to them. Python is the oracle
for the lists only; the Go code is designed from the domain.

New:

- 'engine/battle/candidates.go': 'Board.Actions'. One attack per
  pair of a target and a weapon, from the reachable anchor
  nearest to the current anchor (board distance, then squared
  Euclid distance of the anchors, then column then row). A weapon
  with 'UsableAfterMove' false fires from the current anchor. A
  map attack aims at the cell of the target footprint nearest to
  the firing footprint. A skill is enumerated when it has a use
  left, its effect has room, and its area is the caster (range 0,
  blast 0). A reposition names the anchor nearest to each target
  and the anchor farthest from the nearest target. Standby last.
- 'engine/battle/reactions.go': 'Board.Reactions'. A map weapon
  gives the empty list. Dodge, defend, shield on a unit with one,
  one counter per weapon that can counter, is paid for, and
  reaches. A support defender adds a 'SupportDefend' variant to
  dodge and counter alone. A support attacker of the defender
  adds a 'SupportAttack' false variant to every entry.
  'Board.SupportDefender' and 'Board.SupportAttackers' are
  exported for the engagement issue.
- 'engine/battle/model.go': the activation gate 'Board.Activatable'
  with the sentinel errors 'ErrNoUnit', 'ErrDestroyed',
  'ErrOffPhase', 'ErrActed'; the domain types 'Decision',
  'Reaction', 'Skill', the enums 'ActionKind', 'Stance',
  'SkillAffects'; 'Unit.CanPay', 'Unit.Weapon', 'Cell.Before',
  'RadiusRange.Holds'.
- 'engine/server/candidates.go': the two handlers; 'boardOf' in
  'session.go' shares the session check and the decode with
  'reach'.
- 'engine/differential/candidates_test.go': the ops 'actions' and
  'reactions'; both sides sort by an explicit key.
- 'tests/fixtures/engine/candidate_board.json' and
  'reaction_board.json': 8 'actions' checks and 7 'reactions'
  checks.
- Hand-written Go tests: 'candidates_test.go' (11),
  'reactions_test.go' (10), 'server/candidates_test.go' (8).

Changed:

- 'Board' carries 'Phase' and 'Turn'; 'Unit' carries 'MaxHP',
  'ENMax', 'Acted', 'HasShield', 'Ammo', 'Skills'; 'Weapon'
  carries 'CanCounter' and 'UsableAfterMove'. The codec decodes
  them and encodes a decision and a reaction. A state without a
  phase is a decode error.
- 'docs/spec/battle-engine-protocol.md': the content rules of
  'actions', the refusals for an unknown and a destroyed unit,
  'phase' is mandatory in a loaded state, and the candidate-list
  sentence in the divergence paragraph.
- 'docs/reference/terminology-map.md': support defender, support
  attacker, interceptor.
- 'scripts/write_engine_fixtures.py', 'tests/test_engine_codec.py',
  'tests/test_engine_client.py', 'tests/test_sandbox_ui.py': the
  two boards, the expectations, the coverage tests, and the
  implemented-command list.

## Call chain

'actions': the handler decodes the request, 'Board.Activatable'
refuses an unknown unit (illegal_action), a destroyed unit, a unit
off the phase, or a unit that acted (illegal_state); then
'Board.Actions' enumerates and the codec encodes the list.
'reactions': the handler decodes, 'Board.Reactions' answers or
refuses (illegal_action: unknown unit, unknown weapon, destroyed
unit, a weapon that does not reach).

## The four rules that diverge from the Python oracle

1. Geometry: orthogonal footprint distance and footprint reach,
   against the king step and one cell per unit.
2. No 'none' stance.
3. The move permission is 'usable_after_move' of the weapon, not
   the kind of the action.
4. Python 'legal_skills' reads no area; the engine enumerates only
   the caster-area skill.

The differential boards keep the four out: every unit covers one
cell and stands in one row; every unit of the 'actions' inputs has
move range 0 (a support unit keeps its move range, which is its
support reach); the writer drops the 'none' stance; every fixture
skill has range 0 and blast 0. A Python test guards the board
invariants; the Go test names the four rules in its doc comment.

## Contention points

1. The phase gate lives at the command ('Activatable'), not in
   'Board.Actions'. Whose turn it is does not change which actions
   are legal on the geometry, and the search enumerates the units
   of the phase by construction. The review first put the gate
   inside the enumeration; that made the differential rewrite the
   board phase per check, so the gate moved back out (619f518).
2. 'Decision.Support' is true on every enumerated action, the
   contract default. The attacker's choice of the support attack
   is #64.
3. A skill whose area leaves the caster is not enumerated. The
   center of such an area travels in 'aim', and no rule picks the
   center yet. Open point for the issue that enumerates skill
   areas.
4. 'Reactions' does not check that the attacker can pay the
   weapon; the contract does not ask for it and 'act' refuses an
   action that 'actions' does not give.
5. The map-attack destination follows the attack rule: a map
   weapon with 'usable_after_move' true may move. Python never
   moves for a map attack; the fixtures hold move range 0, so the
   two agree there.

## Verification

- From 'engine': go vet clean; go test ok (battle, differential,
  protocol, server), also with -count=3; gofmt clean.
- uv run ruff check src tests scripts: all checks passed.
- uv run pytest -q: 1119 passed, 4 skipped.
- uv run python scripts/write_engine_fixtures.py --check: clean.
  The earlier golden files came back byte for byte.
- Every one of the 15 candidate checks matched the Python oracle
  on the first run.
- Code review (2026-08-21, high effort): the verified items are
  applied in 2bc7037, 583c9c3, 5290f68 and 619f518. Declined:
  restructuring the pointer fields of 'Decision' (nil is the wire
  null), removing the domain-to-protocol enum maps (the decode
  boundary), an attacker-pay check in 'Reactions' (point 4),
  precomputed distance tables in 'Actions' (the advisor issue
  profiles first).

## Open points

- The efficiency of 'Actions' inside a search (per-anchor distance
  recomputation, one allocation per decision) is unmeasured. The
  advisor issue profiles before it changes the shape.
- 'Board.Roster' still panics; its issue is the deploy flow.
