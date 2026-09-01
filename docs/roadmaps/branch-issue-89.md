# Branch roadmap: issue 89, the position is the identity

> Type: working—deleted at merge

Issue #89. Branch off 'dev' at 'eb3d2f4'.

## The design

'Load' receives a slice of units. The position of a unit in that slice
is its identity, and the engine answers with that position. The same
holds for a weapon in 'Mech.Weapons', a map weapon in
'Mech.MapWeapons', and a skill in the skill list.

The engine translates nothing. There is no name to translate: a name is
not an identity, so no name field exists on a unit or on a weapon.

The client holds a position as an opaque handle. It knows the order it
sent, so it knows every position. A handle is stable inside one session
and promised across none.

### What this forbids

These are the errors of the first attempt, which was dropped. Each one
undoes the change:

- No lookup that walks a slice comparing an identifier. If such a walk
  exists, the identity is still the name and the position is a
  decoration.
- No name or id field kept "for the door". A field kept to translate is
  a translation layer.
- No table from name to position, in the state or beside it.
- No sentinel for a missing count. A slice position either exists or
  does not; there is no third value.
- No struct that pairs an id with a pointer to the thing it names. That
  is one thing held twice, and nothing keeps the two in agreement. An
  id travels between functions; a pointer is how the code touches the
  data at this instant, taken and dropped, never stored beside its own
  id.

## The wire

Every identifier is an integer. Every classification enum stays exactly
as it is: 'Faction', 'Terrain', 'Direction', 'ActionKind', 'Stance',
'SkillKind', 'SkillSource', 'SkillAffects', 'MapWeaponAffects',
'WeaponCategory' and 'Debuff.Kind'.

A name is not an identifier. 'Weapon.Name' and 'MapWeapon.Name' stay:
the name comes from the datamine, a person reads it, and it says what a
weapon is. It was never an identity; it was pressed into service as
one. The name stays data, and the position takes the identity.

Removed, because a position replaces it and it has nothing else to be:
'Unit.ID'. That string is a made-up handle and nothing more.

The rule everywhere: to point at a thing, use a position; to say what a
thing is, use its name, its kind or its category.

On the contract a value that points at a thing is an id, and the field
says so: 'UnitID', 'TargetID', 'WeaponID', 'MapWeaponID',
'SupportDefenderID', 'SupportAttackerIDs', 'ShooterID', 'StruckID',
'PendingIDs', each with an '_id' JSON key. A client does not know that
an id is a slice position and must not depend on it; that is the
engine's implementation. A field named 'Weapon' that holds an integer
also reads as a weapon object, which is wrong twice.

'Decision' carries 'UnitID int', 'TargetID *int', 'WeaponID *int',
'MapWeaponID *int', 'SupportDefenderID *int' and
'SupportAttackerIDs []int'. Exactly one of 'WeaponID' and 'MapWeaponID'
is filled on an attack. The same treatment for 'ResponseAttack'.

Past the gate the engine calls the value an id as well. One concept,
one word: that an id is a slice position states what the value is, not
a second name for it.

An answer that lists things in order needs no identifier field: the
position of a 'WeaponEntry' in 'ActionsResponse.Weapons' is its
identity. It keeps its name, so a client can display it.

The contract methods take an id: 'Actions(unitID int)',
'ReachableCells(unitID int)', 'ResponseAttacks(action *Decision,
defenderID int)'.

The protocol rises to 2.0. A client of 1.x cannot read a 2.0 board.

## Ammunition

'MapWeaponAmmo []int' on the unit, one entry for each entry of
'Mech.MapWeapons', in the same order. The name carries its owner, after
the 0828 ruling on identifiers.

'MapWeaponAmmo[i]' is the rounds left in 'Mech.MapWeapons[i]'. A zero
is a map weapon with no rounds left. There is no other state: whether a
map weapon spends ammunition at all is a question for the definition,
not for the count.

## How an id and a pointer divide the work

An id says WHICH. A pointer is how the code touches the data of that unit at
this instant. The division:

- A structure that outlives a call holds ids. 'Plan', 'answer',
  'supportAttacker', 'Strike', every option type: ids.
- A local variable inside one function may hold a pointer. It is taken from
  the board, used, and dropped.
- A function that must know which unit takes an id. A function that only
  reads or writes the data of a unit, and never reports which one, takes a
  pointer.
- A caller ALREADY KNOWS the id, because the caller passed it. No function
  hands an id back, and nothing pairs an id with a pointer to carry both.

'state.Battle.UnitAt(id int) (*Unit, error)' is the one door from an id to a
pointer. It bounds-checks and refuses with 'battle.ErrNoUnit'.

## The shapes

  type Plan struct {
      kind      battle.ActionKind
      actorID   int
      anchor    battle.Cell
      targetID  *int     // nil on an action that strikes nobody
      weaponID  *int     // nil unless the action fires a weapon
      joining   []supportAttacker
      bearerID  *int
      answer    answer
  }

  type supportAttacker struct {
      UnitID   int
      WeaponID int
  }

  type answer struct {
      response          *battle.ResponseAttack
      counterWeaponID   *int
      supportDefenderID *int
      joining           []supportAttacker
  }

  type Strike struct {
      Kind      StrikeKind
      ShooterID int
      StruckID  int
      WeaponID  int
      Landed    bool
      Damage    int
      Killed    bool
  }

  type SupportDefendOption struct { UnitID int; Incoming Forecast }
  type SupportAttackOption struct { UnitID, WeaponID int; Strike Forecast }
  type SideOptions struct { UnitID int; SupportDefenders []SupportDefendOption
                            SupportAttackers []SupportAttackOption }
  type ResponseAttackOption struct { Stance battle.Stance; WeaponID *int
                                     Incoming Forecast; Counter *Forecast }

A nil '*int' is the absence of a choice, which is what a nil '*state.Unit'
says today. It is not a sentinel: there is no in-band number standing for
"none".

## The signatures

  Prepare(board *state.Battle, decision battle.Decision) (Plan, error)
  Activatable(board *state.Battle, unitID int) (*state.Unit, error)
  LivingUnit(board *state.Battle, unitID int) (*state.Unit, error)
  foe(board *state.Battle, actorID int, targetID *int) (int, error)
  supportDefenders(board *state.Battle, supportedID int,
                   at battle.Footprint) []int
  supportAttackers(board *state.Battle, supportedID int,
                   firing, foe battle.Footprint) []supportAttacker
  Commit(board *state.Battle, plan Plan, dice battle.Dice) Trace
  Menu(board *state.Battle, decision battle.Decision, defenderID int)
      (Options, error)

'Activatable' and 'LivingUnit' answer a pointer because the caller needs the
data next, and the caller keeps the id it passed. That is why no type pairs
the two.

'fires', 'hasENFor', 'covers' and every other predicate over data keep their
pointer parameters. They answer a question about a unit; they never say which
unit.

## What the engine owes

- Bounds-check every position that arrives from the wire, and answer a
  refusal, never a panic. 'Prepare' already owes every error before the
  first write, so the checks belong at that gate.
  Acceptance is exhaustive, not sampled: every position field of
  'Decision' and of 'ResponseAttack' gets a case at -1 and a case at
  'len', each asserting a refusal and no panic. A missed door is a
  reachable crash.
- 'validate' refuses a load where 'len(MapWeaponAmmo)' differs from
  'len(Mech.MapWeapons)'.
- The unit slice is append only: never delete, never reorder. A
  destroyed unit keeps its place with no hit points, which is already
  the behavior. A test pins it across a turn cycle that includes a
  kill.

## Why this lands in one change

An earlier plan split the work: positions inside the engine first, the
wire second. That split cannot be built. While the wire sends names,
the engine must turn a name into a position, so it must keep the names
and walk a slice to compare them. The intermediate state forces on the
engine the translation duty this change exists to remove. The wire and
the engine move together.

## Golden method

Proven four times on issue #88: every golden is byte-identical to
'json.dumps(payload, indent=2, ensure_ascii=True)' plus a newline.
Verify that for all eleven before writing, transform the parsed tree,
and dump it back the same way.

## Progress log

- 2026-09-01: branch opened at 'eb3d2f4'.
- 2026-09-01: a first attempt was dropped and its commits removed. It
  kept the names, resolved them by walking the slice, and invented a
  sentinel for a missing count. The section "What this forbids" records
  what it did wrong.

## Resume point

The rewrite, not started.
