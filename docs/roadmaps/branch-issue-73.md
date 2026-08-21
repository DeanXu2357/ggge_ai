# Branch roadmap: issue #73, retire the Python battle engine

> Type: working—deleted at merge

## What the branch does

The Python sandbox is gone. No file outside 'engine/' holds a rule of
the battle, and no rule of the battle runs in Python at all.

The user ruled on 2026-08-22: remove the implementation, keep the
contract, and add a fake so that the wiring stays testable. Full
behavior is not preserved. The purpose is that no later work reads the
Python code and takes it for the rules.

## The change

Deleted:

| Path | Held |
|---|---|
| src/ggge_ai/sandbox/model.py | the rules: geometry, formulas, enumeration, resolution, the turn cycle |
| src/ggge_ai/sandbox/facade.py | the query contract of the page |
| tests/test_sandbox_model.py | 60 rule cases |
| tests/test_sandbox_geometry.py | 10 rule cases |
| tests/test_sandbox_formulas.py | 7 rule cases |
| tests/test_sandbox_facade.py | 34 facade cases |
| scripts/write_engine_fixtures.py | the writer of the golden cases |

Moved out of the sandbox, because neither holds a rule:

| From | To |
|---|---|
| sandbox/scenario.py | stage/scenario.py, the stage layout |
| sandbox/advise.py | stage/advise.py, the pricing contract of the planner |

Added:

| Path | Holds |
|---|---|
| src/ggge_ai/engine/state.py | the wire structs, the mirror of 'engine/protocol/state.go' |
| src/ggge_ai/engine/session.py | one battle, read through the engine |
| src/ggge_ai/engine/fake.py | the fake engine: the shape of the contract, no rule |

The vocabulary of the wire lives in 'engine/contract.py': Faction,
ActionKind, SkillSource, SkillAffects, Stance and Cell.

## The call chain of the page

    scripts/sandbox_ui.py
      -> EngineSession.from_scenario        engine/session.py
           -> stage/scenario.py             the layout, into a start state
           -> codec.encode_state            engine/codec.py
           -> engine.call("load")
      -> /api/state       session.snapshot          the stored state
      -> /api/decision    session.pending_decision  engine "actions", per unit
      -> /api/reactions   session.reaction_options  engine "reactions"
      -> /api/act         session.act               engine "act"

Without '--engine' the page runs on 'FakeEngine' in the same process.
With '--engine' it runs on the binary. A command that the engine does
not answer comes back empty, and the page still draws the board.

## The wire, after the review

A first cut of 'EngineSession' spoke the shape of the retired facade,
not the shape of the contract. The review caught it. The session and
the fake now speak the commands of the spec:

| Command | Request | Response |
|---|---|---|
| load | state, history | - |
| actions | unit_id | actions |
| reactions | defender_id, attacker_id, attacker_cell, weapon_id | reactions |
| act | unit_id, action, reaction, dice | events, board |
| export | - | state, history |

'act' answers the events and a board summary, not the new state, so
the session reads the state back with 'export'.

The page moved to the same vocabulary: 'unit_id' and 'pos' where it
read 'uid' and 'cell', the bounds of the state where it read a board
of columns and rows.

## What the page lost

The page holds no hit rate any more, because no command of the
contract promises one. Two things follow:

- The dice. The page had a manual mode that named the outcome of each
  hit node. The contract forces the dice with an ordered 'outcomes'
  list, in the resolution order, and the page cannot know that order
  before the engine answers. So the page asks the engine to sample,
  and the manual mode is gone.
- The forecast. A candidate label writes the hit rate and the expected
  damage when the action carries them, and omits them when it does
  not. It invents no field that the contract does not name.

## Contention points for the review

1. The stance. The contract holds four values and no 'none'. The
   Python reaction now carries 'stance: Stance | None', and None is
   the strike that settles no reaction. The wire refuses it, as
   before. Issue #56 owns the same question inside the engine.
2. The fake answers a standby action for every unit and an empty
   reaction list. It is a wiring stub, not a weak model. Reading an
   answer of the fake as a fact of the game is the failure mode, and
   the module docstring says so.
3. The golden fixtures under 'tests/fixtures/engine/' are frozen. The
   Go package 'engine/differential' still reads them, and the writer
   is deleted. Delete a case that the engine must not keep; never
   regenerate one.
4. 'tests/test_engine_codec.py' keeps the parity half, now against
   'engine/state.py'. It lost the three tests that compared the
   golden files with the writer.
5. 'stage/scenario.py' lost 'check_outcome'. Deciding victory and
   defeat is a rule, it had no caller left, and the module says it
   holds no rule.
6. The page script keeps the name 'scripts/sandbox_ui.py'. The word
   sandbox names the board and the page, not the retired module.

## Test mapping

The case-by-case mapping of the 111 deleted Python tests is in the
issue:
https://github.com/DeanXu2357/ggge_ai/issues/73#issuecomment-5373087975

The ruling of 2026-08-22 changes what it is for. It is no longer a
gate on the deletion. It is the list of the rules that the engine
still owes, and it names them: 15 for the turn cycle and the events
(#65), 3 with no case anywhere (counters unlimited in a phase, a
skill the unit does not own, a skill that does not end the
activation), and 10 that only a frozen golden holds.

## Gates

- uv run pytest -q: 988 passed, 4 skipped.
- The page serves the placeholder layout against the fake: 28 units,
  the board bounds, the action list, and the command entries of the
  contract.
- uv run ruff check src tests scripts: clean.
- go vet ./... and go test ./... in 'engine': clean.
- 'battle/vision.py' changed in the first commit of the branch. Its
  evidence: two runs of 'scripts/probe_live_channel.py' on 2026-08-22
  and the frame assets/screenshots/20260822-013704.png.

## What is left

- The engine answers six commands after #63 and #64 merge. Ten of the
  sixteen declared commands have no implementation, and 'act',
  'export' and 'rollback' have no owning issue.
- #42 and #43 were written against the facade. Both need a new home
  in the engine.
