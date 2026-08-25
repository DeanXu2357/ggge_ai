# Branch roadmap: issue 63, the two candidate commands

> Type: working—deleted at merge

## Where the branch stands

The branch stands on 'issue-62-formulas' (5e25add). The two
commands read the domain model of #61 and the formulas of #62.
Merge #62 first, then this branch.

## What the two commands answer

The user ruled on 2026-08-25 that the engine reports and the
client decides. The engine answers what a unit carries and what an
engagement offers. It selects no move, no target and no stance,
and it removes no entry that a resource makes unusable. The client
draws the bands, the user picks, and 'act' judges the pick.

'actions' answers the capability payload of one unit: the status
of the unit, the cells it can move to, the weapon list and the
skill list. It reads no target, no band and no resource. A weapon
with no energy left stays in the list.

'reactions' answers the engagement payload: the reaction options
of the defender against one planned strike, and the support units
of the two sides. The request carries the action of the attacker,
so the engine reads the cell of the strike from 'move_to'.

## Change summary

New:

- 'engine/battle/candidates.go': 'Board.Capabilities'. It gives
  the unit and its reachable cells. It refuses an unknown unit, a
  destroyed unit and a unit off the phase. A unit that acted
  answers: 'acted' is data, not a refusal.
- 'engine/battle/reactions.go': 'Board.Reactions' takes the action
  of the attacker and the defender id, and gives 'Engagement'. The
  list holds dodge, defend, one counter for each weapon that can
  counter and reaches, and 'none'. It holds no 'shield'. An action
  that makes no strike, a map attack among them, gives an empty
  list. 'Board.SupportDefenders' and 'Board.SupportAttackers' run
  for the two sides.
- 'engine/battle/codec.go': 'EncodeCapabilities',
  'EncodeEngagement', 'EncodeUnitStatus', 'EncodeWeapons',
  'EncodeSkills' and 'DecodeDecision'.
- 'engine/protocol/types.go': the payload types 'UnitStatus',
  'WeaponEntry', 'SkillEntry', 'Forecast', 'ReactionOption',
  'SupportDefendOption', 'SupportAttackOption', 'DefenderOptions'
  and 'AttackerOptions'.

Changed:

- 'Board' carries 'Phase' and 'Turn'; 'Unit' carries 'MaxHP',
  'ENMax', 'Acted', 'HasShield', 'Ammo' and 'Skills'; 'Weapon'
  carries 'CanCounter' and 'UsableAfterMove'. A state without a
  phase is a decode error.
- The stance 'none' enters the contract, in
  'engine/protocol/state.go' and in 'engine/contract.py'. The
  error code 'already_acted' enters the contract with it.
- 'docs/spec/battle-engine-protocol.md': the two command sections,
  the error code table, and the divergence paragraph.
- 'docs/reference/terminology-map.md': capability payload,
  engagement payload, forecast, support defender, support
  attacker, interceptor, reaction stance.

Removed:

- The enumeration of one activation: 'Board.Actions', the anchor
  pick 'firingAnchor' and its key 'nearness', the aim pick
  'aimCell', the reposition pick, the skill filter, and the wire
  encoders of a decision. Each one selected for the client.
- 'Board.Activatable' and 'ErrActed'. The gate that refuses a unit
  that acted belongs to 'act'.
- The domain type 'Reaction' and its encoders. The wire type stays
  for the request of 'act'.
- The differential ops 'actions' and 'reactions', and the 15
  candidate checks of the two fixture boards. The Python oracle
  answers a list of decisions and a list of stances; neither
  compares against a capability payload or an engagement payload.
  The two boards keep their 'state', 'events' and 'rules' checks.

## The forecast is a placeholder

Every field of every forecast is null. The rules are written in
the spec and wait for their branch:

- 'damage' is the conservative lower bound: no critical hit and no
  bonus. The one exception is a weapon and a mech that stack the
  critical rate to 100 percent; the bound then holds the critical
  damage.
- 'kill' is true when that bound is at least the hit points of the
  target. The hit roll is no part of it.
- A stance carries the plain result of that stance. An interceptor
  changes no outcome of a stance, so each interceptor carries its
  own forecast.

The domain drops the power of a weapon when it reads the state, so
the branch that fills the forecast adds 'Power' to the domain
'Weapon' first.

## Contention points

1. 'shield' stays in the 'Stance' enum, and 'reactions' never
   answers with it. The shield of a unit settles during the
   damage, in 'act'.
2. 'Decision.Support' and the two support fields of the wire
   'Reaction' still stand. The payload that 'act' takes for a
   support unit is the issue of 'act'.
3. The counter list reads the band and the energy. The stand
   'none' is in the list of every strike, so a defender that
   reaches nothing still answers.

## Open points

- The Python client speaks the retired contract:
  'engine/fake.py' answers 'actions' with a list of decisions,
  'EngineSession.pending_decision' and
  'EngineSession.reaction_options' read that list, and the sandbox
  page builds its command menu from it. Issue #78 holds that work.
  It runs one time, after the engine command branches merge.
- 'Board.Roster' still panics; its issue is the deploy flow.

## Verification

- From 'engine': go vet clean; go test ok (battle, differential,
  protocol, server); gofmt clean.
- uv run ruff check src tests scripts: all checks passed.
- uv run pytest -q: 988 passed, 4 skipped.
