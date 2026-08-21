# Branch roadmap: issue #73, retire the Python battle engine

> Type: working—deleted at merge

## Resume point

Batch 1 is done: the wire vocabulary moved to the engine contract, and
the consumers outside the sandbox read it there.

The deletion of the rules stays blocked. See "What this branch does not
do".

## Why the branch starts with a split, not a delete

The inventory of the issue reads 'model.py' as rules alone. It is also
the vocabulary of the whole Python side: seven modules outside the
sandbox import it, and four of them read enums only. One of the four is
'engine/codec.py', which the issue keeps.

The enums are not rules. The Go package 'engine/protocol' declares the
same six names, and 'src/ggge_ai/engine/contract.py' is the Python
mirror of that package. So the vocabulary has a home that survives the
retirement, and the move is alignment with a contract that exists, not
a new abstraction.

## Batch 1: the vocabulary

Added to 'src/ggge_ai/engine/contract.py', each one a mirror of
'engine/protocol/state.go':

| Python | Go | Note |
|---|---|---|
| Faction | Faction | |
| ActionKind | ActionKind | the model calls it MoveKind |
| SkillSource | SkillSource | |
| SkillAffects | SkillAffects | holds no 'self' value |
| Stance | Stance | holds no 'none' value (issue #56) |

'Cell' was already there.

Repointed at the contract:

| File | Reads |
|---|---|
| src/ggge_ai/battle/state.py | Faction |
| src/ggge_ai/battle/vision.py | Stance, as DefenseKind |
| src/ggge_ai/stage/roster_offline.py | Faction |
| src/ggge_ai/stage/intel_panels.py | ActionKind |
| src/ggge_ai/stage/intel.py | ActionKind, Cell, Faction |

'stage/intel.py' still reads Skill, Unit and Weapon from the model.
Those are the payload work of batch 2.

The name 'MoveKind' does not enter the surviving code. It stays inside
the sandbox and inside the tests that die with it.

## The stance of the vision layer

'battle/vision.py' reads the stance vocabulary of the reaction menu. It
uses dodge, defend, shield and counter, and never 'none'. So the
contract enum, which drops 'none', fits the caller exactly.

## Evidence for the vision change

The commit rule asks for a device screenshot or a run log when
'battle/vision.py' changes.

- Probe on a live frame: 'scripts/probe_live_channel.py', two runs,
  2026-08-22. The module loads and classifies a live frame with the
  contract enum. Screen 'unknown', stage_list score 0.683: the device
  rests on the event-stage list, which the template does not match.
  That score is the state of the device, not an effect of this change.
- Frame: assets/screenshots/20260822-013704.png.
- The change is an import. The enum values are the same, less 'none',
  which this caller never uses.

## What this branch does not do

The rules stay. The deletion needs the engine to answer a turn, and it
cannot yet:

- The engine registers four commands on 'dev'. #63 and #64 add two
  more, and both wait for review.
- No branch registers an 'act' command. #64 ships 'Board.Apply' in the
  battle package and binds no command to it.
- #65, #67 and #68 have no branch.

The plan and the case-by-case test mapping are in the issue:
https://github.com/DeanXu2357/ggge_ai/issues/73#issuecomment-5373087975

Four rulings wait on the user, and the next batches depend on them:

1. Who owns 'act', 'export' and 'rollback'.
2. #42 and #43: land on Python, or move to the engine.
3. Freeze the differential fixtures under the Go tree, or write a
   native Go case for each of the 25 apply checks.
4. The two rule changes of the port: the destroyed unit and the
   out-of-band attack.

## Next batches

- Batch 2: 'sandbox/scenario.py' and 'stage/intel.py' build an engine
  payload, and stop building model objects.
- Batch 3: the deletion, after the blockers land.
